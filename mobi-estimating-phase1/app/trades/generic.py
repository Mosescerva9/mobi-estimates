"""Automation-first generic all-trade lane.

This module is deliberately broad. It is not a replacement for trade-specific
modules; it is the structured fallback lane that lets Mobi account for every
trade in a whole-project estimate without silently omitting weak or unmatured
trade coverage.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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

GENERIC_TRADE_CODE = "general_trade"
GENERIC_MODULE_VERSION = "0.1.0"
GENERIC_SCHEMA_VERSION = "1.0"

GENERIC_CATEGORIES = [
    "generic_scope",
    "assembly_or_system",
    "allowance",
    "quote_based",
    "customer_confirmation_needed",
    "exclusion",
]
GENERIC_UNITS = [
    Unit.EACH,
    Unit.SQUARE_FOOT,
    Unit.LINEAR_FOOT,
    Unit.CUBIC_YARD,
    Unit.SQUARE,
    Unit.TON,
]


class GenericTradeData(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    source_trade_code: str | None = Field(default=None, max_length=64)
    source_trade_name: str | None = Field(default=None, max_length=128)
    pricing_method: str | None = Field(
        default=None,
        description="cost_book | generic_unit_price | quote | allowance | customer_provided | blocked",
    )
    quantity_method: str | None = Field(
        default=None,
        description="drawing | schedule | formula | allowance | quote | customer_confirmation | blocked",
    )
    confidence_note: str | None = Field(default=None, max_length=1000)


class GenericTradeModule(TradeModule):
    trade_code = GENERIC_TRADE_CODE
    trade_name = "Generic all-trade automation lane"
    module_version = GENERIC_MODULE_VERSION
    schema_version = GENERIC_SCHEMA_VERSION
    review_threshold = 0.75

    def get_definition(self) -> TradeDefinition:
        return TradeDefinition(
            trade_code=self.trade_code,
            trade_name=self.trade_name,
            csi_divisions=[
                "01", "02", "03", "04", "05", "06", "07", "08", "09",
                "10", "11", "12", "13", "14", "21", "22", "23", "26",
                "27", "28", "31", "32", "33",
            ],
            description=(
                "Automation-first fallback lane for all trades before a "
                "trade-specific module is mature. It carries scope, basis, "
                "confidence, allowance/quote/clarification decisions, and "
                "customer-visible assumptions without pretending bespoke "
                "trade automation exists."
            ),
            enabled=True,
            module_version=self.module_version,
            schema_version=self.schema_version,
            scope_categories=list(GENERIC_CATEGORIES),
            quantity_types=["count", "area", "length", "volume", "weight", "allowance"],
            supported_units=list(GENERIC_UNITS),
            required_evidence_rules={"allow_customer_visible_basis_without_sheet": True},
            review_threshold=self.review_threshold,
            prompt_versions={"scope_extractor": "generic-v1"},
        )

    def get_scope_categories(self) -> list[str]:
        return list(GENERIC_CATEGORIES)

    def get_allowed_units(self) -> list[Unit]:
        return list(GENERIC_UNITS)

    def route_sheet(self, sheet: SheetContext) -> SheetRoutingResult:
        if not sheet.verified_sheet_number:
            return SheetRoutingResult(
                RoutingStatus.BLOCKED_UNVERIFIED,
                "Generic lane requires verified sheet identity before use.",
            )
        if sheet.requires_ocr:
            return SheetRoutingResult(
                RoutingStatus.BLOCKED_OCR,
                "Sheet requires OCR; generic lane cannot rely on hidden text.",
            )
        return SheetRoutingResult(
            RoutingStatus.REQUIRES_REVIEW,
            "Generic all-trade lane can consider this verified sheet for coverage.",
        )

    def validate_trade_data(
        self, payload: dict[str, Any], *, schema_version: str | None = None
    ) -> dict[str, Any]:
        if schema_version is not None and schema_version != self.schema_version:
            raise ValueError(f"Unsupported schema version '{schema_version}'")
        return GenericTradeData.model_validate(payload).model_dump(mode="json")

    def validate_candidate(self, candidate: CandidateContext) -> ValidationResult:
        errors: list[str] = []
        blocking: list[BlockingIssue] = []
        if candidate.category_code not in GENERIC_CATEGORIES:
            errors.append(f"Unknown generic category '{candidate.category_code}'")
        allowed_units = {unit.value for unit in GENERIC_UNITS}
        if candidate.unit is not None and candidate.unit not in allowed_units:
            blocking.append(
                BlockingIssue(
                    code="unsupported_unit",
                    message=f"Unit '{candidate.unit}' not allowed for generic trade lane",
                )
            )
        try:
            normalized = self.validate_trade_data(candidate.trade_data)
        except ValueError as exc:
            errors.append(f"Invalid generic trade_data: {exc}")
            normalized = {}
        if candidate.evidence_count < 1 and candidate.category_code not in {
            "allowance",
            "quote_based",
            "customer_confirmation_needed",
            "exclusion",
        }:
            blocking.append(
                BlockingIssue(
                    code="missing_basis_or_evidence",
                    message="Generic scope needs evidence or a customer-visible basis.",
                )
            )
        requires_review = bool(blocking) or (
            candidate.confidence is not None and candidate.confidence < self.review_threshold
        )
        return ValidationResult(
            ok=not errors,
            normalized_trade_data=normalized,
            errors=errors,
            blocking_issues=blocking,
            requires_review=requires_review,
        )

    def get_quantity_formulas(self) -> list[QuantityFormula]:
        return []

    def category_requires_quantity(self, category_code: str) -> bool:
        return category_code not in {"exclusion", "customer_confirmation_needed"}

    def allowed_quantity_bases(self, category_code: str) -> set[QuantityBasis]:
        return {
            QuantityBasis.EXPLICIT_PLAN_QUANTITY,
            QuantityBasis.SCHEDULE_COUNT,
            QuantityBasis.DIMENSION_INPUTS,
            QuantityBasis.DETERMINISTIC_DERIVATION,
            QuantityBasis.MANUAL_REVIEWER_ENTRY,
            QuantityBasis.SUPPLIER_QUOTE_QUANTITY,
            QuantityBasis.UNKNOWN,
        }

    def get_prompt_version(self, task_type: str) -> str:
        return "generic-v1"

    def get_prompt(self, task_type: str) -> str:
        return (
            "TASK: Generic all-trade scope candidate drafting. Return ONLY "
            "schema-valid structured data. Do NOT calculate prices. Do NOT "
            "invent rates, quantities, materials, or scope. Preserve uncertainty "
            "as allowance, quote-based, customer_confirmation_needed, exclusion, "
            "or blocked. Cite source evidence when present."
        )


__all__ = ["GenericTradeModule", "GENERIC_TRADE_CODE"]
