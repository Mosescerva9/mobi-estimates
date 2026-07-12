"""Project Quantity Backbone v1.

Creates internal quantity requirement rows from scope items that cannot be priced
because quantity is missing. This is a planning/backbone layer only; it does not
invent quantities or price estimates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection, get_project
from app.extraction.schemas import ReviewStatus
from app.extraction_db import append_review_event, get_scope_item, list_scope_items, update_scope_item
from app.tenant_boundary import build_tenant_project_context, assert_same_tenant_project_access

SUGGESTED_UNITS = {
    "electrical": "EA",
    "plumbing": "EA",
    "hvac": "EA",
    "fire_alarm": "EA",
    "fire_protection": "SF",
    "doors_hardware": "EA",
    "finishes": "SF",
    "sitework": "LS",
    "civil_sitework": "LS",
    "structural": "LS",
    "architectural": "LS",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value or {}, default=str, sort_keys=True)


def _loads(value: str | None) -> Any:
    if value in (None, ""):
        return {}
    return json.loads(value)


def _row(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["payload"] = _loads(data.get("payload"))
    return data


def _project_identity(project_id: UUID) -> dict[str, str]:
    project = get_project(project_id)
    if project is None:
        raise QuantityRequirementError("project_not_found", "Project not found.")
    try:
        return build_tenant_project_context(
            tenant_id=project.get("tenant_id"),
            company_id=project.get("company_id"),
            project_id=str(project_id),
        )
    except PermissionError as exc:
        raise QuantityRequirementError(
            "tenant_identity_required",
            "Project tenant/company identity is required for quantity requirements.",
        ) from exc


def _assert_row_matches_project_identity(row: dict[str, Any], identity: dict[str, str], *, row_name: str) -> None:
    try:
        assert_same_tenant_project_access(
            identity,
            {
                "tenant_id": row.get("tenant_id"),
                "company_id": row.get("company_id"),
                "project_id": row.get("project_id"),
            },
        )
    except PermissionError as exc:
        raise QuantityRequirementError(
            "tenant_identity_mismatch",
            f"{row_name} tenant/company identity does not match project.",
        ) from exc


def _scope_needs_quantity(item: dict[str, Any]) -> bool:
    if item.get("quantity") not in (None, ""):
        return False
    blockers = item.get("blocking_issues") or []
    return any(blocker.get("code") == "missing_quantity" for blocker in blockers if isinstance(blocker, dict))


def _suggested_method(item: dict[str, Any]) -> str:
    method = (item.get("trade_data") or {}).get("pricing_method")
    if method == "allowance":
        return "allowance_amount"
    if method == "quote_based":
        return "quote_scope_quantity_or_lump_sum"
    return "takeoff_or_schedule_count"


def list_quantity_requirements(project_id: UUID) -> list[dict[str, Any]]:
    identity = _project_identity(project_id)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM quantity_requirements WHERE project_id=? "
            "ORDER BY trade_code ASC, created_at ASC",
            (str(project_id),),
        ).fetchall()
    requirements = [_row(row) for row in rows]
    for requirement in requirements:
        _assert_row_matches_project_identity(
            requirement, identity, row_name="Quantity requirement"
        )
    return requirements


class QuantityRequirementError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _to_decimal(value: Any) -> Decimal:
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise QuantityRequirementError("invalid_quantity", "Quantity must be a valid number.") from exc
    if not quantity.is_finite() or quantity <= 0:
        raise QuantityRequirementError("invalid_quantity", "Quantity must be greater than zero.")
    return quantity


def _get_requirement(project_id: UUID, requirement_id: UUID) -> dict[str, Any] | None:
    identity = _project_identity(project_id)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM quantity_requirements WHERE id=? AND project_id=?",
            (str(requirement_id), str(project_id)),
        ).fetchone()
    if not row:
        return None
    requirement = _row(row)
    _assert_row_matches_project_identity(
        requirement, identity, row_name="Quantity requirement"
    )
    return requirement


def _without_missing_quantity(blockers: list[Any]) -> list[Any]:
    return [
        blocker for blocker in blockers
        if not (isinstance(blocker, dict) and blocker.get("code") == "missing_quantity")
    ]


def apply_quantity_requirement(
    project_id: UUID,
    requirement_id: UUID,
    *,
    quantity: Any,
    unit: str,
    quantity_basis: str,
    source: str,
    actor: str = "system",
    note: str | None = None,
) -> dict[str, Any]:
    """Apply a verified quantity to a scope item and resolve the requirement.

    This does not price or approve the scope item. It only clears the quantity
    blocker, leaving any pricing/quote/allowance blockers visible.
    """
    requirement = _get_requirement(project_id, requirement_id)
    if requirement is None:
        raise QuantityRequirementError("not_found", "Quantity requirement not found.")
    if requirement["status"] == "resolved":
        raise QuantityRequirementError("already_resolved", "Quantity requirement is already resolved.")
    scope_item_id = UUID(requirement["scope_item_id"])
    item = get_scope_item(project_id, scope_item_id)
    if item is None:
        raise QuantityRequirementError("scope_not_found", "Linked scope item not found.")
    _assert_row_matches_project_identity(
        item,
        build_tenant_project_context(
            tenant_id=requirement.get("tenant_id"),
            company_id=requirement.get("company_id"),
            project_id=requirement.get("project_id"),
        ),
        row_name="Scope item",
    )

    qty = _to_decimal(quantity)
    unit = unit.strip().upper()
    if not unit:
        raise QuantityRequirementError("invalid_unit", "Unit is required.")
    raw_quantity_inputs = item.get("raw_quantity_inputs") or {}
    applied_input = {
        "quantity": str(qty),
        "unit": unit,
        "quantity_basis": quantity_basis,
        "source": source,
        "actor": actor,
        "note": note,
        "applied_at": _now(),
        "quantity_requirement_id": str(requirement_id),
    }
    raw_quantity_inputs.update({"verified_quantity_input_v1": applied_input})

    blockers = _without_missing_quantity(item.get("blocking_issues") or [])
    review_status = ReviewStatus.BLOCKED.value if blockers else ReviewStatus.PENDING.value
    conflict_status = "blocking" if blockers else "none"
    updated_item = update_scope_item(
        scope_item_id,
        quantity=qty,
        unit=unit,
        quantity_basis=quantity_basis,
        raw_quantity_inputs=raw_quantity_inputs,
        blocking_issues=blockers,
        review_status=review_status,
        conflict_status=conflict_status,
        reviewer_notes=note or "Verified quantity applied from quantity requirement.",
    )
    assert updated_item is not None

    payload = requirement.get("payload") or {}
    payload.update({"applied_quantity": applied_input})
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE quantity_requirements
            SET status='resolved', payload=?, updated_at=?, resolved_at=?
            WHERE id=? AND project_id=?
            """,
            (_dumps(payload), now, now, str(requirement_id), str(project_id)),
        )
        conn.commit()

    append_review_event({
        "project_id": str(project_id),
        "scope_item_id": str(scope_item_id),
        "trade_code": item["trade_code"],
        "action": "quantity_applied",
        "previous_state": item.get("review_status"),
        "new_state": updated_item.get("review_status"),
        "reviewer_id": actor,
        "reviewer_notes": note or f"Applied {qty} {unit} from quantity requirement {requirement_id}.",
    })

    resolved = _get_requirement(project_id, requirement_id)
    return {"requirement": resolved, "scope_item": updated_item}


