"""Persistence helpers for OpenTakeoff worker job status records."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.takeoff.worker import OpenTakeoffJob, OpenTakeoffWorkerErrorCode, OpenTakeoffWorkerStatus

OPEN_TAKEOFF_WORKER_JOBS_TABLE = "opentakeoff_worker_jobs"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_worker_job_record(
    conn: sqlite3.Connection,
    job: OpenTakeoffJob,
    *,
    operation: str,
    requested_by: str | None,
    status: OpenTakeoffWorkerStatus = OpenTakeoffWorkerStatus.QUEUED,
) -> None:
    now = utc_now_iso()
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
) -> None:
    now = utc_now_iso()
    started_at = now if status == OpenTakeoffWorkerStatus.RUNNING else None
    completed_at = now if status in {OpenTakeoffWorkerStatus.COMPLETED, OpenTakeoffWorkerStatus.FAILED} else None
    cancelled_at = now if status == OpenTakeoffWorkerStatus.CANCELLED else None
    category = error_category.value if isinstance(error_category, OpenTakeoffWorkerErrorCode) else error_category
    conn.execute(
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
        WHERE job_id = ?
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
        ),
    )
    conn.commit()


def get_worker_job_record(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        f"SELECT * FROM {OPEN_TAKEOFF_WORKER_JOBS_TABLE} WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    return dict(row) if row else None
