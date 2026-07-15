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
    EvidenceQuarantineError,
    FutureCadBimProvider,
    HumanVerifiedTakeoffProvider,
    ManualTakeoffImportProvider,
    MobiNativeTakeoffProvider,
    ProviderNormalizationResult,
    QuarantinedPayload,
    TakeoffContext,
    TakeoffProvider,
)
from app.takeoff.store import (
    CANONICAL_EVIDENCE_TABLE,
    deserialize_canonical_evidence,
    insert_canonical_evidence,
    list_canonical_evidence_by_project,
    serialize_canonical_evidence,
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
    "EvidenceQuarantineError",
    "FutureCadBimProvider",
    "HumanVerifiedTakeoffProvider",
    "ManualTakeoffImportProvider",
    "MobiNativeTakeoffProvider",
    "ProviderNormalizationResult",
    "QuarantinedPayload",
    "TakeoffContext",
    "TakeoffProvider",
    "CANONICAL_EVIDENCE_TABLE",
    "deserialize_canonical_evidence",
    "insert_canonical_evidence",
    "list_canonical_evidence_by_project",
    "serialize_canonical_evidence",
]
