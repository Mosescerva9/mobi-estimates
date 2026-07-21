"""Provider-neutral takeoff interface.

Every takeoff source implements :class:`TakeoffProvider` and normalizes its own
payload shape into :class:`~app.takeoff.evidence.CanonicalEvidence`. The base
class owns the fail-closed contract:

* A payload may only contain the provider's *explicitly allowed* keys. Any
  unmapped/unknown key quarantines the whole payload — the base class never
  guesses that ``qty`` means ``quantity`` or that ``desc`` means ``description``.
  There is no synonym/alias scanning anywhere in this module.
* Anything that fails Pydantic validation (bad enum, bad unit, missing required
  field) is quarantined with a typed reason, not silently dropped.

Concrete providers in this slice are thin shells: they fix their own provider
kind plus a default evidence class / measurement method, and rely entirely on
the base class for mapping and validation.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.takeoff.evidence import (
    CanonicalEvidence,
    EvidenceClass,
    MeasurementMethod,
    TakeoffProviderKind,
)


class EvidenceQuarantineError(Exception):
    """Raised when a single provider payload cannot become canonical evidence.

    Carries the offending payload and a machine-readable reason code so callers
    can quarantine and audit it instead of coercing it into evidence.
    """

    def __init__(self, reason_code: str, message: str, *, payload: dict[str, Any]):
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message
        self.payload = payload


@dataclass(frozen=True)
class QuarantinedPayload:
    """A payload that failed to normalize, retained for audit — never evidence."""

    reason_code: str
    message: str
    payload: dict[str, Any]


@dataclass
class ProviderNormalizationResult:
    """Typed batch result: canonical evidence plus quarantined payloads.

    Unknown/unmapped payloads never leak into ``evidence``; they land in
    ``quarantined`` with a typed reason instead.
    """

    provider: TakeoffProviderKind
    evidence: list[CanonicalEvidence] = field(default_factory=list)
    quarantined: list[QuarantinedPayload] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.quarantined


@dataclass(frozen=True)
class TakeoffContext:
    """Server-owned identity/lineage fields, never taken from provider payloads.

    Providers transcribe measurements; tenancy, document coordinates, and the
    extractor version are established by the platform and injected here so an
    untrusted payload can never claim to belong to another tenant/project.
    """

    tenant_id: UUID
    company_id: UUID
    project_id: UUID
    document_id: UUID
    sheet_id: UUID
    extractor_version: str


# The closed set of payload keys any provider may map. A key outside this set is
# an unknown/unmapped field and quarantines the payload. This is an allow-list,
# not a synonym table: there are no aliases here to extend.
_ALLOWED_PAYLOAD_FIELDS: frozenset[str] = frozenset({
    "provider_record_id",
    "page_number",
    "region_coordinates",
    "trade",
    "scope_category",
    "description",
    "quantity",
    "unit",
    "confidence",
    "condition",
    "scale",
    "review_status",
    "reviewed_by",
    # A provider may name the exact measurement method for a single payload when
    # its default is not correct for that record (e.g. an OpenTakeoff count is a
    # staff marker tally, not a digital measurement). This is a controlled enum
    # value validated by CanonicalEvidence — never a free-text synonym.
    "measurement_method",
})


class TakeoffProvider(ABC):
    """Abstract base for a takeoff provider.

    Subclasses set :attr:`provider_kind`, :attr:`default_evidence_class`, and
    :attr:`default_measurement_method`. All mapping/validation lives here so the
    fail-closed behavior cannot drift per provider.
    """

    provider_kind: TakeoffProviderKind
    default_evidence_class: EvidenceClass
    default_measurement_method: MeasurementMethod

    # Provider payloads may only carry these keys. Subclasses may narrow this,
    # but may not add synonyms — every key must be a real canonical field.
    allowed_payload_fields: frozenset[str] = _ALLOWED_PAYLOAD_FIELDS

    def normalize(
        self, payload: dict[str, Any], *, context: TakeoffContext
    ) -> CanonicalEvidence:
        """Normalize one provider payload into canonical evidence.

        Raises :class:`EvidenceQuarantineError` when the payload is malformed,
        contains unknown/unmapped keys, or fails canonical validation.
        """
        if not isinstance(payload, dict):
            raise EvidenceQuarantineError(
                "malformed_payload",
                "Provider payload is not a mapping; provenance cannot be verified.",
                payload={"payload": payload},
            )

        unknown_keys = sorted(set(payload) - self.allowed_payload_fields)
        if unknown_keys:
            raise EvidenceQuarantineError(
                "unknown_payload_fields",
                "Provider payload has unmapped fields "
                f"{unknown_keys}; no synonym mapping is applied.",
                payload=payload,
            )

        evidence_fields: dict[str, Any] = {
            **payload,
            "tenant_id": context.tenant_id,
            "company_id": context.company_id,
            "project_id": context.project_id,
            "document_id": context.document_id,
            "sheet_id": context.sheet_id,
            "extractor_version": context.extractor_version,
            "takeoff_provider": self.provider_kind,
            "evidence_class": self.default_evidence_class,
            # Honor an explicit per-payload measurement method when the provider
            # supplied one; otherwise fall back to the provider default. Pydantic
            # validates the value against the MeasurementMethod enum, so an
            # unknown method still fails closed rather than being coerced.
            "measurement_method": payload.get(
                "measurement_method", self.default_measurement_method
            ),
        }

        try:
            return CanonicalEvidence(**evidence_fields)
        except ValidationError as exc:
            raise EvidenceQuarantineError(
                "canonical_validation_failed",
                f"Provider payload failed canonical evidence validation: {exc}",
                payload=payload,
            ) from exc

    def normalize_batch(
        self, payloads: list[dict[str, Any]], *, context: TakeoffContext
    ) -> ProviderNormalizationResult:
        """Normalize many payloads, quarantining any that cannot be mapped."""
        result = ProviderNormalizationResult(provider=self.provider_kind)
        for payload in payloads:
            try:
                result.evidence.append(self.normalize(payload, context=context))
            except EvidenceQuarantineError as exc:
                result.quarantined.append(
                    QuarantinedPayload(
                        reason_code=exc.reason_code,
                        message=exc.message,
                        payload=exc.payload,
                    )
                )
        return result


# ---------------------------------------------------------------------------
# Concrete provider shells
# ---------------------------------------------------------------------------
class MobiNativeTakeoffProvider(TakeoffProvider):
    """Mobi's own extraction pipeline. Emits model candidates by default."""

    provider_kind = TakeoffProviderKind.MOBI_NATIVE
    default_evidence_class = EvidenceClass.MODEL_CANDIDATE
    default_measurement_method = MeasurementMethod.MODEL_INFERENCE


