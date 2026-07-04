"""Trade registry + trade-agnostic core tests (with a fake trade)."""

from __future__ import annotations

import pytest

from app.estimating.quantities import QuantityFormula
from app.estimating.units import Unit
from app.trades import TradeConfigurationError, bootstrap_trades
from app.trades.base import (
    CandidateContext,
    SheetContext,
    SheetRoutingResult,
    TradeDefinition,
    TradeModule,
    ValidationResult,
)
from app.extraction.schemas import RoutingStatus
from app.trades.registry import (
    DisabledTradeError,
    TradeRegistry,
    TradeRegistryError,
    UnknownTradeError,
)


class FakeTradeModule(TradeModule):
    """A minimal fake trade proving the core needs no Painting-specific logic."""

    trade_code = "fake_trade"
    trade_name = "Fake Trade"
    module_version = "9.9.9"
    schema_version = "1.0"

    def get_definition(self) -> TradeDefinition:
        return TradeDefinition(
            trade_code=self.trade_code, trade_name=self.trade_name,
            module_version=self.module_version, schema_version=self.schema_version,
            scope_categories=["fake_category"], quantity_types=["count"],
            supported_units=[Unit.EACH],
        )

    def get_scope_categories(self): return ["fake_category"]
    def get_allowed_units(self): return [Unit.EACH]

    def route_sheet(self, sheet: SheetContext) -> SheetRoutingResult:
        return SheetRoutingResult(RoutingStatus.ELIGIBLE, "fake always eligible")

    def validate_trade_data(self, payload, *, schema_version=None): return dict(payload)
    def validate_candidate(self, candidate: CandidateContext) -> ValidationResult:
        return ValidationResult(ok=True)
    def get_quantity_formulas(self) -> list[QuantityFormula]: return []
    def get_prompt_version(self, task_type: str) -> str: return "v1"
    def get_prompt(self, task_type: str) -> str: return "fake prompt"


def test_register_and_query():
    registry = TradeRegistry()
    registry.register(FakeTradeModule())
    assert registry.is_registered("fake_trade")
    assert "fake_trade" in registry.list_codes()


def test_duplicate_trade_code_rejected():
    registry = TradeRegistry()
    registry.register(FakeTradeModule())
    with pytest.raises(TradeRegistryError):
        registry.register(FakeTradeModule())


def test_unknown_trade_rejected():
    registry = TradeRegistry()
    with pytest.raises(UnknownTradeError):
        registry.get("nope")


def test_disabled_trade_cannot_run():
    registry = TradeRegistry()
    registry.register(FakeTradeModule(), enabled=False)
    with pytest.raises(DisabledTradeError):
        registry.get("fake_trade", require_enabled=True)
    # Still retrievable without the enabled requirement.
    assert registry.get("fake_trade").trade_code == "fake_trade"


def test_core_routes_fake_trade_without_painting_logic():
    registry = TradeRegistry()
    registry.register(FakeTradeModule())
    module = registry.get("fake_trade", require_enabled=True)
    result = module.route_sheet(
        SheetContext(
            sheet_id="s", project_id="p", pdf_page_number=1,
            verified_sheet_number="X-1", verified_sheet_title="t",
            detected_sheet_number=None, detected_sheet_title=None,
            embedded_text="", requires_ocr=False, requires_review=False,
        )
    )
    assert result.eligibility == RoutingStatus.ELIGIBLE


def test_bootstrap_unknown_trade_fails():
    with pytest.raises(TradeConfigurationError):
        bootstrap_trades(["painting", "does_not_exist"])


def test_bootstrap_registers_configured_trades():
    registry = TradeRegistry()
    from app.estimating.quantities import FormulaRegistry

    formulas = FormulaRegistry()
    bootstrap_trades(["painting"], registry=registry, formulas=formulas)
    assert registry.list_codes() == ["painting"]
    assert not registry.is_registered("demo_concrete")
