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
import math
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
    build_count_export,
    sha256_file,
)
from app.takeoff.worker_jobs import (
    create_worker_job_record,
    get_worker_job_record,
    get_worker_job_record_by_idempotency,
    get_worker_job_retry_child,
    insert_worker_job_artifact,
    list_worker_job_artifacts,
    set_worker_job_scale,
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
# Count is a deterministic tally of estimator-placed markers (each marker = one
# EA); the pinned MCP has no native count primitive (see app.takeoff.worker).
COUNT_OPERATION = "measure_count"
MEASUREMENT_OPERATIONS: frozenset[str] = frozenset({LINE_OPERATION, POLYGON_OPERATION, COUNT_OPERATION})

# The measurement endpoint "kind" (line/polygon/count) each map to exactly one
# persisted job operation. A request whose endpoint kind does not equal the
# job's recorded operation is rejected before any state change or provider work.
KIND_TO_OPERATION: dict[str, str] = {
    "line": LINE_OPERATION,
    "polygon": POLYGON_OPERATION,
    "count": COUNT_OPERATION,
}


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
    """Validate and coerce a geometry point list, failing closed on bad shapes.

    Coordinates must be finite real numbers: NaN and ±infinity (which the JSON
    parser accepts) are rejected here so a non-finite coordinate can never reach
    the provider, the length/area math, or the persisted evidence.
    """

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
        x, y = float(point[0]), float(point[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise WorkerApiError(
                "invalid_geometry",
                422,
                "geometry points must be finite (no NaN or infinity)",
            )
        coerced.append((x, y))
    return coerced


def _polygon_area(verts: list[tuple[float, float]]) -> float:
    """Shoelace area of a polygon in the point coordinate space (px^2)."""
    area = 0.0
    n = len(verts)
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _line_length(points: list[tuple[float, float]]) -> float:
    """Total length of a polyline in the point coordinate space (px)."""
    total = 0.0
    for i in range(1, len(points)):
        total += math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
    return total


def _require_line_points(raw: Any) -> list[tuple[float, float]]:
    """A line needs >= 2 finite points and a non-zero total length."""
    points = _points_from_geometry(raw, "points", 2)
    if _line_length(points) <= 0:
        raise WorkerApiError(
            "invalid_geometry", 422, "line geometry must have non-zero length"
        )
    return points


def _require_polygon_verts(raw: Any) -> list[tuple[float, float]]:
    """A polygon needs >= 3 distinct finite vertices and a positive finite area."""
    verts = _points_from_geometry(raw, "vertices", 3)
    distinct = {(round(x, 6), round(y, 6)) for x, y in verts}
    if len(distinct) < 3:
        raise WorkerApiError(
            "invalid_geometry", 422, "polygon geometry must have at least three distinct vertices"
        )
    area = _polygon_area(verts)
    if not math.isfinite(area) or area <= 0:
        raise WorkerApiError(
            "invalid_geometry", 422, "polygon geometry must have positive finite area"
        )
    return verts


def _require_count_marks(raw: Any) -> list[tuple[float, float]]:
    """A count needs at least one valid finite marker."""
    return _points_from_geometry(raw, "points", 1)


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


class OpenTakeoffWorkerApiService:
    """Orchestration for the deployable OpenTakeoff worker API.

    All multi-call lifecycle state (immutable create parameters, the confirmed
    scale, and artifact records) is persisted in SQLite and reconstructed from
    the job row on every request, so a job created/scale-confirmed by one service
    instance can be measured/read by a fresh instance or after a restart. The
    only remaining in-process state is the live MCP subprocess handle used for
    cooperative cancellation, which is inherently per-process and cannot be
    shared across instances.
    """

    def __init__(self, runtime_config: OpenTakeoffRuntimeConfig | None = None) -> None:
        self._runtime_config = runtime_config or OpenTakeoffRuntimeConfig()
        self._worker_service = OpenTakeoffWorkerService(
            artifact_root=storage.data_root(),
            operation_timeout_seconds=self._runtime_config.tool_timeout_seconds,
        )
        # Active measurement runtimes keyed by job id, for cooperative cancel.
        self._sessions: dict[str, OpenTakeoffMCPClient] = {}

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

        if operation not in MEASUREMENT_OPERATIONS:
            raise WorkerApiError(
                "unsupported_operation",
                422,
                "operation must be measure_line, measure_polygon, or measure_count",
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
                return existing, False
            row = create_worker_job_record(
                conn,
                job,
                operation=operation,
                requested_by=requested_by,
                trade=trade,
                scope_category=scope_category,
                default_description=default_description,
                create_condition=condition,
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
        return row, created

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
        with database.get_connection() as conn:
            records = list_worker_job_artifacts(
                conn, job_id=str(job_id), tenant_id=tenant_id, company_id=company_id
            )
        # Return only opaque metadata: the server-only storage_key and internal
        # bookkeeping columns are never exposed to the caller.
        safe: list[dict[str, Any]] = []
        for artifact in records:
            safe.append(
                {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_type": artifact["artifact_type"],
                    "sha256": artifact["sha256"],
                    "bytes": artifact["bytes"],
                    "signed_url": None,
                    "expires_at": None,
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
        with database.get_connection() as conn:
            # Persist the confirmed scale on the durable job row so a measurement
            # handled by a different instance/after a restart can reconstruct it.
            set_worker_job_scale(
                conn,
                str(job_id),
                sheet_id=str(sheet_id),
                sheet_key=sheet_key,
                page_number=page_number,
                scale_source=scale_source,
                scale_label=scale_label,
                units_per_px=units_per_px,
                confirmed_by=actor.role,
            )
            updated = update_worker_job_status(
                conn, job, status=OpenTakeoffWorkerStatus.AWAITING_GEOMETRY
            )
        return updated

    def _scale_from_row(self, row: dict[str, Any]) -> OpenTakeoffScaleConfirmation | None:
        """Reconstruct the confirmed scale from the durable job row, if present."""
        sheet_key = row.get("scale_sheet_key")
        sheet_id = row.get("scale_sheet_id")
        page_number = row.get("scale_page_number")
        if not sheet_key or not sheet_id or page_number is None:
            return None
        return OpenTakeoffScaleConfirmation(
            sheet_id=UUID(str(sheet_id)),
            sheet_key=str(sheet_key),
            page_number=int(page_number),
            scale_source=str(row.get("scale_source") or ""),
            scale_label=str(row.get("scale_label") or ""),
            units_per_px=row.get("scale_units_per_px"),
            confirmed_by=str(row.get("scale_confirmed_by") or "estimator"),
        )

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

        # OPERATION MATCH (before any state change, provider launch, or evidence
        # write): the endpoint kind must equal the persisted job operation. A
        # count job may only be measured through measure-count, a line job only
        # through measure-line, etc. A mismatch is a safe 409 that leaves the job
        # and any evidence untouched.
        expected_operation = KIND_TO_OPERATION.get(kind)
        if expected_operation is None:  # pragma: no cover - guarded by the router
            raise WorkerApiError("unsupported_operation", 422, "Unsupported measurement kind")
        persisted_operation = str(row.get("operation") or "")
        if persisted_operation != expected_operation:
            raise WorkerApiError(
                "operation_mismatch",
                409,
                "Measurement endpoint does not match the job's recorded operation",
            )

        # Reconstruct the confirmed scale and immutable create parameters from the
        # durable job row — never from process-local state — so a fresh instance
        # can measure a job another instance created and scale-confirmed.
        scale = self._scale_from_row(row)
        if scale is None:
            raise WorkerApiError(
                OpenTakeoffWorkerErrorCode.SCALE_MISSING.value,
                409,
                "Scale must be confirmed before measuring",
            )
        create_condition = row.get("create_condition")
        measurement_condition = (condition or create_condition or "MEASURED").strip() or "MEASURED"
        # ``count_export`` is prebuilt for the count operation only; line/polygon
        # capture the real MCP export instead (``count_export`` stays None).
        count_export: dict[str, Any] | None = None
        if kind == "line":
            operation = LINE_OPERATION
            measurements = [
                {
                    "type": "line",
                    "pts": _require_line_points(geometry),
                    "condition": measurement_condition,
                }
            ]
        elif kind == "polygon":
            operation = POLYGON_OPERATION
            measurements = [
                {
                    "type": "polygon",
                    "verts": _require_polygon_verts(geometry),
                    "condition": measurement_condition,
                }
            ]
        else:  # kind == "count" (already validated against the persisted operation)
            operation = COUNT_OPERATION
            marks = _require_count_marks(geometry)
            measurements = [
                {
                    "type": "count",
                    "marks": marks,
                    "condition": measurement_condition,
                }
            ]
            count_export = build_count_export(
                sheet_key=scale.sheet_key,
                units_per_px=scale.units_per_px,
                marks=marks,
                condition=measurement_condition,
            )

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
            trade=str(row.get("trade") or "unspecified"),
            scope_category=str(row.get("scope_category") or "unspecified"),
            default_description=str(row.get("default_description") or "OpenTakeoff worker measurement"),
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
            if count_export is not None:
                # The MCP has no count primitive; the captured export artifact is
                # the deterministic canonical count export the worker built.
                capture.captured_export = count_export
                result = self._worker_service.run_count_export(
                    job=job,
                    client=capture,
                    context=context,
                    options=options,
                    scale=scale,
                    count_export=count_export,
                    persist=False,
                )
            else:
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
            # Persist artifact records durably (same transaction as evidence) so a
            # fresh instance can return them; the storage_key is server-only.
            for artifact in artifacts:
                insert_worker_job_artifact(
                    conn,
                    artifact_id=artifact["artifact_id"],
                    job_id=str(job_id),
                    tenant_id=str(document.tenant_id),
                    company_id=str(document.company_id),
                    project_id=str(document.project_id),
                    artifact_type=artifact["artifact_type"],
                    sha256=artifact["sha256"],
                    bytes_len=artifact["bytes"],
                    storage_key=artifact["storage_key"],
                )
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

    # -- Retry ------------------------------------------------------------
    def retry_job(
        self, *, actor: WorkerActor, tenant_id: str, company_id: str, job_id: UUID
    ) -> tuple[dict[str, Any], bool]:
        """Create (or idempotently return) a real retry attempt of a failed job.

        A retry is a NEW job linked to the failed parent: it carries an
        incremented ``attempt_number``, the parent's ``job_id`` as
        ``parent_job_id``, and the shared ``root_job_id`` of the lineage. The
        original failed job and its persisted error are never mutated. Repeated
        retry requests for the same failed job are idempotent — a deterministic
        idempotency key plus a parent->child lookup collapse them onto the single
        retry attempt, so retries and evidence are never duplicated.
        """
        job, row = self._load_job(tenant_id, company_id, job_id)
        if str(row.get("status")) != OpenTakeoffWorkerStatus.FAILED.value:
            raise WorkerApiError(
                "job_not_failed",
                409,
                "Only a failed job can be retried",
            )

        # Idempotency 1: if this failed job already has a retry child, return it.
        with database.get_connection() as conn:
            existing_child = get_worker_job_retry_child(conn, str(job_id))
        if existing_child is not None:
            return existing_child, False

        parent_attempt = int(row.get("attempt_number") or 1)
        new_attempt = parent_attempt + 1
        root_job_id = str(row.get("root_job_id") or row["job_id"])
        operation = str(row["operation"])
        retry_idempotency = f"{row['idempotency_key']}:retry:{new_attempt}"

        # Re-resolve/verify the document (hash included) before minting the attempt.
        document = resolve_project_document(
            tenant_id=tenant_id,
            company_id=company_id,
            project_id=UUID(str(row["project_id"])),
            document_id=UUID(str(row["document_id"])),
        )
        new_job = OpenTakeoffJob(
            job_id=uuid4(),
            idempotency_key=retry_idempotency,
            document=document,
            engine_version=str(row.get("engine_version") or WORKER_API_ENGINE_VERSION),
        )

        with database.get_connection() as conn:
            # Idempotency 2: a race that already minted this attempt returns it.
            existing = get_worker_job_record_by_idempotency(conn, retry_idempotency)
            if existing is not None:
                return existing, False
            new_row = create_worker_job_record(
                conn,
                new_job,
                operation=operation,
                requested_by=actor.actor_id,
                trade=row.get("trade"),
                scope_category=row.get("scope_category"),
                default_description=row.get("default_description"),
                create_condition=row.get("create_condition"),
                attempt_number=new_attempt,
                parent_job_id=str(job_id),
                root_job_id=root_job_id,
            )
            created = new_row["job_id"] == str(new_job.job_id) and new_row["status"] == (
                OpenTakeoffWorkerStatus.QUEUED.value
            )
            if created:
                update_worker_job_status(
                    conn, new_job, status=OpenTakeoffWorkerStatus.DOCUMENT_LOADED
                )
                new_row = update_worker_job_status(
                    conn, new_job, status=OpenTakeoffWorkerStatus.AWAITING_SCALE_CONFIRMATION
                )
        return new_row, created

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
                # Provenance/measurement method distinguishes a count staff marker
                # tally from a native digital line/polygon measurement.
                "measurement_method": item.measurement_method,
                "evidence_class": item.evidence_class,
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
