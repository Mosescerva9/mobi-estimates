"""Generic pricing input application v1.

Applies verified pricing inputs to generic scope items. This is not a final
estimate/pricing run; it records the basis needed for later deterministic line
item creation and clears the matching blocker while preserving any remaining
blockers.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.extraction.schemas import ReviewStatus
from app.extraction_db import append_review_event, get_scope_item, update_scope_item


class PricingInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _to_decimal(value: Any, field_name: str) -> Decimal:
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PricingInputError("invalid_amount", f"{field_name} must be a valid number.") from exc
    if not dec.is_finite() or dec < 0:
        raise PricingInputError("invalid_amount", f"{field_name} must not be negative.")
    return dec


def _blocker_for_method(method: str) -> str:
    if method == "quote_based":
        return "missing_subcontract_quote"
    if method == "allowance":
        return "missing_allowance_basis"
    return "missing_unit_rate"


def _without_blocker(blockers: list[Any], blocker_code: str) -> list[Any]:
    return [
        blocker for blocker in blockers
        if not (isinstance(blocker, dict) and blocker.get("code") == blocker_code)
    ]


def apply_generic_pricing_input(
    project_id: UUID,
    scope_item_id: UUID,
    *,
    pricing_method: str,
    amount: Any,
    source: str,
    actor: str = "system",
    note: str | None = None,
) -> dict[str, Any]:
    """Apply a verified pricing basis to a generic scope item.

    This does not create a final estimate line or customer price. It records the
    verified basis and removes the corresponding blocker.
    """
    item = get_scope_item(project_id, scope_item_id)
    if item is None:
        raise PricingInputError("not_found", "Scope item not found.")
    trade_data = item.get("trade_data") or {}
    expected_method = trade_data.get("pricing_method") or pricing_method
    if pricing_method != expected_method:
        raise PricingInputError(
            "method_mismatch",
            f"Scope item expects pricing method {expected_method!r}.",
        )
    dec = _to_decimal(amount, "amount")
    if dec == 0:
        raise PricingInputError("invalid_amount", "amount must be greater than zero.")

    blocker_code = _blocker_for_method(pricing_method)
    pricing_basis = {
        "pricing_method": pricing_method,
        "amount": str(dec),
        "source": source,
        "actor": actor,
        "note": note,
        "applied_by": "generic_pricing_input_v1",
    }
    trade_data.update({
        "pricing_method": pricing_method,
        "pricing_basis": pricing_basis,
        "pricing_ready": True,
        "delivery_ready": False,
    })
    blockers = _without_blocker(item.get("blocking_issues") or [], blocker_code)
    review_status = ReviewStatus.BLOCKED.value if blockers else ReviewStatus.PENDING.value
    conflict_status = "blocking" if blockers else "none"
    updated = update_scope_item(
        scope_item_id,
        trade_data=trade_data,
        blocking_issues=blockers,
        review_status=review_status,
        conflict_status=conflict_status,
        reviewer_notes=note or "Verified generic pricing input applied.",
    )
    assert updated is not None
    append_review_event({
        "project_id": str(project_id),
        "scope_item_id": str(scope_item_id),
        "trade_code": item["trade_code"],
        "action": "pricing_input_applied",
        "previous_state": item.get("review_status"),
        "new_state": updated.get("review_status"),
        "reviewer_id": actor,
        "reviewer_notes": note or f"Applied {pricing_method} pricing basis from {source}.",
    })
    return updated
