"""Forward-only SQLite migrations for the lean Mobi MVP.

A tiny, dependency-free migration runner. Each migration has an integer version
and a callable that receives an open ``sqlite3.Connection``. Applied versions are
recorded in a ``schema_migrations`` table, so migrations run exactly once and in
order. Migrations are written defensively (``IF NOT EXISTS`` / guarded
``ALTER TABLE``) so they are safe to run against:

* a brand-new empty database, and
* an existing Phase 1 database that already contains the ``projects`` table.

Nothing here ever drops or recreates existing data.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, NamedTuple


class Migration(NamedTuple):
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


# --- Individual migrations -------------------------------------------------
def _0001_projects(conn: sqlite3.Connection) -> None:
    """Phase 1 baseline: the projects table (no-op on existing Phase 1 DBs)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            contractor_name TEXT,
            original_file_name TEXT,
            stored_file_path TEXT NOT NULL,
            status TEXT NOT NULL,
            page_count INTEGER NOT NULL DEFAULT 0,
            file_sha256 TEXT,
            file_size_bytes INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_message TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_file_sha256 "
        "ON projects (file_sha256)"
    )


def _0002_processing_jobs(conn: sqlite3.Connection) -> None:
    """Phase 2: processing jobs table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 1,
            force INTEGER NOT NULL DEFAULT 0,
            pages_discovered INTEGER NOT NULL DEFAULT 0,
            pages_completed INTEGER NOT NULL DEFAULT 0,
            pages_failed INTEGER NOT NULL DEFAULT 0,
            pages_requiring_ocr INTEGER NOT NULL DEFAULT 0,
            pages_requiring_review INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER,
            error_code TEXT,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_project ON processing_jobs (project_id)"
    )
    # At most one active (queued/processing) job per project. This partial unique
    # index is the database-level guard against concurrent duplicate processing.
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_per_project
        ON processing_jobs (project_id)
        WHERE status IN ('queued', 'processing')
        """
    )


def _0003_sheets(conn: sqlite3.Connection) -> None:
    """Phase 2: per-page sheet records."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sheets (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            job_id TEXT,
            pdf_page_number INTEGER NOT NULL,
            page_index INTEGER NOT NULL,
            detected_sheet_number TEXT,
            verified_sheet_number TEXT,
            detected_sheet_title TEXT,
            verified_sheet_title TEXT,
            detection_confidence REAL,
            requires_review INTEGER NOT NULL DEFAULT 1,
            requires_ocr INTEGER NOT NULL DEFAULT 0,
            text_char_count INTEGER NOT NULL DEFAULT 0,
            page_width_points REAL,
            page_height_points REAL,
            rotation INTEGER NOT NULL DEFAULT 0,
            page_sha256 TEXT,
            duplicate_of_sheet_id TEXT,
            full_image_path TEXT,
            thumbnail_path TEXT,
            text_path TEXT,
            processing_status TEXT NOT NULL DEFAULT 'pending',
            processing_error TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending',
            review_notes TEXT,
            verified_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (job_id) REFERENCES processing_jobs (id),
            FOREIGN KEY (duplicate_of_sheet_id) REFERENCES sheets (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sheets_project ON sheets (project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sheets_project_page "
        "ON sheets (project_id, pdf_page_number)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sheets_page_sha256 ON sheets (page_sha256)"
    )
    # Each PDF page maps to exactly one sheet row per project.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sheets_project_page "
        "ON sheets (project_id, pdf_page_number)"
    )


def _0004_trade_definitions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_definitions (
            trade_code TEXT PRIMARY KEY,
            trade_name TEXT NOT NULL,
            module_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            metadata TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _0005_extraction_runs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extraction_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            status TEXT NOT NULL,
            provider TEXT NOT NULL,
            model_identifier TEXT,
            prompt_version TEXT,
            provider_schema_version TEXT,
            trade_schema_version TEXT,
            attempt INTEGER NOT NULL DEFAULT 1,
            started_at TEXT,
            completed_at TEXT,
            error_code TEXT,
            error_message TEXT,
            input_sheet_count INTEGER NOT NULL DEFAULT 0,
            processed_sheet_count INTEGER NOT NULL DEFAULT 0,
            blocked_sheet_count INTEGER NOT NULL DEFAULT 0,
            failed_sheet_count INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            usage TEXT,
            estimated_cost TEXT,
            dry_run INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_project_trade "
        "ON extraction_runs (project_id, trade_code)"
    )
    # At most one active run per (project, trade) when not a dry run.
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_active_per_project_trade
        ON extraction_runs (project_id, trade_code)
        WHERE status IN ('queued', 'running') AND dry_run = 0
        """
    )


