"""Central trade registry.

Trade modules register here. The shared core queries the registry to discover
trades, route sheets, validate payloads, and load formulas — never by importing a
specific trade directly.
"""

from __future__ import annotations

from app.trades.base import TradeModule


class TradeRegistryError(ValueError):
    """Raised for duplicate, unknown, or disabled trades."""


class UnknownTradeError(TradeRegistryError):
    pass


class DisabledTradeError(TradeRegistryError):
    pass


class TradeRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, TradeModule] = {}
        self._enabled: set[str] = set()

    def register(self, module: TradeModule, *, enabled: bool = True) -> None:
        code = module.trade_code
        if code in self._modules:
            raise TradeRegistryError(f"Duplicate trade code '{code}'")
        self._modules[code] = module
        if enabled:
            self._enabled.add(code)

    def clear(self) -> None:
        self._modules.clear()
        self._enabled.clear()

    def is_registered(self, trade_code: str) -> bool:
        return trade_code in self._modules

    def is_enabled(self, trade_code: str) -> bool:
        return trade_code in self._enabled

    def set_enabled(self, trade_code: str, enabled: bool) -> None:
        if trade_code not in self._modules:
            raise UnknownTradeError(f"Unknown trade '{trade_code}'")
        if enabled:
            self._enabled.add(trade_code)
        else:
            self._enabled.discard(trade_code)

    def get(self, trade_code: str, *, require_enabled: bool = False) -> TradeModule:
        if trade_code not in self._modules:
            raise UnknownTradeError(f"Unknown trade '{trade_code}'")
        if require_enabled and trade_code not in self._enabled:
            raise DisabledTradeError(f"Trade '{trade_code}' is not enabled")
        return self._modules[trade_code]

    def list_codes(self, *, enabled_only: bool = False) -> list[str]:
        codes = self._enabled if enabled_only else set(self._modules)
        return sorted(codes)

    def list_modules(self, *, enabled_only: bool = False) -> list[TradeModule]:
        return [self._modules[c] for c in self.list_codes(enabled_only=enabled_only)]


# Process-wide registry singleton.
trade_registry = TradeRegistry()
