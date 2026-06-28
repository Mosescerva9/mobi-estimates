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

ACTIVE_RUN_STATES = ("queued", "running")


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
    """Atomically reserve an extraction run for a (project, trade).

    Outcomes: ``created``, ``active`` (idempotent), ``exists_completed``.
    """
    now = _now()
    with get_connection() as conn:
        if not dry_run:
            active = _active_run(conn, project_id, trade_code)
            if active is not None:
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
                return ("exists_completed", dict(latest))

        run_id = uuid4()
        attempt = _next_run_attempt(conn, project_id, trade_code)
        try:
            conn.execute(
                """
                INSERT INTO extraction_runs (id, project_id, trade_code, status,
                    provider, model_identifier, prompt_version,
                    provider_schema_version, trade_schema_version, attempt,
                    dry_run, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(run_id), str(project_id), trade_code, provider, model,
                 prompt_version, provider_schema_version, trade_schema_version,
                 attempt, 1 if dry_run else 0, now, now),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            active = _active_run(conn, project_id, trade_code)
            return ("active", dict(active)) if active else ("active", {})
        conn.commit()
        return ("created", dict(conn.execute(
            "SELECT * FROM extraction_runs WHERE id=?", (str(run_id),)
        ).fetchone()))


def get_run(project_id: UUID, run_id: UUID) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM extraction_runs WHERE id=? AND project_id=?",
            (str(run_id), str(project_id)),
        ).fetchone()
    return dict(row) if row else None


def get_latest_run(project_id: UUID, trade_code: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = _latest_run(conn, project_id, trade_code)
    return dict(row) if row else None


def list_runs(project_id: UUID, trade_code: str, *, limit: int, offset: int):
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM extraction_runs WHERE project_id=? AND trade_code=?",
            (str(project_id), trade_code),
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM extraction_runs WHERE project_id=? AND trade_code=? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (str(project_id), trade_code, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows], int(total)


def update_run(run_id: UUID, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return None
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
    "id", "project_id", "extraction_run_id", "trade_code", "trade_module_version",
    "trade_schema_version", "category_code", "description", "location",
    "specification_section", "assembly_designation", "material_or_substrate",
    "existing_condition", "proposed_work", "quantity", "unit", "quantity_basis",
    "raw_quantity_inputs", "extraction_confidence", "conflict_status",
    "review_status", "blocking_issues", "assumptions", "exclusions", "trade_data",
    "original_provider_candidate", "calculation_id", "calculation_version",
    "reviewer_notes", "created_at", "updated_at", "approved_at",
)
_JSON_SCOPE_COLUMNS = {
    "raw_quantity_inputs", "blocking_issues", "assumptions", "exclusions",
    "trade_data", "original_provider_candidate",
}


def insert_scope_item(item: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    payload = {col: item.get(col) for col in SCOPE_COLUMNS}
    payload["created_at"] = now
    payload["updated_at"] = now
    for col in _JSON_SCOPE_COLUMNS:
        payload[col] = _dumps(payload.get(col))
    if payload.get("quantity") is not None:
        payload["quantity"] = str(payload["quantity"])
    cols = ", ".join(SCOPE_COLUMNS)
    placeholders = ", ".join("?" for _ in SCOPE_COLUMNS)
    with get_connection() as conn:
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
        row = conn.execute(
            "SELECT * FROM scope_items WHERE id=? AND project_id=?",
            (str(item_id), str(project_id)),
        ).fetchone()
    return _row_to_scope_dict(row) if row else None


def update_scope_item(item_id: UUID, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_scope_item_raw(item_id)
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
        total = conn.execute(
            f"SELECT COUNT(*) FROM scope_items si WHERE {clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT si.* FROM scope_items si WHERE {clause} "
            "ORDER BY si.created_at ASC, si.id ASC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [_row_to_scope_dict(r) for r in rows], int(total)


def insert_evidence(ev: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO evidence_references (id, scope_item_id, project_id, sheet_id,
                pdf_page_number, verified_sheet_number, evidence_type, description,
                extracted_text_quote, text_block_coords, page_region_coords,
                source_artifact_ref, provider_confidence, requires_human_verification,
                created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ev["id"], ev["scope_item_id"], ev["project_id"], ev["sheet_id"],
             ev["pdf_page_number"], ev["verified_sheet_number"], ev["evidence_type"],
             ev["description"], ev.get("extracted_text_quote"),
             _dumps(ev.get("text_block_coords")), _dumps(ev.get("page_region_coords")),
             ev.get("source_artifact_ref"), ev.get("provider_confidence"),
             1 if ev.get("requires_human_verification", True) else 0, now, now),
        )
        conn.commit()
    return ev


def list_evidence(scope_item_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM evidence_references WHERE scope_item_id=? ORDER BY created_at",
            (str(scope_item_id),),
        ).fetchall()
    out = []
    for r in rows:
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
