"""Estimate readiness gate v1.

Evaluates whether an automated project estimate package is ready for internal
owner review. This is not customer delivery and not final estimate approval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.boe import draft_boe
from app.coverage_db import validate_coverage
from app.extraction_db import list_scope_items
from app.provenance_confidence import summarize_scope_provenance
from app.qa_findings import list_qa_findings
from app.quantity_requirements import list_quantity_requirements


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    return {
        "project_id": str(project_id),
        "generated_at": _now(),
        "status": "ready_for_owner_review" if ready_for_owner_review else "blocked",
        "ready_for_owner_review": ready_for_owner_review,
        "customer_delivery_ready": False,
        "customer_delivery_gate": "Final construction estimate delivery remains approval-gated.",
        "summary": {
            "scope_item_count": scope_total,
            "coverage_complete": coverage["complete"],
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
            "open_quantity_requirements": open_quantity_reqs,
            "missing_pricing_inputs": missing_pricing_inputs,
            "open_scope_blockers": open_scope_blockers,
            "provenance_confidence": provenance,
            "assumptions_register": assumptions_register,
            "critical_qa_findings": critical_findings,
        },
    }
