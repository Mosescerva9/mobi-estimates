"""Phase 5 data access: proposals, proposal versions, line items, snapshots,
and the append-only proposal review log. Issued proposal versions are immutable."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection
from app.tenant_boundary import (
    assert_same_tenant_project_access,
    build_tenant_project_context,
)


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


def _project_identity(c: Any, project_id: UUID) -> dict[str, str]:
    row = c.execute(
        "SELECT id, tenant_id, company_id FROM projects WHERE id=?", (str(project_id),)
    ).fetchone()
    if row is None:
        raise PermissionError("proposal_project_not_found")
    return build_tenant_project_context(
        tenant_id=row["tenant_id"],
        company_id=row["company_id"],
        project_id=row["id"],
    )


def _version_identity(
    c: Any,
    project_id: str | UUID,
    proposal_id: str | UUID,
    version_id: str | UUID,
) -> dict[str, str]:
    """Return verified tenant identity for a parent-scoped proposal version.

    Child/version artifact operations must not authorize from ``version_id``
    alone. Require the caller's already-validated route/request parent scope and
    join through project -> proposal -> version so a guessed child ID cannot be
    read or mutated outside that trusted parent context.
    """

    row = c.execute(
        """
        SELECT
            proposal_versions.id AS version_id,
            proposal_versions.proposal_id AS version_proposal_id,
            proposal_versions.project_id AS version_project_id,
            proposal_versions.tenant_id AS version_tenant_id,
            proposal_versions.company_id AS version_company_id,
            proposals.id AS proposal_id,
            proposals.project_id AS proposal_project_id,
            proposals.tenant_id AS proposal_tenant_id,
            proposals.company_id AS proposal_company_id,
            projects.id AS project_id,
            projects.tenant_id AS project_tenant_id,
            projects.company_id AS project_company_id
        FROM projects
        JOIN proposals ON proposals.project_id = projects.id
        JOIN proposal_versions ON proposal_versions.proposal_id = proposals.id
        WHERE projects.id=? AND proposals.id=? AND proposal_versions.id=?
        """,
        (str(project_id), str(proposal_id), str(version_id)),
    ).fetchone()
    if row is None:
        raise PermissionError("proposal_version_not_found")
    identity = build_tenant_project_context(
        tenant_id=row["project_tenant_id"],
        company_id=row["project_company_id"],
        project_id=row["project_id"],
    )
    assert str(row["proposal_id"]) == str(proposal_id)
    assert str(row["version_proposal_id"]) == str(proposal_id)
    assert_same_tenant_project_access(
        identity,
        {
            "tenant_id": row["proposal_tenant_id"],
            "company_id": row["proposal_company_id"],
            "project_id": row["proposal_project_id"],
        },
    )
    assert_same_tenant_project_access(
        identity,
        {
            "tenant_id": row["version_tenant_id"],
            "company_id": row["version_company_id"],
            "project_id": row["version_project_id"],
        },
    )
    return identity


def _assert_row_identity(identity: dict[str, str], row: dict[str, Any]) -> None:
    assert_same_tenant_project_access(
        identity,
        {
            "tenant_id": row.get("tenant_id"),
            "company_id": row.get("company_id"),
            "project_id": row.get("project_id"),
        },
    )


def create_proposal(project_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    pid = _nid()
    now = _now()
    with get_connection() as c:
        identity = _project_identity(c, project_id)
        c.execute(
            "INSERT INTO proposals (id,project_id,estimate_id,name,client_name,"
            "status,created_at,updated_at,tenant_id,company_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                pid,
                str(project_id),
                str(data["estimate_id"]),
                data["name"],
                data.get("client_name"),
                "active",
                now,
                now,
                identity["tenant_id"],
                identity["company_id"],
            ),
        )
        c.commit()
    return get_proposal(project_id, UUID(pid))


def get_proposal(project_id: UUID, proposal_id: UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        identity = _project_identity(c, project_id)
        row = c.execute(
            "SELECT * FROM proposals WHERE id=? AND project_id=?",
            (str(proposal_id), str(project_id)),
        ).fetchone()
    if row:
        try:
            _assert_row_identity(identity, dict(row))
        except PermissionError:
            return None
    return dict(row) if row else None


def list_proposals(project_id: UUID) -> list[dict]:
    with get_connection() as c:
        identity = _project_identity(c, project_id)
        rows = c.execute(
            "SELECT * FROM proposals WHERE project_id=? AND tenant_id=? AND company_id=? ORDER BY created_at DESC",
            (str(project_id), identity["tenant_id"], identity["company_id"]),
        ).fetchall()
    return [dict(r) for r in rows]


def next_version_number(proposal_id: UUID) -> int:
    with get_connection() as c:
        proposal = c.execute(
            "SELECT tenant_id, company_id FROM proposals WHERE id=?", (str(proposal_id),)
        ).fetchone()
        if proposal is None or not proposal["tenant_id"] or not proposal["company_id"]:
            raise PermissionError("proposal_tenant_context_required")
        row = c.execute(
            "SELECT COALESCE(MAX(version_number),0) FROM proposal_versions "
            "WHERE proposal_id=? AND tenant_id=? AND company_id=?",
            (str(proposal_id), proposal["tenant_id"], proposal["company_id"]),
        ).fetchone()
    return int(row[0]) + 1


_VERSION_JSON = ("inclusions", "exclusions", "assumptions", "clarifications")


def create_version(
    proposal_id: UUID, project_id: UUID, data: dict[str, Any], line_items: list[dict]
) -> dict[str, Any]:
    vid = _nid()
    now = _now()
    with get_connection() as c:
        identity = _project_identity(c, project_id)
        proposal = c.execute(
            "SELECT project_id, tenant_id, company_id FROM proposals WHERE id=?",
            (str(proposal_id),),
        ).fetchone()
        if proposal is None:
            raise PermissionError("proposal_tenant_context_required")
        _assert_row_identity(identity, dict(proposal))
        c.execute(
            "INSERT INTO proposal_versions (id,proposal_id,project_id,estimate_version_id,"
            "version_number,status,prepared_by,client_name,client_contact,valid_until,"
            "detail_level,currency,total_sell_price,cover_notes,terms,inclusions,"
            "exclusions,assumptions,clarifications,created_at,updated_at,tenant_id,company_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                vid,
                str(proposal_id),
                str(project_id),
                str(data["estimate_version_id"]),
                data["version_number"],
                "draft",
                data.get("prepared_by"),
                data.get("client_name"),
                data.get("client_contact"),
                str(data["valid_until"]) if data.get("valid_until") else None,
                data.get("detail_level", "trade"),
                data.get("currency", "USD"),
                str(data.get("total_sell_price"))
                if data.get("total_sell_price") is not None
                else None,
                data.get("cover_notes", ""),
                data.get("terms", ""),
                _dumps(data.get("inclusions", [])),
                _dumps(data.get("exclusions", [])),
                _dumps(data.get("assumptions", [])),
                _dumps(data.get("clarifications", [])),
                now,
                now,
                identity["tenant_id"],
                identity["company_id"],
            ),
        )
        for order, li in enumerate(line_items):
            c.execute(
                "INSERT INTO proposal_line_items (id,version_id,section,trade_code,"
                "category_code,description,location,quantity,unit,sell_price,sort_order,tenant_id,company_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    _nid(),
                    vid,
                    li.get("section"),
                    li.get("trade_code"),
                    li.get("category_code"),
                    li.get("description"),
                    li.get("location"),
                    li.get("quantity"),
                    li.get("unit"),
                    str(li["sell_price"]),
                    order,
                    identity["tenant_id"],
                    identity["company_id"],
                ),
            )
        c.execute(
            "UPDATE proposals SET current_version_id=?, updated_at=? "
            "WHERE id=? AND project_id=? AND tenant_id=? AND company_id=?",
            (
                vid,
                now,
                str(proposal_id),
                str(project_id),
                identity["tenant_id"],
                identity["company_id"],
            ),
        )
        c.commit()
    version = get_version(project_id, proposal_id, vid)
    if version is None:
        raise PermissionError("proposal_version_not_found")
    return version


def get_version(
    project_id: str | UUID,
    proposal_id: str | UUID,
    version_id: str | UUID,
) -> dict[str, Any] | None:
    with get_connection() as c:
        try:
            identity = _version_identity(c, project_id, proposal_id, version_id)
        except PermissionError:
            return None
        row = c.execute(
            "SELECT * FROM proposal_versions "
            "WHERE id=? AND proposal_id=? AND project_id=? AND tenant_id=? AND company_id=?",
            (
                str(version_id),
                str(proposal_id),
                str(project_id),
                identity["tenant_id"],
                identity["company_id"],
            ),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            _assert_row_identity(identity, d)
        except PermissionError:
            return None
    for k in _VERSION_JSON:
        d[k] = _loads(d.get(k)) or []
    return d


def list_versions(proposal_id: UUID) -> list[dict]:
    with get_connection() as c:
        proposal = c.execute(
            """
            SELECT
                proposals.project_id AS proposal_project_id,
                proposals.tenant_id AS proposal_tenant_id,
                proposals.company_id AS proposal_company_id,
                projects.id AS project_id,
                projects.tenant_id AS project_tenant_id,
                projects.company_id AS project_company_id
            FROM proposals
            JOIN projects ON projects.id = proposals.project_id
            WHERE proposals.id=?
            """,
            (str(proposal_id),),
        ).fetchone()
        if proposal is None:
            return []
        try:
            identity = build_tenant_project_context(
                tenant_id=proposal["project_tenant_id"],
                company_id=proposal["project_company_id"],
                project_id=proposal["project_id"],
            )
            assert_same_tenant_project_access(
                identity,
                {
                    "tenant_id": proposal["proposal_tenant_id"],
                    "company_id": proposal["proposal_company_id"],
                    "project_id": proposal["proposal_project_id"],
                },
            )
        except PermissionError:
            return []
        rows = c.execute(
            "SELECT * FROM proposal_versions "
            "WHERE proposal_id=? AND project_id=? AND tenant_id=? AND company_id=? "
            "ORDER BY version_number",
            (
                str(proposal_id),
                identity["project_id"],
                identity["tenant_id"],
                identity["company_id"],
            ),
        ).fetchall()
    return [dict(r) for r in rows]


def get_line_items(
    project_id: str | UUID,
    proposal_id: str | UUID,
    version_id: str | UUID,
) -> list[dict]:
    with get_connection() as c:
        try:
            identity = _version_identity(c, project_id, proposal_id, version_id)
        except PermissionError:
            return []
        rows = c.execute(
            """
            SELECT proposal_line_items.*
            FROM proposal_line_items
            JOIN proposal_versions ON proposal_versions.id = proposal_line_items.version_id
            WHERE proposal_line_items.version_id=?
              AND proposal_versions.proposal_id=?
              AND proposal_versions.project_id=?
              AND proposal_line_items.tenant_id=?
              AND proposal_line_items.company_id=?
            ORDER BY proposal_line_items.sort_order
            """,
            (
                str(version_id),
                str(proposal_id),
                str(project_id),
                identity["tenant_id"],
                identity["company_id"],
            ),
        ).fetchall()
    return [dict(r) for r in rows]


def update_version(
    project_id: str | UUID,
    proposal_id: str | UUID,
    version_id: str | UUID,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    for k in _VERSION_JSON:
        if k in fields:
            fields[k] = _dumps(fields[k])
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_connection() as c:
        identity = _version_identity(c, project_id, proposal_id, version_id)
        c.execute(
            f"UPDATE proposal_versions SET {cols} "
            "WHERE id=? AND proposal_id=? AND project_id=? AND tenant_id=? AND company_id=?",
            [
                *fields.values(),
                str(version_id),
                str(proposal_id),
                str(project_id),
                identity["tenant_id"],
                identity["company_id"],
            ],
        )
        c.commit()
    return get_version(project_id, proposal_id, version_id)


def save_snapshot(
    project_id: str | UUID,
    proposal_id: str | UUID,
    version_id: str | UUID,
    snapshot_json: str,
    snapshot_hash: str,
) -> None:
    with get_connection() as c:
        identity = _version_identity(c, project_id, proposal_id, version_id)
        c.execute(
            """
            DELETE FROM proposal_snapshots
            WHERE version_id=?
              AND tenant_id=?
              AND company_id=?
              AND EXISTS (
                SELECT 1 FROM proposal_versions
                WHERE proposal_versions.id=proposal_snapshots.version_id
                  AND proposal_versions.proposal_id=?
                  AND proposal_versions.project_id=?
              )
            """,
            (
                str(version_id),
                identity["tenant_id"],
                identity["company_id"],
                str(proposal_id),
                str(project_id),
            ),
        )
        c.execute(
            "INSERT INTO proposal_snapshots (id,version_id,snapshot_json,"
            "snapshot_hash,created_at,tenant_id,company_id) VALUES (?,?,?,?,?,?,?)",
            (
                _nid(),
                str(version_id),
                snapshot_json,
                snapshot_hash,
                _now(),
                identity["tenant_id"],
                identity["company_id"],
            ),
        )
        c.commit()


def get_snapshot(
    project_id: str | UUID,
    proposal_id: str | UUID,
    version_id: str | UUID,
) -> dict[str, Any] | None:
    with get_connection() as c:
        try:
            identity = _version_identity(c, project_id, proposal_id, version_id)
        except PermissionError:
            return None
        row = c.execute(
            """
            SELECT proposal_snapshots.*
            FROM proposal_snapshots
            JOIN proposal_versions ON proposal_versions.id = proposal_snapshots.version_id
            WHERE proposal_snapshots.version_id=?
              AND proposal_versions.proposal_id=?
              AND proposal_versions.project_id=?
              AND proposal_snapshots.tenant_id=?
              AND proposal_snapshots.company_id=?
            """,
            (
                str(version_id),
                str(proposal_id),
                str(project_id),
                identity["tenant_id"],
                identity["company_id"],
            ),
        ).fetchone()
    return dict(row) if row else None


def append_review_event(
    project_id: UUID,
    proposal_id: str | UUID,
    version_id: str | UUID,
    event: dict[str, Any],
) -> None:
    with get_connection() as c:
        identity = _project_identity(c, project_id)
        version_identity = _version_identity(c, project_id, proposal_id, version_id)
        assert_same_tenant_project_access(identity, version_identity)
        c.execute(
            "INSERT INTO proposal_review_events (id,version_id,project_id,action,"
            "previous_state,new_state,actor,notes,created_at,tenant_id,company_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                _nid(),
                str(version_id),
                str(project_id),
                event["action"],
                event.get("previous_state"),
                event.get("new_state"),
                event.get("actor", "system"),
                event.get("notes"),
                _now(),
                identity["tenant_id"],
                identity["company_id"],
            ),
        )
        c.commit()


def list_review_events(
    project_id: str | UUID,
    proposal_id: str | UUID,
    version_id: str | UUID,
) -> list[dict]:
    with get_connection() as c:
        try:
            identity = _version_identity(c, project_id, proposal_id, version_id)
        except PermissionError:
            return []
        rows = c.execute(
            """
            SELECT proposal_review_events.*
            FROM proposal_review_events
            JOIN proposal_versions ON proposal_versions.id = proposal_review_events.version_id
            WHERE proposal_review_events.version_id=?
              AND proposal_versions.proposal_id=?
              AND proposal_versions.project_id=?
              AND proposal_review_events.project_id=?
              AND proposal_review_events.tenant_id=?
              AND proposal_review_events.company_id=?
            ORDER BY proposal_review_events.created_at
            """,
            (
                str(version_id),
                str(proposal_id),
                str(project_id),
                identity["project_id"],
                identity["tenant_id"],
                identity["company_id"],
            ),
        ).fetchall()
    return [dict(r) for r in rows]
