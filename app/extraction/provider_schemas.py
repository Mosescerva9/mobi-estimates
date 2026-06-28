"""Provider request/response contracts.

Providers return *raw* data which the extraction service validates into these
models (``extra="forbid"`` → unknown fields rejected; missing required → malformed
rejected). Provider output is never trusted until validated here, then re-validated
by the trade module, and finally anchored to verified sheets server-side.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.estimating.quantities import QuantityBasis
from app.extraction.schemas import EvidenceType

PROVIDER_SCHEMA_VERSION = "1.0"


class ProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# --- Requests --------------------------------------------------------------
class ProviderSheetInput(ProviderModel):
    sheet_id: UUID
    pdf_page_number: int = Field(ge=1)
    verified_sheet_number: str | None = None
    verified_sheet_title: str | None = None
    embedded_text: str = ""


class SheetClassificationRequest(ProviderModel):
    trade_code: str
    prompt_version: str
    sheets: list[ProviderSheetInput]


class ScopeExtractionRequest(ProviderModel):
    trade_code: str
    prompt_version: str
    allowed_categories: list[str]
    allowed_units: list[str]
    sheets: list[ProviderSheetInput]


# --- Responses -------------------------------------------------------------
class ProviderSheetClassification(ProviderModel):
    sheet_id: UUID
    relevance: str  # relevant | not_relevant | uncertain
    reason: str = ""


class SheetClassificationResponse(ProviderModel):
    provider_schema_version: str = PROVIDER_SCHEMA_VERSION
    classifications: list[ProviderSheetClassification]


class ProviderEvidence(ProviderModel):
    pdf_page_number: int = Field(ge=1)
    # The sheet number the provider *claims*; NEVER trusted — the server replaces
    # it with the verified sheet number from the database.
    claimed_sheet_number: str | None = None
    evidence_type: EvidenceType
    description: str = Field(min_length=1, max_length=1000)
    extracted_text_quote: str | None = Field(default=None, max_length=4000)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)


class ProviderQuantity(ProviderModel):
    basis: QuantityBasis
    value: Decimal | None = None
    unit: str | None = None
    raw_inputs: dict[str, Any] = Field(default_factory=dict)
    formula_id: str | None = None


class ProviderScopeCandidate(ProviderModel):
    category_code: str
    description: str = Field(min_length=1, max_length=1000)
    location: str | None = None
    quantity: ProviderQuantity
    trade_data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[ProviderEvidence] = Field(min_length=1)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    assumptions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    conflicts_flagged: list[str] = Field(default_factory=list)


class ScopeExtractionResponse(ProviderModel):
    provider_schema_version: str = PROVIDER_SCHEMA_VERSION
    trade_code: str
    candidates: list[ProviderScopeCandidate] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
