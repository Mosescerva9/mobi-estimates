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
        sheets=[{
            "sheet_id": str(uuid4()),
            "pdf_page_number": 1,
            "embedded_text": "General note: paint corridors with the specified coating system.",
        }],
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


# ---------------------------------------------------------------------------
# OpenAI extraction provider now uses the GPT-5.6 Responses API structured path.
# ---------------------------------------------------------------------------
def _sheet_request(trade_code: str = "painting") -> ScopeExtractionRequest:
    return _request(trade_code)


class _RecordingResponsesClient:
    """Stub GPT-5.6 client that records parse kwargs and returns a scripted result."""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._result


def test_openai_provider_extract_uses_strict_live_schema_and_adapts():
    """The provider sends the dedicated numeric-free live schema (NOT the legacy
    contract) and adapts the parsed result into the caller contract server-side."""
    from app.analysis.schemas import ParsedResult
    from app.extraction.live_schemas import (
        LiveScopeCandidate,
        LiveScopeEvidence,
        LiveScopeExtractionOutput,
    )
    from app.extraction.openai_provider import OpenAIExtractionProvider
    from app.extraction.provider_schemas import ScopeExtractionResponse

    parsed = LiveScopeExtractionOutput(
        trade_code="painting",
        candidates=[
            LiveScopeCandidate(
                category_code="interior_walls",
                description="Paint all interior corridor walls",
                location="Level 1",
                evidence=[LiveScopeEvidence(pdf_page_number=1, quote="paint corridors")],
                assumptions=[],
                exclusions=[],
            )
        ],
    )
    client = _RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    provider = OpenAIExtractionProvider(client=client)

    raw = provider.extract_scope(_sheet_request("painting"))

    # Strict live schema is what goes to the model — never the legacy contract.
    call = client.calls[0]
    assert call["text_format"] is LiveScopeExtractionOutput
    assert call["text_format"] is not ScopeExtractionResponse
    assert "system_prompt" in call and "source_blocks" in call

    # The adapted output validates against the legacy contract with NULL quantity
    # (the live model never authors a number) and re-validates cleanly.
    response = ScopeExtractionResponse.model_validate(raw)
    assert response.trade_code == "painting"
    assert len(response.candidates) == 1
    candidate = response.candidates[0]
    assert candidate.quantity.value is None
    assert candidate.quantity.basis == "unknown"
    assert candidate.confidence is None
    assert candidate.evidence[0].confidence is None
    assert candidate.evidence[0].extracted_text_quote == "paint corridors"


def test_openai_provider_drops_hallucinated_or_wrong_page_scope_quotes():
    """A supplied page number is not enough: the quote must occur on that page."""
    from app.analysis.schemas import ParsedResult
    from app.extraction.live_schemas import (
        LiveScopeCandidate,
        LiveScopeEvidence,
        LiveScopeExtractionOutput,
    )
    from app.extraction.openai_provider import OpenAIExtractionProvider
    from app.extraction.provider_schemas import ScopeExtractionResponse

    parsed = LiveScopeExtractionOutput(
        trade_code="painting",
        candidates=[
            LiveScopeCandidate(
                category_code="interior_walls",
                description="Unsupported candidate",
                location=None,
                evidence=[
                    LiveScopeEvidence(
                        pdf_page_number=1,
                        quote="this quote does not occur on the supplied page",
                    )
                ],
                assumptions=[],
                exclusions=[],
            ),
            LiveScopeCandidate(
                category_code="interior_walls",
                description="Wrong-page candidate",
                location=None,
                evidence=[
                    LiveScopeEvidence(pdf_page_number=99, quote="paint corridors")
                ],
                assumptions=[],
                exclusions=[],
            ),
        ],
    )
    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(
            result=ParsedResult(parsed=parsed, metadata=None)
        )
    )

    response = ScopeExtractionResponse.model_validate(
        provider.extract_scope(_sheet_request("painting"))
    )
    assert response.candidates == []


def test_openai_provider_classify_maps_page_to_verified_sheet_id():
    from app.analysis.schemas import ParsedResult
    from app.extraction.live_schemas import (
        LiveSheetClassificationItem,
        LiveSheetClassificationOutput,
    )
    from app.extraction.openai_provider import OpenAIExtractionProvider
    from app.extraction.provider_schemas import (
        SheetClassificationRequest,
        SheetClassificationResponse,
    )

    sheet_id = str(uuid4())
    request = SheetClassificationRequest(
        trade_code="painting",
        prompt_version="v1",
        sheets=[{"sheet_id": sheet_id, "pdf_page_number": 1, "embedded_text": "x"}],
    )
    parsed = LiveSheetClassificationOutput(
        classifications=[
            LiveSheetClassificationItem(pdf_page_number=1, relevance="relevant", reason="paint notes"),
            # Page 99 is not a supplied sheet — the server drops it (never invents).
            LiveSheetClassificationItem(pdf_page_number=99, relevance="relevant", reason=None),
        ]
    )
    client = _RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    provider = OpenAIExtractionProvider(client=client)

    raw = provider.classify_sheets(request)

    assert client.calls[0]["text_format"] is LiveSheetClassificationOutput
    response = SheetClassificationResponse.model_validate(raw)
    assert len(response.classifications) == 1
    assert str(response.classifications[0].sheet_id) == sheet_id
    assert response.classifications[0].relevance == "relevant"


def test_openai_provider_maps_timeout_to_provider_timeout():
    from app.analysis.openai_client import ResponsesTimeout
    from app.extraction.openai_provider import OpenAIExtractionProvider

    provider = OpenAIExtractionProvider(client=_RecordingResponsesClient(exc=ResponsesTimeout()))
    with pytest.raises(ProviderTimeout):
        provider.extract_scope(_sheet_request())


def test_openai_provider_maps_unavailable_to_live_unavailable():
    from app.analysis.openai_client import ResponsesUnavailable
    from app.extraction.openai_provider import OpenAIExtractionProvider

    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(exc=ResponsesUnavailable())
    )
    with pytest.raises(LiveExtractionUnavailable):
        provider.extract_scope(_sheet_request())


def test_openai_provider_maps_refusal_to_response_invalid():
    from app.analysis.openai_client import ResponsesRefused
    from app.extraction.base import ProviderResponseInvalid
    from app.extraction.openai_provider import OpenAIExtractionProvider

    provider = OpenAIExtractionProvider(client=_RecordingResponsesClient(exc=ResponsesRefused()))
    with pytest.raises(ProviderResponseInvalid):
        provider.extract_scope(_sheet_request())
