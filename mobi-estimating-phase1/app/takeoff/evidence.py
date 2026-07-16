"""Canonical, versioned takeoff-evidence contract.

``CanonicalEvidence`` is the single typed shape every takeoff provider must emit.
It is intentionally trade-agnostic and provider-agnostic: the provenance of a
measurement (who/what produced it, how it was measured, and whether a human has
verified it) is expressed through controlled enums, not free text, so downstream
gates can reason about evidence maturity without string/synonym matching.

Like ``app.extraction.schemas``, this model forbids unknown fields and uses
lenient enum coercion (``use_enum_values``) so controlled enum strings parse
cleanly across the API/provider/DB boundary. It does **not** replace the strict
canonical estimating schemas in ``app.schemas``; it feeds them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.estimating.units import Unit

CANONICAL_EVIDENCE_SCHEMA_VERSION = "takeoff_evidence_v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceModel(BaseModel):
    """Shared base: forbid unknown fields; lenient enum coercion."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------
class EvidenceClass(str, Enum):
    """How a piece of takeoff evidence came to exist.

    This is a *closed* set. A payload whose class is not one of these values
    fails schema validation; providers must map to one of these classes rather
    than inventing a synonym.
    """

    MEASURED = "measured"
    FORMULA_DERIVED = "formula_derived"
    SCHEDULE_EXTRACTED = "schedule_extracted"
    SPECIFICATION_EXTRACTED = "specification_extracted"
    CUSTOMER_SUPPLIED = "customer_supplied"
    HUMAN_VERIFIED = "human_verified"
    VENDOR_QUOTE = "vendor_quote"
    COST_BOOK = "cost_book"
    ALLOWANCE = "allowance"
    MODEL_CANDIDATE = "model_candidate"
    TEST_FIXTURE = "test_fixture"
    UNSUPPORTED = "unsupported"


# Closed set of every valid evidence class (stable, sorted for API surfaces).
EVIDENCE_CLASSES: frozenset[EvidenceClass] = frozenset(EvidenceClass)

# Evidence classes that must never be treated as human-reviewed simply because
# they validated. These are model/test/unsupported provenance: valid evidence
# rows, but only a real review can promote them to human-verified status.
NON_HUMAN_REVIEWED_EVIDENCE_CLASSES: frozenset[EvidenceClass] = frozenset({
    EvidenceClass.MODEL_CANDIDATE,
    EvidenceClass.TEST_FIXTURE,
    EvidenceClass.UNSUPPORTED,
})


class MeasurementMethod(str, Enum):
    """The mechanism that produced the quantity, independent of provider."""

    DIGITAL_MEASUREMENT = "digital_measurement"
    FORMULA = "formula"
    SCHEDULE_COUNT = "schedule_count"
    SPECIFICATION = "specification"
    CUSTOMER_DECLARATION = "customer_declaration"
    MANUAL_ENTRY = "manual_entry"
    VENDOR_QUOTE = "vendor_quote"
    COST_BOOK_LOOKUP = "cost_book_lookup"
    ALLOWANCE_ESTIMATE = "allowance_estimate"
    MODEL_INFERENCE = "model_inference"
    NONE = "none"


class TakeoffProviderKind(str, Enum):
    """Which provider lane produced the evidence."""

    MOBI_NATIVE = "mobi_native"
    OPEN_TAKEOFF = "open_takeoff"
    MANUAL_IMPORT = "manual_import"
    HUMAN_VERIFIED = "human_verified"
    CUSTOMER_SUPPLIED = "customer_supplied"
    AUTHORIZED_THIRD_PARTY = "authorized_third_party"
    FUTURE_CAD_BIM = "future_cad_bim"
    FUTURE_THIRD_PARTY = "future_third_party"
    UNKNOWN = "unknown"


class EvidenceReviewStatus(str, Enum):
    """Human-review state of a single evidence row.

    Kept aligned with ``app.extraction.schemas.ReviewStatus`` values so the two
    contracts stay interoperable, but owned here so the takeoff package does not
    depend on extraction internals.
    """

    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    BLOCKED = "blocked"


# Review states that represent an affirmative human decision on the row.
_HUMAN_DECIDED_STATES: frozenset[EvidenceReviewStatus] = frozenset({
    EvidenceReviewStatus.APPROVED,
    EvidenceReviewStatus.CORRECTED,
})


# ---------------------------------------------------------------------------
# Canonical evidence
# ---------------------------------------------------------------------------
class CanonicalEvidence(EvidenceModel):
    """The single typed evidence row every takeoff provider must emit."""

    schema_version: Literal["takeoff_evidence_v1"] = CANONICAL_EVIDENCE_SCHEMA_VERSION
    evidence_id: UUID = Field(default_factory=uuid4)

    # Tenancy / document coordinates -----------------------------------------
    tenant_id: UUID
    company_id: UUID
    project_id: UUID
    document_id: UUID
    sheet_id: UUID
    page_number: int = Field(ge=1)
    region_coordinates: tuple[float, float, float, float] | None = None

    # Provenance -------------------------------------------------------------
    takeoff_provider: TakeoffProviderKind
    provider_record_id: str = Field(min_length=1, max_length=256)
    evidence_class: EvidenceClass
    measurement_method: MeasurementMethod

    # Scope / measurement ----------------------------------------------------
    trade: str = Field(min_length=1, max_length=64)
    scope_category: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1000)
    quantity: Decimal | None = None
    unit: Unit | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)

    # Takeoff measurement provenance (provider-neutral, free of synonym mapping).
    # ``condition`` names the takeoff condition/measurement style a digital tool
    # recorded the quantity under; ``scale`` records the drawing scale the region
    # was measured at. Both are optional so providers that cannot express them
    # (manual entry, customer declarations) simply omit them.
    condition: str | None = Field(default=None, min_length=1, max_length=128)
    scale: str | None = Field(default=None, min_length=1, max_length=64)

    # Review -----------------------------------------------------------------
    review_status: EvidenceReviewStatus = EvidenceReviewStatus.PENDING
    reviewed_by: str | None = Field(default=None, max_length=128)

    # Lineage / timestamps ---------------------------------------------------
    extractor_version: str = Field(min_length=1, max_length=64)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_human_reviewed(self) -> bool:
        """True only when a human affirmatively decided this row.

        ``use_enum_values`` stores enum members as their string values, so this
        compares against the underlying values. Model/test/unsupported classes
        are never human-reviewed merely by validating; they must reach an
        approved/corrected review state and name a reviewer first.
        """
        return (
            self.review_status in {s.value for s in _HUMAN_DECIDED_STATES}
            and bool(self.reviewed_by)
        )
