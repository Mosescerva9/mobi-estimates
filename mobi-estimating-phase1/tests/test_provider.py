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


@pytest.fixture(autouse=True)
def _bootstrap_trades_for_provider_tests():
    """The live OpenAI provider resolves the requested trade's authoritative scope
    categories through the process-wide trade registry. These provider tests do not
    boot the full app, so bootstrap the registry deterministically (independent of
    test ordering) with the same enabled set the suite uses elsewhere."""
    from app.trades import bootstrap_trades

    bootstrap_trades(["painting", "demo_concrete", "general_trade"])
    yield


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


def test_explicit_openai_run_fails_closed_when_live_disabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", False)
    monkeypatch.setattr(settings, "openai_api_key", "configured-provider-key-marker")
    # An explicitly named openai run must NEVER silently degrade to the mock when
    # live is disabled — it fails closed so no mock payload is persisted as if it
    # were the requested live result.
    with pytest.raises(LiveExtractionUnavailable):
        get_provider("openai", use_live=True)


def test_explicit_openai_run_fails_closed_when_use_live_false(monkeypatch):
    # Even with live enabled, a caller that resolves the openai provider without
    # use_live (e.g. the flag flipped between claim and execution) fails closed.
    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", "configured-provider-key-marker")
    with pytest.raises(LiveExtractionUnavailable):
        get_provider("openai", use_live=False)


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
    """The provider sends the dedicated numeric-free, CATEGORY-CONSTRAINED live
    schema (NOT the legacy contract) and adapts the parsed result server-side."""
    from app.analysis.schemas import ParsedResult
    from app.extraction.live_schemas import (
        LiveScopeCandidate,
        LiveScopeEvidence,
        LiveScopeExtractionOutput,
        build_live_scope_output_model,
    )
    from app.extraction.openai_provider import OpenAIExtractionProvider
    from app.extraction.provider_schemas import ScopeExtractionResponse
    from app.trades.registry import trade_registry

    parsed = LiveScopeExtractionOutput(
        candidates=[
            LiveScopeCandidate(
                category_code="interior_walls",
                evidence=[LiveScopeEvidence(pdf_page_number=1, quote="paint corridors")],
            )
        ],
    )
    client = _RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    provider = OpenAIExtractionProvider(client=client)

    raw = provider.extract_scope(_sheet_request("painting"))

    # The strict, category-constrained live schema is what goes to the model — the
    # SAME object the server-side builder produces for the painting trade — never
    # the legacy contract nor the unconstrained generic live schema.
    call = client.calls[0]
    painting_cats = tuple(
        trade_registry.get("painting").get_definition().scope_categories
    )
    assert call["text_format"] is build_live_scope_output_model(painting_cats)
    assert call["text_format"] is not LiveScopeExtractionOutput
    assert call["text_format"] is not ScopeExtractionResponse
    assert "system_prompt" in call and "source_blocks" in call
    # The system prompt carries the server-generated allowlist guidance naming the
    # exact authoritative enum values (guidance only; the schema is authoritative).
    assert "interior_walls" in call["system_prompt"]

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
    # Description/location/assumptions/exclusions are SERVER-derived, never model
    # prose: the description equals the exact sourced quote and the rest are empty.
    assert candidate.description == "paint corridors"
    assert candidate.evidence[0].description == "paint corridors"
    assert candidate.location is None
    assert candidate.assumptions == []
    assert candidate.exclusions == []


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
        candidates=[
            LiveScopeCandidate(
                category_code="interior_walls",
                evidence=[
                    LiveScopeEvidence(
                        pdf_page_number=1,
                        quote="this quote does not occur on the supplied page",
                    )
                ],
            ),
            LiveScopeCandidate(
                category_code="interior_walls",
                evidence=[
                    LiveScopeEvidence(pdf_page_number=99, quote="paint corridors")
                ],
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
        LiveSheetRelevance,
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
            LiveSheetClassificationItem(pdf_page_number=1, relevance=LiveSheetRelevance.RELEVANT),
            # Page 99 is not a supplied sheet — the server drops it (never invents).
            LiveSheetClassificationItem(pdf_page_number=99, relevance=LiveSheetRelevance.RELEVANT),
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
    # The reason is a fixed server value (empty), never model-authored prose.
    assert response.classifications[0].reason == ""


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


# ---------------------------------------------------------------------------
# Error retryability mapping: the extraction ProviderError must carry the SDK's
# retryability faithfully so the service retries only what could plausibly help.
# ---------------------------------------------------------------------------
def test_openai_provider_timeout_is_retryable():
    from app.analysis.openai_client import ResponsesTimeout
    from app.extraction.openai_provider import OpenAIExtractionProvider

    provider = OpenAIExtractionProvider(client=_RecordingResponsesClient(exc=ResponsesTimeout()))
    with pytest.raises(ProviderTimeout) as excinfo:
        provider.extract_scope(_sheet_request())
    assert excinfo.value.retryable is True


def test_openai_provider_rate_limit_is_retryable_timeout():
    from app.analysis.openai_client import ResponsesRateLimited
    from app.extraction.openai_provider import OpenAIExtractionProvider

    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(exc=ResponsesRateLimited())
    )
    with pytest.raises(ProviderTimeout) as excinfo:
        provider.extract_scope(_sheet_request())
    assert excinfo.value.retryable is True


def test_openai_provider_unavailable_is_non_retryable():
    from app.analysis.openai_client import ResponsesUnavailable
    from app.extraction.openai_provider import OpenAIExtractionProvider

    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(exc=ResponsesUnavailable())
    )
    with pytest.raises(LiveExtractionUnavailable) as excinfo:
        provider.extract_scope(_sheet_request())
    assert excinfo.value.retryable is False


