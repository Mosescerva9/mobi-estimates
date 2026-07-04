"""Trade registry bootstrap.

Maps trade codes to their module classes and registers the configured set into the
shared registry + formula registry. The shared core depends only on the registry,
never on a specific trade module.
"""

from __future__ import annotations

from app.estimating.quantities import FormulaRegistry, formula_registry
from app.trades.demo_concrete import DemoConcreteTradeModule
from app.trades.painting import PaintingTradeModule
from app.trades.registry import TradeRegistry, trade_registry

# All trade modules the build knows how to construct. A trade is only registered
# (and therefore visible/usable) when its code appears in MOBI_ENABLED_TRADES.
AVAILABLE_TRADE_MODULES = {
    PaintingTradeModule.trade_code: PaintingTradeModule,
    DemoConcreteTradeModule.trade_code: DemoConcreteTradeModule,
}


class TradeConfigurationError(ValueError):
    """Raised when MOBI_ENABLED_TRADES references an unknown trade code."""


def bootstrap_trades(
    enabled_trades: list[str],
    *,
    registry: TradeRegistry = trade_registry,
    formulas: FormulaRegistry = formula_registry,
) -> None:
    """(Re)build the trade + formula registries from the configured trade list."""
    unknown = [code for code in enabled_trades if code not in AVAILABLE_TRADE_MODULES]
    if unknown:
        raise TradeConfigurationError(
            f"Unknown configured trade(s): {sorted(set(unknown))}. "
            f"Available: {sorted(AVAILABLE_TRADE_MODULES)}"
        )

    registry.clear()
    formulas.clear()
    for code in enabled_trades:
        module = AVAILABLE_TRADE_MODULES[code]()
        registry.register(module, enabled=True)
        for formula in module.get_quantity_formulas():
            formulas.register(formula)


__all__ = [
    "AVAILABLE_TRADE_MODULES",
    "TradeConfigurationError",
    "bootstrap_trades",
]
