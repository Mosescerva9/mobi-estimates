"""Deployable internal OpenTakeoff worker API service layer.

This module is the safe server-side orchestration for the VPS-side OpenTakeoff
worker API. It sits between the authenticated Mobi worker API router and the
real OpenTakeoff MCP subprocess runtime:

* It resolves a tenant-scoped project *document* from the database and
  tenant-scoped storage — it never accepts a client-supplied filesystem path.
* It enforces staff actor roles (estimator/reviewer/admin) and denies customer
  roles for measurement operations.
* It drives the actual :class:`OpenTakeoffMCPClient` runtime, persists measured
  canonical evidence with ``review_status=pending``, and moves the job to
  ``awaiting_review`` — it never marks anything customer-ready.
* It writes tenant/company/project-scoped artifacts (export JSON, canonical
  evidence JSON, worker metadata JSON, and a ``marked_region_metadata`` record)
  and returns artifact identifiers with ``signed_url``/``expires_at`` of
  ``None`` — never a local filesystem path.

The browser/portal only ever submits IDs and geometry; identity and security are
derived from authenticated headers and server-resolved rows, never trusted from
the JSON body.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from app import database
from app.services import storage
from app.takeoff.evidence import CANONICAL_EVIDENCE_SCHEMA_VERSION
from app.takeoff.mcp_runtime import (
    OPEN_TAKEOFF_MCP_PACKAGE,
    OPEN_TAKEOFF_MCP_VERSION,
    OpenTakeoffMCPClient,
    OpenTakeoffRuntimeConfig,
    OpenTakeoffRuntimeError,
)
from app.takeoff.opentakeoff import OpenTakeoffNormalizeOptions
from app.takeoff.providers import TakeoffContext
from app.takeoff.store import insert_canonical_evidence
from app.takeoff.worker import (
    OpenTakeoffJob,
    OpenTakeoffScaleConfirmation,
    OpenTakeoffWorkerErrorCode,
    OpenTakeoffWorkerService,
    OpenTakeoffWorkerStatus,
    ResolvedProjectDocument,
    sha256_file,
)
from app.takeoff.worker_jobs import (
    create_worker_job_record,
    get_worker_job_record,
    get_worker_job_record_by_idempotency,
    update_worker_job_status,
)
from app.tenant_boundary import (
    assert_request_matches_project_tenant,
    assert_same_tenant_project_access,
    build_tenant_project_context,
)

# Staff actor roles allowed to drive the internal worker API. Customer roles are
# explicitly *not* here and are denied for every measurement operation.
STAFF_ACTOR_ROLES: frozenset[str] = frozenset({"estimator", "reviewer", "admin"})

# The engine/extractor version stamped onto canonical evidence and metadata.
WORKER_API_ENGINE_VERSION = "mobi-opentakeoff-worker-api-v1"

# Supported worker-API measurement operations.
LINE_OPERATION = "measure_line"
POLYGON_OPERATION = "measure_polygon"


class WorkerApiError(Exception):
    """A structured, HTTP-mappable worker API failure.

    ``code`` is a stable machine-readable slug, ``http_status`` maps to the HTTP
    response, and ``message`` is a bounded, non-sensitive description (no raw
    document content or local paths).
    """

    def __init__(self, code: str, http_status: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message


@dataclass(frozen=True)
class WorkerActor:
    """An authenticated staff actor derived from request headers."""

    role: str
    actor_id: str


def require_staff_actor(role: str | None, actor_id: str | None) -> WorkerActor:
    """Return the staff actor or deny customer/blank/unknown roles.

    Measurement and job operations are staff-only. A missing actor id or a role
    outside estimator/reviewer/admin (including any customer role) fails closed.
    """

    normalized_role = (role or "").strip().lower()
    normalized_id = (actor_id or "").strip()
    if not normalized_id:
        raise WorkerApiError(
            "actor_id_required", 403, "X-Mobi-Actor-Id is required for worker operations"
        )
    if normalized_role not in STAFF_ACTOR_ROLES:
        raise WorkerApiError(
            "actor_role_forbidden",
            403,
            "Worker operations require an estimator, reviewer, or admin actor role",
        )
    return WorkerActor(role=normalized_role, actor_id=normalized_id)


def reconcile_body_identity(field: str, header_value: str, body_value: str | None) -> None:
    """Fail closed if a body-supplied identity value disagrees with the header.

    Identity is always taken from the authenticated header. If the JSON body also
    carries the value it must match exactly; a mismatch is a spoofing attempt.
    """

    if body_value is None:
        return
    if str(body_value).strip() != str(header_value).strip():
        raise WorkerApiError(
            "identity_mismatch",
            403,
            f"Body {field} does not match the authenticated request identity",
        )


def _require_identity_headers(tenant_id: str | None, company_id: str | None) -> dict[str, str]:
    """Return normalized request tenant/company identity or fail closed."""

    try:
        # ``project_id`` is validated per-row later; this only checks request-level
        # tenant identity is present and well-formed.
        context = build_tenant_project_context(
            tenant_id=tenant_id,
            company_id=company_id,
            project_id="request-level-tenant-identity",
        )
    except PermissionError as exc:
        raise WorkerApiError(
            "tenant_identity_required", 403, "Missing or invalid tenant identity headers"
        ) from exc
    return {"tenant_id": context["tenant_id"], "company_id": context["company_id"]}


def resolve_project_document(
    *,
    tenant_id: str,
    company_id: str,
    project_id: UUID,
    document_id: UUID,
) -> ResolvedProjectDocument:
    """Resolve and verify a tenant-scoped project document from the database.

    The single-document project model requires ``document_id == project_id``. The
    project row must exist, carry matching tenant/company identity, resolve its
    ``stored_file_path`` strictly inside the data root, and match its recorded
    SHA-256 before the provider is ever launched.
    """

    if document_id != project_id:
        raise WorkerApiError(
            "document_project_mismatch",
            422,
            "document_id must equal project_id in the single-document project model",
        )
    project = database.get_project(project_id)
    if project is None:
        raise WorkerApiError("document_not_found", 404, "Project document not found")
    try:
        assert_request_matches_project_tenant(
            project_row=project,
            request_tenant_id=tenant_id,
            request_company_id=company_id,
        )
    except PermissionError as exc:
        raise WorkerApiError("forbidden", 403, str(exc)) from exc

    stored_path = project.get("stored_file_path")
    if not stored_path:
        raise WorkerApiError("document_not_found", 404, "Project has no stored document")
    try:
        safe_path = storage.resolve_within_data_root(str(stored_path))
    except ValueError as exc:
        # A stored path that escapes the data root is a corrupt/unsafe row, not a
        # client error surface; never echo the path.
        raise WorkerApiError("document_not_found", 404, "Project document is unavailable") from exc
    if not safe_path.is_file():
        raise WorkerApiError("document_not_found", 404, "Project document is unavailable")

    recorded_hash = project.get("file_sha256")
    if not recorded_hash:
        raise WorkerApiError(
            "document_hash_missing", 422, "Project document has no recorded content hash"
        )
    if sha256_file(safe_path) != recorded_hash:
        raise WorkerApiError(
            OpenTakeoffWorkerErrorCode.DOCUMENT_HASH_MISMATCH.value,
            409,
            "Project document content hash does not match the recorded hash",
        )

    return ResolvedProjectDocument(
        tenant_id=UUID(str(project["tenant_id"])),
        company_id=UUID(str(project["company_id"])),
        project_id=UUID(str(project["id"])),
        document_id=document_id,
        safe_local_path=safe_path,
        original_filename=str(project.get("original_file_name") or f"{project_id}.pdf"),
        sha256=str(recorded_hash),
    )


def _assert_row_tenant(row: dict[str, Any], tenant_id: str, company_id: str) -> None:
    """Deny access unless the job row matches the request tenant/company scope."""

    actor = build_tenant_project_context(
        tenant_id=tenant_id, company_id=company_id, project_id=str(row["project_id"])
    )
    try:
        assert_same_tenant_project_access(
            actor,
            {
                "tenant_id": row.get("tenant_id"),
                "company_id": row.get("company_id"),
                "project_id": row.get("project_id"),
            },
        )
    except PermissionError as exc:
        raise WorkerApiError("forbidden", 403, "Job is not accessible in this tenant scope") from exc


def _points_from_geometry(raw: Any, key: str, minimum: int) -> list[tuple[float, float]]:
    """Validate and coerce a geometry point list, failing closed on bad shapes."""

    if not isinstance(raw, dict):
        raise WorkerApiError("invalid_geometry", 422, "geometry must be an object")
    points = raw.get(key)
    if not isinstance(points, list) or len(points) < minimum:
        raise WorkerApiError(
            "invalid_geometry",
            422,
            f"geometry.{key} must be a list of at least {minimum} points",
        )
    coerced: list[tuple[float, float]] = []
    for point in points:
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 2
            or isinstance(point[0], bool)
            or isinstance(point[1], bool)
            or not isinstance(point[0], (int, float))
            or not isinstance(point[1], (int, float))
        ):
            raise WorkerApiError(
                "invalid_geometry", 422, "geometry points must be [x, y] numeric pairs"
            )
        coerced.append((float(point[0]), float(point[1])))
    return coerced


class _ExportCapturingClient:
    """Thin delegating wrapper that records the provider's export payload.

    The tested :class:`OpenTakeoffWorkerService` runs load/scale/measure/export
    internally with its own client; wrapping the runtime lets the worker API
    persist the raw OpenTakeoff export artifact without duplicating that logic.
    """

    def __init__(self, inner: OpenTakeoffMCPClient) -> None:
        self._inner = inner
        self.captured_export: dict[str, Any] = {}

    def load_plan(self, path):  # noqa: ANN001 - matches provider protocol
        return self._inner.load_plan(path)

    def sheet_info(self, sheet):  # noqa: ANN001
        return self._inner.sheet_info(sheet)

    def set_scale(self, sheet, scale):  # noqa: ANN001
        return self._inner.set_scale(sheet, scale)

    def measure_line(self, sheet, pts, condition):  # noqa: ANN001
        return self._inner.measure_line(sheet, pts, condition)

    def measure_polygon(self, sheet, verts, condition):  # noqa: ANN001
        return self._inner.measure_polygon(sheet, verts, condition)

    def export_takeoff(self):
        self.captured_export = self._inner.export_takeoff()
        return self.captured_export

    def close(self) -> None:
        self._inner.close()


@dataclass
class _JobState:
    """Per-job in-memory context for the multi-call worker API lifecycle.

    Trade/scope defaults and the confirmed scale are held in-process for the
    single-process worker MVP. Job status and identity are the durable record in
    the database; this is convenience state for chaining confirm-scale/measure.
    """

    trade: str
    scope_category: str
    default_description: str
    condition: str | None = None
    scale: OpenTakeoffScaleConfirmation | None = None


class OpenTakeoffWorkerApiService:
    """Stateful orchestration for the deployable OpenTakeoff worker API."""

    def __init__(self, runtime_config: OpenTakeoffRuntimeConfig | None = None) -> None:
        self._runtime_config = runtime_config or OpenTakeoffRuntimeConfig()
        self._worker_service = OpenTakeoffWorkerService(
            artifact_root=storage.data_root(),
            operation_timeout_seconds=self._runtime_config.tool_timeout_seconds,
        )
        # Active measurement runtimes keyed by job id, for cooperative cancel.
        self._sessions: dict[str, OpenTakeoffMCPClient] = {}
        self._job_state: dict[str, _JobState] = {}
        self._artifacts: dict[str, list[dict[str, Any]]] = {}

    # -- Job creation -----------------------------------------------------
    def create_job(
        self,
        *,
        actor: WorkerActor,
        tenant_id: str,
        company_id: str,
        project_id: UUID,
        document_id: UUID,
        operation: str,
        trade: str,
        scope_category: str,
        condition: str | None,
        default_description: str,
        idempotency_key: str,
        requested_by: str | None,
    ) -> tuple[dict[str, Any], bool]:
        """Create (or idempotently return) a worker job. Returns (row, created)."""

        if operation not in {LINE_OPERATION, POLYGON_OPERATION}:
            raise WorkerApiError(
                "unsupported_operation", 422, "operation must be measure_line or measure_polygon"
            )
        document = resolve_project_document(
            tenant_id=tenant_id,
            company_id=company_id,
            project_id=project_id,
            document_id=document_id,
        )
        try:
            job = self._worker_service.create_job(
                document, operation=operation, payload_hash=idempotency_key
            )
        except ValueError as exc:
            raise WorkerApiError(str(exc), 409, "Document could not be prepared for takeoff") from exc

        with database.get_connection() as conn:
            existing = get_worker_job_record_by_idempotency(conn, job.idempotency_key)
            if existing is not None:
                self._record_job_state(existing["job_id"], trade, scope_category, condition, default_description)
                return existing, False
            row = create_worker_job_record(
                conn, job, operation=operation, requested_by=requested_by
            )
            created = row["job_id"] == str(job.job_id) and row["status"] == (
                OpenTakeoffWorkerStatus.QUEUED.value
            )
            if created:
                update_worker_job_status(
                    conn, job, status=OpenTakeoffWorkerStatus.DOCUMENT_LOADED
                )
                row = update_worker_job_status(
                    conn, job, status=OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION
                )
        self._record_job_state(row["job_id"], trade, scope_category, condition, default_description)
        return row, created

    def _record_job_state(
        self, job_id: str, trade: str, scope_category: str, condition: str | None, default_description: str
    ) -> None:
        state = self._job_state.get(job_id)
        if state is None:
            self._job_state[job_id] = _JobState(
                trade=trade,
                scope_category=scope_category,
                default_description=default_description,
                condition=condition,
            )

    # -- Read -------------------------------------------------------------
    def get_job(self, *, tenant_id: str, company_id: str, job_id: UUID) -> dict[str, Any]:
        with database.get_connection() as conn:
            row = get_worker_job_record(conn, str(job_id))
        if row is None:
            raise WorkerApiError("job_not_found", 404, "Worker job not found")
        _assert_row_tenant(row, tenant_id, company_id)
        return row

    def get_artifacts(self, *, tenant_id: str, company_id: str, job_id: UUID) -> list[dict[str, Any]]:
        # Verify tenant scope against the durable row before returning artifacts.
        self.get_job(tenant_id=tenant_id, company_id=company_id, job_id=job_id)
        safe: list[dict[str, Any]] = []
        for artifact in self._artifacts.get(str(job_id), []):
            safe.append(
                {
                    key: value
                    for key, value in artifact.items()
                    if key not in {"storage_key", "relative_path"}
                }
            )
        return safe

    # -- Scale confirmation ----------------------------------------------
    def confirm_scale(
        self,
        *,
        actor: WorkerActor,
        tenant_id: str,
        company_id: str,
        job_id: UUID,
        sheet_id: UUID,
        page_number: int,
        scale_source: str,
        scale_label: str,
        units_per_px: float | None,
    ) -> dict[str, Any]:
        job, row = self._load_job(tenant_id, company_id, job_id)
        document = resolve_project_document(
            tenant_id=tenant_id,
            company_id=company_id,
            project_id=UUID(str(row["project_id"])),
            document_id=UUID(str(row["document_id"])),
        )
        sheet = database.get_sheet(UUID(str(row["project_id"])), sheet_id)
        if sheet is None:
            raise WorkerApiError(
                "sheet_not_found",
                422,
                "sheet_id must reference a sheet for the requested project and tenant",
            )
        if int(sheet.get("pdf_page_number") or 0) != page_number:
            raise WorkerApiError(
                "sheet_page_mismatch",
                422,
                "sheet_id pdf_page_number must match the requested page_number",
            )
        sheet_key = f"{document.original_filename}#{page_number}"
        if not scale_source.strip() or not scale_label.strip():
            raise WorkerApiError(
                OpenTakeoffWorkerErrorCode.SCALE_UNCONFIRMED.value,
                422,
                "scale_source and scale_label are required to confirm scale",
            )
        scale = OpenTakeoffScaleConfirmation(
            sheet_id=sheet_id,
            sheet_key=sheet_key,
            page_number=page_number,
            scale_source=scale_source,
            scale_label=scale_label,
            units_per_px=units_per_px,
            confirmed_by=actor.role,
        )
        state = self._job_state.setdefault(
            str(job_id), _JobState(trade="", scope_category="", default_description="")
        )
        state.scale = scale
        with database.get_connection() as conn:
            updated = update_worker_job_status(
                conn, job, status=OpenTakeoffWorkerStatus.AWAITING_GEOMETRY
            )
        return updated

    # -- Measurement ------------------------------------------------------
    def measure(
        self,
        *,
        actor: WorkerActor,
        tenant_id: str,
        company_id: str,
        job_id: UUID,
        kind: str,
        geometry: Any,
        condition: str | None,
    ) -> dict[str, Any]:
        job, row = self._load_job(tenant_id, company_id, job_id)
        state = self._job_state.get(str(job_id))
        if state is None or state.scale is None:
            raise WorkerApiError(
                OpenTakeoffWorkerErrorCode.SCALE_MISSING.value,
                409,
                "Scale must be confirmed before measuring",
            )
        scale = state.scale
        measurement_condition = (condition or state.condition or "MEASURED").strip() or "MEASURED"
        if kind == "line":
            operation = LINE_OPERATION
            measurements = [
                {
                    "type": "line",
                    "pts": _points_from_geometry(geometry, "points", 2),
                    "condition": measurement_condition,
                }
            ]
        elif kind == "polygon":
            operation = POLYGON_OPERATION
            measurements = [
                {
                    "type": "polygon",
                    "verts": _points_from_geometry(geometry, "vertices", 3),
                    "condition": measurement_condition,
                }
            ]
        else:  # pragma: no cover - guarded by the router
            raise WorkerApiError("unsupported_operation", 422, "Unsupported measurement kind")

        # Re-resolve and re-verify the document (hash included) before launching.
        document = resolve_project_document(
            tenant_id=tenant_id,
            company_id=company_id,
            project_id=UUID(str(row["project_id"])),
            document_id=UUID(str(row["document_id"])),
        )
        job.document = document
        context = TakeoffContext(
            tenant_id=document.tenant_id,
            company_id=document.company_id,
            project_id=document.project_id,
            document_id=document.document_id,
            sheet_id=scale.sheet_id,
            extractor_version=WORKER_API_ENGINE_VERSION,
        )
        options = OpenTakeoffNormalizeOptions(
            trade=state.trade or "unspecified",
            scope_category=state.scope_category or "unspecified",
            default_description=state.default_description or "OpenTakeoff worker measurement",
            page_by_sheet={scale.sheet_key: scale.page_number},
        )

        with database.get_connection() as conn:
            update_worker_job_status(
                conn, job, status=OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT
            )

        runtime = OpenTakeoffMCPClient(self._runtime_config)
        capture = _ExportCapturingClient(runtime)
        self._sessions[str(job_id)] = runtime
        try:
            result = self._worker_service.run_linear_or_polygon_export(
                job=job,
                client=capture,
                context=context,
                options=options,
                scale=scale,
                measurements=measurements,
                persist=False,
            )
        except (OpenTakeoffRuntimeError, TimeoutError, RuntimeError, ValueError) as exc:
            self._sessions.pop(str(job_id), None)
            category = getattr(exc, "category", None) or OpenTakeoffWorkerErrorCode.PROVIDER_CRASH
            category_value = (
                category.value if isinstance(category, OpenTakeoffWorkerErrorCode) else str(category)
            )
            with database.get_connection() as conn:
                update_worker_job_status(
                    conn,
                    job,
                    status=OpenTakeoffWorkerStatus.FAILED,
                    error_category=category_value,
                    safe_error_message="OpenTakeoff measurement failed",
                )
            raise WorkerApiError(
                "measurement_failed", 500, "OpenTakeoff measurement failed"
            ) from exc
        finally:
            self._sessions.pop(str(job_id), None)

        if result.quarantined or not result.evidence:
            with database.get_connection() as conn:
                update_worker_job_status(
                    conn,
                    job,
                    status=OpenTakeoffWorkerStatus.FAILED,
                    error_category=OpenTakeoffWorkerErrorCode.NORMALIZATION_FAILED.value,
                    safe_error_message="OpenTakeoff export produced no valid measured evidence",
                )
            raise WorkerApiError(
                "normalization_failed", 422, "OpenTakeoff export produced no valid measured evidence"
            )

        evidence_ids = [str(item.evidence_id) for item in result.evidence]

        with database.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = get_worker_job_record(conn, str(job_id))
            if current is None or current["status"] != OpenTakeoffWorkerStatus.RUNNING_MEASUREMENT.value:
                conn.rollback()
                raise WorkerApiError(
                    "job_not_running_measurement",
                    409,
                    "Job is no longer running measurement; evidence/artifacts were not persisted",
                )
            artifacts = self._write_artifacts(
                document=document,
                job_id=str(job_id),
                operation=operation,
                actor=actor,
                scale=scale,
                measurements=measurements,
                export=capture.captured_export,
                result=result,
            )
            artifact_ids = [artifact["artifact_id"] for artifact in artifacts]
            for evidence in result.evidence:
                insert_canonical_evidence(evidence, conn=conn)
            updated = update_worker_job_status(
                conn,
                job,
                status=OpenTakeoffWorkerStatus.AWAITING_REVIEW,
                artifact_ids=artifact_ids,
                evidence_ids=evidence_ids,
                attempt_count=1,
            )
        self._artifacts[str(job_id)] = artifacts
        return updated

    # -- Cancellation -----------------------------------------------------
    def cancel(self, *, actor: WorkerActor, tenant_id: str, company_id: str, job_id: UUID) -> dict[str, Any]:
        job, row = self._load_job(tenant_id, company_id, job_id)
        if row["status"] in {
            OpenTakeoffWorkerStatus.COMPLETED.value,
            OpenTakeoffWorkerStatus.FAILED.value,
            OpenTakeoffWorkerStatus.CANCELLED.value,
        }:
            raise WorkerApiError(
                "job_terminal", 409, f"Job is already {row['status']} and cannot be cancelled"
            )
        # Stop any tracked in-flight measurement session first.
        session = self._sessions.pop(str(job_id), None)
        if session is not None:
            session.cancel()
        job.cancelled = True
        with database.get_connection() as conn:
            updated = update_worker_job_status(
                conn, job, status=OpenTakeoffWorkerStatus.CANCELLED
            )
        return updated

    # -- Internals --------------------------------------------------------
    def _load_job(
        self, tenant_id: str, company_id: str, job_id: UUID
    ) -> tuple[OpenTakeoffJob, dict[str, Any]]:
        row = self.get_job(tenant_id=tenant_id, company_id=company_id, job_id=job_id)
        job = OpenTakeoffJob(
            job_id=UUID(str(row["job_id"])),
            idempotency_key=str(row["idempotency_key"]),
            document=ResolvedProjectDocument(
                tenant_id=UUID(str(row["tenant_id"])),
                company_id=UUID(str(row["company_id"])),
                project_id=UUID(str(row["project_id"])),
                document_id=UUID(str(row["document_id"])),
                # Path is re-resolved on measurement; a placeholder keeps the job
                # object well-formed for status writes that never touch the file.
                safe_local_path=storage.data_root(),
                original_filename="",
                sha256="",
            ),
            engine_version=str(row.get("engine_version") or WORKER_API_ENGINE_VERSION),
        )
        return job, row

    def _write_artifacts(
        self,
        *,
        document: ResolvedProjectDocument,
        job_id: str,
        operation: str,
        actor: WorkerActor,
        scale: OpenTakeoffScaleConfirmation,
        measurements: list[dict[str, Any]],
        export: dict[str, Any],
        result: Any,
    ) -> list[dict[str, Any]]:
        base = (
            storage.project_dir(
                document.project_id,
                tenant_id=str(document.tenant_id),
                company_id=str(document.company_id),
            )
            / "opentakeoff_worker"
            / job_id
        )
        evidence_payloads = [item.model_dump(mode="json") for item in result.evidence]
        quantities = [
            {
                "provider_record_id": item.provider_record_id,
                "quantity": str(item.quantity) if item.quantity is not None else None,
                "unit": item.unit,
                "review_status": item.review_status,
            }
            for item in result.evidence
        ]
        marked_region = {
            "artifact_kind": "marked_region_metadata",
            "note": (
                "Deterministic geometry/scale metadata only; this is not a rendered "
                "plan image and contains no plan pixels."
            ),
            "sheet_id": str(scale.sheet_id),
            "sheet_key": scale.sheet_key,
            "page_number": scale.page_number,
            "operation": operation,
            "scale": {
                "source": scale.scale_source,
                "label": scale.scale_label,
                "units_per_px": scale.units_per_px,
            },
            "geometry": measurements,
            "region_coordinates": [
                list(item.region_coordinates) if item.region_coordinates else None
                for item in result.evidence
            ],
        }
        worker_metadata = {
            "job_id": job_id,
            "tenant_id": str(document.tenant_id),
            "company_id": str(document.company_id),
            "project_id": str(document.project_id),
            "document_id": str(document.document_id),
            "original_filename": document.original_filename,
            "operation": operation,
            "provider": OPEN_TAKEOFF_MCP_PACKAGE,
            "engine_version": f"{OPEN_TAKEOFF_MCP_PACKAGE}@{OPEN_TAKEOFF_MCP_VERSION}",
            "extractor_version": WORKER_API_ENGINE_VERSION,
            "schema_version": CANONICAL_EVIDENCE_SCHEMA_VERSION,
            "actor_role": actor.role,
            "actor_id": actor.actor_id,
            "review_status": "pending",
            "quantities": quantities,
        }

        specs = [
            ("opentakeoff_export", "export.json", export),
            ("canonical_evidence", "canonical_evidence.json", evidence_payloads),
            ("marked_region_metadata", "marked_region_metadata.json", marked_region),
            ("worker_metadata", "worker_metadata.json", worker_metadata),
        ]
        artifacts: list[dict[str, Any]] = []
        for artifact_type, filename, payload in specs:
            text = json.dumps(payload, sort_keys=True, default=str)
            data = text.encode("utf-8")
            path = base / filename
            storage.atomic_write_text(path, text)
            artifacts.append(
                {
                    "artifact_id": uuid4().hex,
                    "artifact_type": artifact_type,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                    # Server-only tenant/company/project-scoped storage key. It is
                    # stripped from API responses; callers receive only opaque
                    # artifact_id/type/hash/size metadata until signed URLs are
                    # implemented.
                    "storage_key": storage.relative_to_data_root(path),
                    "signed_url": None,
                    "expires_at": None,
                }
            )
        return artifacts


# Module-level singleton so confirm-scale/measure/cancel share in-process state
# (active runtime sessions, confirmed scale) across separate HTTP requests.
worker_api_service = OpenTakeoffWorkerApiService()