def test_openai_provider_refusal_is_non_retryable():
    from app.analysis.openai_client import ResponsesRefused
    from app.extraction.base import ProviderResponseInvalid
    from app.extraction.openai_provider import OpenAIExtractionProvider

    provider = OpenAIExtractionProvider(client=_RecordingResponsesClient(exc=ResponsesRefused()))
    with pytest.raises(ProviderResponseInvalid) as excinfo:
        provider.extract_scope(_sheet_request())
    assert excinfo.value.retryable is False


@pytest.mark.parametrize("schema_invalid", [True, False])
def test_openai_provider_schema_and_mismatch_are_non_retryable(schema_invalid):
    from app.analysis.openai_client import (
        ResponsesModelMismatch,
        ResponsesSchemaInvalid,
    )
    from app.extraction.base import ProviderResponseInvalid
    from app.extraction.openai_provider import OpenAIExtractionProvider

    exc = ResponsesSchemaInvalid() if schema_invalid else ResponsesModelMismatch()
    provider = OpenAIExtractionProvider(client=_RecordingResponsesClient(exc=exc))
    with pytest.raises(ProviderResponseInvalid) as excinfo:
        provider.extract_scope(_sheet_request())
    assert excinfo.value.retryable is False


@pytest.mark.parametrize("retryable", [True, False])
def test_openai_provider_generic_error_mirrors_retryable(retryable):
    """A generic ResponsesProviderError must become a response-invalid error whose
    retryable flag mirrors the SDK's classification EXACTLY — a transient
    connection error (retryable=True) must never be collapsed to non-retryable."""
    from app.analysis.openai_client import ResponsesProviderError
    from app.extraction.base import ProviderResponseInvalid
    from app.extraction.openai_provider import OpenAIExtractionProvider

    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(exc=ResponsesProviderError(retryable=retryable))
    )
    with pytest.raises(ProviderResponseInvalid) as excinfo:
        provider.extract_scope(_sheet_request())
    # Safe code preserved, no raw payload, retryability faithfully mirrored.
    assert excinfo.value.code == "provider_response_invalid"
    assert excinfo.value.retryable is retryable


