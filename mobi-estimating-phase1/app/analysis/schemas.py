"""Strict Pydantic schemas for GPT-5.6 structured project analysis.

Design guarantees:

* ``extra="forbid"`` everywhere — the model cannot smuggle unknown keys past
  validation.
* Every string/list is bounded so a runaway or adversarial response cannot
  balloon downstream storage.
* There is **no** numeric measurement, quantity, unit-cost, price, arithmetic, or
  final-total field anywhere in this analysis schema. The layer describes and
  flags; it never authors numbers. Any figure that appears in the source stays as
  verbatim text inside a bounded description/quote and is always paired with a
  source reference — it is never re-expressed as a structured numeric value the
  system might later mistake for an estimate.
* Provider metadata (model alias, reasoning effort, request/response ids, schema
  version) is captured separately and is explicitly *not* estimate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

PROJECT_ANALYSIS_SCHEMA_VERSION = "1.0"


class AnalysisModel(BaseModel):
    """Base model: unknown fields forbidden, enum values serialized as strings."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# Bounded free-text helpers -------------------------------------------------
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
MediumText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


# Enumerations --------------------------------------------------------------
class ProjectType(str, Enum):
    COMMERCIAL = "commercial"
    RESIDENTIAL = "residential"
    CIVIL = "civil"
    INDUSTRIAL = "industrial"
    INSTITUTIONAL = "institutional"
    MIXED_USE = "mixed_use"
    RENOVATION = "renovation"
    OTHER = "other"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class RiskSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class RfiPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MissingDocumentImpact(str, Enum):
    BLOCKING = "blocking"
    SIGNIFICANT = "significant"
    MINOR = "minor"
    UNKNOWN = "unknown"


# Source grounding ----------------------------------------------------------
class AnalysisSourceReference(AnalysisModel):
    """A grounding anchor for an important finding.

    At least one locator (document id/name, page, or sheet) must be present so a
    finding can never claim to be "from the documents" with no way to check it.
    The optional ``quote`` is a bounded verbatim snippet from the supplied source.
    """

    document_id: Annotated[str, StringConstraints(max_length=128)] | None
    document_name: Annotated[str, StringConstraints(max_length=256)] | None
    page_number: Annotated[int, Field(ge=1, le=100_000)] | None
    sheet_number: Annotated[str, StringConstraints(max_length=64)] | None
    quote: Annotated[str, StringConstraints(max_length=2000)] | None

    @model_validator(mode="after")
    def _require_a_locator(self) -> "AnalysisSourceReference":
        if not any(
            (
                self.document_id,
                self.document_name,
                self.page_number is not None,
                self.sheet_number,
            )
        ):
            raise ValueError(
                "source reference requires at least one locator (document id/name, "
                "page, or sheet)"
            )
        return self


class SourcedText(AnalysisModel):
    """A single factual value paired with a mandatory source reference.

    Used for factual bid-document claims — the top-level identity facts
    (project/customer/location/bid date), and the individual identified trades and
    relevant plan sheets. Because the reference is required, such a directly-stated
    fact can never be asserted without a grounding anchor the server can verify
    against the supplied documents.
    """

    value: MediumText
    source_reference: AnalysisSourceReference


class SourcedProjectType(AnalysisModel):
    """The project type as a sourced fact: an enum value plus a mandatory,
    server-verifiable source reference.

    Project type is a factual classification of the bid documents, not a reviewer
    assumption, so it can never be asserted without a grounding anchor. When the
    documents do not establish a type, the top-level ``project_type`` is ``null``
    rather than a guessed value.
    """

    value: ProjectType
    source_reference: AnalysisSourceReference


# Nested findings -----------------------------------------------------------
# Every field below is REQUIRED (no Pydantic defaults). Optional facts are
# expressed as ``X | None`` and must be emitted explicitly (as ``null`` when
# absent). This keeps the generated JSON Schema free of ``default`` keywords,
# which OpenAI strict Structured Outputs rejects, and forces the model to make an
# explicit choice for every field rather than inheriting a silent default.
class SheetIndexEntry(AnalysisModel):
    """One sheet-index row. A sheet index is a factual claim about the drawing set,
    so each entry carries a required, server-verifiable source reference."""

    sheet_number: ShortText
    title: MediumText | None
    discipline: ShortText | None
    source_reference: AnalysisSourceReference


class SpecificationSection(AnalysisModel):
    """One specification section. A cited spec section is a factual document claim,
    so its source reference is required (never null)."""

    section_number: Annotated[str, StringConstraints(max_length=32)] | None
    title: MediumText | None
    source_reference: AnalysisSourceReference


class ScopeObservation(AnalysisModel):
    """A scope item observed in (or inferred from) the source.

    ``observed_in_source`` distinguishes a directly stated fact from an
    assumption/inference so downstream reviewers never treat the two the same. It
    is required (never defaulted true) so the model must commit to whether the
    item is grounded. A directly observed item (``observed_in_source`` true) MUST
    carry a ``source_reference``; an inferred/assumed item may set
    ``observed_in_source`` false and omit the reference — but such items belong in
    ``assumptions``/``recommended_rfis``, not asserted here as fact. No
    quantity/measurement/price field exists here by design.
    """

    trade: ShortText | None
    description: LongText
    observed_in_source: bool
    source_reference: AnalysisSourceReference | None

    @model_validator(mode="after")
    def _observed_requires_reference(self) -> "ScopeObservation":
        if self.observed_in_source and self.source_reference is None:
            raise ValueError(
                "a scope item marked observed_in_source must carry a source reference"
            )
        return self


