"""Provider-layer tests (mock provider + validation + registry)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import settings
from app.extraction.base import LiveExtractionUnavailable, ProviderTimeout
from app.extraction.mock_provider import MockExtractionProvider
from app.extraction.provider_schemas import (
    ScopeExtractionRequest,
    ScopeExtractionResponse,
)
from app.extraction.registry import get_provider


def _request(trade_code: str) -> ScopeExtractionRequest:
    return ScopeExtractionRequest(
        trade_code=trade_code, prompt_version="v1",
        allowed_categories=["interior_walls", "slab_on_grade"],
        allowed_units=["SF", "EA", "CY"],
        sheets=[{"sheet_id": str(uuid4()), "pdf_page_number": 1, "embedded_text": "x"}],
    )


def test_mock_handles_painting():
    raw = MockExtractionProvider().extract_scope(_request("painting"))
    response = ScopeExtractionResponse.model_validate(raw)
    assert response.trade_code == "painting"
    assert len(response.candidates) == 2


def test_mock_handles_second_trade():
    raw = MockExtractionProvider().extract_scope(_request("demo_concrete"))
    response = ScopeExtractionResponse.model_validate(raw)
    assert response.candidates[0].category_code == "slab_on_grade"
    assert response.candidates[0].quantity.unit == "CY"


def test_malformed_output_rejected():
    raw = MockExtractionProvider(behavior="malformed").extract_scope(_request("painting"))
    with pytest.raises(ValidationError):
        ScopeExtractionResponse.model_validate(raw)


def test_unknown_field_rejected():
    raw = MockExtractionProvider().extract_scope(_request("painting"))
    raw["surprise_field"] = True
    with pytest.raises(ValidationError):
        ScopeExtractionResponse.model_validate(raw)


def test_missing_evidence_rejected():
    raw = MockExtractionProvider().extract_scope(_request("painting"))
    raw["candidates"][0]["evidence"] = []  # provider must supply >= 1 evidence
    with pytest.raises(ValidationError):
        ScopeExtractionResponse.model_validate(raw)


def test_unsupported_trade_yields_no_candidates():
    raw = MockExtractionProvider().extract_scope(_request("nonexistent_trade"))
    response = ScopeExtractionResponse.model_validate(raw)
    assert response.candidates == []


def test_timeout_is_raised():
    with pytest.raises(ProviderTimeout):
        MockExtractionProvider(behavior="timeout").extract_scope(_request("painting"))


def test_transient_failures_then_success():
    provider = MockExtractionProvider(transient_failures=2)
    with pytest.raises(ProviderTimeout):
        provider.extract_scope(_request("painting"))
    with pytest.raises(ProviderTimeout):
        provider.extract_scope(_request("painting"))
    # Third call succeeds.
    raw = provider.extract_scope(_request("painting"))
    assert raw["trade_code"] == "painting"


def test_live_provider_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", False)
    # Requesting openai without live enabled falls back to the offline mock.
    provider = get_provider("openai", use_live=True)
    assert provider.provider_name == "mock"


def test_missing_api_key_does_not_break_startup(monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(LiveExtractionUnavailable):
        get_provider("openai", use_live=True)


def test_default_provider_is_mock():
    assert get_provider().provider_name == "mock"