def draft_quantity_requirements(project_id: UUID) -> dict[str, Any]:
    identity = _project_identity(project_id)
    items, _ = list_scope_items(project_id, filters={"requires_review": True}, limit=1000, offset=0)
    candidates = [item for item in items if _scope_needs_quantity(item)]
    now = _now()
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with get_connection() as conn:
        for item in candidates:
            _assert_row_matches_project_identity(item, identity, row_name="Scope item")
            existing = conn.execute(
                "SELECT * FROM quantity_requirements WHERE project_id=? AND scope_item_id=?",
                (str(project_id), item["id"]),
            ).fetchone()
            if existing:
                _assert_row_matches_project_identity(
                    _row(existing), identity, row_name="Quantity requirement"
                )
                skipped.append({"scope_item_id": item["id"], "reason": "requirement_exists"})
                continue
            trade_code = item["trade_code"]
            payload = {
                "scope_description": item.get("description"),
                "pricing_method": (item.get("trade_data") or {}).get("pricing_method"),
                "source": "quantity_backbone_v1",
            }
            req = {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "tenant_id": identity["tenant_id"],
                "company_id": identity["company_id"],
                "scope_item_id": item["id"],
                "trade_code": trade_code,
                "status": "open",
                "requirement_type": "quantity_needed",
                "suggested_method": _suggested_method(item),
                "suggested_unit": SUGGESTED_UNITS.get(trade_code, "LS"),
                "basis_note": "Quantity is required before this generic scope item can be priced.",
                "payload": payload,
                "created_at": now,
                "updated_at": now,
            }
            conn.execute(
                """
                INSERT INTO quantity_requirements (id, project_id, tenant_id,
                    company_id, scope_item_id, trade_code, status, requirement_type,
                    suggested_method, suggested_unit, basis_note, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req["id"], req["project_id"], req["tenant_id"], req["company_id"],
                    req["scope_item_id"], req["trade_code"], req["status"], req["requirement_type"],
                    req["suggested_method"], req["suggested_unit"], req["basis_note"],
                    _dumps(req["payload"]), req["created_at"], req["updated_at"],
                ),
            )
            created.append(req)
        conn.commit()
    return {
        "project_id": str(project_id),
        "created_count": len(created),
        "skipped_count": len(skipped),
        "items": created,
        "skipped": skipped,
    }