class Alternate(AnalysisModel):
    identifier: Annotated[str, StringConstraints(max_length=64)] | None
    description: LongText
    source_reference: AnalysisSourceReference


class Allowance(AnalysisModel):
    identifier: Annotated[str, StringConstraints(max_length=64)] | None
    description: LongText
    source_reference: AnalysisSourceReference


class UnitRequirement(AnalysisModel):
    description: LongText
    source_reference: AnalysisSourceReference


class BidInstruction(AnalysisModel):
    description: LongText
    source_reference: AnalysisSourceReference


class Exclusion(AnalysisModel):
    """A project exclusion. An exclusion is a factual bid-document claim (something
    the documents state is out of scope), so it carries a required source
    reference — unlike a reviewer ``assumption``, which is unsourced."""

    description: LongText
    source_reference: AnalysisSourceReference


class MissingDocument(AnalysisModel):
    document_type: MediumText
    description: LongText | None
    impact: MissingDocumentImpact


class PlanSpecConflict(AnalysisModel):
    """A conflict between the plans and the specifications. A conflict cannot be
    established without both sides, so BOTH ``plan_reference`` and
    ``spec_reference`` are required and server-verified."""

    description: LongText
    severity: RiskSeverity
    plan_reference: AnalysisSourceReference
    spec_reference: AnalysisSourceReference


class RecommendedRfi(AnalysisModel):
    question: LongText
    rationale: LongText | None
    priority: RfiPriority
    source_reference: AnalysisSourceReference | None


class RiskFlag(AnalysisModel):
    description: LongText
    severity: RiskSeverity
    source_reference: AnalysisSourceReference | None


# Top-level analysis --------------------------------------------------------
class ProjectAnalysis(AnalysisModel):
    """Structured, source-grounded project analysis. Purely descriptive: it holds
    no numeric measurements, prices, or totals — only observed facts, flagged
    risks, missing information, and grounded references.

    Note: this model carries NO ``schema_version`` field. The schema version is
    operational provenance and is injected server-side into
    :class:`ProviderCallMetadata` after a successful parse — never authored by the
    model — so it cannot be spoofed and so the output schema stays default-free.
    """

    # Important top-level identity facts are sourced: each present value carries a
    # required, server-verifiable source reference (or is null when unknown).
    project_name: SourcedText | None
    customer_name: SourcedText | None
    project_location: SourcedText | None
    # Verbatim text exactly as stated in the source; never parsed into a calendar
    # date or inferred when absent — and always paired with a source reference.
    bid_due_date: SourcedText | None
    # Project type is a sourced fact (enum value + required reference) or null when
    # the documents do not establish one — never a bare, unsourced guess.
    project_type: SourcedProjectType | None

    sheet_index: list[SheetIndexEntry] = Field(max_length=1000)
    specification_sections: list[SpecificationSection] = Field(max_length=1000)
    # Trades and relevant plan sheets are factual document claims, so each is a
    # sourced value rather than a bare string.
    identified_trades: list[SourcedText] = Field(max_length=200)
    scope_items: list[ScopeObservation] = Field(max_length=1000)
    alternates: list[Alternate] = Field(max_length=200)
    allowances: list[Allowance] = Field(max_length=200)
    unit_requirements: list[UnitRequirement] = Field(max_length=200)
    relevant_plan_sheets: list[SourcedText] = Field(max_length=1000)
    bid_instructions: list[BidInstruction] = Field(max_length=200)
    missing_documents: list[MissingDocument] = Field(max_length=200)
    plan_spec_conflicts: list[PlanSpecConflict] = Field(max_length=200)
    recommended_rfis: list[RecommendedRfi] = Field(max_length=200)
    # Reviewer assumptions stay unsourced; exclusions are factual bid claims and
    # are sourced.
    assumptions: list[LongText] = Field(max_length=200)
    exclusions: list[Exclusion] = Field(max_length=200)
    risk_flags: list[RiskFlag] = Field(max_length=200)

    confidence_level: ConfidenceLevel
    source_references: list[AnalysisSourceReference] = Field(max_length=1000)


# Provider metadata ---------------------------------------------------------
class ProviderCallMetadata(AnalysisModel):
    """Proof-of-provenance for a single model call.

    This is operational/audit metadata, NOT estimate evidence: it proves *which*
    model alias and reasoning effort produced the structured output, plus safe
    provider request/response ids and the schema version. Callers must never treat
    any field here as a measurement, price, approval, or delivery signal.
    """

    provider: str = "openai"
    api: str = "responses"
    requested_model: ShortText
    returned_model: ShortText | None = None
    reasoning_effort: ShortText
    schema_version: ShortText
    response_id: Annotated[str, StringConstraints(max_length=256)] | None = None
    request_id: Annotated[str, StringConstraints(max_length=256)] | None = None
    parse_success: bool = False
    # Token counts only — never any content.
    usage: dict[str, int] = Field(default_factory=dict)


@dataclass(frozen=True)
class ParsedResult:
    """A validated parse plus its provenance metadata."""

    parsed: Any
    metadata: ProviderCallMetadata
