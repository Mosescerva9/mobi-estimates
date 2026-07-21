"""Provider-neutral takeoff architecture (Milestone 2, slice 1).

This package owns the *canonical evidence contract* and the *provider-neutral
takeoff interface*. Every takeoff source — Mobi-native extraction, a manual
import, a human-verified entry, an authorized third-party tool, or a future
CAD/BIM importer — must normalize its output into the single canonical
``CanonicalEvidence`` model before anything downstream (routing, quantity
engine, pricing, delivery lock) is allowed to see it.

Design rules for this slice:

* The canonical evidence schema is Pydantic-based and **forbids unknown fields**.
* Unknown / unmapped provider payloads fail closed via typed quarantine errors
  and typed result fields — never via synonym or alias scanning.
* Concrete providers may be shells, but they must return canonical evidence from
  explicitly mapped payloads and quarantine anything they cannot map.
"""

from __future__ import annotations

from app.takeoff.evidence import (
    CANONICAL_EVIDENCE_SCHEMA_VERSION,
    EVIDENCE_CLASSES,
    NON_HUMAN_REVIEWED_EVIDENCE_CLASSES,
    CanonicalEvidence,
    EvidenceClass,
    EvidenceReviewStatus,
    MeasurementMethod,
    TakeoffProviderKind,
)
from app.takeoff.providers import (
    AuthorizedThirdPartyProvider,
    CustomerSuppliedProvider,
    EvidenceQuarantineError,
    FutureCadBimProvider,
    FutureThirdPartyProvider,
    HumanVerifiedTakeoffProvider,
    ManualTakeoffImportProvider,
    MobiNativeTakeoffProvider,
    OpenTakeoffProvider,
    ProviderNormalizationResult,
    QuarantinedPayload,
    TakeoffContext,
    TakeoffProvider,
)
from app.takeoff.opentakeoff import (
    OpenTakeoffNormalizeOptions,
    normalize_opentakeoff_export,
)
from app.takeoff.store import (
    CANONICAL_EVIDENCE_TABLE,
    deserialize_canonical_evidence,
    insert_canonical_evidence,
    list_canonical_evidence_by_project,
    serialize_canonical_evidence,
)
from app.takeoff.worker import (
    SUPPORTED_MVP_OPERATIONS,
    UNSUPPORTED_MVP_OPERATIONS,
    build_count_export,
    OpenTakeoffArtifact,
    OpenTakeoffJob,
    OpenTakeoffOperation,
    OpenTakeoffScaleConfirmation,
    OpenTakeoffWorkerError,
    OpenTakeoffWorkerErrorCode,
    OpenTakeoffWorkerService,
    OpenTakeoffWorkerStatus,
    ResolvedProjectDocument,
)
from app.takeoff.mcp_runtime import (
    OPEN_TAKEOFF_MCP_INTEGRITY,
    OPEN_TAKEOFF_MCP_LICENSE,
    OPEN_TAKEOFF_MCP_PACKAGE,
    OPEN_TAKEOFF_MCP_REPOSITORY,
    OPEN_TAKEOFF_MCP_VERSION,
    OpenTakeoffMCPClient,
    OpenTakeoffRuntimeConfig,
    OpenTakeoffRuntimeDiagnostics,
    OpenTakeoffRuntimeError,
)

__all__ = [
    "CANONICAL_EVIDENCE_SCHEMA_VERSION",
    "EVIDENCE_CLASSES",
    "NON_HUMAN_REVIEWED_EVIDENCE_CLASSES",
    "CanonicalEvidence",
    "EvidenceClass",
    "EvidenceReviewStatus",
    "MeasurementMethod",
    "TakeoffProviderKind",
    "AuthorizedThirdPartyProvider",
    "CustomerSuppliedProvider",
    "EvidenceQuarantineError",
    "FutureCadBimProvider",
    "FutureThirdPartyProvider",
    "HumanVerifiedTakeoffProvider",
    "ManualTakeoffImportProvider",
    "MobiNativeTakeoffProvider",
    "OpenTakeoffProvider",
    "ProviderNormalizationResult",
    "QuarantinedPayload",
    "TakeoffContext",
    "TakeoffProvider",
    "OpenTakeoffNormalizeOptions",
    "normalize_opentakeoff_export",
    "CANONICAL_EVIDENCE_TABLE",
    "deserialize_canonical_evidence",
    "insert_canonical_evidence",
    "list_canonical_evidence_by_project",
    "serialize_canonical_evidence",
    "SUPPORTED_MVP_OPERATIONS",
    "UNSUPPORTED_MVP_OPERATIONS",
    "build_count_export",
    "OpenTakeoffArtifact",
    "OpenTakeoffJob",
    "OpenTakeoffOperation",
    "OpenTakeoffScaleConfirmation",
    "OpenTakeoffWorkerError",
    "OpenTakeoffWorkerErrorCode",
    "OpenTakeoffWorkerService",
    "OpenTakeoffWorkerStatus",
    "ResolvedProjectDocument",
    "OPEN_TAKEOFF_MCP_INTEGRITY",
    "OPEN_TAKEOFF_MCP_LICENSE",
    "OPEN_TAKEOFF_MCP_PACKAGE",
    "OPEN_TAKEOFF_MCP_REPOSITORY",
    "OPEN_TAKEOFF_MCP_VERSION",
    "OpenTakeoffMCPClient",
    "OpenTakeoffRuntimeConfig",
    "OpenTakeoffRuntimeDiagnostics",
    "OpenTakeoffRuntimeError",
]
