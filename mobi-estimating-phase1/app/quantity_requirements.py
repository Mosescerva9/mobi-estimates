"""Project Quantity Backbone v1.

Creates internal quantity requirement rows from scope items that cannot be priced
because quantity is missing. This is a planning/backbone layer only; it does not
invent quantities or price estimates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection
from app.extraction_db import list_scope_items

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
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM quantity_requirements WHERE project_id=? "
            "ORDER BY trade_code ASC, created_at ASC",
            (str(project_id),),
        ).fetchall()
    return [_row(row) for row in rows]


def draft_quantity_requirements(project_id: UUID) -> dict[str, Any]:
    items, _ = list_scope_items(project_id, filters={"requires_review": True}, limit=1000, offset=0)
    candidates = [item for item in items if _scope_needs_quantity(item)]
    now = _now()
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with get_connection() as conn:
        for item in candidates:
            existing = conn.execute(
                "SELECT * FROM quantity_requirements WHERE project_id=? AND scope_item_id=?",
                (str(project_id), item["id"]),
            ).fetchone()
            if existing:
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
                INSERT INTO quantity_requirements (id, project_id, scope_item_id,
                    trade_code, status, requirement_type, suggested_method,
                    suggested_unit, basis_note, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req["id"], req["project_id"], req["scope_item_id"], req["trade_code"],
                    req["status"], req["requirement_type"], req["suggested_method"],
                    req["suggested_unit"], req["basis_note"], _dumps(req["payload"]),
                    req["created_at"], req["updated_at"],
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