# ---------------------------------------------------------------------------
# service._call_with_retries: retry ONLY retryable errors, re-raise the rest.
# ---------------------------------------------------------------------------
class _ScriptedProvider:
    """Provider stub whose extract_scope yields a scripted sequence of outcomes.

    Each outcome is either a ProviderError to raise or a dict to return. Records
    how many times it was called so retry behavior can be asserted exactly.
    """

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def extract_scope(self, request):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


_OK = {"trade_code": "painting", "candidates": []}


def test_call_with_retries_retries_retryable_timeout_then_succeeds(monkeypatch):
    from app.extraction import service

    monkeypatch.setattr(settings, "extraction_max_retries", 3)
    provider = _ScriptedProvider([ProviderTimeout(), _OK])

    result = service._call_with_retries(provider, _request("painting"))

    assert result == _OK
    # One retryable failure then success: exactly two calls.
    assert provider.calls == 2


def test_call_with_retries_reraises_non_retryable_response_invalid_once(monkeypatch):
    from app.extraction import service
    from app.extraction.base import ProviderResponseInvalid

    # Plenty of retries configured; a non-retryable error must still call once.
    monkeypatch.setattr(settings, "extraction_max_retries", 5)
    provider = _ScriptedProvider([ProviderResponseInvalid(), _OK])

    with pytest.raises(ProviderResponseInvalid):
        service._call_with_retries(provider, _request("painting"))
    assert provider.calls == 1


def test_call_with_retries_reraises_non_retryable_refusal_once(monkeypatch):
    from app.extraction import service
    from app.extraction.base import ProviderResponseInvalid

    monkeypatch.setattr(settings, "extraction_max_retries", 5)
    # A refusal maps to a non-retryable response-invalid error (retryable=False).
    provider = _ScriptedProvider([ProviderResponseInvalid(retryable=False), _OK])

    with pytest.raises(ProviderResponseInvalid):
        service._call_with_retries(provider, _request("painting"))
    assert provider.calls == 1


def test_call_with_retries_generic_retryable_true_exhausts_attempts(monkeypatch):
    from app.extraction import service
    from app.extraction.base import ProviderResponseInvalid

    monkeypatch.setattr(settings, "extraction_max_retries", 2)
    # A generic error the SDK deemed transient (retryable=True) is retried up to
    # retries+1 attempts before finally surfacing.
    provider = _ScriptedProvider(
        [ProviderResponseInvalid(retryable=True) for _ in range(3)]
    )

    with pytest.raises(ProviderResponseInvalid):
        service._call_with_retries(provider, _request("painting"))
    assert provider.calls == 3  # extraction_max_retries + 1


def test_call_with_retries_generic_retryable_false_calls_once(monkeypatch):
    from app.extraction import service
    from app.extraction.base import ProviderResponseInvalid

    monkeypatch.setattr(settings, "extraction_max_retries", 2)
    # Same generic error class, but flagged non-retryable: re-raised immediately.
    provider = _ScriptedProvider([ProviderResponseInvalid(retryable=False), _OK])

    with pytest.raises(ProviderResponseInvalid):
        service._call_with_retries(provider, _request("painting"))
    assert provider.calls == 1


