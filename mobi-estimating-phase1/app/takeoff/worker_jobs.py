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

# Forward-only worker-job status machine. The deployable worker API drives the
# richer lifecycle (queued -> document_loaded -> awaiting_scale_confirmation ->
# awaiting_geometry -> running_measurement -> awaiting_review -> completed) while
# the legacy in-process values (running, awaiting_geometry_confirmation) remain a
# valid superset so v39 rows and older callers still validate. Terminal states
# (completed/failed/cancelled) can never transition further, so a timed-out or
# crashed job can never be marked completed.
ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    OpenTakeoffWorkerStatus.QUEUED.value: {
        OpenTakeoffWorkerStatus.STARTING.value,
        OpenTakeoffWorkerStatus.DOCUMENT_LOADED.value,
        OpenTakeoffWorkerStatus.RUNNING.value,
        OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
        OpenTakeoffWorkerStatus.FAILED.value,
    },
    OpenTakeoffWorkerStatus.STARTING.value: {
        OpenTakeoffWorkerStatus.DOCUMENT_LOADED.value,
        OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.DOCUMENT_LOADED.value: {
        OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION.value,
        OpenTakeoffWorkerStatus.AWAITING_GEOMETRY.value,
        OpenTakeoffWorkerStatus.RUNNING.value,
        OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.RUNNING.value: {
        OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION.value,
        OpenTakeoffWorkerStatus.AWAITING_GEOMETRY.value,
        OpenTakeoffWorkerStatus.AWAITING_GEOMETRY_CONFIRMATION.value,
        OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT.value,
        OpenTakeoffWorkerStatus.AWAITING_REVIEW.value,
        OpenTakeoffWorkerStatus.COMPLETED.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION.value: {
        OpenTakeoffWorkerStatus.AWAITING_GEOMETRY.value,
        OpenTakeoffWorkerStatus.RUNNING.value,
        OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.AWAITING_GEOMETRY.value: {
        OpenTakeoffWorkerStatus.RUNNING.value,
        OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.AWAITING_GEOMETRY_CONFIRMATION.value: {
        OpenTakeoffWorkerStatus.RUNNING.value,
        OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT.value: {
        OpenTakeoffWorkerStatus.AWAITING_REVIEW.value,
        OpenTakeoffWorkerStatus.COMPLETED.value,
        OpenTakeoffWorkerStatus.FAILED.value,
        OpenTakeoffWorkerStatus.CANCELLED.value,
    },
    OpenTakeoffWorkerStatus.AWAITING_REVIEW.value: {
        OpenTakeoffWorkerStatus.COMPLETED.value,
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
    trade: str | None = None,
    scope_category: str | None = None,
    default_description: str | None = None,
    create_condition: str | None = None,
    attempt_number: int = 1,
    parent_job_id: str | None = None,
    root_job_id: str | None = None,
) -> dict[str, Any]:
    """Create (or idempotently return) a worker job row.

    ``trade``/``scope_category``/``default_description``/``create_condition`` are
    the immutable create parameters persisted so a fresh service instance can
    reconstruct the normalize options without any process-local state. The
    lineage columns (``attempt_number``/``parent_job_id``/``root_job_id``) carry
    durable retry lineage; a first attempt is number 1 with itself as root.
    """
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
                artifact_ids, evidence_ids, attempt_count, created_at, updated_at,
                trade, scope_category, default_description, create_condition,
                attempt_number, parent_job_id, root_job_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                trade,
                scope_category,
                default_description,
                create_condition,
                attempt_number,
                parent_job_id,
                root_job_id or str(job.job_id),
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


def set_worker_job_scale(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    sheet_id: str,
    sheet_key: str,
    page_number: int,
    scale_source: str,
    scale_label: str,
    units_per_px: float | None,
    confirmed_by: str,
) -> None:
    """Persist the confirmed scale onto the job row (written once at confirm-scale).

    This is the durable record of scale confirmation so a measurement request
    handled by a different instance can reconstruct the confirmed scale instead
    of relying on process-local state.
    """
    conn.execute(
        f"""
        UPDATE {OPEN_TAKEOFF_WORKER_JOBS_TABLE}
        SET scale_sheet_id = ?,
            scale_sheet_key = ?,
            scale_page_number = ?,
            scale_source = ?,
            scale_label = ?,
            scale_units_per_px = ?,
            scale_confirmed_by = ?,
            scale_confirmed_at = ?,
            updated_at = ?
        WHERE job_id = ?
        """,
        (
            sheet_id,
            sheet_key,
            page_number,
            scale_source,
            scale_label,
            units_per_px,
            confirmed_by,
            utc_now_iso(),
            utc_now_iso(),
            job_id,
        ),
    )
    conn.commit()


WORKER_JOB_ARTIFACTS_TABLE = "opentakeoff_worker_job_artifacts"


def insert_worker_job_artifact(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    job_id: str,
    tenant_id: str,
    company_id: str,
    project_id: str,
    artifact_type: str,
    sha256: str,
    bytes_len: int,
    storage_key: str,
) -> None:
    """Persist one artifact record for a worker job (tenant/company scoped)."""
    conn.execute(
        f"""
        INSERT INTO {WORKER_JOB_ARTIFACTS_TABLE} (
            artifact_id, job_id, tenant_id, company_id, project_id,
            artifact_type, sha256, bytes, storage_key, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            job_id,
            tenant_id,
            company_id,
            project_id,
            artifact_type,
            sha256,
            bytes_len,
            storage_key,
            utc_now_iso(),
        ),
    )


def list_worker_job_artifacts(
    conn: sqlite3.Connection, *, job_id: str, tenant_id: str, company_id: str
) -> list[dict[str, Any]]:
    """List a job's artifact records within one tenant/company scope, fail closed.

    Never returns a row whose tenant/company do not match the caller scope; the
    server-only ``storage_key`` is included here for the service to strip before
    returning to the API caller.
    """
    if not str(tenant_id).strip() or not str(company_id).strip():
        raise ValueError("tenant_id and company_id are required to list artifacts")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""
        SELECT * FROM {WORKER_JOB_ARTIFACTS_TABLE}
        WHERE job_id = ? AND tenant_id = ? AND company_id = ?
        ORDER BY created_at, artifact_id
        """,
        (job_id, str(tenant_id), str(company_id)),
    ).fetchall()
    return [dict(row) for row in rows]


def get_worker_job_retry_child(
    conn: sqlite3.Connection, parent_job_id: str
) -> dict[str, Any] | None:
    """Return the (single) retry child of a job, if one has been created."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        f"SELECT * FROM {OPEN_TAKEOFF_WORKER_JOBS_TABLE} "
        "WHERE parent_job_id = ? ORDER BY created_at LIMIT 1",
        (parent_job_id,),
    ).fetchone()
    return _row_to_dict(row)


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
    _RUNNING_STATES = {
        OpenTakeoffWorkerStatus.STARTING,
        OpenTakeoffWorkerStatus.RUNNING,
        OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT,
    }
    started_at = now if status in _RUNNING_STATES else None
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
