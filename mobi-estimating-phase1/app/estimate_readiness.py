"""Estimate readiness gate v1.

Evaluates whether an automated project estimate package is ready for internal
owner review. This is not customer delivery and not final estimate approval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.boe import draft_boe
from app.capability_registry import (
    classify_delivery_sources,
    classify_supported_scope,
    evaluate_delivery_lock,
    get_capability_registry,
)
from app.coverage_db import validate_coverage
from app.extraction_db import list_scope_items
from app.provenance_confidence import summarize_scope_provenance
from app.qa_findings import list_qa_findings
from app.quantity_requirements import list_quantity_requirements


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_delivery_sources(scope_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gather the quantity/pricing sources that would back a final estimate.

    These feed the delivery lock's test-only-source check so that scaffolding
    quantities/prices can never be treated as real customer-delivery evidence.
    """
    sources: list[dict[str, Any]] = []
    for item in scope_items:
        scope_item_id = item.get("id")
        trade_data = item.get("trade_data") or {}
        pricing_basis = trade_data.get("pricing_basis") or {}
        if isinstance(pricing_basis, dict):
            sources.append({
                "scope_item_id": scope_item_id,
                "kind": "pricing_basis",
                "source": pricing_basis.get("source"),
            })
        raw_quantity_inputs = item.get("raw_quantity_inputs") or {}
        verified_quantity = raw_quantity_inputs.get("verified_quantity_input_v1") or {}
        if item.get("quantity") not in (None, ""):
            sources.append({
                "scope_item_id": scope_item_id,
                "kind": "quantity_input",
                "source": verified_quantity.get("source") if isinstance(verified_quantity, dict) else None,
            })
    return sources


def _list_all_scope_items(project_id: UUID, *, page_size: int = 10000) -> tuple[list[dict[str, Any]], int]:
    """Page through every scope item so readiness cannot miss late blockers."""
    all_items: list[dict[str, Any]] = []
    offset = 0
    total = 0
    while True:
        page, total = list_scope_items(project_id, filters={}, limit=page_size, offset=offset)
        all_items.extend(page)
        if len(all_items) >= total or not page:
            break
        offset += len(page)
    return all_items, total


