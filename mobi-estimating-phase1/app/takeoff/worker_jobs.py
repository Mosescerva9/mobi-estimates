"""Persistence helpers for OpenTakeoff worker job status records."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.takeoff.worker import OpenTakeoffJob, OpenTakeoffWorkerErrorCode, OpenTakeoffWorkerStatus

OPEN_TAKEOFF_WORKER_JOBS_TABLE = "opentakeoff_worker_jobs"

TERMINAL_STATUSES = {
    OpenTakeoffWorkerStatus.COMPLETED.value,
    OpenTakeoffWorkerStatus.FAILED.value,
    OpenTakeoffWorkerStatus.CANCELLED.value,
}

ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    OpenTakeoffWorkerStatus.QUEUED.value: {
        OpenTakeoffWorkerStatus.RUNNING.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
        OpenTakeoffWorkerStatus.FAILED.value,
    },
    OpenTakeoffWorkerStatus.RUNNING.value: {
        OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION.value,
        OpenTakeoffWorkerStatus.AWAITING_GEOMETRY_CONFIRMATION.value,
        OpenTakeoffWorkerStatus.COMPLETED.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION.value: {
        OpenTakeoffWorkerStatus.RUNNING.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.AWAITING_GEOMETRY_CONFIRMATION.value: {
        OpenTakeoffWorkerStatus.RUNNING.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def get_worker_job_record(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        f"SELECT * FROM {OPEN_TAKEOFF_WORKER_JOBS_TABLE} WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    return _row_to_dict(row)


def get_worker_job_record_by_idempotency(conn: sqlite3.Connection, idempotency_key: str) -> dict[str, Any] | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        f"SELECT * FROM {OPEN_TAKEOFF_WORKER_JOBS_TABLE} WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    return _row_to_dict(row)


def create_worker_job_record(
    conn: sqlite3.Connection,
    job: OpenTakeoffJob,
    *,
    operation: str,
    requested_by: str | None,
    status: OpenTakeoffWorkerStatus = OpenTakeoffWorkerStatus.QUEUED,
) -> dict[str, Any]:
    existing = get_worker_job_record_by_idempotency(conn, job.idempotency_key)
    if existing:
        return existing
    now = utc_now_iso()
    try:
        conn.execute(
            f"""
            INSERT INTO {OPEN_TAKEOFF_WORKER_JOBS_TABLE} (
                job_id, tenant_id, company_id, project_id, document_id, provider,
                engine_version, operation, idempotency_key, status, requested_by,
                artifact_ids, evidence_ids, attempt_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(job.job_id),
                str(job.document.tenant_id),
                str(job.document.company_id),
                str(job.document.project_id),
                str(job.document.document_id),
                "open_takeoff",
                job.engine_version,
                operation,
                job.idempotency_key,
                status.value,
                requested_by,
                "[]",
                "[]",
                0,
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = get_worker_job_record_by_idempotency(conn, job.idempotency_key)
        if existing:
            return existing
        raise
    created = get_worker_job_record(conn, str(job.job_id))
    assert created is not None
    return created


def _validate_transition(current: str, target: str) -> None:
    if current == target:
        return
    if current in TERMINAL_STATUSES:
        raise ValueError(f"invalid_worker_job_transition:{current}->{target}")
    if target not in ALLOWED_STATUS_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid_worker_job_transition:{current}->{target}")


def update_worker_job_status(
    conn: sqlite3.Connection,
    job: OpenTakeoffJob,
    *,
    status: OpenTakeoffWorkerStatus,
    error_category: OpenTakeoffWorkerErrorCode | str | None = None,
    safe_error_message: str | None = None,
    artifact_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    attempt_count: int | None = None,
) -> dict[str, Any]:
    current = get_worker_job_record(conn, str(job.job_id))
    if current is None:
        raise ValueError("worker_job_not_found")
    _validate_transition(str(current["status"]), status.value)
    now = utc_now_iso()
    started_at = now if status == OpenTakeoffWorkerStatus.RUNNING else None
    completed_at = now if status in {OpenTakeoffWorkerStatus.COMPLETED, OpenTakeoffWorkerStatus.FAILED} else None
    cancelled_at = now if status == OpenTakeoffWorkerStatus.CANCELLED else None
    category = error_category.value if isinstance(error_category, OpenTakeoffWorkerErrorCode) else error_category
    cursor = conn.execute(
        f"""
        UPDATE {OPEN_TAKEOFF_WORKER_JOBS_TABLE}
        SET status = ?,
            started_at = COALESCE(started_at, ?),
            completed_at = COALESCE(completed_at, ?),
            cancelled_at = COALESCE(cancelled_at, ?),
            error_category = COALESCE(?, error_category),
            safe_error_message = COALESCE(?, safe_error_message),
            artifact_ids = COALESCE(?, artifact_ids),
            evidence_ids = COALESCE(?, evidence_ids),
            attempt_count = COALESCE(?, attempt_count),
            updated_at = ?
        WHERE job_id = ? AND status = ?
        """,
        (
            status.value,
            started_at,
            completed_at,
            cancelled_at,
            category,
            safe_error_message,
            json.dumps(artifact_ids) if artifact_ids is not None else None,
            json.dumps(evidence_ids) if evidence_ids is not None else None,
            attempt_count,
            now,
            str(job.job_id),
            current["status"],
        ),
    )
    if cursor.rowcount != 1:
        raise ValueError("worker_job_concurrent_status_update")
    conn.commit()
    updated = get_worker_job_record(conn, str(job.job_id))
    assert updated is not None
    return updated
