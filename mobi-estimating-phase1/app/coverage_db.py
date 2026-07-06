"""Trade Coverage Matrix data access and completeness validation.

The coverage matrix is the automation-first all-trade control layer: every
trade detected in a project receives an explicit disposition so no scope can
silently disappear. This module is intentionally backend-local and deterministic;
it does not send external messages, deliver estimates, or perform pricing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection

JSON_COLUMNS = {"csi_divisions", "detected_from", "blockers", "evidence_refs"}

TERMINAL_DISPOSITIONS = {
    "included_module",
    "included_generic",
    "included_quote",
    "allowance",
    "customer_confirmation_needed",
    "excluded_by_customer",
    "excluded_by_mobi",
    "not_applicable",
    "blocked_needs_info",
    "blocked_needs_source_data",
}
INCLUDED_DISPOSITIONS = {
    "included_module",
    "included_generic",
    "included_quote",
    "allowance",
    "customer_confirmation_needed",
}
BLOCKED_DISPOSITIONS = {"blocked_needs_info", "blocked_needs_source_data"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value or [], default=str, sort_keys=True)


def _loads(value: str | None) -> Any:
    if value in (None, ""):
        return []
    return json.loads(value)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for column in JSON_COLUMNS:
        data[column] = _loads(data.get(column))
    data["confidence"] = float(data["confidence"]) if data.get("confidence") is not None else None
    return data


def create_coverage_row(project_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    row_id = str(uuid4())
    values = {
        "id": row_id,
        "project_id": str(project_id),
        "trade_code": payload["trade_code"],
        "trade_name": payload["trade_name"],
        "csi_divisions": _dumps(payload.get("csi_divisions")),
        "detected_from": _dumps(payload.get("detected_from")),
        "disposition": payload.get("disposition", "undispositioned"),
        "basis_note": payload.get("basis_note"),
        "confidence": payload.get("confidence"),
        "status": payload.get("status", "draft"),
        "blockers": _dumps(payload.get("blockers")),
        "evidence_refs": _dumps(payload.get("evidence_refs")),
        "created_at": now,
        "updated_at": now,
    }
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO trade_coverage_rows ({columns}) VALUES ({placeholders})",
            list(values.values()),
        )
        conn.commit()
    row = get_coverage_row(project_id, UUID(row_id))
    assert row is not None
    return row


def list_coverage_rows(project_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trade_coverage_rows WHERE project_id=? "
            "ORDER BY trade_code ASC, created_at ASC",
            (str(project_id),),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_coverage_row(project_id: UUID, row_id: UUID) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM trade_coverage_rows WHERE project_id=? AND id=?",
            (str(project_id), str(row_id)),
        ).fetchone()
    return _row_to_dict(row) if row else None


def update_coverage_row(
    project_id: UUID, row_id: UUID, fields: dict[str, Any]
) -> dict[str, Any] | None:
    if not fields:
        return get_coverage_row(project_id, row_id)
    allowed = {
        "trade_name",
        "csi_divisions",
        "detected_from",
        "disposition",
        "basis_note",
        "confidence",
        "status",
        "blockers",
        "evidence_refs",
    }
    updates: dict[str, Any] = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return get_coverage_row(project_id, row_id)
    for column in JSON_COLUMNS:
        if column in updates:
            updates[column] = _dumps(updates[column])
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key}=?" for key in updates)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE trade_coverage_rows SET {assignments} WHERE project_id=? AND id=?",
            [*updates.values(), str(project_id), str(row_id)],
        )
        conn.commit()
    return get_coverage_row(project_id, row_id)


def count_scope_items_by_trade(project_id: UUID) -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT trade_code, COUNT(*) AS count FROM scope_items "
            "WHERE project_id=? AND review_status != 'rejected' GROUP BY trade_code",
            (str(project_id),),
        ).fetchall()
    return {str(row["trade_code"]): int(row["count"]) for row in rows}


def validate_coverage(project_id: UUID) -> dict[str, Any]:
    """Return deterministic completeness findings for a project's coverage matrix."""
    rows = list_coverage_rows(project_id)
    scope_counts = count_scope_items_by_trade(project_id)
    findings: list[dict[str, Any]] = []

    if not rows:
        findings.append({
            "severity": "critical",
            "code": "coverage_matrix_empty",
            "message": "Project has no trade coverage rows.",
        })

    for row in rows:
        row_ref = {"coverage_row_id": row["id"], "trade_code": row["trade_code"]}
        disposition = row.get("disposition") or "undispositioned"
        if disposition == "undispositioned" or disposition not in TERMINAL_DISPOSITIONS:
            findings.append({
                **row_ref,
                "severity": "critical",
                "code": "undispositioned_trade",
                "message": "Trade coverage row has no terminal disposition.",
            })
            continue

        if disposition in BLOCKED_DISPOSITIONS and not row.get("blockers"):
            findings.append({
                **row_ref,
                "severity": "critical",
                "code": "blocked_without_blockers",
                "message": "Blocked coverage rows must list blockers/customer needs.",
            })

        if disposition in INCLUDED_DISPOSITIONS:
            has_basis = bool((row.get("basis_note") or "").strip())
            has_scope = scope_counts.get(row["trade_code"], 0) > 0
            has_evidence = bool(row.get("evidence_refs"))
            if not (has_basis or has_scope or has_evidence):
                findings.append({
                    **row_ref,
                    "severity": "major",
                    "code": "included_without_basis",
                    "message": (
                        "Included coverage rows need a basis note, evidence refs, "
                        "or at least one non-rejected scope item."
                    ),
                })

    critical_count = sum(1 for item in findings if item["severity"] == "critical")
    major_count = sum(1 for item in findings if item["severity"] == "major")
    return {
        "project_id": str(project_id),
        "complete": critical_count == 0 and major_count == 0,
        "row_count": len(rows),
        "critical_count": critical_count,
        "major_count": major_count,
        "findings": findings,
    }
