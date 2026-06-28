"""Canonical, trade-agnostic extraction schemas (shared core).

These models are independent of any single trade. Trade-specific detail lives in a
validated ``trade_data`` payload owned by the applicable trade module. All models
forbid unknown fields. They are intentionally *not* in Pydantic ``strict`` mode (so
documented enum strings parse across the API/provider/DB boundary), and they do
**not** replace or weaken the strict canonical estimating schemas in
``app.schemas`` (e.g. ``SourceReference``), which remain the trusted source-of-truth
contract for downstream pricing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.estimating.quantities import QuantityBasis
from app.estimating.units import Unit


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CoreModel(BaseModel):
    """Shared base: forbid unknown fields; lenient enum/decimal coercion."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ExtractionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_EXTRACTION_STATES: frozenset[ExtractionStatus] = frozenset(
    {ExtractionStatus.QUEUED, ExtractionStatus.RUNNING}
)


class RoutingStatus(str, Enum):
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    BLOCKED_UNVERIFIED = "blocked_unverified"
    BLOCKED_OCR = "blocked_ocr"
    REQUIRES_REVIEW = "requires_review"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class ConflictSeverity(str, Enum):
    INFORMATION = "information"
    WARNING = "warning"
    BLOCKING = "blocking"


class SharedConflictCode(str, Enum):
    SCHEDULE_CONFLICTS_WITH_PLAN = "schedule_conflicts_with_plan"
    SPEC_CONFLICTS_WITH_DRAWING = "spec_conflicts_with_drawing"
    ADDENDUM_MAY_SUPERSEDE = "addendum_may_supersede"
    DUPLICATE_SCOPE_CANDIDATE = "duplicate_scope_candidate"
    MULTIPLE_QUANTITIES_FOR_SCOPE = "multiple_quantities_for_scope"
    MISSING_QUANTITY = "missing_quantity"
    MISSING_UNIT = "missing_unit"
    MISSING_DIMENSIONS = "missing_dimensions"
    MISSING_VERIFIED_SHEET = "missing_verified_sheet"
    OCR_REQUIRED = "ocr_required"
    UNSUPPORTED_UNIT = "unsupported_unit"
    UNSUPPORTED_FORMULA = "unsupported_formula"
    PROVIDER_RESPONSE_LACKS_EVIDENCE = "provider_response_lacks_evidence"
    QUANTITY_NOT_REPRODUCIBLE = "quantity_not_reproducible"
    TRADE_VALIDATION_FAILED = "trade_validation_failed"
    TRADE_CLASSIFICATION_UNCERTAIN = "trade_classification_uncertain"


class EvidenceType(str, Enum):
    SCHEDULE = "schedule"
    FINISH_SCHEDULE = "finish_schedule"
    ROOM_FINISH_SCHEDULE = "room_finish_schedule"
    DOOR_SCHEDULE = "door_schedule"
    EQUIPMENT_SCHEDULE = "equipment_schedule"
    FIXTURE_SCHEDULE = "fixture_schedule"
    GENERAL_NOTE = "general_note"
    KEYNOTE = "keynote"
    LEGEND = "legend"
    DRAWING_DIMENSION = "drawing_dimension"
    EXPLICIT_QUANTITY = "explicit_quantity"
    DETAIL = "detail"
    SECTION = "section"
    ELEVATION = "elevation"
    FLOOR_PLAN = "floor_plan"
    REFLECTED_CEILING_PLAN = "reflected_ceiling_plan"
    SPECIFICATION_NOTE = "specification_note"
    ADDENDUM = "addendum"
    REVIEWER_ENTRY = "reviewer_entry"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
class EvidenceReference(CoreModel):
    """A trusted, server-built reference anchoring a scope item to a verified sheet."""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    sheet_id: UUID
    pdf_page_number: int = Field(ge=1)
    # Always populated from the database sheet record, never from the provider.
    verified_sheet_number: str = Field(min_length=1, max_length=64)
    evidence_type: EvidenceType
    description: str = Field(min_length=1, max_length=1000)
    extracted_text_quote: str | None = Field(default=None, max_length=4000)
    text_block_coords: tuple[float, float, float, float] | None = None
    page_region_coords: tuple[float, float, float, float] | None = None
    source_artifact_ref: str | None = Field(default=None, max_length=512)
    provider_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    requires_human_verification: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------
