"""Painting candidate + payload validation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.estimating.quantities import QuantityBasis
from app.estimating.units import Unit
from app.extraction.schemas import BlockingIssue
from app.trades.base import CandidateContext, ValidationResult
from app.trades.painting.schemas import (
    PAINTING_ALLOWED_UNITS,
    PAINTING_QUANTITYLESS_CATEGORIES,
    PAINTING_SCHEMA_VERSION,
    PaintingCategory,
    PaintingTradeData,
)

_ALLOWED_UNIT_VALUES = {u.value for u in PAINTING_ALLOWED_UNITS}
_VALID_CATEGORIES = {c.value for c in PaintingCategory}

# Quantity bases painting accepts (no profit/price bases; provider may transcribe
# explicit/schedule values, Python derives dimension/derivation totals).
_ALLOWED_BASES = {
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


def validate_painting_trade_data(
    payload: dict[str, Any], *, schema_version: str | None = None
) -> dict[str, Any]:
    if schema_version is not None and schema_version != PAINTING_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported painting schema version '{schema_version}'; "
            f"this module speaks '{PAINTING_SCHEMA_VERSION}'"
        )
    model = PaintingTradeData.model_validate(payload)
    return model.model_dump(mode="json")


def category_requires_quantity(category_code: str) -> bool:
    return category_code not in PAINTING_QUANTITYLESS_CATEGORIES


def validate_painting_candidate(
    candidate: CandidateContext, *, review_threshold: float
) -> ValidationResult:
    errors: list[str] = []
    blocking: list[BlockingIssue] = []
    requires_review = False

    if candidate.category_code not in _VALID_CATEGORIES:
        errors.append(f"Unknown painting category '{candidate.category_code}'")

    # Quantity basis must be one painting accepts.
    basis = candidate.quantity_basis
    basis_value = basis.value if isinstance(basis, QuantityBasis) else basis
    if basis_value not in {b.value for b in _ALLOWED_BASES}:
        errors.append(f"Quantity basis '{basis_value}' is not allowed for painting")

    # Unit (when present) must be supported.
    if candidate.unit is not None and candidate.unit not in _ALLOWED_UNIT_VALUES:
        blocking.append(
            BlockingIssue(code="unsupported_unit",
                          message=f"Unit '{candidate.unit}' is not allowed for painting")
        )

    # Trade-specific payload must validate.
    normalized: dict[str, Any] = {}
    try:
        normalized = validate_painting_trade_data(candidate.trade_data)
    except (ValidationError, ValueError) as exc:
        errors.append(f"Invalid painting trade_data: {exc}")
        requires_review = True

    # Evidence is mandatory for every candidate.
    if candidate.evidence_count < 1:
        blocking.append(
            BlockingIssue(code="provider_response_lacks_evidence",
                          message="Candidate has no evidence reference")
        )

    # Quantity is required for most categories.
    if (
        category_requires_quantity(candidate.category_code)
        and candidate.quantity_value is None
    ):
        # Not a hard validation error (item may exist unresolved), but it blocks
        # approval and needs review.
        requires_review = True

    # Low confidence always needs review.
    if candidate.confidence is not None and candidate.confidence < review_threshold:
        requires_review = True

    return ValidationResult(
        ok=not errors,
        normalized_trade_data=normalized,
        errors=errors,
        blocking_issues=blocking,
        requires_review=requires_review or bool(blocking),
    )
