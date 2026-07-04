"""Trade-module interface — the contract every trade plugs into the shared core.

The shared core never contains ``if trade == "painting"`` logic. Instead it loads
behavior through this interface from the trade registry, so adding a future trade
means writing a new module, not editing the core.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.estimating.quantities import QuantityBasis, QuantityFormula
from app.estimating.units import Unit
from app.extraction.schemas import (
    BlockingIssue,
    Conflict,
    RoutingStatus,
)


class TradeDefinition(BaseModel):
    """Canonical, serializable description of a trade module."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    trade_code: str = Field(min_length=2, max_length=64)
    trade_name: str = Field(min_length=1, max_length=128)
    csi_divisions: list[str] | None = None
    description: str = Field(default="", max_length=1000)
    enabled: bool = True
    module_version: str
    schema_version: str
    scope_categories: list[str]
    quantity_types: list[str]
    supported_units: list[Unit]
    required_evidence_rules: dict[str, Any] = Field(default_factory=dict)
    review_threshold: float = 0.9
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Context objects passed into a trade module (plain dataclasses, not API models)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SheetContext:
    sheet_id: str
    project_id: str
    pdf_page_number: int
    verified_sheet_number: str | None
    verified_sheet_title: str | None
    detected_sheet_number: str | None
    detected_sheet_title: str | None
    embedded_text: str
    requires_ocr: bool
    requires_review: bool


@dataclass(frozen=True)
class CandidateContext:
    """A provider candidate (untrusted) presented to the trade module."""

    category_code: str
    description: str
    location: str | None
    quantity_basis: QuantityBasis
    quantity_value: Any | None
    unit: str | None
    raw_quantity_inputs: dict[str, Any]
    trade_data: dict[str, Any]
    evidence_count: int
    confidence: float | None


# ---------------------------------------------------------------------------
# Result objects returned by a trade module
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SheetRoutingResult:
    eligibility: RoutingStatus
    reason: str


@dataclass
class ValidationResult:
    ok: bool
    normalized_trade_data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    blocking_issues: list[BlockingIssue] = field(default_factory=list)
    requires_review: bool = False


class TradeModule(ABC):
    """Abstract base class for a trade module."""

    trade_code: str
    trade_name: str
    module_version: str
    schema_version: str

    # --- identity / definition ---------------------------------------------
    @abstractmethod
    def get_definition(self) -> TradeDefinition: ...

    @abstractmethod
    def get_scope_categories(self) -> list[str]: ...

    @abstractmethod
    def get_allowed_units(self) -> list[Unit]: ...

    # --- routing ------------------------------------------------------------
    @abstractmethod
    def route_sheet(self, sheet: SheetContext) -> SheetRoutingResult: ...

    # --- validation ---------------------------------------------------------
    @abstractmethod
    def validate_trade_data(
        self, payload: dict[str, Any], *, schema_version: str | None = None
    ) -> dict[str, Any]:
        """Validate/normalize a trade-specific payload. Raises on invalid data."""

    @abstractmethod
    def validate_candidate(self, candidate: CandidateContext) -> ValidationResult: ...

    # --- conflicts ----------------------------------------------------------
    def detect_conflicts(
        self, candidate: CandidateContext, related_items: list[dict[str, Any]]
    ) -> list[Conflict]:
        return []

    # --- quantities ---------------------------------------------------------
    @abstractmethod
    def get_quantity_formulas(self) -> list[QuantityFormula]: ...

    def category_requires_quantity(self, category_code: str) -> bool:
        return True

    def allowed_quantity_bases(self, category_code: str) -> set[QuantityBasis]:
        return set(QuantityBasis)

    # --- prompts ------------------------------------------------------------
    @abstractmethod
    def get_prompt_version(self, task_type: str) -> str: ...

    @abstractmethod
    def get_prompt(self, task_type: str) -> str: ...

    # --- pricing (Phase 4; default no-op so non-pricing trades still work) ---
    def get_assembly_templates(self) -> list[dict[str, Any]]:
        """Structural assembly templates (no prices). Default: none."""
        return []

    def map_scope_to_assembly(
        self, category_code: str, trade_data: dict[str, Any]
    ) -> list[str]:
        """Deterministic scope→assembly mapping. Returns candidate assembly codes
        (0 = unpriced, 1 = mapped, >1 with equal priority = conflict)."""
        return []

    def validate_pricing_inputs(
        self, *, category_code: str, trade_data: dict[str, Any], assembly: dict[str, Any]
    ) -> list[str]:
        """Trade-specific pricing validation. Returns a list of error strings."""
        return []
