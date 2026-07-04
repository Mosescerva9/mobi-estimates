"""Unit tests for the canonical Pydantic schemas and their guarantees."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    EstimateLineItem,
    PaintingScopeItem,
    PaintingSurface,
    PaintingUnit,
    PricingBreakdown,
    PricingStatus,
    ProjectStatus,
    ProjectStatusResponse,
    SourceReference,
)


def make_source(**overrides):
    data = dict(page_number=1, sheet_number="A-101", evidence="Wall finish schedule")
    data.update(overrides)
    return SourceReference(**data)


def make_scope_item(**overrides):
    data = dict(
        project_id=uuid4(),
        description="Paint corridor walls",
        location="Level 1 Corridor",
        surface=PaintingSurface.WALL,
        substrate="gypsum board",
        coating_system="2 coats latex eggshell",
        coats=2,
        quantity=Decimal("1200.0"),
        unit=PaintingUnit.SQUARE_FOOT,
        source=make_source(),
        confidence_score=Decimal("0.950"),
        review_required=False,
    )
    data.update(overrides)
    return PaintingScopeItem(**data)


# ---------------------------------------------------------------------------
# Strict validation
# ---------------------------------------------------------------------------
def test_strict_validation_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        SourceReference(
            page_number=1,
            sheet_number="A-101",
            evidence="note",
            unexpected_field="boom",
        )


def test_strict_validation_rejects_float_quantity():
    # strict mode forbids implicit float -> Decimal coercion.
    with pytest.raises(ValidationError):
        make_scope_item(quantity=1200.5)


# ---------------------------------------------------------------------------
# Source reference (evidence) requirements
# ---------------------------------------------------------------------------
def test_missing_page_reference_is_rejected():
    with pytest.raises(ValidationError):
        SourceReference(sheet_number="A-101", evidence="Wall schedule")


def test_missing_sheet_reference_is_rejected():
    with pytest.raises(ValidationError):
        SourceReference(page_number=1, evidence="Wall schedule")


def test_page_number_must_be_positive():
    with pytest.raises(ValidationError):
        make_source(page_number=0)


def test_evidence_is_required():
    with pytest.raises(ValidationError):
        SourceReference(page_number=1, sheet_number="A-101")


# ---------------------------------------------------------------------------
# Quantity / confidence
# ---------------------------------------------------------------------------
def test_invalid_quantity_zero_rejected():
    with pytest.raises(ValidationError):
        make_scope_item(quantity=Decimal("0"))


def test_invalid_quantity_negative_rejected():
    with pytest.raises(ValidationError):
        make_scope_item(quantity=Decimal("-5"))


def test_invalid_confidence_score_above_one():
    with pytest.raises(ValidationError):
        make_scope_item(confidence_score=Decimal("1.500"))


def test_invalid_confidence_score_negative():
    with pytest.raises(ValidationError):
        make_scope_item(confidence_score=Decimal("-0.100"))


# ---------------------------------------------------------------------------
# Human-review guarantee
# ---------------------------------------------------------------------------
def test_low_confidence_requires_review():
    with pytest.raises(ValidationError):
        make_scope_item(confidence_score=Decimal("0.500"), review_required=False)


def test_low_confidence_with_review_is_accepted():
    item = make_scope_item(confidence_score=Decimal("0.500"), review_required=True)
    assert item.review_required is True


def test_high_confidence_can_skip_review():
    item = make_scope_item(confidence_score=Decimal("0.950"), review_required=False)
    assert item.review_required is False


def test_scope_item_defaults_to_review_required():
    item = make_scope_item(confidence_score=Decimal("0.950"), review_required=True)
    # Build without specifying review_required -> defaults to True.
    data = item.model_dump()
    data.pop("review_required")
    data.pop("id")
    data.pop("created_at")
    rebuilt = PaintingScopeItem(**data)
    assert rebuilt.review_required is True


# ---------------------------------------------------------------------------
# Estimate line item
# ---------------------------------------------------------------------------
def make_pricing(**overrides):
    data = dict(
        material_cost=Decimal("100.00"),
        labor_cost=Decimal("200.00"),
        direct_cost=Decimal("300.00"),
        overhead_amount=Decimal("30.00"),
        profit_amount=Decimal("40.00"),
        total_price=Decimal("370.00"),
        calculation_engine_version="pricing-engine-0.0.1",
    )
    data.update(overrides)
    return PricingBreakdown(**data)


def make_line_item(**overrides):
    data = dict(
        project_id=uuid4(),
        scope_item_id=uuid4(),
        cost_code="09-9100",
        description="Paint corridor walls",
        quantity=Decimal("1200.0"),
        unit=PaintingUnit.SQUARE_FOOT,
        source=make_source(),
    )
    data.update(overrides)
    return EstimateLineItem(**data)


def test_estimate_line_item_unpriced_default():
    item = make_line_item()
    assert item.pricing_status == PricingStatus.UNPRICED
    assert item.pricing is None


def test_estimate_line_item_priced_requires_pricing():
    with pytest.raises(ValidationError):
        make_line_item(pricing_status=PricingStatus.PRICED, pricing=None)


def test_estimate_line_item_unpriced_forbids_pricing():
    with pytest.raises(ValidationError):
        make_line_item(pricing_status=PricingStatus.UNPRICED, pricing=make_pricing())


def test_estimate_line_item_priced_is_valid():
    item = make_line_item(
        pricing_status=PricingStatus.PRICED, pricing=make_pricing()
    )
    assert item.pricing is not None
    assert item.pricing.total_price == Decimal("370.00")


def test_estimate_line_item_requires_source():
    with pytest.raises(ValidationError):
        EstimateLineItem(
            project_id=uuid4(),
            scope_item_id=uuid4(),
            cost_code="09-9100",
            description="Paint corridor walls",
            quantity=Decimal("1200.0"),
            unit=PaintingUnit.SQUARE_FOOT,
        )


def test_project_status_response_round_trips():
    from datetime import datetime, timezone

    resp = ProjectStatusResponse(
        project_id=uuid4(),
        name="Demo",
        status=ProjectStatus.UPLOADED,
        original_file_name="plans.pdf",
        page_count=2,
        file_sha256="a" * 64,
        file_size_bytes=1234,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert resp.page_count == 2
