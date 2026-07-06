"""Customer Revision Parser / Workflow v1.

Parses customer or reviewer free-text revision feedback into internal request rows.
No external messages are sent and no estimate/proposal is regenerated here.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection

ACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("exclude", re.compile(r"\b(exclude|remove|deduct|delete|take out|omit)\b", re.I)),
    ("include", re.compile(r"\b(include|add|carry|price|provide)\b", re.I)),
    ("revise", re.compile(r"\b(revise|change|update|adjust|swap|replace)\b", re.I)),
    ("clarify", re.compile(r"\b(confirm|clarify|question|verify|is it|does this)\b", re.I)),
)

TRADE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("electrical", ("electrical", "electric", "power", "lighting", "panel", "outlet")),
    ("plumbing", ("plumbing", "plumber", "fixture", "water", "sanitary", "gas line")),
    ("hvac", ("hvac", "mechanical", "duct", "diffuser", "rtu", "air")),
    ("fire_alarm", ("fire alarm", "fa system", "notification", "detector")),
    ("fire_protection", ("sprinkler", "fire protection", "fp system")),
    ("doors_hardware", ("door", "hardware", "frame", "lockset")),
    ("finishes", ("paint", "floor", "finish", "tile", "ceiling")),
    ("sitework", ("site", "civil", "grading", "paving", "asphalt", "concrete walk")),
)

SHEET_RE = re.compile(r"\b([A-Z]{1,3}[- ]?\d{1,4}(?:\.\d+)?)\b")


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


def _split_items(text: str) -> list[str]:
    candidates: list[str] = []
    for raw in re.split(r"\n+|(?:^|\s)(?:[-*•]|\d+[.)])\s+", text):
        clean = raw.strip(" \t-•*")
        if len(clean) >= 4:
            candidates.append(clean)
    return candidates or [text.strip()]


def _action(text: str) -> str:
    for action, pattern in ACTION_PATTERNS:
        if pattern.search(text):
            return action
    return "review"


def _trade(text: str) -> str | None:
    lower = text.lower()
    for trade_code, keywords in TRADE_KEYWORDS:
        if any(keyword in lower for keyword in keywords):
            return trade_code
    return None


def _confidence(action: str, trade_code: str | None, sheet_refs: list[str]) -> float:
    score = 0.35
    if action != "review":
        score += 0.2
    if trade_code:
        score += 0.25
    if sheet_refs:
        score += 0.15
    return min(score, 0.95)


def create_revision_requests(
    project_id: UUID,
    *,
    source: str,
    raw_text: str,
    actor: str = "customer",
) -> dict[str, Any]:
    now = _now()
    items = []
    for text in _split_items(raw_text):
        action = _action(text)
        trade_code = _trade(text)
        sheet_refs = SHEET_RE.findall(text)
        payload = {
            "raw_text": text,
            "sheet_refs": sheet_refs,
            "parser": "customer_revision_parser_v1",
        }
        items.append({
            "id": str(uuid4()),
            "project_id": str(project_id),
            "source": source,
            "actor": actor,
            "action": action,
            "trade_code": trade_code,
            "status": "open",
            "summary": text[:500],
            "confidence": _confidence(action, trade_code, sheet_refs),
            "payload": payload,
            "created_at": now,
            "updated_at": now,
        })
    with get_connection() as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO customer_revision_requests (id, project_id, source,
                    actor, action, trade_code, status, summary, confidence, payload,
                    created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"], item["project_id"], item["source"], item["actor"],
                    item["action"], item["trade_code"], item["status"], item["summary"],
                    item["confidence"], _dumps(item["payload"]), item["created_at"],
                    item["updated_at"],
                ),
            )
        conn.commit()
    return {"project_id": str(project_id), "created_count": len(items), "items": items}


def list_revision_requests(project_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM customer_revision_requests WHERE project_id=? "
            "ORDER BY created_at ASC, id ASC",
            (str(project_id),),
        ).fetchall()
    return [_row(row) for row in rows]
