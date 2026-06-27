from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

from app.config import settings
from app.schemas import ProjectStatus
from app.status_rules import assert_transition


def _db_path() -> Path:
    return settings.db_path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a configured SQLite connection that is always closed afterwards.

    Using ``contextlib.closing`` is important: a bare ``with sqlite3.connect(...)``
    only manages the transaction and leaks the underlying connection handle.
    """
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    with closing(connection):
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        yield connection


def init_db() -> None:
    """Create the database schema if it does not already exist (idempotent)."""
    with get_connection() as connection:
        connection.execute(
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
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_file_sha256 "
            "ON projects (file_sha256)"
        )
        connection.commit()


def check_health() -> bool:
    """Lightweight readiness probe: confirm the database is reachable."""
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def create_project(
    *,
    project_id: UUID,
    name: str,
    contractor_name: str | None,
    original_file_name: str,
    stored_file_path: str,
    status: str,
    page_count: int,
    file_sha256: str,
    file_size_bytes: int,
) -> dict[str, Any]:
    timestamp = utc_now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, name, contractor_name, original_file_name, stored_file_path,
                status, page_count, file_sha256, file_size_bytes,
                created_at, updated_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                str(project_id),
                name,
                contractor_name,
                original_file_name,
                stored_file_path,
                status,
                page_count,
                file_sha256,
                file_size_bytes,
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
        return _get_project(connection, project_id)


def get_project(project_id: UUID) -> dict[str, Any] | None:
    with get_connection() as connection:
        return _get_project(connection, project_id)


def _get_project(
    connection: sqlite3.Connection, project_id: UUID
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM projects WHERE id = ?", (str(project_id),)
    ).fetchone()
    return dict(row) if row is not None else None


def get_project_by_sha256(file_sha256: str) -> dict[str, Any] | None:
    """Return the first existing project that stored an identical file, if any."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM projects WHERE file_sha256 = ? ORDER BY created_at LIMIT 1",
            (file_sha256,),
        ).fetchone()
    return dict(row) if row is not None else None


def update_project_status(
    project_id: UUID,
    new_status: ProjectStatus,
    *,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    """Transition a project to ``new_status`` enforcing the lifecycle rules.

    Returns the updated row, or ``None`` if the project does not exist. Raises
    :class:`app.status_rules.InvalidStatusTransition` for disallowed transitions.
    """
    with get_connection() as connection:
        current = _get_project(connection, project_id)
        if current is None:
            return None
        assert_transition(ProjectStatus(current["status"]), new_status)
        connection.execute(
            "UPDATE projects SET status = ?, error_message = ?, updated_at = ? "
            "WHERE id = ?",
            (
                new_status.value,
                error_message,
                utc_now_iso(),
                str(project_id),
            ),
        )
        connection.commit()
        return _get_project(connection, project_id)
