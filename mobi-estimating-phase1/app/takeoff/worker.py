"""OpenTakeoff worker/service boundary for demonstrated MVP workflows.

This module is intentionally provider-process agnostic. It defines the safe Mobi
side of the worker contract: project/document resolution, supported operation
selection, explicit scale confirmation, structured errors, idempotency, artifact
hashing, and evidence persistence. The actual MCP subprocess adapter can plug
into this boundary without changing the safety contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.takeoff.opentakeoff import OpenTakeoffNormalizeOptions, normalize_opentakeoff_export
from app.takeoff.providers import ProviderNormalizationResult, TakeoffContext
from app.takeoff.store import insert_canonical_evidence


class OpenTakeoffWorkerErrorCode(str, Enum):
    DOCUMENT_NOT_FOUND = "document_not_found"
    UNSUPPORTED_DOCUMENT = "unsupported_document"
    RASTER_NOT_SUPPORTED = "raster_not_supported"
    SHEET_NOT_FOUND = "sheet_not_found"
    SCALE_MISSING = "scale_missing"
    SCALE_UNCONFIRMED = "scale_unconfirmed"
    MEASUREMENT_INVALID = "measurement_invalid"
    TRACE_AMBIGUOUS = "trace_ambiguous"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_CRASH = "provider_crash"
    NORMALIZATION_FAILED = "normalization_failed"
    PERSISTENCE_FAILED = "persistence_failed"
    ARTIFACT_FAILED = "artifact_failed"
    CANCELLED = "cancelled"


class OpenTakeoffWorkerStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OpenTakeoffOperation(str, Enum):
    LOAD_PROJECT_DOCUMENT = "load_project_document"
    INSPECT_SHEET = "inspect_sheet"
    READ_SHEET_TEXT = "read_sheet_text"
    CONFIRM_SCALE = "confirm_scale"
    MEASURE_LINE = "measure_line"
    MEASURE_POLYGON = "measure_polygon"
    EXPORT_TAKEOFF = "export_takeoff"
    NORMALIZE_EVIDENCE = "normalize_evidence"
    PERSIST_EVIDENCE = "persist_evidence"
    GENERATE_MARKED_ARTIFACT = "generate_marked_artifact"


SUPPORTED_MVP_OPERATIONS: frozenset[OpenTakeoffOperation] = frozenset({
    OpenTakeoffOperation.LOAD_PROJECT_DOCUMENT,
    OpenTakeoffOperation.INSPECT_SHEET,
    OpenTakeoffOperation.READ_SHEET_TEXT,
    OpenTakeoffOperation.CONFIRM_SCALE,
    OpenTakeoffOperation.MEASURE_LINE,
    OpenTakeoffOperation.MEASURE_POLYGON,
    OpenTakeoffOperation.EXPORT_TAKEOFF,
    OpenTakeoffOperation.NORMALIZE_EVIDENCE,
    OpenTakeoffOperation.PERSIST_EVIDENCE,
    OpenTakeoffOperation.GENERATE_MARKED_ARTIFACT,
})

# Held behind estimator review/fallback after the capability benchmark.
UNSUPPORTED_MVP_OPERATIONS: frozenset[str] = frozenset({
    "one_click_area_on_gap_prone_geometry",
    "apply_deduction",
    "record_count",
    "raster_or_scanned_plan_measurement",
})


@dataclass(frozen=True)
class ResolvedProjectDocument:
    """Allowlisted server-side document resolution result.

    The worker accepts this object from Mobi's project/document layer. It never
    accepts arbitrary customer-provided filesystem paths.
    """

    tenant_id: UUID
    company_id: UUID
    project_id: UUID
    document_id: UUID
    safe_local_path: Path
    original_filename: str
    sha256: str


@dataclass(frozen=True)
class OpenTakeoffScaleConfirmation:
    sheet_id: UUID
    sheet_key: str
    page_number: int
    scale_source: str
    scale_label: str
    units_per_px: float | None = None
    confirmed_by: str = "estimator"


@dataclass(frozen=True)
class OpenTakeoffArtifact:
    artifact_type: str
    path: Path
    sha256: str
    bytes: int


@dataclass(frozen=True)
class OpenTakeoffWorkerError:
    code: OpenTakeoffWorkerErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenTakeoffJob:
    job_id: UUID
    idempotency_key: str
    document: ResolvedProjectDocument
    status: OpenTakeoffWorkerStatus = OpenTakeoffWorkerStatus.QUEUED
    provider_version: str = "opentakeoff-mcp"
    engine_version: str = "mobi-opentakeoff-worker-v1"
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[OpenTakeoffArtifact] = field(default_factory=list)
    errors: list[OpenTakeoffWorkerError] = field(default_factory=list)
    cancelled: bool = False

    def add_event(self, event_type: str, **payload: Any) -> None:
        safe_payload = {key: value for key, value in payload.items() if "secret" not in key.lower()}
        self.audit_events.append({"event_type": event_type, "payload": safe_payload})


class OpenTakeoffProviderClient(Protocol):
    """Small MCP/client seam for demonstrated operations only."""

    def load_plan(self, path: Path) -> dict[str, Any]: ...
    def sheet_info(self, sheet: str) -> dict[str, Any]: ...
    def set_scale(self, sheet: str, scale: OpenTakeoffScaleConfirmation) -> dict[str, Any]: ...
    def measure_line(self, sheet: str, pts: list[tuple[float, float]], condition: str) -> dict[str, Any]: ...
    def measure_polygon(self, sheet: str, verts: list[tuple[float, float]], condition: str) -> dict[str, Any]: ...
    def export_takeoff(self) -> dict[str, Any]: ...
    def close(self) -> None: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_idempotency_key(project_id: UUID, document_id: UUID, operation: str, payload_hash: str) -> str:
    return f"{project_id}:{document_id}:{operation}:{payload_hash}"


class OpenTakeoffWorkerService:
    """Safe Mobi worker boundary around demonstrated OpenTakeoff workflows."""

    def __init__(self, *, artifact_root: Path, operation_timeout_seconds: float = 30.0) -> None:
        self.artifact_root = artifact_root
        self.operation_timeout_seconds = operation_timeout_seconds

    def create_job(self, document: ResolvedProjectDocument, *, operation: str, payload_hash: str) -> OpenTakeoffJob:
        if not document.safe_local_path.is_file():
            raise ValueError(OpenTakeoffWorkerErrorCode.DOCUMENT_NOT_FOUND.value)
        if not document.safe_local_path.suffix.lower() == ".pdf":
            raise ValueError(OpenTakeoffWorkerErrorCode.UNSUPPORTED_DOCUMENT.value)
        expected_hash = sha256_file(document.safe_local_path)
        if expected_hash != document.sha256:
            raise ValueError("document_hash_mismatch")
        return OpenTakeoffJob(
            job_id=uuid4(),
            idempotency_key=build_idempotency_key(
                document.project_id, document.document_id, operation, payload_hash
            ),
            document=document,
        )

    def require_supported(self, operation: OpenTakeoffOperation) -> None:
        if operation not in SUPPORTED_MVP_OPERATIONS:
            raise ValueError(OpenTakeoffWorkerErrorCode.MEASUREMENT_INVALID.value)

    def run_linear_or_polygon_export(
        self,
        *,
        job: OpenTakeoffJob,
        client: OpenTakeoffProviderClient,
        context: TakeoffContext,
        options: OpenTakeoffNormalizeOptions,
        scale: OpenTakeoffScaleConfirmation,
        measurements: list[dict[str, Any]],
        persist: bool = True,
    ) -> ProviderNormalizationResult:
        """Run demonstrated explicit-scale line/polygon workflows and normalize.

        ``measurements`` supports only:
        - {"type": "line", "pts": [(x, y), ...], "condition": "..."}
        - {"type": "polygon", "verts": [(x, y), ...], "condition": "..."}
        """

        if job.cancelled:
            job.status = OpenTakeoffWorkerStatus.CANCELLED
            raise RuntimeError(OpenTakeoffWorkerErrorCode.CANCELLED.value)
        if not scale.scale_source or not scale.scale_label:
            raise ValueError(OpenTakeoffWorkerErrorCode.SCALE_UNCONFIRMED.value)

        job.status = OpenTakeoffWorkerStatus.RUNNING
        started = monotonic()
        try:
            job.add_event("load_project_document", document_id=str(job.document.document_id))
            client.load_plan(job.document.safe_local_path)
            job.add_event("confirm_scale", sheet=scale.sheet_key, source=scale.scale_source)
            client.set_scale(scale.sheet_key, scale)
            for measurement in measurements:
                if monotonic() - started > self.operation_timeout_seconds:
                    raise TimeoutError(OpenTakeoffWorkerErrorCode.PROVIDER_TIMEOUT.value)
                kind = measurement.get("type")
                condition = str(measurement.get("condition") or "MEASURED")
                if kind == "line":
                    self.require_supported(OpenTakeoffOperation.MEASURE_LINE)
                    client.measure_line(scale.sheet_key, measurement["pts"], condition)
                elif kind == "polygon":
                    self.require_supported(OpenTakeoffOperation.MEASURE_POLYGON)
                    client.measure_polygon(scale.sheet_key, measurement["verts"], condition)
                else:
                    raise ValueError(OpenTakeoffWorkerErrorCode.MEASUREMENT_INVALID.value)
            export = client.export_takeoff()
            result = normalize_opentakeoff_export(export, context=context, options=options)
            if result.quarantined:
                job.errors.append(OpenTakeoffWorkerError(
                    OpenTakeoffWorkerErrorCode.NORMALIZATION_FAILED,
                    "OpenTakeoff export contained quarantined payloads.",
                    details={"count": len(result.quarantined)},
                ))
            if persist:
                for evidence in result.evidence:
                    insert_canonical_evidence(evidence)
            job.status = OpenTakeoffWorkerStatus.SUCCEEDED if not job.errors else OpenTakeoffWorkerStatus.FAILED
            return result
        except TimeoutError as exc:
            job.status = OpenTakeoffWorkerStatus.FAILED
            job.errors.append(OpenTakeoffWorkerError(OpenTakeoffWorkerErrorCode.PROVIDER_TIMEOUT, str(exc), retryable=True))
            raise
        except Exception as exc:
            job.status = OpenTakeoffWorkerStatus.FAILED
            job.errors.append(OpenTakeoffWorkerError(OpenTakeoffWorkerErrorCode.PROVIDER_CRASH, str(exc), retryable=False))
            raise
        finally:
            client.close()
