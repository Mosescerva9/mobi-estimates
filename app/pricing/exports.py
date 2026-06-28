"""Estimate exports (JSON + CSV). No filesystem paths or secrets are emitted."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

_LINE_FIELDS = [
    "scope_item_id", "trade_code", "category_code", "description", "location",
    "assembly_code", "quantity", "unit", "labor_hours", "crew_hours",
    "labor_cost", "material_cost", "equipment_cost", "subcontract_cost",
    "other_direct_cost", "direct_cost_total", "status",
]


def estimate_json(version: dict[str, Any], line_items: list[dict[str, Any]],
                  rollup: dict[str, Any], exceptions: list[dict[str, Any]]) -> str:
    payload = {
        "estimate_version": {
            "id": version.get("id"), "estimate_id": version.get("estimate_id"),
            "version_number": version.get("version_number"),
            "status": version.get("status"),
            "cost_book_version_id": version.get("cost_book_version_id"),
            "pricing_engine_version": version.get("pricing_engine_version"),
            "rounding_policy": version.get("rounding_policy"),
            "snapshot_hash": version.get("snapshot_hash"),
            "currency": version.get("currency"),
            "pricing_date": version.get("pricing_date"),
            "inclusions": _loads(version.get("inclusions")),
            "exclusions": _loads(version.get("exclusions")),
            "assumptions": _loads(version.get("assumptions")),
            "clarifications": _loads(version.get("clarifications")),
        },
        "rollup": rollup,
        "line_items": [{k: li.get(k) for k in _LINE_FIELDS} for li in line_items],
        "exceptions": exceptions,
    }
    return json.dumps(payload, indent=2, default=str)


def estimate_csv(line_items: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_LINE_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for li in line_items:
        writer.writerow({k: li.get(k, "") for k in _LINE_FIELDS})
    return buffer.getvalue()


def _loads(value: Any) -> Any:
    if value in (None, ""):
        return []
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []
