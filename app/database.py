from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

from app.config import settings
from app.migrations import apply_migrations
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
    """Bring the database schema up to date via forward-only migrations.

    Safe and idempotent: it never drops or recreates existing data, and it
    upgrades an existing Phase 1 database in place.
    """
    with get_connection() as connection:
        apply_migrations(connection)


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


# ---------------------------------------------------------------------------
# Processing jobs
# ---------------------------------------------------------------------------
_ACTIVE_JOB_STATES = ("queued", "processing")


def _get_job(connection: sqlite3.Connection, job_id: UUID) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM processing_jobs WHERE id = ?", (str(job_id),)
    ).fetchone()
    return dict(row) if row is not None else None


def _get_active_job(
    connection: sqlite3.Connection, project_id: UUID
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM processing_jobs WHERE project_id = ? AND status IN (?, ?) "
        "ORDER BY created_at DESC LIMIT 1",
        (str(project_id), *_ACTIVE_JOB_STATES),
    ).fetchone()
    return dict(row) if row is not None else None


def _next_attempt(connection: sqlite3.Connection, project_id: UUID) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(attempt), 0) FROM processing_jobs WHERE project_id = ?",
        (str(project_id),),
    ).fetchone()
    return int(row[0]) + 1


def get_job(job_id: UUID) -> dict[str, Any] | None:
    with get_connection() as connection:
        return _get_job(connection, job_id)


def get_latest_job(project_id: UUID) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM processing_jobs WHERE project_id = ? "
            "ORDER BY created_at DESC, attempt DESC LIMIT 1",
            (str(project_id),),
        ).fetchone()
    return dict(row) if row is not None else None


def can_transition_to_queued(current: ProjectStatus) -> bool:
    from app.status_rules import can_transition

    return can_transition(current, ProjectStatus.QUEUED)


def claim_processing_slot(
    project_id: UUID, *, force: bool
) -> tuple[str, dict | None, dict | None]:
    """Atomically claim a processing slot for a project.

    Returns ``(outcome, job, project)`` where ``outcome`` is one of:

    * ``not_found``         - project does not exist
    * ``active``            - an active job already exists (idempotent; no new job)
    * ``already_processed`` - already ready_for_review and ``force`` not set
    * ``terminal``          - project is complete (cannot reprocess)
    * ``invalid_state``     - project status cannot transition to queued
    * ``created``           - a new queued job was created

    The partial unique index ``uq_jobs_active_per_project`` guarantees two
    concurrent callers cannot both create an active job.
    """
    with get_connection() as connection:
        project = _get_project(connection, project_id)
        if project is None:
            return ("not_found", None, None)

        current = ProjectStatus(project["status"])
        active = _get_active_job(connection, project_id)
        if active is not None:
            return ("active", active, project)

        if current == ProjectStatus.COMPLETE:
            return ("terminal", None, project)
        if current == ProjectStatus.READY_FOR_REVIEW and not force:
            return ("already_processed", None, project)
        if not can_transition_to_queued(current):
            return ("invalid_state", None, project)

        attempt = _next_attempt(connection, project_id)
        job_id = uuid4()
        timestamp = utc_now_iso()
        try:
            connection.execute(
                """
                INSERT INTO processing_jobs (
                    id, project_id, status, attempt, force,
                    created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    str(job_id),
                    str(project_id),
                    attempt,
                    1 if force else 0,
                    timestamp,
                    timestamp,
                ),
            )
        except sqlite3.IntegrityError:
            # Lost a race against a concurrent claim; return the active job.
            connection.rollback()
            active = _get_active_job(connection, project_id)
            return ("active", active, project)

        connection.execute(
            "UPDATE projects SET status = ?, error_message = NULL, updated_at = ? "
            "WHERE id = ?",
            (ProjectStatus.QUEUED.value, timestamp, str(project_id)),
        )
        connection.commit()
        return ("created", _get_job(connection, job_id), project)


def update_job(job_id: UUID, **fields: Any) -> dict[str, Any] | None:
    """Update arbitrary columns on a processing job (always bumps updated_at)."""
    if not fields:
        return get_job(job_id)
    fields["updated_at"] = utc_now_iso()
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [str(job_id)]
    with get_connection() as connection:
        connection.execute(
            f"UPDATE processing_jobs SET {columns} WHERE id = ?", values
        )
        connection.commit()
        return _get_job(connection, job_id)


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------
SHEET_COLUMNS = (
    "id", "project_id", "job_id", "pdf_page_number", "page_index",
    "detected_sheet_number", "verified_sheet_number", "detected_sheet_title",
    "verified_sheet_title", "detection_confidence", "requires_review",
    "requires_ocr", "text_char_count", "page_width_points", "page_height_points",
    "rotation", "page_sha256", "duplicate_of_sheet_id", "full_image_path",
    "thumbnail_path", "text_path", "processing_status", "processing_error",
    "review_status", "review_notes", "verified_at", "created_at", "updated_at",
)


def insert_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    timestamp = utc_now_iso()
    payload = {key: sheet.get(key) for key in SHEET_COLUMNS}
    payload["created_at"] = timestamp
    payload["updated_at"] = timestamp
    placeholders = ", ".join("?" for _ in SHEET_COLUMNS)
    columns = ", ".join(SHEET_COLUMNS)
    with get_connection() as connection:
        connection.execute(
            f"INSERT INTO sheets ({columns}) VALUES ({placeholders})",
            [payload[key] for key in SHEET_COLUMNS],
        )
        connection.commit()
        return _get_sheet(connection, UUID(payload["id"]))


def _get_sheet(
    connection: sqlite3.Connection, sheet_id: UUID
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM sheets WHERE id = ?", (str(sheet_id),)
    ).fetchone()
    return dict(row) if row is not None else None


def get_sheet(project_id: UUID, sheet_id: UUID) -> dict[str, Any] | None:
    """Fetch a sheet, validating it belongs to the given project."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM sheets WHERE id = ? AND project_id = ?",
            (str(sheet_id), str(project_id)),
        ).fetchone()
    return dict(row) if row is not None else None


def list_sheets(
    project_id: UUID, *, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    """Return a page of sheets (ordered by PDF page number) and the total count."""
    with get_connection() as connection:
        total = connection.execute(
            "SELECT COUNT(*) FROM sheets WHERE project_id = ?", (str(project_id),)
        ).fetchone()[0]
        rows = connection.execute(
            "SELECT * FROM sheets WHERE project_id = ? "
            "ORDER BY pdf_page_number ASC LIMIT ? OFFSET ?",
            (str(project_id), limit, offset),
        ).fetchall()
    return [dict(row) for row in rows], int(total)


def find_duplicate_page(
    connection: sqlite3.Connection, project_id: UUID, page_sha256: str
) -> str | None:
    """Return the id of an earlier sheet in this project with the same checksum."""
    row = connection.execute(
        "SELECT id FROM sheets WHERE project_id = ? AND page_sha256 = ? "
        "ORDER BY pdf_page_number ASC LIMIT 1",
        (str(project_id), page_sha256),
    ).fetchone()
    return row[0] if row is not None else None


def delete_sheets_for_project(project_id: UUID) -> int:
    """Delete all sheet rows for a project (used by forced reprocessing)."""
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM sheets WHERE project_id = ?", (str(project_id),)
        )
        connection.commit()
        return cursor.rowcount


def count_sheets(project_id: UUID) -> int:
    with get_connection() as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM sheets WHERE project_id = ?",
                (str(project_id),),
            ).fetchone()[0]
        )


def update_sheet_verification(
    project_id: UUID,
    sheet_id: UUID,
    *,
    verified_sheet_number: str | None,
    verified_sheet_title: str | None,
    review_notes: str | None,
    review_status: str,
    requires_review: bool,
) -> dict[str, Any] | None:
    """Apply a human verification to a sheet without destroying detected values."""
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM sheets WHERE id = ? AND project_id = ?",
            (str(sheet_id), str(project_id)),
        ).fetchone()
        if existing is None:
            return None
        now = utc_now_iso()
        connection.execute(
            """
            UPDATE sheets SET
                verified_sheet_number = ?,
                verified_sheet_title = ?,
                review_notes = ?,
                review_status = ?,
                requires_review = ?,
                verified_at = ?,
                updated_at = ?
            WHERE id = ? AND project_id = ?
            """,
            (
                verified_sheet_number,
                verified_sheet_title,
                review_notes,
                review_status,
                1 if requires_review else 0,
                now,
                now,
                str(sheet_id),
                str(project_id),
            ),
        )
        connection.commit()
        return _get_sheet(connection, sheet_id)
