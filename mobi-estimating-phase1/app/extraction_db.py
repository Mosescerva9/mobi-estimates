"""Phase 3 data access: extraction runs, routing, scope items, evidence,
derivations, conflicts, and the append-only review log.

This reuses the shared SQLite connection from ``app.database`` (one data layer,
split by domain) and serializes JSON/Decimal columns consistently.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection
from app.tenant_boundary import build_tenant_project_context, assert_same_tenant_project_access

ACTIVE_RUN_STATES = ("queued", "running")
_IMMUTABLE_RUN_IDENTITY_FIELDS = frozenset({"tenant_id", "company_id", "project_id"})
_MUTABLE_RUN_FIELDS = frozenset(
    {
        "status",
        "started_at",
        "completed_at",
        "error_code",
        "error_message",
        "input_sheet_count",
        "processed_sheet_count",
        "blocked_sheet_count",
        "failed_sheet_count",
        "candidate_count",
        "usage",
        "estimated_cost",
        "updated_at",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, sort_keys=True)


def _loads(value: str | None) -> Any:
    if value in (None, ""):
        return None
    return json.loads(value)


# ---------------------------------------------------------------------------
# Trade definitions
# ---------------------------------------------------------------------------
def upsert_trade_definition(
    *, trade_code: str, trade_name: str, module_version: str,
    schema_version: str, enabled: bool, metadata: dict[str, Any],
) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO trade_definitions (trade_code, trade_name, module_version,
                schema_version, enabled, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_code) DO UPDATE SET
                trade_name=excluded.trade_name,
                module_version=excluded.module_version,
                schema_version=excluded.schema_version,
                enabled=excluded.enabled,
                metadata=excluded.metadata,
                updated_at=excluded.updated_at
            """,
            (trade_code, trade_name, module_version, schema_version,
             1 if enabled else 0, _dumps(metadata), now, now),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Extraction runs
# ---------------------------------------------------------------------------
def _active_run(conn: sqlite3.Connection, project_id: UUID, trade_code: str):
    return conn.execute(
        "SELECT * FROM extraction_runs WHERE project_id=? AND trade_code=? "
        "AND status IN (?, ?) AND dry_run=0 ORDER BY created_at DESC LIMIT 1",
        (str(project_id), trade_code, *ACTIVE_RUN_STATES),
    ).fetchone()


def _latest_run(conn: sqlite3.Connection, project_id: UUID, trade_code: str):
    return conn.execute(
        "SELECT * FROM extraction_runs WHERE project_id=? AND trade_code=? "
        "AND dry_run=0 ORDER BY created_at DESC, attempt DESC LIMIT 1",
        (str(project_id), trade_code),
    ).fetchone()


def _get_project_identity(
    conn: sqlite3.Connection, project_id: UUID
) -> dict[str, str] | None:
    row = conn.execute(
        "SELECT id, tenant_id, company_id FROM projects WHERE id=?", (str(project_id),)
    ).fetchone()
    if row is None:
        return None
    try:
        return build_tenant_project_context(
            tenant_id=row["tenant_id"],
            company_id=row["company_id"],
            project_id=row["id"],
        )
    except PermissionError:
        return None


def _run_matches_project_identity(
    run: sqlite3.Row | dict[str, Any], identity: dict[str, str]
) -> bool:
    try:
        assert_same_tenant_project_access(
            identity,
            {
                "tenant_id": run["tenant_id"],
                "company_id": run["company_id"],
                "project_id": run["project_id"],
            },
        )
    except PermissionError:
        return False
    return True


def _next_run_attempt(conn: sqlite3.Connection, project_id: UUID, trade_code: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(attempt),0) FROM extraction_runs "
        "WHERE project_id=? AND trade_code=?",
        (str(project_id), trade_code),
    ).fetchone()
    return int(row[0]) + 1


