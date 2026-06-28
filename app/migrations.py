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


MIGRATIONS: list[Migration] = [
    Migration(1, "projects", _0001_projects),
    Migration(2, "processing_jobs", _0002_processing_jobs),
    Migration(3, "sheets", _0003_sheets),
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