def _0006_sheet_routing_decisions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sheet_routing_decisions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            extraction_run_id TEXT,
            eligibility TEXT NOT NULL,
            reason TEXT NOT NULL,
            automatic INTEGER NOT NULL DEFAULT 1,
            manual_override TEXT,
            reviewer_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (sheet_id) REFERENCES sheets (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_routing_project_trade "
        "ON sheet_routing_decisions (project_id, trade_code)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_routing_project_trade_sheet "
        "ON sheet_routing_decisions (project_id, trade_code, sheet_id)"
    )


def _0007_scope_items(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scope_items (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            extraction_run_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            trade_module_version TEXT NOT NULL,
            trade_schema_version TEXT NOT NULL,
            category_code TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT,
            specification_section TEXT,
            assembly_designation TEXT,
            material_or_substrate TEXT,
            existing_condition TEXT,
            proposed_work TEXT,
            quantity TEXT,
            unit TEXT,
            quantity_basis TEXT NOT NULL,
            raw_quantity_inputs TEXT,
            extraction_confidence REAL,
            conflict_status TEXT NOT NULL DEFAULT 'none',
            review_status TEXT NOT NULL DEFAULT 'pending',
            blocking_issues TEXT,
            assumptions TEXT,
            exclusions TEXT,
            trade_data TEXT,
            original_provider_candidate TEXT,
            calculation_id TEXT,
            calculation_version TEXT,
            reviewer_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            approved_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (extraction_run_id) REFERENCES extraction_runs (id)
        )
        """
    )
    for column in ("project_id", "extraction_run_id"):
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_scope_items_{column} "
            f"ON scope_items ({column})"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scope_items_project_trade "
        "ON scope_items (project_id, trade_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scope_items_review "
        "ON scope_items (project_id, review_status)"
    )


def _0008_evidence_references(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_references (
            id TEXT PRIMARY KEY,
            scope_item_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            pdf_page_number INTEGER NOT NULL,
            verified_sheet_number TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            description TEXT NOT NULL,
            extracted_text_quote TEXT,
            text_block_coords TEXT,
            page_region_coords TEXT,
            source_artifact_ref TEXT,
            provider_confidence REAL,
            requires_human_verification INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id),
            FOREIGN KEY (sheet_id) REFERENCES sheets (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_scope_item "
        "ON evidence_references (scope_item_id)"
    )


def _0009_quantity_derivations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quantity_derivations (
            id TEXT PRIMARY KEY,
            scope_item_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            formula_id TEXT NOT NULL,
            formula_version TEXT NOT NULL,
            inputs TEXT NOT NULL,
            output_value TEXT NOT NULL,
            output_unit TEXT NOT NULL,
            calculated_at TEXT NOT NULL,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_derivations_scope_item "
        "ON quantity_derivations (scope_item_id)"
    )


def _0010_conflicts(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conflicts (
            id TEXT PRIMARY KEY,
            scope_item_id TEXT NOT NULL,
            code TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT NOT NULL,
            competing_evidence TEXT,
            resolution_status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conflicts_scope_item "
        "ON conflicts (scope_item_id)"
    )


def _0011_review_events(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_events (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            scope_item_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            action TEXT NOT NULL,
            previous_state TEXT,
            new_state TEXT,
            reviewer_id TEXT NOT NULL DEFAULT 'system',
            reviewer_notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_events_scope_item "
        "ON review_events (scope_item_id)"
    )


MIGRATIONS: list[Migration] = [
    Migration(1, "projects", _0001_projects),
    Migration(2, "processing_jobs", _0002_processing_jobs),
    Migration(3, "sheets", _0003_sheets),
    Migration(4, "trade_definitions", _0004_trade_definitions),
    Migration(5, "extraction_runs", _0005_extraction_runs),
    Migration(6, "sheet_routing_decisions", _0006_sheet_routing_decisions),
    Migration(7, "scope_items", _0007_scope_items),
    Migration(8, "evidence_references", _0008_evidence_references),
    Migration(9, "quantity_derivations", _0009_quantity_derivations),
    Migration(10, "conflicts", _0010_conflicts),
    Migration(11, "review_events", _0011_review_events),
]


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_migrations_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply all pending migrations in order. Returns the versions applied."""
    _ensure_migrations_table(conn)
    applied: list[int] = []
    version = current_version(conn)
    for migration in sorted(MIGRATIONS, key=lambda m: m.version):
        if migration.version <= version:
            continue
        migration.apply(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) "
            "VALUES (?, ?, ?)",
            (
                migration.version,
                migration.name,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        applied.append(migration.version)
    return applied
