"""Phase 5 data access: proposals, proposal versions, line items, snapshots,
and the append-only proposal review log. Issued proposal versions are immutable."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, default=str, sort_keys=True)


def _loads(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (list, dict)):
        return value
    return json.loads(value)


def _nid() -> str:
    return str(uuid4())


def create_proposal(project_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    pid = _nid()
    now = _now()
    with get_connection() as c:
        c.execute("INSERT INTO proposals (id,project_id,estimate_id,name,client_name,"
                  "status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                  (pid, str(project_id), str(data["estimate_id"]), data["name"],
                   data.get("client_name"), "active", now, now))
        c.commit()
    return get_proposal(project_id, UUID(pid))


def get_proposal(project_id: UUID, proposal_id: UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute("SELECT * FROM proposals WHERE id=? AND project_id=?",
                        (str(proposal_id), str(project_id))).fetchone()
    return dict(row) if row else None


def list_proposals(project_id: UUID) -> list[dict]:
    with get_connection() as c:
        rows = c.execute("SELECT * FROM proposals WHERE project_id=? ORDER BY created_at DESC",
                         (str(project_id),)).fetchall()
    return [dict(r) for r in rows]


def next_version_number(proposal_id: UUID) -> int:
    with get_connection() as c:
        row = c.execute("SELECT COALESCE(MAX(version_number),0) FROM proposal_versions "
                        "WHERE proposal_id=?", (str(proposal_id),)).fetchone()
    return int(row[0]) + 1


_VERSION_JSON = ("inclusions", "exclusions", "assumptions", "clarifications")


def create_version(proposal_id: UUID, project_id: UUID, data: dict[str, Any],
                   line_items: list[dict]) -> dict[str, Any]:
    vid = _nid()
    now = _now()
    with get_connection() as c:
        c.execute(
            "INSERT INTO proposal_versions (id,proposal_id,project_id,estimate_version_id,"
            "version_number,status,prepared_by,client_name,client_contact,valid_until,"
            "detail_level,currency,total_sell_price,cover_notes,terms,inclusions,"
            "exclusions,assumptions,clarifications,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, str(proposal_id), str(project_id), str(data["estimate_version_id"]),
             data["version_number"], "draft", data.get("prepared_by"),
             data.get("client_name"), data.get("client_contact"),
             str(data["valid_until"]) if data.get("valid_until") else None,
             data.get("detail_level", "trade"), data.get("currency", "USD"),
             str(data.get("total_sell_price")) if data.get("total_sell_price") is not None else None,
             data.get("cover_notes", ""), data.get("terms", ""),
             _dumps(data.get("inclusions", [])), _dumps(data.get("exclusions", [])),
             _dumps(data.get("assumptions", [])), _dumps(data.get("clarifications", [])),
             now, now))
        for order, li in enumerate(line_items):
            c.execute(
                "INSERT INTO proposal_line_items (id,version_id,section,trade_code,"
                "category_code,description,location,quantity,unit,sell_price,sort_order) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (_nid(), vid, li.get("section"), li.get("trade_code"),
                 li.get("category_code"), li.get("description"), li.get("location"),
                 li.get("quantity"), li.get("unit"), str(li["sell_price"]), order))
        c.execute("UPDATE proposals SET current_version_id=?, updated_at=? WHERE id=?",
                  (vid, now, str(proposal_id)))
        c.commit()
    return get_version(vid)


def get_version(version_id: str | UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute("SELECT * FROM proposal_versions WHERE id=?", (str(version_id),)).fetchone()
    if not row:
        return None
    d = dict(row)
    for k in _VERSION_JSON:
        d[k] = _loads(d.get(k)) or []
    return d


def list_versions(proposal_id: UUID) -> list[dict]:
    with get_connection() as c:
        rows = c.execute("SELECT * FROM proposal_versions WHERE proposal_id=? "
                         "ORDER BY version_number", (str(proposal_id),)).fetchall()
    return [dict(r) for r in rows]


def get_line_items(version_id: str) -> list[dict]:
    with get_connection() as c:
        rows = c.execute("SELECT * FROM proposal_line_items WHERE version_id=? "
                         "ORDER BY sort_order", (str(version_id),)).fetchall()
    return [dict(r) for r in rows]


def update_version(version_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    for k in _VERSION_JSON:
        if k in fields:
            fields[k] = _dumps(fields[k])
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_connection() as c:
        c.execute(f"UPDATE proposal_versions SET {cols} WHERE id=?",
                  [*fields.values(), str(version_id)])
        c.commit()
    return get_version(version_id)


def save_snapshot(version_id: str, snapshot_json: str, snapshot_hash: str) -> None:
    with get_connection() as c:
        c.execute("DELETE FROM proposal_snapshots WHERE version_id=?", (str(version_id),))
        c.execute("INSERT INTO proposal_snapshots (id,version_id,snapshot_json,"
                  "snapshot_hash,created_at) VALUES (?,?,?,?,?)",
                  (_nid(), str(version_id), snapshot_json, snapshot_hash, _now()))
        c.commit()


def get_snapshot(version_id: str) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute("SELECT * FROM proposal_snapshots WHERE version_id=?",
                        (str(version_id),)).fetchone()
    return dict(row) if row else None


def append_review_event(version_id: str, project_id: UUID, event: dict[str, Any]) -> None:
    with get_connection() as c:
        c.execute("INSERT INTO proposal_review_events (id,version_id,project_id,action,"
                  "previous_state,new_state,actor,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                  (_nid(), str(version_id), str(project_id), event["action"],
                   event.get("previous_state"), event.get("new_state"),
                   event.get("actor", "system"), event.get("notes"), _now()))
        c.commit()


def list_review_events(version_id: str) -> list[dict]:
    with get_connection() as c:
        rows = c.execute("SELECT * FROM proposal_review_events WHERE version_id=? "
                         "ORDER BY created_at", (str(version_id),)).fetchall()
    return [dict(r) for r in rows]