class QuantityCandidate(CoreModel):
    """A proposed quantity. Transcribed values may come from a provider; derived
    values must be produced by the deterministic engine."""

    basis: QuantityBasis
    value: Decimal | None = Field(default=None)
    unit: Unit | None = None
    raw_inputs: dict[str, Any] = Field(default_factory=dict)
    formula_id: str | None = None
    source: str = Field(default="provider", max_length=32)


class QuantityDerivation(CoreModel):
    id: UUID = Field(default_factory=uuid4)
    scope_item_id: UUID
    trade_code: str
    formula_id: str
    formula_version: str
    inputs: dict[str, Any]
    output_value: Decimal
    output_unit: Unit
    calculated_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Conflicts / issues / notes
# ---------------------------------------------------------------------------
class Conflict(CoreModel):
    id: UUID = Field(default_factory=uuid4)
    scope_item_id: UUID | None = None
    code: str = Field(min_length=1, max_length=64)
    severity: ConflictSeverity
    description: str = Field(min_length=1, max_length=1000)
    competing_evidence: list[UUID] = Field(default_factory=list)
    resolution_status: str = Field(default="open", max_length=32)
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None


class BlockingIssue(CoreModel):
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class Assumption(CoreModel):
    text: str = Field(min_length=1, max_length=500)


class Exclusion(CoreModel):
    text: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Scope items
# ---------------------------------------------------------------------------
class ScopeItem(CoreModel):
    """Canonical, trade-agnostic scope item. Trade detail lives in ``trade_data``."""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    extraction_run_id: UUID
    trade_code: str = Field(min_length=2, max_length=64)
    trade_module_version: str
    trade_schema_version: str
    category_code: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1000)
    location: str | None = Field(default=None, max_length=255)
    specification_section: str | None = Field(default=None, max_length=64)
    assembly_designation: str | None = Field(default=None, max_length=128)
    material_or_substrate: str | None = Field(default=None, max_length=255)
    existing_condition: str | None = Field(default=None, max_length=255)
    proposed_work: str | None = Field(default=None, max_length=500)
    quantity: Decimal | None = None
    unit: Unit | None = None
    quantity_basis: QuantityBasis = QuantityBasis.UNKNOWN
    raw_quantity_inputs: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    extraction_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    conflict_status: str = Field(default="none", max_length=32)
    review_status: ReviewStatus = ReviewStatus.PENDING
    blocking_issues: list[BlockingIssue] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)
    trade_data: dict[str, Any] = Field(default_factory=dict)
    original_provider_candidate: dict[str, Any] = Field(default_factory=dict)
    calculation_id: str | None = None
    calculation_version: str | None = None
    reviewer_notes: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Runs / requests / results
# ---------------------------------------------------------------------------
class ExtractionRequest(CoreModel):
    force: bool = False
    selected_sheet_ids: list[UUID] | None = None
    use_live_provider: bool = False
    max_pages: int | None = Field(default=None, ge=1)
    dry_run: bool = False


class ProviderUsage(CoreModel):
    provider: str
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: Decimal | None = None


class ExtractionRun(CoreModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    trade_code: str
    status: ExtractionStatus = ExtractionStatus.QUEUED
    provider: str
    model_identifier: str | None = None
    prompt_version: str | None = None
    provider_schema_version: str | None = None
    trade_schema_version: str | None = None
    attempt: int = 1
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    input_sheet_count: int = 0
    processed_sheet_count: int = 0
    blocked_sheet_count: int = 0
    failed_sheet_count: int = 0
    candidate_count: int = 0
    usage: dict[str, Any] = Field(default_factory=dict)
    estimated_cost: Decimal | None = None
    dry_run: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SheetRoutingDecision(CoreModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    sheet_id: UUID
    trade_code: str
    extraction_run_id: UUID | None = None
    eligibility: RoutingStatus
    reason: str = Field(min_length=1, max_length=500)
    automatic: bool = True
    manual_override: RoutingStatus | None = None
    reviewer_notes: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def effective_status(self) -> RoutingStatus:
        return self.manual_override or self.eligibility


class ReviewEvent(CoreModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    scope_item_id: UUID
    trade_code: str
    action: str = Field(min_length=1, max_length=64)
    previous_state: str | None = None
    new_state: str | None = None
    reviewer_id: str = Field(default="system", max_length=128)
    reviewer_notes: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalResult(CoreModel):
    approved: bool
    scope_item_id: UUID
    review_status: ReviewStatus
    blocking_issues: list[BlockingIssue] = Field(default_factory=list)
