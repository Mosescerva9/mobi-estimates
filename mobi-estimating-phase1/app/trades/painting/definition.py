"""Painting trade module — the first reference implementation of TradeModule."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.estimating.quantities import QuantityBasis, QuantityFormula
from app.estimating.units import Unit
from app.extraction.schemas import Conflict
from app.trades.base import (
    CandidateContext,
    SheetContext,
    SheetRoutingResult,
    TradeDefinition,
    TradeModule,
    ValidationResult,
)
from app.trades.painting.assemblies import (
    map_painting_scope,
    painting_assembly_templates,
    validate_painting_pricing_inputs,
)
from app.trades.painting.conflicts import detect_painting_conflicts
from app.trades.painting.quantities import painting_formulas
from app.trades.painting.routing import route_painting_sheet
from app.trades.painting.schemas import (
    PAINTING_ALLOWED_UNITS,
    PAINTING_MODULE_VERSION,
    PAINTING_SCHEMA_VERSION,
    PAINTING_TRADE_CODE,
    PaintingCategory,
)
from app.trades.painting.validation import (
    category_requires_quantity,
    validate_painting_candidate,
    validate_painting_trade_data,
)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_PROMPT_FILES = {
    "sheet_classifier": "sheet_classifier_v1.txt",
    "schedule_extractor": "schedule_extractor_v1.txt",
    "notes_extractor": "notes_extractor_v1.txt",
    "scope_extractor": "scope_extractor_v1.txt",
}
_PROMPT_VERSIONS = {task: "v1" for task in _PROMPT_FILES}


@lru_cache(maxsize=None)
def _read_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


class PaintingTradeModule(TradeModule):
    trade_code = PAINTING_TRADE_CODE
    trade_name = "Painting & Coatings"
    module_version = PAINTING_MODULE_VERSION
    schema_version = PAINTING_SCHEMA_VERSION
    review_threshold = 0.9

    def get_definition(self) -> TradeDefinition:
        return TradeDefinition(
            trade_code=self.trade_code,
            trade_name=self.trade_name,
            csi_divisions=["09"],
            description="Field and shop painting and coatings (CSI Division 09).",
            enabled=True,
            module_version=self.module_version,
            schema_version=self.schema_version,
            scope_categories=self.get_scope_categories(),
            quantity_types=["area", "length", "count"],
            supported_units=PAINTING_ALLOWED_UNITS,
            required_evidence_rules={"min_evidence_references": 1},
            review_threshold=self.review_threshold,
            prompt_versions=dict(_PROMPT_VERSIONS),
        )

    def get_scope_categories(self) -> list[str]:
        return [category.value for category in PaintingCategory]

    def get_allowed_units(self) -> list[Unit]:
        return list(PAINTING_ALLOWED_UNITS)

    def route_sheet(self, sheet: SheetContext) -> SheetRoutingResult:
        return route_painting_sheet(sheet)

    def validate_trade_data(
        self, payload: dict[str, Any], *, schema_version: str | None = None
    ) -> dict[str, Any]:
        return validate_painting_trade_data(payload, schema_version=schema_version)

    def validate_candidate(self, candidate: CandidateContext) -> ValidationResult:
        return validate_painting_candidate(
            candidate, review_threshold=self.review_threshold
        )

    def detect_conflicts(
        self, candidate: CandidateContext, related_items: list[dict[str, Any]]
    ) -> list[Conflict]:
        return detect_painting_conflicts(candidate, related_items)

    def get_quantity_formulas(self) -> list[QuantityFormula]:
        return painting_formulas()

    def category_requires_quantity(self, category_code: str) -> bool:
        return category_requires_quantity(category_code)

    def allowed_quantity_bases(self, category_code: str) -> set[QuantityBasis]:
        return {
            QuantityBasis.EXPLICIT_PLAN_QUANTITY,
            QuantityBasis.SCHEDULE_COUNT,
            QuantityBasis.SCHEDULE_LENGTH,
            QuantityBasis.SCHEDULE_AREA,
            QuantityBasis.DRAWING_COUNT,
            QuantityBasis.DIMENSION_INPUTS,
            QuantityBasis.DETERMINISTIC_DERIVATION,
            QuantityBasis.MANUAL_REVIEWER_ENTRY,
            QuantityBasis.UNKNOWN,
        }

    def get_prompt_version(self, task_type: str) -> str:
        if task_type not in _PROMPT_VERSIONS:
            raise KeyError(f"Unknown painting prompt task '{task_type}'")
        return _PROMPT_VERSIONS[task_type]

    def get_prompt(self, task_type: str) -> str:
        if task_type not in _PROMPT_FILES:
            raise KeyError(f"Unknown painting prompt task '{task_type}'")
        return _read_prompt(_PROMPT_FILES[task_type])

    # --- pricing (Phase 4) --------------------------------------------------
    def get_assembly_templates(self) -> list[dict[str, Any]]:
        return painting_assembly_templates()

    def map_scope_to_assembly(
        self, category_code: str, trade_data: dict[str, Any]
    ) -> list[str]:
        return map_painting_scope(category_code, trade_data)

    def validate_pricing_inputs(
        self, *, category_code: str, trade_data: dict[str, Any], assembly: dict[str, Any]
    ) -> list[str]:
        return validate_painting_pricing_inputs(
            category_code=category_code, trade_data=trade_data, assembly=assembly
        )
