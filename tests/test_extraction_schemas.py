"""Canonical extraction-schema + trade-payload validation tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extraction.schemas import (
    EvidenceReference,
    QuantityCandidate,
    ReviewStatus,
    ScopeItem,
)
from app.trades.demo_concrete import DemoConcreteTradeData
from app.trades.painting.schemas import PaintingTradeData


def _evidence(**over):
    data = dict(
        project_id=uuid4(), sheet_id=uuid4(), pdf_page_number=1,
        verified_sheet_number="A-101", evidence_type="finish_schedule",
        description="Finish schedule",
    )
    data.update(over)
    return EvidenceReference(**data)


def _scope_item(**over):
    data = dict(
        project_id=uuid4(), extraction_run_id=uuid4(), trade_code="painting",
        trade_module_version="1.0.0", trade_schema_version="1.0",
        category_code="interior_walls", description="Paint walls",
    )
    data.update(over)
    return ScopeItem(**data)


def test_valid_generic_scope_item():
    item = _scope_item(quantity=Decimal("100"), unit="SF")
    assert item.review_status == ReviewStatus.PENDING.value
    assert item.trade_code == "painting"


def test_scope_item_unknown_field_rejected():
    with pytest.raises(ValidationError):
        _scope_item(surprise="boom")


def test_null_unresolved_quantity_allowed():
    item = _scope_item(quantity=None, unit=None)
    assert item.quantity is None  # allowed at the schema level (blocked at approval)


def test_valid_painting_trade_payload():
    payload = PaintingTradeData(substrate="gypsum", coating_system="latex",
                                finish_coats=2, interior_exterior="interior")
    assert payload.finish_coats == 2


def test_painting_payload_unknown_field_rejected():
    with pytest.raises(ValidationError):
        PaintingTradeData(thickness_in=6)  # a concrete field, not painting


def test_valid_second_trade_payload():
    payload = DemoConcreteTradeData(mix_design="3000psi", thickness_in=6)
    assert payload.thickness_in == 6


def test_second_trade_payload_rejects_painting_field():
    with pytest.raises(ValidationError):
        DemoConcreteTradeData(coating_system="latex")  # a painting field


def test_evidence_requires_verified_sheet_number():
    with pytest.raises(ValidationError):
        _evidence(verified_sheet_number="")


def test_evidence_unknown_type_rejected():
    with pytest.raises(ValidationError):
        _evidence(evidence_type="not_a_real_type")


def test_evidence_confidence_bounds():
    with pytest.raises(ValidationError):
        _evidence(provider_confidence=Decimal("1.5"))


def test_quantity_candidate_invalid_unit_rejected():
    with pytest.raises(ValidationError):
        QuantityCandidate(basis="schedule_count", value=Decimal("3"), unit="WIDGETS")


def test_quantity_candidate_invalid_basis_rejected():
    with pytest.raises(ValidationError):
        QuantityCandidate(basis="totally_made_up", value=Decimal("3"))
