"""Authoritative category enum constrained INTO the live Structured-Outputs schema.

The live scope output schema constrains ``category_code`` to an exact enum of the
requested trade's authoritative ``scope_categories`` (resolved server-side from the
enabled trade registry). This is defense-in-depth on top of the existing pre-insert
allowlist guard: a non-authoritative category can no longer be emitted/parsed by the
Structured-Outputs contract at all, so it is rejected before any adaptation or
persistence — while the exact ``gpt-5.6``/``medium``/``tools=[]``/``store=false``
call shape and every server-side fail-closed guard are preserved.
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.analysis.openai_client import GPT56ResponsesClient
from app.extraction.base import ProviderResponseInvalid
from app.extraction.live_schemas import (
    LiveScopeCategoryError,
    LiveScopeCandidate,
    LiveScopeEvidence,
    LiveScopeExtractionOutput,
    build_live_scope_output_model,
)
from app.extraction.openai_provider import OpenAIExtractionProvider
from app.extraction.provider_schemas import (
    ScopeExtractionRequest,
    ScopeExtractionResponse,
)
from app.trades.painting.schemas import PaintingCategory
from app.trades.registry import trade_registry


@pytest.fixture(autouse=True)
def _bootstrap_trades():
    """The provider resolves authoritative categories through the process-wide
    registry; bootstrap it deterministically without booting the full app."""
    from app.trades import bootstrap_trades

    bootstrap_trades(["painting", "demo_concrete", "general_trade"])
    yield


_PAINTING_CATEGORIES = tuple(c.value for c in PaintingCategory)


class _RecordingResponsesClient:
    """Stub GPT-5.6 client that records parse kwargs and returns a scripted result."""

    def __init__(self, result=None):
        self._result = result
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


def _request(trade_code: str = "painting", *, allowed_categories=None) -> ScopeExtractionRequest:
    return ScopeExtractionRequest(
        trade_code=trade_code,
        prompt_version="v1",
        # A hostile/irrelevant caller-supplied list must NOT influence the schema —
        # the server owns the authoritative category set.
        allowed_categories=allowed_categories or ["totally_bogus_caller_category"],
        allowed_units=["SF", "EA"],
        sheets=[{
            "sheet_id": str(uuid4()),
            "pdf_page_number": 1,
            "embedded_text": "General note: paint corridors with the specified coating system.",
        }],
    )


# ---------------------------------------------------------------------------
# 1. Generated schema includes EXACTLY the painting authoritative enum
# ---------------------------------------------------------------------------
def test_generated_json_schema_category_enum_is_exact_painting_set():
    from openai.lib._pydantic import to_strict_json_schema

    model = build_live_scope_output_model(_PAINTING_CATEGORIES)
    schema = to_strict_json_schema(model)

    candidate_def = next(
        value for name, value in schema["$defs"].items() if "Candidate" in name
    )
    enum = candidate_def["properties"]["category_code"]["enum"]
    # Exactly the painting categories, in order — no more, no fewer.
    assert enum == list(_PAINTING_CATEGORIES)
    # Closed object + all-required (strict Structured-Outputs invariants preserved).
    assert candidate_def["additionalProperties"] is False
    assert sorted(candidate_def["required"]) == ["category_code", "evidence"]


def test_builder_is_deterministic_and_cached():
    a = build_live_scope_output_model(_PAINTING_CATEGORIES)
    b = build_live_scope_output_model(_PAINTING_CATEGORIES)
    assert a is b  # cached on the exact normalized category tuple


# ---------------------------------------------------------------------------
# 2. Valid authoritative category parses/adapts
# ---------------------------------------------------------------------------
def test_valid_authoritative_category_parses_and_adapts():
    from app.analysis.schemas import ParsedResult

    model = build_live_scope_output_model(_PAINTING_CATEGORIES)
    parsed = model(
        candidates=[
            {
                "category_code": "interior_walls",
                "evidence": [{"pdf_page_number": 1, "quote": "paint corridors"}],
            }
        ]
    )
    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    )

    response = ScopeExtractionResponse.model_validate(provider.extract_scope(_request()))
    assert response.trade_code == "painting"
    assert len(response.candidates) == 1
    candidate = response.candidates[0]
    assert candidate.category_code == "interior_walls"
    # Fail-closed adaptation invariants preserved: null quantity/confidence, empty
    # assumptions/exclusions, description derived from the exact sourced quote.
    assert candidate.quantity.value is None
    assert candidate.quantity.basis == "unknown"
    assert candidate.confidence is None
    assert candidate.assumptions == []
    assert candidate.exclusions == []
    assert candidate.description == "paint corridors"
    assert candidate.evidence[0].extracted_text_quote == "paint corridors"


# ---------------------------------------------------------------------------
# 3. Non-authoritative category rejected by the schema BEFORE adaptation
# ---------------------------------------------------------------------------
def test_non_authoritative_category_rejected_by_structured_output_schema():
    """The exact production failure: a live model emitting a non-authoritative
    painting category is now rejected by the Structured-Outputs schema itself
    (Pydantic ``Literal`` enum) — before any server-side adaptation/persistence."""
    model = build_live_scope_output_model(_PAINTING_CATEGORIES)
    with pytest.raises(ValidationError):
        model(
            candidates=[
                {
                    # A plausible but NON-authoritative painting category.
                    "category_code": "wallpaper_removal",
                    "evidence": [{"pdf_page_number": 1, "quote": "paint corridors"}],
                }
            ]
        )


def test_provider_rejects_contract_violating_unconstrained_parsed_model():
    """Even a stubbed client cannot bypass the exact dynamic model contract."""
    from app.analysis.schemas import ParsedResult

    unconstrained = LiveScopeExtractionOutput(
        candidates=[
            LiveScopeCandidate(
                category_code="wallpaper_removal",
                evidence=[
                    LiveScopeEvidence(
                        pdf_page_number=1,
                        quote="paint corridors",
                    )
                ],
            )
        ]
    )
    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(
            result=ParsedResult(parsed=unconstrained, metadata=None)
        )
    )

    with pytest.raises(ProviderResponseInvalid) as excinfo:
        provider.extract_scope(_request())
    assert excinfo.value.retryable is False


# ---------------------------------------------------------------------------
# 4. Empty/malformed category definitions fail BEFORE client.parse / dispatch
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        (),
        ("interior_walls", "interior_walls"),
        ("  ",),
        (" interior_walls",),
        ("interior_walls ",),
        ("x" * 201,),
    ],
)
def test_malformed_category_set_fails_closed_at_build(bad):
    with pytest.raises(LiveScopeCategoryError):
        build_live_scope_output_model(bad)


def test_empty_category_definition_fails_before_provider_dispatch(monkeypatch):
    """If a trade's authoritative category set is empty/malformed, the provider fails
    closed with a non-retryable error and NEVER dispatches a provider call."""

    class _EmptyDef:
        scope_categories: list[str] = []

    class _EmptyModule:
        def get_definition(self):
            return _EmptyDef()

    monkeypatch.setattr(trade_registry, "get", lambda *a, **k: _EmptyModule())
    client = _RecordingResponsesClient()
    provider = OpenAIExtractionProvider(client=client)

    with pytest.raises(ProviderResponseInvalid) as excinfo:
        provider.extract_scope(_request())
    assert excinfo.value.retryable is False
    # The provider was NEVER dispatched — fail-closed before any billable call.
    assert client.calls == []


@pytest.mark.parametrize("raw_categories", ["abc", None, {"interior_walls": True}, {"interior_walls"}])
def test_malformed_category_container_fails_before_provider_dispatch(
    monkeypatch, raw_categories
):
    class _MalformedDef:
        scope_categories = raw_categories

    class _MalformedModule:
        def get_definition(self):
            return _MalformedDef()

    monkeypatch.setattr(trade_registry, "get", lambda *a, **k: _MalformedModule())
    client = _RecordingResponsesClient()
    provider = OpenAIExtractionProvider(client=client)

    with pytest.raises(ProviderResponseInvalid) as excinfo:
        provider.extract_scope(_request())
    assert excinfo.value.retryable is False
    assert client.calls == []


# ---------------------------------------------------------------------------
# 5. Provider uses the requested trade's authoritative categories (server-owned)
# ---------------------------------------------------------------------------
def test_provider_uses_requested_trade_authoritative_categories_not_caller_input():
    from app.analysis.schemas import ParsedResult

    model = build_live_scope_output_model(_PAINTING_CATEGORIES)
    parsed = model(candidates=[])
    client = _RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    provider = OpenAIExtractionProvider(client=client)

    # Caller supplies a bogus allowed_categories list; it MUST be ignored.
    provider.extract_scope(_request("painting", allowed_categories=["bogus"]))

    sent = client.calls[0]["text_format"]
    # The schema constrained to the SERVER-resolved painting categories, never the
    # caller list — identity-equal to the builder's output for painting.
    assert sent is build_live_scope_output_model(_PAINTING_CATEGORIES)
    assert "bogus" not in client.calls[0]["system_prompt"]
    assert "interior_walls" in client.calls[0]["system_prompt"]


def test_response_preserves_trusted_request_trade_code():
    """Trade identity comes from the trusted request, never model output."""
    from app.analysis.schemas import ParsedResult

    model = build_live_scope_output_model(_PAINTING_CATEGORIES)
    parsed = model(candidates=[])
    provider = OpenAIExtractionProvider(
        client=_RecordingResponsesClient(result=ParsedResult(parsed=parsed, metadata=None))
    )
    response = ScopeExtractionResponse.model_validate(provider.extract_scope(_request()))
    assert response.trade_code == "painting"


def test_different_trade_yields_its_own_category_enum():
    """A different enabled trade resolves its OWN authoritative categories."""
    concrete_cats = tuple(
        trade_registry.get("demo_concrete").get_definition().scope_categories
    )
    painting_model = build_live_scope_output_model(_PAINTING_CATEGORIES)
    concrete_model = build_live_scope_output_model(concrete_cats)
    assert painting_model is not concrete_model
    assert set(_PAINTING_CATEGORIES) != set(concrete_cats)


# ---------------------------------------------------------------------------
# 6. Real OpenAI SDK 2.46 offline serializer/parser with the generated schema
# ---------------------------------------------------------------------------
def _responses_envelope(*, model, output_text):
    return {
        "id": "resp_contract",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": model,
        "output": [
            {
                "id": "msg_contract",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": output_text, "annotations": []}
                ],
            }
        ],
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": None,
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": {"effort": "medium", "summary": None},
        "store": False,
        "temperature": None,
        "text": {"format": {"type": "text"}, "verbosity": "medium"},
        "tool_choice": "auto",
        "tools": [],
        "top_logprobs": 0,
        "top_p": None,
        "truncation": "disabled",
        "usage": {
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 5,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 15,
        },
        "metadata": {},
        "service_tier": "default",
        "safety_identifier": None,
        "prompt_cache_key": None,
    }


def _find_enum_values(node, key="category_code"):
    """Return every ``enum`` list attached to a ``category_code`` property."""
    found: list[list] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "properties" and isinstance(v, dict) and key in v:
                enum = v[key].get("enum")
                if enum is not None:
                    found.append(enum)
            found.extend(_find_enum_values(v, key))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_enum_values(item, key))
    return found


def _candidate_dict(category_code: str, quote: str) -> dict:
    """A candidate dict valid for any dynamically-constrained scope output model."""
    return {
        "category_code": category_code,
        "evidence": [LiveScopeEvidence(pdf_page_number=1, quote=quote).model_dump()],
    }


def test_real_sdk_246_serializes_and_parses_constrained_schema(monkeypatch):
    """The installed SDK's real request serializer/parser (no network) must accept
    the dynamically-built constrained model: strict json_schema, tools=[],
    store=false, model gpt-5.6, effort medium, and the category enum on the wire."""
    model = build_live_scope_output_model(_PAINTING_CATEGORIES)
    instance = model(candidates=[_candidate_dict("interior_walls", "paint corridors")])
    output_text = instance.model_dump_json()

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            request=request,
            json=_responses_envelope(model="gpt-5.6-sol-2026-07-01", output_text=output_text),
        )

    sdk = httpx.Client(transport=httpx.MockTransport(handler))
    from openai import OpenAI

    openai_client = OpenAI(api_key="configured-provider-marker", http_client=sdk)
    client = GPT56ResponsesClient(
        api_key="configured-provider-marker",
        model="gpt-5.6",
        reasoning_effort="medium",
        timeout_seconds=30,
        live_enabled=True,
    )
    monkeypatch.setattr(client, "_new_client", lambda: openai_client)

    result = client.parse(
        system_prompt="system",
        source_blocks=["synthetic source"],
        text_format=model,
        schema_version="1.0",
        max_source_chars=1000,
    )

    body = captured["body"]
    assert body["model"] == "gpt-5.6"
    assert body["reasoning"] == {"effort": "medium"}
    assert body["store"] is False
    assert body["tools"] == []
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    # The authoritative enum is present on the wire schema exactly once, exact set.
    enums = _find_enum_values(body["text"]["format"]["schema"])
    assert enums and all(set(e) == set(_PAINTING_CATEGORIES) for e in enums)
    assert isinstance(result.parsed, model)
    assert result.parsed.candidates[0].category_code == "interior_walls"
