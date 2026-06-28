"""Painting trade-specific pricing validation (thin module re-exporting)."""

from app.trades.painting.assemblies import validate_painting_pricing_inputs

__all__ = ["validate_painting_pricing_inputs"]
