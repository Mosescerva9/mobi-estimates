"""Demonstration second trade module (Concrete).

This module exists to prove the shared core is trade-agnostic: it uses a different
unit set, a different formula, and a different trade payload than Painting, with no
Painting-specific code path involved. It is NOT enabled in production unless
explicitly configured via ``MOBI_ENABLED_TRADES``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.estimating.formulas import (
    cubic_feet_to_cubic_yards,
    inches_to_feet,
    prism_volume,
)
from app.estimating.quantities import QuantityBasis, QuantityFormula
from app.estimating.units import Unit
from app.extraction.schemas import BlockingIssue, RoutingStatus
from app.trades.base import (
    CandidateContext,
    SheetContext,
    SheetRoutingResult,
    TradeDefinition,
    TradeModule,
    ValidationResult,
)

DEMO_CONCRETE_TRADE_CODE = "demo_concrete"
DEMO_CONCRETE_MODULE_VERSION = "0.1.0"
DEMO_CONCRETE_SCHEMA_VERSION = "1.0"

DEMO_CONCRETE_CATEGORIES = [
    "slab_on_grade",
    "foundation",
    "unclassified_concrete",
]
DEMO_CONCRETE_UNITS = [Unit.CUBIC_YARD, Unit.SQUARE_FOOT, Unit.LINEAR_FOOT]


class DemoConcreteTradeData(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    mix_design: str | None = Field(default=None, max_length=64)
    thickness_in: float | None = Field(default=None, ge=0)
    reinforcement: str | None = Field(default=None, max_length=128)


class SlabVolumeFormula(QuantityFormula):
    """Slab volume in cubic yards — a different unit/formula than any Painting one."""

    formula_id = "demo_concrete.slab_volume"
    version = "1.0"
    output_unit = Unit.CUBIC_YARD
    supported_trade_codes = frozenset({DEMO_CONCRETE_TRADE_CODE})
    required_inputs = ("length_ft", "width_ft", "thickness_in")

    def _compute(self, values: dict[str, Decimal]) -> Decimal:
        thickness_ft = inches_to_feet(values["thickness_in"])
        cubic_feet = prism_volume(values["length_ft"], values["width_ft"], thickness_ft)
        return cubic_feet_to_cubic_yards(cubic_feet)


class DemoConcreteTradeModule(TradeModule):
    trade_code = DEMO_CONCRETE_TRADE_CODE
    trade_name = "Concrete (demonstration)"
    module_version = DEMO_CONCRETE_MODULE_VERSION
    schema_version = DEMO_CONCRETE_SCHEMA_VERSION
    review_threshold = 0.9

    def get_definition(self) -> TradeDefinition:
        return TradeDefinition(
            trade_code=self.trade_code,
            trade_name=self.trade_name,
            csi_divisions=["03"],
            description="Demonstration concrete module proving trade-agnostic core.",
            enabled=True,
            module_version=self.module_version,
            schema_version=self.schema_version,
            scope_categories=list(DEMO_CONCRETE_CATEGORIES),
            quantity_types=["volume", "area"],
            supported_units=list(DEMO_CONCRETE_UNITS),
            required_evidence_rules={"min_evidence_references": 1},
            review_threshold=self.review_threshold,
            prompt_versions={"scope_extractor": "v1"},
        )

    def get_scope_categories(self) -> list[str]:
        return list(DEMO_CONCRETE_CATEGORIES)

    def get_allowed_units(self) -> list[Unit]:
        return list(DEMO_CONCRETE_UNITS)

    def route_sheet(self, sheet: SheetContext) -> SheetRoutingResult:
        if not sheet.verified_sheet_number:
            return SheetRoutingResult(
                RoutingStatus.BLOCKED_UNVERIFIED, "No verified sheet number."
            )
        if sheet.requires_ocr:
            return SheetRoutingResult(RoutingStatus.BLOCKED_OCR, "Requires OCR.")
        blob = " ".join(
            filter(None, [sheet.verified_sheet_number, sheet.verified_sheet_title or "",
                          sheet.embedded_text or ""])
        ).upper()
        if any(k in blob for k in ("CONCRETE", "SLAB", "FOUNDATION", "FOOTING")):
            return SheetRoutingResult(RoutingStatus.ELIGIBLE, "Concrete keyword found.")
        prefix = sheet.verified_sheet_number[:1].upper()
        if prefix in ("S", "C"):
            return SheetRoutingResult(
                RoutingStatus.REQUIRES_REVIEW,
                "Structural/civil sheet without explicit concrete keyword.",
            )
        return SheetRoutingResult(RoutingStatus.EXCLUDED, "No concrete signal.")

    def validate_trade_data(
        self, payload: dict[str, Any], *, schema_version: str | None = None
    ) -> dict[str, Any]:
        if schema_version is not None and schema_version != self.schema_version:
            raise ValueError(f"Unsupported schema version '{schema_version}'")
        return DemoConcreteTradeData.model_validate(payload).model_dump(mode="json")

    def validate_candidate(self, candidate: CandidateContext) -> ValidationResult:
        errors: list[str] = []
        blocking: list[BlockingIssue] = []
        if candidate.category_code not in DEMO_CONCRETE_CATEGORIES:
            errors.append(f"Unknown concrete category '{candidate.category_code}'")
        allowed_units = {u.value for u in DEMO_CONCRETE_UNITS}
        if candidate.unit is not None and candidate.unit not in allowed_units:
            blocking.append(
                BlockingIssue(code="unsupported_unit",
                              message=f"Unit '{candidate.unit}' not allowed for concrete")
            )
        normalized: dict[str, Any] = {}
        try:
            normalized = self.validate_trade_data(candidate.trade_data)
        except ValueError as exc:
            errors.append(f"Invalid concrete trade_data: {exc}")
        if candidate.evidence_count < 1:
            blocking.append(
                BlockingIssue(code="provider_response_lacks_evidence",
                              message="Candidate has no evidence reference")
            )
        requires_review = bool(blocking) or (
            candidate.confidence is not None
            and candidate.confidence < self.review_threshold
        )
        return ValidationResult(
            ok=not errors,
            normalized_trade_data=normalized,
            errors=errors,
            blocking_issues=blocking,
            requires_review=requires_review,
        )

    def get_quantity_formulas(self) -> list[QuantityFormula]:
        return [SlabVolumeFormula()]

    def category_requires_quantity(self, category_code: str) -> bool:
        return category_code != "unclassified_concrete"

    def allowed_quantity_bases(self, category_code: str) -> set[QuantityBasis]:
        return {
            QuantityBasis.DIMENSION_INPUTS,
            QuantityBasis.DETERMINISTIC_DERIVATION,
            QuantityBasis.EXPLICIT_PLAN_QUANTITY,
            QuantityBasis.MANUAL_REVIEWER_ENTRY,
            QuantityBasis.UNKNOWN,
        }

    def get_assembly_templates(self) -> list[dict[str, Any]]:
        from app.trades.demo_concrete.assemblies import concrete_assembly_templates
        return concrete_assembly_templates()

    def map_scope_to_assembly(
        self, category_code: str, trade_data: dict[str, Any]
    ) -> list[str]:
        from app.trades.demo_concrete.assemblies import map_concrete_scope
        return map_concrete_scope(category_code, trade_data)

    def validate_pricing_inputs(
        self, *, category_code: str, trade_data: dict[str, Any], assembly: dict[str, Any]
    ) -> list[str]:
        from app.trades.demo_concrete.assemblies import validate_concrete_pricing_inputs
        return validate_concrete_pricing_inputs(
            category_code=category_code, trade_data=trade_data, assembly=assembly
        )

    def get_prompt_version(self, task_type: str) -> str:
        return "v1"

    def get_prompt(self, task_type: str) -> str:
        return (
            "TASK: Concrete scope extraction (demonstration v1)\n"
            "Return ONLY schema-valid structured data. Do NOT calculate prices. "
            "Do NOT calculate derived quantities. Do NOT infer missing dimensions. "
            "Do NOT invent materials or scope. Cite every item to supplied evidence. "
            "Return null when information is absent. Flag conflicts."
        )


__all__ = ["DemoConcreteTradeModule", "DEMO_CONCRETE_TRADE_CODE"]