def claim_extraction_run(
    *, project_id: UUID, trade_code: str, provider: str, model: str | None,
    prompt_version: str | None, provider_schema_version: str | None,
    trade_schema_version: str | None, force: bool, dry_run: bool,
) -> tuple[str, dict[str, Any]]:
    """Atomically reserve a tenant-scoped extraction run for a project/trade.

    Outcomes: ``created``, ``active`` (idempotent), ``exists_completed``, or
    ``tenant_unscoped`` when the project/run identity cannot be proven.
    """
    now = _now()
    with get_connection() as conn:
        identity = _get_project_identity(conn, project_id)
        if identity is None:
            return ("tenant_unscoped", {})

        if not dry_run:
            active = _active_run(conn, project_id, trade_code)
            if active is not None:
                if not _run_matches_project_identity(active, identity):
                    return ("tenant_unscoped", {})
                return ("active", dict(active))
            latest = _latest_run(conn, project_id, trade_code)
            # A run that finished successfully (with or without candidates to
            # review) requires an explicit force to re-run. Failed/cancelled runs
            # may be retried without force.
            if (
                latest is not None
                and latest["status"] in ("needs_review", "completed")
                and not force
            ):
                if not _run_matches_project_identity(latest, identity):
                    return ("tenant_unscoped", {})
                return ("exists_completed", dict(latest))

        run_id = uuid4()
        attempt = _next_run_attempt(conn, project_id, trade_code)
        try:
            conn.execute(
                """
                INSERT INTO extraction_runs (id, project_id, tenant_id, company_id,
                    trade_code, status, provider, model_identifier, prompt_version,
                    provider_schema_version, trade_schema_version, attempt,
                    dry_run, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(run_id), str(project_id), identity["tenant_id"],
                 identity["company_id"], trade_code, provider, model, prompt_version,
                 provider_schema_version, trade_schema_version, attempt,
                 1 if dry_run else 0, now, now),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            active = _active_run(conn, project_id, trade_code)
            if active is None or not _run_matches_project_identity(active, identity):
                return ("tenant_unscoped", {})
            return ("active", dict(active))
        conn.commit()
        return ("created", dict(conn.execute(
            "SELECT * FROM extraction_runs WHERE id=?", (str(run_id),)
        ).fetchone()))


def get_run(project_id: UUID, run_id: UUID) -> dict[str, Any] | None:
    with get_connection() as conn:
        identity = _get_project_identity(conn, project_id)
        if identity is None:
            return None
        row = conn.execute(
            "SELECT * FROM extraction_runs WHERE id=? AND project_id=?",
            (str(run_id), str(project_id)),
        ).fetchone()
    return dict(row) if row and _run_matches_project_identity(row, identity) else None


def get_latest_run(project_id: UUID, trade_code: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        identity = _get_project_identity(conn, project_id)
        if identity is None:
            return None
        row = _latest_run(conn, project_id, trade_code)
    return dict(row) if row and _run_matches_project_identity(row, identity) else None


def list_runs(project_id: UUID, trade_code: str, *, limit: int, offset: int):
    with get_connection() as conn:
        identity = _get_project_identity(conn, project_id)
        if identity is None:
            return [], 0
        total = conn.execute(
            "SELECT COUNT(*) FROM extraction_runs WHERE project_id=? AND tenant_id=? AND company_id=? AND trade_code=?",
            (str(project_id), identity["tenant_id"], identity["company_id"], trade_code),
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM extraction_runs WHERE project_id=? AND tenant_id=? AND company_id=? AND trade_code=? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (str(project_id), identity["tenant_id"], identity["company_id"], trade_code, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows], int(total)


def update_run(run_id: UUID, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return None
    unknown_fields = sorted(set(fields) - _MUTABLE_RUN_FIELDS)
    if unknown_fields:
        identity_fields = sorted(set(unknown_fields) & _IMMUTABLE_RUN_IDENTITY_FIELDS)
        if identity_fields:
            raise ValueError(
                "extraction run identity fields are immutable: " + ",".join(identity_fields)
            )
        raise ValueError(
            "extraction run update contains unsupported fields: " + ",".join(unknown_fields)
        )
    immutable_fields = sorted(set(fields) & _IMMUTABLE_RUN_IDENTITY_FIELDS)
    if immutable_fields:
        raise ValueError(
            "extraction run identity fields are immutable: " + ",".join(immutable_fields)
        )
    for key in ("usage",):
        if key in fields and not isinstance(fields[key], (str, type(None))):
            fields[key] = _dumps(fields[key])
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE extraction_runs SET {cols} WHERE id=?",
            [*fields.values(), str(run_id)],
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM extraction_runs WHERE id=?", (str(run_id),)
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Routing decisions
# ---------------------------------------------------------------------------
def upsert_routing_decision(
    *, project_id: UUID, sheet_id: UUID, trade_code: str,
    extraction_run_id: UUID | None, eligibility: str, reason: str,
    automatic: bool, manual_override: str | None = None,
    reviewer_notes: str | None = None,
) -> dict[str, Any]:
    now = _now()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM sheet_routing_decisions WHERE project_id=? AND "
            "trade_code=? AND sheet_id=?",
            (str(project_id), trade_code, str(sheet_id)),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO sheet_routing_decisions (id, project_id, sheet_id,
                    trade_code, extraction_run_id, eligibility, reason, automatic,
                    manual_override, reviewer_notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), str(project_id), str(sheet_id), trade_code,
                 str(extraction_run_id) if extraction_run_id else None,
                 eligibility, reason, 1 if automatic else 0,
                 manual_override, reviewer_notes, now, now),
            )
        else:
            # Preserve a manual override unless this call sets one.
            new_override = manual_override if manual_override is not None else existing["manual_override"]
            conn.execute(
                """
                UPDATE sheet_routing_decisions SET eligibility=?, reason=?,
                    automatic=?, manual_override=?, reviewer_notes=?,
                    extraction_run_id=COALESCE(?, extraction_run_id), updated_at=?
                WHERE id=?
                """,
                (eligibility, reason, 1 if automatic else 0, new_override,
                 reviewer_notes if reviewer_notes is not None else existing["reviewer_notes"],
                 str(extraction_run_id) if extraction_run_id else None, now,
                 existing["id"]),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM sheet_routing_decisions WHERE project_id=? AND "
            "trade_code=? AND sheet_id=?",
            (str(project_id), trade_code, str(sheet_id)),
        ).fetchone()
    return dict(row)


def set_manual_override(
    project_id: UUID, trade_code: str, sheet_id: UUID, *,
    manual_override: str, reviewer_notes: str | None,
) -> dict[str, Any] | None:
    now = _now()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM sheet_routing_decisions WHERE project_id=? AND "
            "trade_code=? AND sheet_id=?",
            (str(project_id), trade_code, str(sheet_id)),
        ).fetchone()
        if existing is None:
            return None
        conn.execute(
            "UPDATE sheet_routing_decisions SET manual_override=?, reviewer_notes=?, "
            "automatic=0, updated_at=? WHERE id=?",
            (manual_override, reviewer_notes, now, existing["id"]),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM sheet_routing_decisions WHERE id=?", (existing["id"],)
        ).fetchone()
    return dict(row)


def list_routing(project_id: UUID, trade_code: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT r.*, s.pdf_page_number AS pdf_page_number "
            "FROM sheet_routing_decisions r JOIN sheets s ON s.id = r.sheet_id "
            "WHERE r.project_id=? AND r.trade_code=? ORDER BY s.pdf_page_number",
            (str(project_id), trade_code),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Scope items / evidence / derivations / conflicts / review events
# ---------------------------------------------------------------------------
SCOPE_COLUMNS = (
    "id", "project_id", "tenant_id", "company_id", "extraction_run_id",
    "trade_code", "trade_module_version", "trade_schema_version", "category_code",
    "description", "location", "specification_section", "assembly_designation",
    "material_or_substrate", "existing_condition", "proposed_work", "quantity",
    "unit", "quantity_basis", "raw_quantity_inputs", "extraction_confidence",
    "conflict_status", "review_status", "blocking_issues", "assumptions",
    "exclusions", "trade_data", "original_provider_candidate", "calculation_id",
    "calculation_version", "reviewer_notes", "created_at", "updated_at", "approved_at",
)
_JSON_SCOPE_COLUMNS = {
    "raw_quantity_inputs", "blocking_issues", "assumptions", "exclusions",
    "trade_data", "original_provider_candidate",
}
_IMMUTABLE_SCOPE_IDENTITY_FIELDS = frozenset(
    {"tenant_id", "company_id", "project_id", "extraction_run_id"}
)
_MUTABLE_SCOPE_FIELDS = frozenset(set(SCOPE_COLUMNS) - _IMMUTABLE_SCOPE_IDENTITY_FIELDS - {"id", "created_at"})


def _scope_identity_for_insert(
    conn: sqlite3.Connection, payload: dict[str, Any]
) -> dict[str, str]:
    try:
        project_id = UUID(str(payload.get("project_id")))
        extraction_run_id = UUID(str(payload.get("extraction_run_id")))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "project_id and extraction_run_id are required for tenant-scoped scope item creation"
        ) from exc

    identity = _get_project_identity(conn, project_id)
    if identity is None:
        raise ValueError("tenant_id and company_id are required for scope item creation")

    run = conn.execute(
        "SELECT id, project_id, tenant_id, company_id FROM extraction_runs WHERE id=?",
        (str(extraction_run_id),),
    ).fetchone()
    if run is None:
        raise ValueError("extraction_run_id must reference an existing tenant-scoped run")
    try:
        assert_same_tenant_project_access(
            identity,
            {
                "tenant_id": run["tenant_id"],
                "company_id": run["company_id"],
                "project_id": run["project_id"],
            },
        )
    except PermissionError as exc:
        raise ValueError("scope item extraction run identity must match project tenant") from exc

    if payload.get("tenant_id") is not None or payload.get("company_id") is not None:
        try:
            assert_same_tenant_project_access(
                identity,
                {
                    "tenant_id": payload.get("tenant_id"),
                    "company_id": payload.get("company_id"),
                    "project_id": payload.get("project_id"),
                },
            )
        except PermissionError as exc:
            raise ValueError("scope item tenant/company identity must match project") from exc
    return identity


def insert_scope_item(item: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    payload = {col: item.get(col) for col in SCOPE_COLUMNS}
    payload["created_at"] = now
    payload["updated_at"] = now
    with get_connection() as conn:
        identity = _scope_identity_for_insert(conn, payload)
        payload["tenant_id"] = identity["tenant_id"]
        payload["company_id"] = identity["company_id"]
        for col in _JSON_SCOPE_COLUMNS:
            payload[col] = _dumps(payload.get(col))
        if payload.get("quantity") is not None:
            payload["quantity"] = str(payload["quantity"])
        cols = ", ".join(SCOPE_COLUMNS)
        placeholders = ", ".join("?" for _ in SCOPE_COLUMNS)
        conn.execute(
            f"INSERT INTO scope_items ({cols}) VALUES ({placeholders})",
            [payload[c] for c in SCOPE_COLUMNS],
        )
        conn.commit()
    return get_scope_item_raw(UUID(payload["id"]))


def _row_to_scope_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for col in _JSON_SCOPE_COLUMNS:
        data[col] = _loads(data.get(col))
    return data


def get_scope_item_raw(item_id: UUID) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM scope_items WHERE id=?", (str(item_id),)
        ).fetchone()
    return _row_to_scope_dict(row) if row else None


def get_scope_item(project_id: UUID, item_id: UUID) -> dict[str, Any] | None:
    with get_connection() as conn:
        identity = _get_project_identity(conn, project_id)
        if identity is None:
            return None
        row = conn.execute(
            "SELECT * FROM scope_items WHERE id=? AND project_id=?",
            (str(item_id), str(project_id)),
        ).fetchone()
    return _row_to_scope_dict(row) if row and _run_matches_project_identity(row, identity) else None


def update_scope_item(item_id: UUID, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_scope_item_raw(item_id)
    unknown_fields = sorted(set(fields) - _MUTABLE_SCOPE_FIELDS)
    if unknown_fields:
        identity_fields = sorted(set(unknown_fields) & _IMMUTABLE_SCOPE_IDENTITY_FIELDS)
        if identity_fields:
            raise ValueError(
                "scope item identity fields are immutable: " + ",".join(identity_fields)
            )
        raise ValueError(
            "scope item update contains unsupported fields: " + ",".join(unknown_fields)
        )
    identity_fields = sorted(set(fields) & _IMMUTABLE_SCOPE_IDENTITY_FIELDS)
    if identity_fields:
        raise ValueError(
            "scope item identity fields are immutable: " + ",".join(identity_fields)
        )
    for col in list(fields):
        if col in _JSON_SCOPE_COLUMNS:
            fields[col] = _dumps(fields[col])
        elif col == "quantity" and fields[col] is not None:
            fields[col] = str(fields[col])
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE scope_items SET {cols} WHERE id=?",
            [*fields.values(), str(item_id)],
        )
        conn.commit()
    return get_scope_item_raw(item_id)


def list_scope_items(
    project_id: UUID, *, filters: dict[str, Any], limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    where = ["si.project_id = ?"]
    params: list[Any] = [str(project_id)]
    sheet_id = filters.get("sheet_id")
    if filters.get("trade_code"):
        where.append("si.trade_code = ?"); params.append(filters["trade_code"])
    if filters.get("extraction_run_id"):
        where.append("si.extraction_run_id = ?"); params.append(str(filters["extraction_run_id"]))
    if filters.get("category_code"):
        where.append("si.category_code = ?"); params.append(filters["category_code"])
    if filters.get("review_status"):
        where.append("si.review_status = ?"); params.append(filters["review_status"])
    if filters.get("missing_quantity"):
        where.append("si.quantity IS NULL")
    if filters.get("requires_review"):
        where.append("si.review_status IN ('pending','blocked')")
    if filters.get("conflict_severity"):
        where.append(
            "EXISTS (SELECT 1 FROM conflicts c WHERE c.scope_item_id=si.id "
            "AND c.severity=? AND c.resolution_status='open')"
        )
        params.append(filters["conflict_severity"])
    if sheet_id:
        where.append(
            "EXISTS (SELECT 1 FROM evidence_references e WHERE e.scope_item_id=si.id "
            "AND e.sheet_id=?)"
        )
        params.append(str(sheet_id))
    clause = " AND ".join(where)
    with get_connection() as conn:
        identity = _get_project_identity(conn, project_id)
        if identity is None:
            return [], 0
        clause = f"{clause} AND si.tenant_id = ? AND si.company_id = ?"
        params.extend([identity["tenant_id"], identity["company_id"]])
        total = conn.execute(
            f"SELECT COUNT(*) FROM scope_items si WHERE {clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT si.* FROM scope_items si WHERE {clause} "
            "ORDER BY si.created_at ASC, si.id ASC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [_row_to_scope_dict(r) for r in rows], int(total)


def _evidence_identity_for_insert(
    conn: sqlite3.Connection, ev: dict[str, Any]
) -> dict[str, str]:
    try:
        project_id = UUID(str(ev.get("project_id")))
        scope_item_id = UUID(str(ev.get("scope_item_id")))
        sheet_id = UUID(str(ev.get("sheet_id")))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "project_id, scope_item_id, and sheet_id are required for tenant-scoped evidence creation"
        ) from exc

    identity = _get_project_identity(conn, project_id)
    if identity is None:
        raise ValueError("tenant_id and company_id are required for evidence creation")

    scope_item = conn.execute(
        "SELECT id, project_id, tenant_id, company_id FROM scope_items WHERE id=?",
        (str(scope_item_id),),
    ).fetchone()
    if scope_item is None:
        raise ValueError("scope_item_id must reference an existing tenant-scoped scope item")
    sheet = conn.execute(
        "SELECT id, project_id, tenant_id, company_id FROM sheets WHERE id=?",
        (str(sheet_id),),
    ).fetchone()
    if sheet is None:
        raise ValueError("sheet_id must reference an existing tenant-scoped sheet")

    for label, row in (("scope item", scope_item), ("sheet", sheet)):
        try:
            assert_same_tenant_project_access(
                identity,
                {
                    "tenant_id": row["tenant_id"],
                    "company_id": row["company_id"],
                    "project_id": row["project_id"],
                },
            )
        except PermissionError as exc:
            raise ValueError(f"evidence {label} identity must match project tenant") from exc

    if ev.get("tenant_id") is not None or ev.get("company_id") is not None:
        try:
            assert_same_tenant_project_access(
                identity,
                {
                    "tenant_id": ev.get("tenant_id"),
                    "company_id": ev.get("company_id"),
                    "project_id": ev.get("project_id"),
                },
            )
        except PermissionError as exc:
            raise ValueError("evidence tenant/company identity must match project") from exc
    return identity


def _evidence_matches_scope_identity(
    ev: sqlite3.Row | dict[str, Any], scope_item: sqlite3.Row | dict[str, Any]
) -> bool:
    try:
        assert_same_tenant_project_access(
            {
                "tenant_id": scope_item["tenant_id"],
                "company_id": scope_item["company_id"],
                "project_id": scope_item["project_id"],
            },
            {
                "tenant_id": ev["tenant_id"],
                "company_id": ev["company_id"],
                "project_id": ev["project_id"],
            },
        )
    except (KeyError, PermissionError):
        return False
    return True


def insert_evidence(ev: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    record = dict(ev)
    with get_connection() as conn:
        identity = _evidence_identity_for_insert(conn, record)
        record["tenant_id"] = identity["tenant_id"]
        record["company_id"] = identity["company_id"]
        conn.execute(
            """
            INSERT INTO evidence_references (id, scope_item_id, project_id, tenant_id,
                company_id, sheet_id, pdf_page_number, verified_sheet_number,
                evidence_type, description, extracted_text_quote, text_block_coords,
                page_region_coords, source_artifact_ref, provider_confidence,
                requires_human_verification, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record["id"], record["scope_item_id"], record["project_id"],
             record["tenant_id"], record["company_id"], record["sheet_id"],
             record["pdf_page_number"], record["verified_sheet_number"],
             record["evidence_type"], record["description"],
             record.get("extracted_text_quote"), _dumps(record.get("text_block_coords")),
             _dumps(record.get("page_region_coords")), record.get("source_artifact_ref"),
             record.get("provider_confidence"),
             1 if record.get("requires_human_verification", True) else 0, now, now),
        )
        conn.commit()
    return record