def evaluate_estimate_readiness(project_id: UUID) -> dict[str, Any]:
    coverage = validate_coverage(project_id)
    scope_items, scope_total = _list_all_scope_items(project_id)
    findings = list_qa_findings(project_id)
    quantity_reqs = list_quantity_requirements(project_id)
    boe = draft_boe(project_id)
    assumptions_register = boe.get("assumptions_register") or {}
    register_summary = assumptions_register.get("summary") or {}
    provenance = summarize_scope_provenance(scope_items)
    supported_scope = classify_supported_scope(scope_items)
    delivery_sources = _collect_delivery_sources(scope_items)
    delivery_source_check = classify_delivery_sources(delivery_sources)

    open_scope_blockers: list[dict[str, Any]] = []
    missing_pricing_inputs: list[dict[str, Any]] = []
    for item in scope_items:
        blockers = item.get("blocking_issues") or []
        if blockers:
            open_scope_blockers.append({
                "scope_item_id": item["id"],
                "trade_code": item["trade_code"],
                "blockers": blockers,
            })
        trade_data = item.get("trade_data") or {}
        if item.get("category_code") == "generic_scope" and not trade_data.get("pricing_ready"):
            missing_pricing_inputs.append({
                "scope_item_id": item["id"],
                "trade_code": item["trade_code"],
                "pricing_method": trade_data.get("pricing_method"),
            })

    open_quantity_reqs = [row for row in quantity_reqs if row.get("status") == "open"]
    open_findings = [row for row in findings if row.get("status") == "open"]
    critical_findings = [row for row in open_findings if row.get("severity") == "critical"]
    major_findings = [row for row in open_findings if row.get("severity") == "major"]
    blockers: list[dict[str, Any]] = []
    if not coverage["complete"]:
        blockers.append({"code": "coverage_incomplete", "count": len(coverage.get("findings", []))})
    if open_quantity_reqs:
        blockers.append({"code": "open_quantity_requirements", "count": len(open_quantity_reqs)})
    if missing_pricing_inputs:
        blockers.append({"code": "missing_pricing_inputs", "count": len(missing_pricing_inputs)})
    if open_scope_blockers:
        blockers.append({"code": "open_scope_blockers", "count": len(open_scope_blockers)})
    if supported_scope["unsupported_scope_item_count"]:
        blockers.append({
            "code": "unsupported_customer_delivery_scope",
            "count": supported_scope["unsupported_scope_item_count"],
        })
    if delivery_source_check["test_only_source_count"]:
        blockers.append({
            "code": "test_only_delivery_sources",
            "count": delivery_source_check["test_only_source_count"],
        })
    if provenance["missing_extraction_provenance"]:
        blockers.append({
            "code": "missing_extraction_provenance",
            "count": len(provenance["missing_extraction_provenance"]),
        })
    if provenance["low_extraction_confidence"]:
        blockers.append({
            "code": "low_extraction_confidence",
            "count": len(provenance["low_extraction_confidence"]),
            "threshold": provenance["low_confidence_threshold"],
        })
    if provenance["quantity_basis_unclear"]:
        blockers.append({
            "code": "quantity_basis_unclear",
            "count": len(provenance["quantity_basis_unclear"]),
        })
    if critical_findings:
        blockers.append({"code": "critical_qa_findings", "count": len(critical_findings)})
    register_blocking_entry_count = int(register_summary.get("blocking_entry_count") or 0)
    if register_blocking_entry_count:
        blockers.append({
            "code": "assumptions_register_blocking_entries",
            "count": register_blocking_entry_count,
        })

    ready_for_owner_review = len(blockers) == 0 and scope_total > 0

    # Final customer-delivery lock. Owner approval has no persistence path in this
    # slice, so it is always absent -> the lock stays fail-closed. Evidence and
    # review completeness are surfaced so the lock reports *why* it is closed.
    evidence_complete = (
        scope_total > 0
        and not provenance["missing_extraction_provenance"]
        and not provenance["low_extraction_confidence"]
        and not provenance["quantity_basis_unclear"]
    )
    delivery_lock = evaluate_delivery_lock(
        evidence_complete=evidence_complete,
        required_reviews_complete=ready_for_owner_review,
        owner_approval=None,
        delivery_sources=delivery_sources,
        supported_scope=supported_scope["supported_scope"],
        unsupported_scope=supported_scope,
    )
    customer_delivery_ready = delivery_lock["delivery_unlocked"]

    return {
        "project_id": str(project_id),
        "generated_at": _now(),
        "status": "ready_for_owner_review" if ready_for_owner_review else "blocked",
        "ready_for_owner_review": ready_for_owner_review,
        "customer_delivery_ready": customer_delivery_ready,
        "customer_delivery_lock": delivery_lock,
        "capability_registry": get_capability_registry(),
        "customer_delivery_gate": "Final construction estimate delivery remains approval-gated.",
        "summary": {
            "scope_item_count": scope_total,
            "coverage_complete": coverage["complete"],
            "unsupported_customer_delivery_scope_count": supported_scope["unsupported_scope_item_count"],
            "supported_customer_delivery_scope": supported_scope["supported_scope"],
            "test_only_delivery_source_count": delivery_source_check["test_only_source_count"],
            "no_test_only_delivery_evidence": delivery_source_check["no_test_only_delivery_evidence"],
            "open_quantity_requirement_count": len(open_quantity_reqs),
            "missing_pricing_input_count": len(missing_pricing_inputs),
            "open_scope_blocker_count": len(open_scope_blockers),
            "items_with_trusted_evidence_count": provenance["items_with_trusted_evidence_count"],
            "items_missing_trusted_evidence_count": provenance["items_missing_trusted_evidence_count"],
            "low_confidence_item_count": provenance["low_confidence_item_count"],
            "quantity_basis_unclear_count": provenance["quantity_basis_unclear_count"],
            "trusted_evidence_coverage_rate": provenance["trusted_evidence_coverage_rate"],
            "critical_qa_finding_count": len(critical_findings),
            "major_qa_finding_count": len(major_findings),
            "assumption_count": int(register_summary.get("assumption_count") or 0),
            "exclusion_count": int(register_summary.get("exclusion_count") or 0),
            "open_question_count": int(register_summary.get("open_question_count") or 0),
            "register_blocking_entry_count": register_blocking_entry_count,
            "register_critical_entry_count": int(register_summary.get("critical_entry_count") or 0),
            "boe_status": boe.get("status"),
        },
        "blockers": blockers,
        "details": {
            "coverage_findings": coverage.get("findings", []),
            "unsupported_customer_delivery_scope": supported_scope,
            "delivery_source_check": delivery_source_check,
            "open_quantity_requirements": open_quantity_reqs,
            "missing_pricing_inputs": missing_pricing_inputs,
            "open_scope_blockers": open_scope_blockers,
            "provenance_confidence": provenance,
            "assumptions_register": assumptions_register,
            "critical_qa_findings": critical_findings,
        },
    }