# ---------------------------------------------------------------------------
# Free-text safety: fail closed on model-authored prohibited content
# ---------------------------------------------------------------------------
# Adversarial strings — one per prohibited class. Each must be rejected.
_PROHIBITED_FREE_TEXT = [
    "Apply coating at $4.50 per unit",  # currency symbol
    "Material budget is 500 dollars for this area",  # numeric currency word
    "Total price for the corridor package",  # explicit money term
    "Cost applies to the corridor package",  # standalone cost term
    "Total applies to the corridor package",  # standalone total term
    "Unit cost applies to each opening",  # unit cost term
    "Paint 120 SF of interior gypsum board",  # numeric + area unit
    "Install 10 linear feet of base",  # numeric + length unit
    "Provide 5 gallons of primer",  # numeric + volume unit
    "Provide 25 EA of the specified fixture",  # numeric + count unit
    "Coating solids are 65%",  # numeric percentage
    "Studs at 2x4 spacing throughout",  # dimension shorthand
    "Wall height is 9' at the lobby",  # feet mark dimension
    # Any model-authored digit is prohibited, even without an adjacent unit.
    "Apply 3 coats",  # bare count, no unit
    "Paint 6 openings",  # bare count, no unit
    "Provide 4 assemblies",  # bare count, no unit
    "Refer to detail 12 on the plan",  # incidental digit / reference number
    "This scope has been approved by the owner",  # approval claim
    "Approve scope before mobilization",  # broad approval action
    "This work has been authorized by the owner",  # authorization (US)
    "Change order authorised for the corridor",  # authorisation (UK)
    "Pending authorization from the client",  # authorization noun
    "Include in the final proposal to the client",  # proposal/final claim
    "The package is finalized",  # final-status claim
    "Punch list completed and signed off",  # completion status
    "Marked as complete for this area",  # completion status
    "Balance due on the corridor package",  # payment / balance
    "We emailed the customer the updated scope",  # messaging claim
    "Send the customer a message",  # broad customer communication
    "Contact the client to schedule the work",  # customer communication
    "Send notification to the customer before start",  # customer notification
    "Customer notification required before painting",  # customer notification
    "Deliver to the customer once painted",  # delivery claim / "once"
    "Payment is due on completion",  # payment claim
    # Spelled-out number words (cardinal + ordinal) are now rejected too: with all
    # descriptive prose removed from the model schema, denylist completeness is no
    # longer a persistence dependency, so this filter is maximally strict.
    "Apply two finish coats over the substrate",  # spelled cardinal 'two'
    "Provide three assemblies as specified",  # spelled cardinal 'three'
    "Prepare four openings on the level",  # spelled cardinal 'four'
    "Coat six columns in the lobby",  # spelled cardinal 'six'
    "Apply the second finish coat",  # spelled ordinal 'second'
    "Prepare the third layer of the assembly",  # spelled ordinal 'third'
    "Prime the surface twice before topcoat",  # spelled multiplier 'twice'
]

# Valid, ordinary sourced descriptive scope — must NOT be rejected. With word-
# numbers now prohibited, every safe example contains NO cardinal or ordinal
# number word (nor any digit).
_SAFE_FREE_TEXT = [
    "Primer and finish coats on interior gypsum board walls",
    "Paint corridor walls with the specified coating system",
    "High-build epoxy over prepared concrete masonry units",
    "Field-verify existing conditions before starting",
    "Apply the specified coating system over the prepared substrate",
    "Interior latex on lobby soffits and columns",
    "Sand, prime, and topcoat exposed metal railings",
    "Provide a full coat on all exposed surfaces",
]


@pytest.mark.parametrize("text", _PROHIBITED_FREE_TEXT)
def test_free_text_validator_rejects_prohibited(text):
    from app.extraction.live_schemas import (
        LiveTextPolicyViolation,
        assert_free_text_safe,
    )

    with pytest.raises(LiveTextPolicyViolation):
        assert_free_text_safe(text)


@pytest.mark.parametrize("text", _SAFE_FREE_TEXT)
def test_free_text_validator_allows_safe_scope(text):
    from app.extraction.live_schemas import assert_free_text_safe

    # Must not raise.
    assert_free_text_safe(text)


def test_free_text_validator_allows_empty():
    from app.extraction.live_schemas import assert_free_text_safe

    assert_free_text_safe(None)
    assert_free_text_safe("")


@pytest.mark.parametrize("forbidden", ["description", "location", "assumptions", "exclusions"])
def test_live_scope_candidate_schema_exposes_no_prose_field(forbidden):
    """STRUCTURAL safety: the model output schema has NO descriptive prose field,
    and (extra=forbid) it cannot accept one — so no denylist is a persistence
    dependency for these classes."""
    from app.extraction.live_schemas import LiveScopeCandidate, LiveScopeEvidence

    # The only model-authored fields are the category code and the evidence.
    assert set(LiveScopeCandidate.model_fields) == {"category_code", "evidence"}

    # A smuggled prose field is rejected at construction (extra="forbid").
    value: object = ["x"] if forbidden in {"assumptions", "exclusions"} else "x"
    with pytest.raises(ValidationError):
        LiveScopeCandidate(
            category_code="interior_walls",
            evidence=[LiveScopeEvidence(pdf_page_number=1, quote="paint corridors")],
            **{forbidden: value},  # type: ignore[arg-type]
        )


