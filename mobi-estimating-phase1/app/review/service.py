"""Human-review workflow service.

Enforces the shared review rules: AI items are never auto-approved, approval needs
trusted evidence (and a resolved quantity where the trade requires one), blocking
issues prevent approval, corrections preserve the original provider candidate,
review history is append-only, and re-validation reruns after every correction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.estimating.quantities import (
    FormulaError,
    QuantityBasis,
    QuantityInputError,
    formula_registry,
)
from app.extraction.schemas import ConflictSeverity, ReviewStatus
from app.extraction_db import (
    append_review_event,
    delete_conflicts_for_item,
    get_scope_item,
    insert_conflict,
    insert_quantity_derivation,
    list_conflicts,
    list_evidence,
    update_scope_item,
)
from app.review.schemas import CorrectionRequest
from app.trades.base import CandidateContext
from app.trades.registry import trade_registry


class ReviewError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _module(trade_code: str):
    from app.trades.registry import UnknownTradeError

    try:
        return trade_registry.get(trade_code)
    except UnknownTradeError as exc:
        raise ReviewError("unknown_trade", f"Trade '{trade_code}' is not registered") from exc


def _candidate_context(item: dict[str, Any]) -> CandidateContext:
    quantity = item.get("quantity")
    return CandidateContext(
        category_code=item["category_code"],
        description=item["description"],
        location=item.get("location"),
        quantity_basis=QuantityBasis(item["quantity_basis"]),
        quantity_value=Decimal(quantity) if quantity not in (None, "") else None,
        unit=item.get("unit"),
        raw_quantity_inputs=item.get("raw_quantity_inputs") or {},
        trade_data=item.get("trade_data") or {},
        evidence_count=len(list_evidence(UUID(item["id"]))),
        confidence=item.get("extraction_confidence"),
    )


def _revalidate(module, item: dict[str, Any]) -> tuple[list[dict], str]:
    """Rerun trade validation + conflict detection; refresh stored conflicts.

    Returns (blocking_issues, conflict_status)."""
    ctx = _candidate_context(item)
    validation = module.validate_candidate(ctx)
    blocking_issues = [bi.model_dump() for bi in validation.blocking_issues]

    delete_conflicts_for_item(UUID(item["id"]))
    conflicts = module.detect_conflicts(ctx, [])
    has_blocking_conflict = False
    for conflict in conflicts:
        row = conflict.model_dump(mode="json")
        row["id"] = str(uuid4())
        row["scope_item_id"] = item["id"]
        insert_conflict(row)
        if row["severity"] == ConflictSeverity.BLOCKING.value:
            has_blocking_conflict = True

    has_blocking = bool(blocking_issues) or has_blocking_conflict
    status = "blocking" if has_blocking else ("warning" if conflicts else "none")
    return blocking_issues, status


def _approval_blockers(module, item: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if item["review_status"] == ReviewStatus.REJECTED.value:
        issues.append({"code": "item_rejected",
                       "message": "Rejected items cannot be approved; correct first"})

    evidence = list_evidence(UUID(item["id"]))
    trusted = [e for e in evidence if e.get("verified_sheet_number")]
    if not trusted:
        issues.append({"code": "missing_verified_sheet",
                       "message": "Approval requires at least one trusted evidence "
                                  "reference on a verified sheet"})

    if module.category_requires_quantity(item["category_code"]) and item.get("quantity") in (None, ""):
        issues.append({"code": "missing_quantity",
                       "message": "Approval requires a resolved quantity for this category"})

    for conflict in list_conflicts(UUID(item["id"]), open_only=True):
        if conflict["severity"] == ConflictSeverity.BLOCKING.value:
            issues.append({"code": conflict["code"], "message": conflict["description"]})

    for issue in item.get("blocking_issues") or []:
        issues.append({"code": issue.get("code", "blocking"),
                       "message": issue.get("message", "Blocking issue")})
    return issues


def approve_item(
    project_id: UUID, item_id: UUID, *, reviewer_id: str, reviewer_notes: str | None
) -> dict[str, Any]:
    item = get_scope_item(project_id, item_id)
    if item is None:
        raise ReviewError("not_found", "Scope item not found")
    module = _module(item["trade_code"])
    blockers = _approval_blockers(module, item)
    previous = item["review_status"]

    if blockers:
        update_scope_item(item_id, review_status=ReviewStatus.BLOCKED.value,
                          blocking_issues=blockers)
        append_review_event({
            "project_id": str(project_id), "scope_item_id": str(item_id),
            "trade_code": item["trade_code"], "action": "approve_blocked",
            "previous_state": previous, "new_state": ReviewStatus.BLOCKED.value,
            "reviewer_id": reviewer_id, "reviewer_notes": reviewer_notes,
        })
        return {"approved": False, "scope_item_id": str(item_id),
                "review_status": ReviewStatus.BLOCKED.value, "blocking_issues": blockers}

    update_scope_item(item_id, review_status=ReviewStatus.APPROVED.value,
                      approved_at=_now(), reviewer_notes=reviewer_notes,
                      blocking_issues=[])
    append_review_event({
        "project_id": str(project_id), "scope_item_id": str(item_id),
        "trade_code": item["trade_code"], "action": "approve",
        "previous_state": previous, "new_state": ReviewStatus.APPROVED.value,
        "reviewer_id": reviewer_id, "reviewer_notes": reviewer_notes,
    })
    return {"approved": True, "scope_item_id": str(item_id),
            "review_status": ReviewStatus.APPROVED.value, "blocking_issues": []}


def reject_item(
    project_id: UUID, item_id: UUID, *, reason: str, reviewer_id: str
) -> dict[str, Any]:
    if not reason or not reason.strip():
        raise ReviewError("reason_required", "A rejection reason is required")
    item = get_scope_item(project_id, item_id)
    if item is None:
        raise ReviewError("not_found", "Scope item not found")
    previous = item["review_status"]
    update_scope_item(item_id, review_status=ReviewStatus.REJECTED.value,
                      reviewer_notes=reason)
    append_review_event({
        "project_id": str(project_id), "scope_item_id": str(item_id),
        "trade_code": item["trade_code"], "action": "reject",
        "previous_state": previous, "new_state": ReviewStatus.REJECTED.value,
        "reviewer_id": reviewer_id, "reviewer_notes": reason,
    })
    return get_scope_item(project_id, item_id)


def correct_item(
    project_id: UUID, item_id: UUID, corrections: CorrectionRequest
) -> dict[str, Any]:
    item = get_scope_item(project_id, item_id)
    if item is None:
        raise ReviewError("not_found", "Scope item not found")
    module = _module(item["trade_code"])
    previous = item["review_status"]

    updates: dict[str, Any] = {}
    for field in ("description", "location", "category_code",
                  "specification_section", "material_or_substrate"):
        value = getattr(corrections, field)
        if value is not None:
            updates[field] = value

    if corrections.trade_data is not None:
        # Re-validate the trade payload through the trade module.
        try:
            updates["trade_data"] = module.validate_trade_data(
                corrections.trade_data, schema_version=item["trade_schema_version"]
            )
        except ValueError as exc:
            raise ReviewError("invalid_trade_data", str(exc)) from exc

    if corrections.quantity is not None:
        # Reviewer-supplied quantity is marked manual_reviewer_entry.
        updates["quantity"] = corrections.quantity
        updates["quantity_basis"] = QuantityBasis.MANUAL_REVIEWER_ENTRY.value
        if corrections.unit is not None:
            updates["unit"] = corrections.unit
    elif corrections.unit is not None:
        updates["unit"] = corrections.unit

    if corrections.reviewer_notes is not None:
        updates["reviewer_notes"] = corrections.reviewer_notes

    # original_provider_candidate is intentionally never in `updates`.
    update_scope_item(item_id, **updates)

    refreshed = get_scope_item(project_id, item_id)
    blocking_issues, conflict_status = _revalidate(module, refreshed)
    new_status = (
        ReviewStatus.BLOCKED.value if blocking_issues else ReviewStatus.CORRECTED.value
    )
    update_scope_item(item_id, review_status=new_status,
                      blocking_issues=blocking_issues, conflict_status=conflict_status)
    append_review_event({
        "project_id": str(project_id), "scope_item_id": str(item_id),
        "trade_code": item["trade_code"], "action": "correct",
        "previous_state": previous, "new_state": new_status,
        "reviewer_id": corrections.reviewer_id,
        "reviewer_notes": corrections.reviewer_notes,
    })
    return get_scope_item(project_id, item_id)


def recalculate_item(
    project_id: UUID, item_id: UUID, *, formula_id: str, inputs: dict[str, Any],
    reviewer_id: str,
) -> dict[str, Any]:
    item = get_scope_item(project_id, item_id)
    if item is None:
        raise ReviewError("not_found", "Scope item not found")
    trade_code = item["trade_code"]
    # Only registered formulas for THIS trade — never arbitrary client expressions.
    try:
        formula = formula_registry.get_for_trade(formula_id, trade_code)
    except FormulaError as exc:
        raise ReviewError("unsupported_formula", str(exc)) from exc
    try:
        result = formula.calculate(inputs)
    except QuantityInputError as exc:
        raise ReviewError("invalid_inputs", str(exc)) from exc

    insert_quantity_derivation({
        "id": str(uuid4()), "scope_item_id": str(item_id), "trade_code": trade_code,
        "formula_id": result.formula_id, "formula_version": result.formula_version,
        "inputs": result.inputs, "output_value": result.value,
        "output_unit": result.unit.value,
    })
    update_scope_item(
        item_id, quantity=result.value, unit=result.unit.value,
        quantity_basis=QuantityBasis.DETERMINISTIC_DERIVATION.value,
        raw_quantity_inputs=inputs, calculation_id=result.formula_id,
        calculation_version=result.formula_version,
    )
    module = _module(trade_code)
    refreshed = get_scope_item(project_id, item_id)
    blocking_issues, conflict_status = _revalidate(module, refreshed)
    update_scope_item(item_id, blocking_issues=blocking_issues,
                      conflict_status=conflict_status)
    append_review_event({
        "project_id": str(project_id), "scope_item_id": str(item_id),
        "trade_code": trade_code, "action": "recalculate",
        "previous_state": item["review_status"], "new_state": item["review_status"],
        "reviewer_id": reviewer_id,
        "reviewer_notes": f"Recalculated via {formula_id}",
    })
    return get_scope_item(project_id, item_id)