class OpenTakeoffProvider(TakeoffProvider):
    """An OpenTakeoff digital-measurement import.

    OpenTakeoff produces measured digital takeoff quantities, so its evidence is
    ``measured`` via ``digital_measurement`` by default. Like every provider it
    only maps explicitly allowed keys — an OpenTakeoff export field that is not a
    canonical field quarantines the payload rather than being synonym-mapped.
    """

    provider_kind = TakeoffProviderKind.OPEN_TAKEOFF
    default_evidence_class = EvidenceClass.MEASURED
    default_measurement_method = MeasurementMethod.DIGITAL_MEASUREMENT


class ManualTakeoffImportProvider(TakeoffProvider):
    """A human manually entering/importing takeoff quantities."""

    provider_kind = TakeoffProviderKind.MANUAL_IMPORT
    default_evidence_class = EvidenceClass.MEASURED
    default_measurement_method = MeasurementMethod.MANUAL_ENTRY


class CustomerSuppliedProvider(TakeoffProvider):
    """A customer supplying/declaring their own takeoff quantities.

    The provenance is ``customer_supplied`` via ``customer_declaration``: the
    quantity came from the customer, not from a Mobi measurement, and must never
    be mistaken for a reviewed measurement until a human verifies it.
    """

    provider_kind = TakeoffProviderKind.CUSTOMER_SUPPLIED
    default_evidence_class = EvidenceClass.CUSTOMER_SUPPLIED
    default_measurement_method = MeasurementMethod.CUSTOMER_DECLARATION


class HumanVerifiedTakeoffProvider(TakeoffProvider):
    """A reviewer-confirmed takeoff entry."""

    provider_kind = TakeoffProviderKind.HUMAN_VERIFIED
    default_evidence_class = EvidenceClass.HUMAN_VERIFIED
    default_measurement_method = MeasurementMethod.DIGITAL_MEASUREMENT


class AuthorizedThirdPartyProvider(TakeoffProvider):
    """An authorized external takeoff tool integration."""

    provider_kind = TakeoffProviderKind.AUTHORIZED_THIRD_PARTY
    default_evidence_class = EvidenceClass.MEASURED
    default_measurement_method = MeasurementMethod.DIGITAL_MEASUREMENT


class FutureCadBimProvider(TakeoffProvider):
    """Placeholder for a future CAD/BIM importer.

    Until the importer is real, its evidence is explicitly ``unsupported`` so it
    can never be mistaken for delivery-grade measurement.
    """

    provider_kind = TakeoffProviderKind.FUTURE_CAD_BIM
    default_evidence_class = EvidenceClass.UNSUPPORTED
    default_measurement_method = MeasurementMethod.NONE


class FutureThirdPartyProvider(TakeoffProvider):
    """Placeholder for a not-yet-implemented third-party takeoff integration.

    The provider exists so the lane is named and addressable, but until a real
    adapter is implemented its evidence is explicitly ``unsupported`` — it can
    never masquerade as delivery-grade measurement just because it validated.
    """

    provider_kind = TakeoffProviderKind.FUTURE_THIRD_PARTY
    default_evidence_class = EvidenceClass.UNSUPPORTED
    default_measurement_method = MeasurementMethod.NONE