def test_live_scope_output_schema_exposes_no_trade_field():
    """Trade identity comes only from the trusted request, never model output."""
    from app.extraction.live_schemas import LiveScopeExtractionOutput

    assert set(LiveScopeExtractionOutput.model_fields) == {"candidates"}
    with pytest.raises(ValidationError):
        LiveScopeExtractionOutput(candidates=[], trade_code="painting")  # type: ignore[call-arg]


def test_live_classification_item_schema_exposes_no_reason_field():
    """The classification item has ONLY a page number and relevance verdict — no
    model-authored reason field, and (extra=forbid) it cannot accept one."""
    from app.extraction.live_schemas import LiveSheetClassificationItem, LiveSheetRelevance

    assert set(LiveSheetClassificationItem.model_fields) == {"pdf_page_number", "relevance"}
    with pytest.raises(ValidationError):
        LiveSheetClassificationItem(
            pdf_page_number=1,
            relevance=LiveSheetRelevance.RELEVANT,
            reason="Approved final proposal; total price applies",  # type: ignore[call-arg]
        )


def test_live_structured_models_reject_python_coercions():
    """Strict live schemas reject hostile Python-side type coercion before use."""
    from app.extraction.live_schemas import (
        LiveScopeCandidate,
        LiveScopeEvidence,
        LiveScopeExtractionOutput,
        LiveSheetClassificationItem,
        LiveSheetRelevance,
    )

    with pytest.raises(ValidationError):
        LiveScopeEvidence(pdf_page_number="1", quote="paint corridors")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        LiveSheetClassificationItem(
            pdf_page_number="1",  # type: ignore[arg-type]
            relevance=LiveSheetRelevance.RELEVANT,
        )
    with pytest.raises(ValidationError):
        LiveScopeCandidate(
            category_code=123,  # type: ignore[arg-type]
            evidence=[LiveScopeEvidence(pdf_page_number=1, quote="paint corridors")],
        )
    with pytest.raises(ValidationError):
        LiveScopeExtractionOutput(candidates=tuple())  # type: ignore[arg-type]


def test_openai_provider_requires_literal_not_normalized_quote():
    """Only a LITERAL exact substring of the raw page text is persisted. A quote
    whose case/whitespace was altered (normalized but not literal) is dropped; the
    exact same-page quote persists and becomes the server-derived description."""
    from app.analysis.schemas import ParsedResult
    from app.extraction.live_schemas import (
        LiveScopeCandidate,
        LiveScopeEvidence,
        LiveScopeExtractionOutput,
    )
    from app.extraction.openai_provider import OpenAIExtractionProvider
    from app.extraction.provider_schemas import ScopeExtractionResponse

    # _request(...) supplies page 1 text: "General note: paint corridors with the
    # specified coating system." The literal substring is "paint corridors".
    parsed = LiveScopeExtractionOutput(
        candidates=[
            # Case + whitespace altered: normalizes to the source but is NOT a
            # literal substring -> dropped (no literally-sourced evidence).
            LiveScopeCandidate(
                category_code="interior_walls",
                evidence=[LiveScopeEvidence(pdf_page_number=1, quote="Paint   Corridors")],
            ),
            # Exact literal substring -> persists.
            LiveScopeCandidate(
                category_code="interior_walls",
                evidence=[LiveScopeEvidence(pdf_page_number=1, quote="paint corridors")],
            ),
        ],
    )
    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    )

    response = ScopeExtractionResponse.model_validate(
        provider.extract_scope(_sheet_request("painting"))
    )
    assert len(response.candidates) == 1
    candidate = response.candidates[0]
    assert candidate.evidence[0].extracted_text_quote == "paint corridors"
    # The persisted description is the exact sourced quote, not model prose.
    assert candidate.description == "paint corridors"


