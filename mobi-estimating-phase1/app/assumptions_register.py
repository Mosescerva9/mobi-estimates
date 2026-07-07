"""Assumptions / Exclusions / Open Questions Register v1.

Builds a deterministic internal register from coverage, scope, provenance,
quantity, and QA state. This module only summarizes risk language; it does not
approve, price, message, or deliver customer-facing final estimates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.coverage_db import validate_coverage
from app.extraction_db import list_scope_items
from app.provenance_confidence import summarize_scope_provenance
from app.qa_findings import list_qa_findings
from app.quantity_requirements import list_quantity_requirements


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_all_scope_items(project_id: UUID, *, page_size: int = 10000) -> tuple[list[dict[str, Any]], int]:
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


def _entry(
    *,
    kind: str,
    code: str,
    message: str,
    source: str,
    severity: str = "major",
    trade_code: str | None = None,
    scope_item_id: str | None = None,
    coverage_row_id: str | None = None,
    qa_finding_id: str | None = None,
    customer_visible_candidate: bool = True,
    blocks_delivery: bool = True,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "code": code,
        "severity": severity,
        "trade_code": trade_code,
        "scope_item_id": scope_item_id,
        "coverage_row_id": coverage_row_id,
        "qa_finding_id": qa_finding_id,
        "source": source,
        "message": message,
        "customer_visible_candidate": customer_visible_candidate,
        "blocks_delivery": blocks_delivery,
    }


def _add_unique(entries: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    marker = (
        entry.get("kind"),
        entry.get("code"),
        entry.get("trade_code"),
        entry.get("scope_item_id"),
        entry.get("coverage_row_id"),
        entry.get("message"),
    )
    for existing in entries:
        if marker == (
            existing.get("kind"),
            existing.get("code"),
            existing.get("trade_code"),
            existing.get("scope_item_id"),
            existing.get("coverage_row_id"),
            existing.get("message"),
        ):
            return
    entries.append(entry)


def build_assumptions_register(project_id: UUID) -> dict[str, Any]:
    """Return a structured internal register for BOE/owner-review packets."""
    scope_items, scope_total = _list_all_scope_items(project_id)
    coverage = validate_coverage(project_id)
    qa_findings = list_qa_findings(project_id)
    quantity_requirements = list_quantity_requirements(project_id)
    provenance = summarize_scope_provenance(scope_items)

    assumptions: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    open_questions: list[dict[str, Any]] = []

    for item in scope_items:
        trade_code = item.get("trade_code")
        scope_item_id = item.get("id")
        for raw in item.get("assumptions") or []:
            text = raw.get("text") if isinstance(raw, dict) else str(raw)
            if text:
                _add_unique(assumptions, _entry(
                    kind="assumption",
                    code="scope_item_assumption",
                    message=text,
                    source="scope_item.assumptions",
                    severity="minor",
                    trade_code=trade_code,
                    scope_item_id=scope_item_id,
                    blocks_delivery=False,
                ))
        for raw in item.get("exclusions") or []:
            text = raw.get("text") if isinstance(raw, dict) else str(raw)
            if text:
                _add_unique(exclusions, _entry(
                    kind="exclusion",
                    code="scope_item_exclusion",
                    message=text,
                    source="scope_item.exclusions",
                    severity="minor",
                    trade_code=trade_code,
                    scope_item_id=scope_item_id,
                    blocks_delivery=False,
                ))
        for blocker in item.get("blocking_issues") or []:
            code = blocker.get("code") if isinstance(blocker, dict) else "scope_blocker"
            message = blocker.get("message") if isinstance(blocker, dict) else str(blocker)
            if message:
                _add_unique(open_questions, _entry(
                    kind="open_question",
                    code=code or "scope_blocker",
                    message=message,
                    source="scope_item.blocking_issues",
                    severity="critical" if code in {"missing_quantity", "missing_pricing_basis"} else "major",
                    trade_code=trade_code,
                    scope_item_id=scope_item_id,
                ))

    for finding in coverage.get("findings", []):
        _add_unique(open_questions, _entry(
            kind="open_question",
            code=finding["code"],
            message=finding["message"],
            source="coverage_validation",
            severity=finding.get("severity") or "major",
            trade_code=finding.get("trade_code"),
            coverage_row_id=finding.get("coverage_row_id"),
        ))

    for row in quantity_requirements:
        if row.get("status") != "open":
            continue
        payload = row.get("payload") or {}
        _add_unique(open_questions, _entry(
            kind="open_question",
            code="open_quantity_requirement",
            message=f"Quantity required for {payload.get('scope_description') or row.get('trade_code') or 'scope item'}.",
            source="quantity_requirements",
            severity="critical",
            trade_code=row.get("trade_code"),
            scope_item_id=row.get("scope_item_id"),
        ))

    for row in provenance.get("missing_extraction_provenance", []):
        _add_unique(open_questions, _entry(
            kind="open_question",
            code="missing_extraction_provenance",
            message="Confirm the plan source/evidence for this scope item before relying on it.",
            source="provenance_confidence.missing_extraction_provenance",
            severity="critical",
            trade_code=row.get("trade_code"),
            scope_item_id=row.get("scope_item_id"),
        ))
    for row in provenance.get("low_extraction_confidence", []):
        _add_unique(open_questions, _entry(
            kind="open_question",
            code="low_extraction_confidence",
            message=row.get("message") or "Extraction confidence is below the accepted threshold.",
            source="provenance_confidence.low_extraction_confidence",
            severity="critical",
            trade_code=row.get("trade_code"),
            scope_item_id=row.get("scope_item_id"),
        ))
    for row in provenance.get("quantity_basis_unclear", []):
        _add_unique(assumptions, _entry(
            kind="assumption",
            code="quantity_basis_unclear",
            message="Quantity exists but its basis/source is unclear and must be treated as unverified.",
            source="provenance_confidence.quantity_basis_unclear",
            severity="critical",
            trade_code=row.get("trade_code"),
            scope_item_id=row.get("scope_item_id"),
        ))

    for finding in qa_findings:
        if finding.get("status") != "open":
            continue
        _add_unique(open_questions, _entry(
            kind="open_question",
            code=finding.get("code") or "qa_finding",
            message=finding.get("message") or "Open QA finding requires resolution.",
            source="qa_findings",
            severity=finding.get("severity") or "major",
            trade_code=finding.get("trade_code"),
            scope_item_id=finding.get("scope_item_id"),
            coverage_row_id=finding.get("coverage_row_id"),
            qa_finding_id=finding.get("id"),
        ))

    all_entries = [*assumptions, *exclusions, *open_questions]
    blocking = [entry for entry in all_entries if entry.get("blocks_delivery")]
    return {
        "project_id": str(project_id),
        "generated_at": _now(),
        "register_type": "assumptions_exclusions_open_questions_v1",
        "customer_delivery_ready": False,
        "customer_delivery_gate": "Register is internal risk language only; final customer estimate delivery remains separately approval-gated.",
        "summary": {
            "scope_item_count": scope_total,
            "assumption_count": len(assumptions),
            "exclusion_count": len(exclusions),
            "open_question_count": len(open_questions),
            "blocking_entry_count": len(blocking),
            "critical_entry_count": sum(1 for entry in all_entries if entry.get("severity") == "critical"),
            "customer_visible_candidate_count": sum(1 for entry in all_entries if entry.get("customer_visible_candidate")),
        },
        "assumptions": assumptions,
        "exclusions": exclusions,
        "open_questions": open_questions,
        "all_entries": all_entries,
    }
