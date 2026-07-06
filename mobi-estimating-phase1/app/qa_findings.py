"""QA Findings Log v1 data access and deterministic generator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.coverage_db import validate_coverage
from app.database import get_connection
from app.extraction_db import list_scope_items

JSON_COLUMNS = {"payload"}
AUTO_SOURCE = "automated_qa_v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value or {}, default=str, sort_keys=True)


def _loads(value: str | None) -> Any:
    if value in (None, ""):
        return {}
    return json.loads(value)


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["payload"] = _loads(data.get("payload"))
    return data


def list_qa_findings(project_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM qa_findings WHERE project_id=? "
            "ORDER BY severity DESC, trade_code ASC, created_at ASC",
            (str(project_id),),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _replace_auto_findings(project_id: UUID, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM qa_findings WHERE project_id=? AND source=?",
            (str(project_id), AUTO_SOURCE),
        )
        for finding in findings:
            conn.execute(
                """
                INSERT INTO qa_findings (id, project_id, source, code, severity,
                    trade_code, coverage_row_id, scope_item_id, message, status,
                    payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    str(project_id),
                    AUTO_SOURCE,
                    finding["code"],
                    finding["severity"],
                    finding.get("trade_code"),
                    finding.get("coverage_row_id"),
                    finding.get("scope_item_id"),
                    finding["message"],
                    _dumps(finding.get("payload")),
                    now,
                    now,
                ),
            )
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM qa_findings WHERE project_id=? AND source=? "
            "ORDER BY severity DESC, trade_code ASC, created_at ASC",
            (str(project_id), AUTO_SOURCE),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _coverage_findings(project_id: UUID) -> list[dict[str, Any]]:
    validation = validate_coverage(project_id)
    out: list[dict[str, Any]] = []
    for item in validation["findings"]:
        out.append({
            "code": item["code"],
            "severity": item["severity"],
            "trade_code": item.get("trade_code"),
            "coverage_row_id": item.get("coverage_row_id"),
            "message": item["message"],
            "payload": {"source": "coverage_validator", **item},
        })
    return out


def _scope_blocker_findings(project_id: UUID) -> list[dict[str, Any]]:
    items, _ = list_scope_items(
        project_id,
        filters={"requires_review": True},
        limit=1000,
        offset=0,
    )
    out: list[dict[str, Any]] = []
    for item in items:
        for blocker in item.get("blocking_issues") or []:
            code = blocker.get("code") or "scope_blocker"
            out.append({
                "code": code,
                "severity": "critical" if code in {"missing_quantity", "missing_pricing_basis"} else "major",
                "trade_code": item.get("trade_code"),
                "scope_item_id": item.get("id"),
                "message": blocker.get("message") or "Scope item has an unresolved blocker.",
                "payload": {
                    "source": "scope_item_blocking_issues",
                    "scope_item_id": item.get("id"),
                    "category_code": item.get("category_code"),
                    "review_status": item.get("review_status"),
                    "blocker": blocker,
                },
            })
    return out


def draft_qa_findings(project_id: UUID) -> dict[str, Any]:
    findings = [*_coverage_findings(project_id), *_scope_blocker_findings(project_id)]
    rows = _replace_auto_findings(project_id, findings)
    critical = sum(1 for row in rows if row["severity"] == "critical")
    major = sum(1 for row in rows if row["severity"] == "major")
    return {
        "project_id": str(project_id),
        "finding_count": len(rows),
        "critical_count": critical,
        "major_count": major,
        "items": rows,
    }
