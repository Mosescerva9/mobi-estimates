"""Dedicated, strict-safe output schemas for the live GPT-5.6 extraction path.

The legacy provider response contracts in :mod:`app.extraction.provider_schemas`
are unsafe to hand to a live model as an OpenAI Structured-Outputs
``text_format``:

* they carry model-authored ``Decimal`` quantity/confidence fields — but the live
  model must NEVER output a measurement, quantity, dimension, unit cost, price, or
  numeric confidence;
* they use ``dict[str, Any]`` free-form maps, which produce
  ``additionalProperties: true`` and are rejected by strict Structured Outputs;
* they carry Pydantic ``default`` values, which emit JSON-Schema ``default``
  keywords that strict Structured Outputs also rejects.

These dedicated schemas are what the live model actually fills in. They are
closed (``extra="forbid"``), fully default-free (every field required; optional
facts are ``X | None`` emitted explicitly), and contain **no** numeric
quantity/price/confidence field at all. The provider adapts them into the
existing caller contract server-side, leaving quantities null and constructing
all evidence/source metadata itself — the model never authors that metadata.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

LIVE_EXTRACTION_SCHEMA_VERSION = "1.0"


class LiveExtractionModel(BaseModel):
    """Base: unknown keys forbidden, enums serialized as their string values."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# Bounded free-text helpers (mirror the analysis-layer bounds).
_ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
_MediumText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
_LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
_QuoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class LiveSheetRelevance(str, Enum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    UNCERTAIN = "uncertain"


# --- Classification --------------------------------------------------------
class LiveSheetClassificationItem(LiveExtractionModel):
    """One sheet relevance decision, keyed by the page locator the model saw.

    The model is only ever shown ``page`` / ``sheet_number`` — never the internal
    sheet UUID — so it keys by ``pdf_page_number``; the server maps that back to a
    verified sheet id. ``reason`` is required-nullable free text (no default).
    """

    pdf_page_number: Annotated[int, Field(ge=1, le=100_000)]
    relevance: LiveSheetRelevance
    reason: _MediumText | None


class LiveSheetClassificationOutput(LiveExtractionModel):
    classifications: list[LiveSheetClassificationItem] = Field(max_length=1000)


# --- Scope -----------------------------------------------------------------
class LiveScopeEvidence(LiveExtractionModel):
    """A grounding anchor for a scope candidate: a page plus a required verbatim
    quote from that supplied page. The server verifies the normalized quote is an
    exact substring before adapting/persisting the candidate. No numeric field
    exists here by design."""

    pdf_page_number: Annotated[int, Field(ge=1, le=100_000)]
    quote: _QuoteText


class LiveScopeCandidate(LiveExtractionModel):
    """A candidate scope item. Purely descriptive — it has NO quantity, unit,
    price, or confidence field. The server supplies a null quantity and all
    evidence metadata; the model only describes and cites."""

    category_code: _ShortText
    description: _LongText
    location: _ShortText | None
    evidence: list[LiveScopeEvidence] = Field(min_length=1, max_length=100)
    assumptions: list[_LongText] = Field(max_length=100)
    exclusions: list[_LongText] = Field(max_length=100)


class LiveScopeExtractionOutput(LiveExtractionModel):
    trade_code: _ShortText
    candidates: list[LiveScopeCandidate] = Field(max_length=1000)