def list_evidence(scope_item_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        scope_item = conn.execute(
            "SELECT id, project_id, tenant_id, company_id FROM scope_items WHERE id=?",
            (str(scope_item_id),),
        ).fetchone()
        if scope_item is None:
            return []
        try:
            scope_identity = build_tenant_project_context(
                tenant_id=scope_item["tenant_id"],
                company_id=scope_item["company_id"],
                project_id=scope_item["project_id"],
            )
        except PermissionError:
            return []
        rows = conn.execute(
            """
            SELECT e.*
            FROM evidence_references e
            JOIN sheets s ON s.id = e.sheet_id
            WHERE e.scope_item_id=?
              AND e.tenant_id=?
              AND e.company_id=?
              AND e.project_id=?
              AND s.project_id=e.project_id
              AND s.tenant_id=e.tenant_id
              AND s.company_id=e.company_id
            ORDER BY e.created_at
            """,
            (
                str(scope_item_id),
                scope_identity["tenant_id"],
                scope_identity["company_id"],
                scope_identity["project_id"],
            ),
        ).fetchall()
    out = []
    for r in rows:
        if not _evidence_matches_scope_identity(r, scope_item):
            continue
        d = dict(r)
        d["text_block_coords"] = _loads(d.get("text_block_coords"))
        d["page_region_coords"] = _loads(d.get("page_region_coords"))
        out.append(d)
    return out


def insert_quantity_derivation(d: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO quantity_derivations (id, scope_item_id, trade_code,
                formula_id, formula_version, inputs, output_value, output_unit,
                calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (d["id"], d["scope_item_id"], d["trade_code"], d["formula_id"],
             d["formula_version"], _dumps(d["inputs"]), str(d["output_value"]),
             d["output_unit"], d.get("calculated_at") or _now()),
        )
        conn.commit()
    return d


def get_latest_derivation(scope_item_id: UUID) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM quantity_derivations WHERE scope_item_id=? "
            "ORDER BY calculated_at DESC LIMIT 1",
            (str(scope_item_id),),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["inputs"] = _loads(d.get("inputs"))
    return d


def insert_conflict(c: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conflicts (id, scope_item_id, code, severity, description,
                competing_evidence, resolution_status, created_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (c["id"], c["scope_item_id"], c["code"], c["severity"], c["description"],
             _dumps(c.get("competing_evidence", [])),
             c.get("resolution_status", "open"), now, c.get("resolved_at")),
        )
        conn.commit()
    return c


def list_conflicts(scope_item_id: UUID, *, open_only: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM conflicts WHERE scope_item_id=?"
    params: list[Any] = [str(scope_item_id)]
    if open_only:
        query += " AND resolution_status='open'"
    query += " ORDER BY created_at"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["competing_evidence"] = _loads(d.get("competing_evidence")) or []
        out.append(d)
    return out


def delete_conflicts_for_item(scope_item_id: UUID) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM conflicts WHERE scope_item_id=?", (str(scope_item_id),))
        conn.commit()


def append_review_event(ev: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    record = {**ev, "id": ev.get("id") or str(uuid4()), "created_at": now}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO review_events (id, project_id, scope_item_id, trade_code,
                action, previous_state, new_state, reviewer_id, reviewer_notes,
                created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record["id"], record["project_id"], record["scope_item_id"],
             record["trade_code"], record["action"], record.get("previous_state"),
             record.get("new_state"), record.get("reviewer_id", "system"),
             record.get("reviewer_notes"), now),
        )
        conn.commit()
    return record


def list_review_events(scope_item_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM review_events WHERE scope_item_id=? ORDER BY created_at",
            (str(scope_item_id),),
        ).fetchall()
    return [dict(r) for r in rows]