def test_openai_provider_allows_sourced_evidence_quote_with_numbers():
    """Evidence quotes are verbatim literal source substrings, so a number in a
    quote is sourced (not model-authored) and IS persisted; the server-derived
    description is that same sourced quote."""
    from app.analysis.schemas import ParsedResult
    from app.extraction.live_schemas import (
        LiveScopeCandidate,
        LiveScopeEvidence,
        LiveScopeExtractionOutput,
    )
    from app.extraction.openai_provider import OpenAIExtractionProvider
    from app.extraction.provider_schemas import (
        ScopeExtractionRequest,
        ScopeExtractionResponse,
    )

    # Source text legitimately contains a measurement; the quote cites it verbatim.
    request = ScopeExtractionRequest(
        trade_code="painting",
        prompt_version="v1",
        allowed_categories=["interior_walls"],
        allowed_units=["SF"],
        sheets=[{
            "sheet_id": str(uuid4()),
            "pdf_page_number": 1,
            "embedded_text": "Note: paint 120 SF of interior gypsum board walls.",
        }],
    )
    parsed = LiveScopeExtractionOutput(
        candidates=[
            LiveScopeCandidate(
                category_code="interior_walls",
                evidence=[LiveScopeEvidence(pdf_page_number=1, quote="paint 120 SF of interior gypsum board")],
            )
        ],
    )
    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    )

    response = ScopeExtractionResponse.model_validate(provider.extract_scope(request))
    assert len(response.candidates) == 1
    assert response.candidates[0].evidence[0].extracted_text_quote == "paint 120 SF of interior gypsum board"
    # The server-derived description is the sourced quote itself (bounded), never
    # model prose — a sourced number therefore survives into the description.
    assert response.candidates[0].description == "paint 120 SF of interior gypsum board"


def test_openai_provider_evidence_description_derives_from_its_own_quote():
    """Each evidence description must derive from its OWN exact sourced quote — not
    the candidate's first quote. The candidate description stays the first sourced
    quote, but a second evidence carries its own distinct quote as its description."""
    from app.analysis.schemas import ParsedResult
    from app.extraction.live_schemas import (
        LiveScopeCandidate,
        LiveScopeEvidence,
        LiveScopeExtractionOutput,
    )
    from app.extraction.openai_provider import OpenAIExtractionProvider
    from app.extraction.provider_schemas import (
        ScopeExtractionRequest,
        ScopeExtractionResponse,
    )

    # Two distinct literal phrases on the SAME page's raw text.
    first_quote = "paint corridors"
    second_quote = "prime the soffits"
    request = ScopeExtractionRequest(
        trade_code="painting",
        prompt_version="v1",
        allowed_categories=["interior_walls"],
        allowed_units=["SF"],
        sheets=[{
            "sheet_id": str(uuid4()),
            "pdf_page_number": 1,
            "embedded_text": f"General note: {first_quote} then {second_quote} throughout.",
        }],
    )
    parsed = LiveScopeExtractionOutput(
        candidates=[
            LiveScopeCandidate(
                category_code="interior_walls",
                evidence=[
                    LiveScopeEvidence(pdf_page_number=1, quote=first_quote),
                    LiveScopeEvidence(pdf_page_number=1, quote=second_quote),
                ],
            )
        ],
    )
    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    )

    response = ScopeExtractionResponse.model_validate(provider.extract_scope(request))
    assert len(response.candidates) == 1
    candidate = response.candidates[0]
    assert len(candidate.evidence) == 2
    # Candidate description = FIRST sourced quote (bounded).
    assert candidate.description == first_quote[:1000]
    # Each evidence description = its OWN exact sourced quote (bounded), and the
    # second is NOT the candidate's first quote.
    assert candidate.evidence[0].description == first_quote[:1000]
    assert candidate.evidence[1].description == second_quote[:1000]
    assert candidate.evidence[1].description != candidate.description
    assert candidate.evidence[0].extracted_text_quote == first_quote
    assert candidate.evidence[1].extracted_text_quote == second_quote
