"""Extraction Provenance & Confidence Model v1.

Summarizes whether internal scope items have enough source evidence and
confidence to proceed to owner-review readiness. This is an internal quality gate
only; it never sends messages, prices, approves, or delivers estimates.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.database import get_connection
from app.extraction_db import list_evidence

LOW_CONFIDENCE_THRESHOLD = 0.55
UNCLEAR_QUANTITY_BASES = {None, "", "unknown", "customer_revision_pending_rescope"}


def _sheet_is_verified(project_id: str, sheet_id: str | None, verified_sheet_number: str | None) -> bool:
    if not sheet_id or not verified_sheet_number:
        return False
    with get_connection() as conn:
        row = conn.execute(
            "SELECT verified_sheet_number, review_status FROM sheets WHERE id=? AND project_id=?",
            (sheet_id, project_id),
        ).fetchone()
    return bool(
        row
        and row["review_status"] == "verified"
        and row["verified_sheet_number"] == verified_sheet_number
    )


def _trusted_evidence(project_id: str, scope_item_id: str) -> list[dict[str, Any]]:
    evidence = list_evidence(UUID(scope_item_id))
    return [
        row for row in evidence
        if row.get("verified_sheet_number")
        and row.get("pdf_page_number") is not None
        and _sheet_is_verified(project_id, row.get("sheet_id"), row.get("verified_sheet_number"))
    ]


def _evidence_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sheet_id": row.get("sheet_id"),
        "pdf_page_number": row.get("pdf_page_number"),
        "verified_sheet_number": row.get("verified_sheet_number"),
        "evidence_type": row.get("evidence_type"),
        "description": row.get("description"),
        "extracted_text_quote": row.get("extracted_text_quote"),
        "provider_confidence": row.get("provider_confidence"),
        "requires_human_verification": bool(row.get("requires_human_verification")),
    }


def _confidence_reason(confidence: Any, trusted_count: int) -> str:
    if confidence is None:
        return "No extraction confidence score is recorded."
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        return "Extraction confidence score is not numeric."
    if score < LOW_CONFIDENCE_THRESHOLD:
        return f"Extraction confidence {score:.2f} is below threshold {LOW_CONFIDENCE_THRESHOLD:.2f}."
    if trusted_count == 0:
        return "No trusted verified-sheet evidence is attached."
    return "Trusted evidence and confidence are present."


def summarize_scope_provenance(scope_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return readiness-facing provenance/confidence summary for scope items."""
    items_with_trusted_evidence: list[dict[str, Any]] = []
    missing_provenance: list[dict[str, Any]] = []
    low_confidence: list[dict[str, Any]] = []
    quantity_basis_unclear: list[dict[str, Any]] = []

    for item in scope_items:
        evidence = _trusted_evidence(item["project_id"], item["id"])
        confidence = item.get("extraction_confidence")
        public_base = {
            "scope_item_id": item["id"],
            "trade_code": item.get("trade_code"),
            "category_code": item.get("category_code"),
            "description": item.get("description"),
        }
        if evidence:
            items_with_trusted_evidence.append({
                **public_base,
                "evidence_count": len(evidence),
                "primary_evidence": _evidence_public(evidence[0]),
                "extraction_confidence": confidence,
            })
        else:
            missing_provenance.append({
                **public_base,
                "code": "missing_extraction_provenance",
                "message": "Scope item has no trusted verified-sheet evidence reference.",
                "extraction_confidence": confidence,
            })

        confidence_missing_or_invalid = False
        try:
            score = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            score = None
            confidence_missing_or_invalid = True
        if score is None:
            confidence_missing_or_invalid = True
        if confidence_missing_or_invalid or (score is not None and score < LOW_CONFIDENCE_THRESHOLD):
            low_confidence.append({
                **public_base,
                "code": "low_extraction_confidence",
                "message": _confidence_reason(confidence, len(evidence)),
                "extraction_confidence": score,
                "threshold": LOW_CONFIDENCE_THRESHOLD,
                "evidence_count": len(evidence),
            })

        quantity_basis = item.get("quantity_basis")
        if item.get("quantity") not in (None, "") and quantity_basis in UNCLEAR_QUANTITY_BASES:
            quantity_basis_unclear.append({
                **public_base,
                "code": "quantity_basis_unclear",
                "message": "Scope item has a quantity but no clear quantity basis/source.",
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "quantity_basis": quantity_basis,
            })

    total = len(scope_items)
    items_with_evidence_count = len(items_with_trusted_evidence)
    return {
        "scope_item_count": total,
        "items_with_trusted_evidence_count": items_with_evidence_count,
        "items_missing_trusted_evidence_count": len(missing_provenance),
        "low_confidence_item_count": len(low_confidence),
        "quantity_basis_unclear_count": len(quantity_basis_unclear),
        "trusted_evidence_coverage_rate": round(items_with_evidence_count / total, 4) if total else 0,
        "missing_extraction_provenance": missing_provenance,
        "low_extraction_confidence": low_confidence,
        "quantity_basis_unclear": quantity_basis_unclear,
        "items_with_trusted_evidence": items_with_trusted_evidence,
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
    }
