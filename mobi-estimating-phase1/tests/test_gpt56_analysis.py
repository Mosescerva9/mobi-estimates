"""Offline tests for the GPT-5.6 structured project-analysis layer.

Everything here mocks the OpenAI SDK — no network, no key, no paid call. The tests
assert the exact model alias ``gpt-5.6`` and reasoning effort ``medium`` (enforced
at config AND independently in the client before any dispatch), the strict
Responses API structured-output contract (no tools, no server-side storage,
bounded input, default-free strict json_schema), strict returned-model
acceptance, fail-closed error mapping, post-parse source grounding, no
secret/source leakage, and that unsupported measurements/prices can never enter
any structured output schema.
"""

from __future__ import annotations

import json

import httpx
import pytest
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ValidationError

from app.analysis import service
from app.analysis.openai_client import (
    EXPECTED_MODEL_ALIAS,
    EXPECTED_REASONING_EFFORT,
    GPT56ResponsesClient,
    ResponsesConfigInvalid,
    ResponsesEmptyOutput,
    ResponsesError,
    ResponsesGroundingError,
    ResponsesModelMismatch,
    ResponsesProviderError,
    ResponsesRateLimited,
    ResponsesRefused,
    ResponsesSchemaInvalid,
    ResponsesTimeout,
    ResponsesUnavailable,
    _is_accepted_returned_model,
)
from app.analysis.schemas import (
    Allowance,
    Alternate,
    AnalysisSourceReference,
    BidInstruction,
    Exclusion,
    ParsedResult,
    PlanSpecConflict,
    ProjectAnalysis,
    ProviderCallMetadata,
    ScopeObservation,
    SheetIndexEntry,
    SourcedProjectType,
    SourcedText,
    SpecificationSection,
    UnitRequirement,
)
from app.analysis.service import (
    AnalysisSourceDocument,
    ProjectAnalysisRequest,
    analyze_project,
)
from app.config import DOCUMENTED_REASONING_EFFORTS, Settings, settings
from app.extraction.live_schemas import (
    LiveScopeExtractionOutput,
    LiveSheetClassificationOutput,
)
from scripts.verify_gpt56_live import (
    TinyProbe,
    _preflight_exact_model_effort,
    _ProbeRef,
)


# ---------------------------------------------------------------------------
# Analysis fixtures (every schema field is now required — no defaults)
# ---------------------------------------------------------------------------
def _ref(**overrides) -> AnalysisSourceReference:
    base = dict(
        document_id=None,
        document_name=None,
        page_number=None,
        sheet_number=None,
        quote=None,
    )
    base.update(overrides)
    return AnalysisSourceReference(**base)


def _full_analysis(**overrides) -> ProjectAnalysis:
    """Construct a fully-specified ProjectAnalysis.

    Because the schema is default-free (strict Structured Outputs rejects
    defaults), every field must be supplied explicitly. This mirrors what the
    model is required to emit.
    """

    base = dict(
        project_name=None,
        customer_name=None,
        project_location=None,
        bid_due_date=None,
        project_type=None,
        sheet_index=[],
        specification_sections=[],
        identified_trades=[],
        scope_items=[],
        alternates=[],
        allowances=[],
        unit_requirements=[],
        relevant_plan_sheets=[],
        bid_instructions=[],
        missing_documents=[],
        plan_spec_conflicts=[],
        recommended_rfis=[],
        assumptions=[],
        exclusions=[],
        risk_flags=[],
        confidence_level="unknown",
        source_references=[],
    )
    base.update(overrides)
    return ProjectAnalysis(**base)


# ---------------------------------------------------------------------------
# Fake OpenAI SDK doubles
# ---------------------------------------------------------------------------
class FakeUsage:
    input_tokens = 12
    output_tokens = 7
    total_tokens = 19


class _RefusalPart:
    type = "refusal"


class _RefusalItem:
    content = [_RefusalPart()]


class FakeResponse:
    def __init__(self, *, model, output_parsed, output=None, usage=FakeUsage()):
        self.model = model
        self.output_parsed = output_parsed
        self.id = "resp_test_123"
        self._request_id = "req_test_123"
        self.output = output or []
        self.usage = usage


class FakeResponsesEndpoint:
    def __init__(self, *, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.response


class FakeOpenAI:
    def __init__(self, endpoint):
        self.responses = endpoint


def make_client(monkeypatch, endpoint, **overrides) -> GPT56ResponsesClient:
    kwargs = dict(
        api_key="provider-secret-marker",
        model="gpt-5.6",
        reasoning_effort="medium",
        timeout_seconds=30,
        live_enabled=True,
    )
    kwargs.update(overrides)
    client = GPT56ResponsesClient(**kwargs)
    monkeypatch.setattr(client, "_new_client", lambda: FakeOpenAI(endpoint))
    return client


def valid_response(output_parsed=None, model="gpt-5.6-sol-2026-01-01"):
    if output_parsed is None:
        output_parsed = _full_analysis()
    return FakeResponse(model=model, output_parsed=output_parsed)


# ---------------------------------------------------------------------------
# Configuration: exact model + effort lock (Finding 1, 8)
# ---------------------------------------------------------------------------
def _local_settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        deployment_environment="local",
        engine_auth_mode="local_dev_open",
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_default_model_and_effort_are_exact():
    s = _local_settings()
    assert s.openai_model == "gpt-5.6"
    assert s.openai_reasoning_effort == "medium"


def test_reasoning_effort_rejects_unknown_values():
    with pytest.raises(ValidationError):
        _local_settings(openai_reasoning_effort="banana")


def test_reasoning_effort_rejects_all_documented_efforts_except_medium():
    """GPT-5.6 documents these efforts, but Mobi enforces medium only."""
    for effort in DOCUMENTED_REASONING_EFFORTS - {"medium"}:
        with pytest.raises(ValidationError):
            _local_settings(openai_reasoning_effort=effort)
    assert _local_settings(openai_reasoning_effort="medium").openai_reasoning_effort == "medium"


def test_model_rejects_everything_but_exact_alias():
    for model in ("gpt-4o", "gpt-5.6-sol", "gpt-5.60", "gpt-5.5", "", "gpt-5.6-terra"):
        with pytest.raises(ValidationError):
            _local_settings(openai_model=model)
    assert _local_settings(openai_model="gpt-5.6").openai_model == "gpt-5.6"
    # Surrounding whitespace is normalized to the exact alias, not rejected.
    assert _local_settings(openai_model="  gpt-5.6  ").openai_model == "gpt-5.6"


def test_live_disabled_by_default():
    s = _local_settings()
    assert s.enable_live_project_analysis is False


def test_readiness_never_leaks_key_material():
    s = _local_settings(
        openai_api_key="configured-provider-key-marker",
        enable_live_project_analysis=True,
    )
    readiness = s.project_analysis_readiness()
    assert readiness["model"] == "gpt-5.6"
    assert readiness["reasoning_effort"] == "medium"
    assert readiness["api_key_present"] is True
    assert readiness["live_enabled"] is True
    assert readiness["ready_for_live_call"] is True
    assert "configured-provider-key-marker" not in json.dumps(readiness)
    assert "openai_api_key" not in readiness


def test_readiness_not_ready_without_key_or_enablement():
    assert _local_settings().project_analysis_readiness()["ready_for_live_call"] is False
    assert (
        _local_settings(enable_live_project_analysis=True)
        .project_analysis_readiness()["ready_for_live_call"]
        is False
    )


# ---------------------------------------------------------------------------
# Client: exact model/effort enforced BEFORE any SDK call (Finding 1, 6)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "overrides",
    [
        {"model": "gpt-4o"},
        {"model": "gpt-5.6-sol"},
        {"model": "gpt-5.60"},
        {"reasoning_effort": "high"},
        {"reasoning_effort": "none"},
        {"reasoning_effort": "xhigh"},
    ],
)
def test_client_rejects_wrong_model_or_effort_with_zero_sdk_calls(monkeypatch, overrides):
    endpoint = FakeResponsesEndpoint(response=valid_response())
    # A client somehow built outside the lock must fail closed before dispatch.
    client = GPT56ResponsesClient(
        api_key="configured-provider-marker",
        model=overrides.get("model", "gpt-5.6"),
        reasoning_effort=overrides.get("reasoning_effort", "medium"),
        timeout_seconds=30,
        live_enabled=True,
    )
    called = {"new_client": 0}

    def _spy():
        called["new_client"] += 1
        return FakeOpenAI(endpoint)

    monkeypatch.setattr(client, "_new_client", _spy)
    with pytest.raises(ResponsesConfigInvalid):
        client.parse(
            system_prompt="s", source_blocks=["x"], text_format=ProjectAnalysis,
            schema_version="1.0", max_source_chars=100,
        )
    assert called["new_client"] == 0
    assert endpoint.calls == []


# ---------------------------------------------------------------------------
# Returned-model strict acceptance (Finding 2)
# ---------------------------------------------------------------------------
def test_accepted_returned_models():
    for m in ("gpt-5.6", "gpt-5.6-sol", "gpt-5.6-sol-2026-07-01"):
        assert _is_accepted_returned_model(m), m


@pytest.mark.parametrize(
    "returned",
    [
        "gpt-5.60",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.6-sol-terra",
        "gpt-5.6-sol-preview",
        "gpt-5.6-sol-2026-7-1",
        "gpt-5.6-sol-2026-02-30",
        "gpt-5.6-sol-2026-13-01",
        "gpt-5.6-sol-2026-00-10",
        "gpt-5.6-sol-2026-07-01-preview",
        "gpt-4o",
        "gpt-5.6-",
        "GPT-5.6",
        None,
        42,
        [],
        {"model": "gpt-5.6"},
    ],
)
def test_rejected_returned_models(returned):
    assert not _is_accepted_returned_model(returned)


@pytest.mark.parametrize("returned", ["gpt-5.60", "gpt-5.6-terra", "gpt-5.6-luna"])
def test_variant_returned_model_is_mismatch(monkeypatch, returned):
    resp = valid_response(model=returned)
    endpoint = FakeResponsesEndpoint(response=resp)
    client = make_client(monkeypatch, endpoint)
    with pytest.raises(ResponsesModelMismatch):
        client.parse(
            system_prompt="s", source_blocks=["x"], text_format=ProjectAnalysis,
            schema_version="1.0", max_source_chars=100,
        )


@pytest.mark.parametrize("returned", ["gpt-5.6", "gpt-5.6-sol", "gpt-5.6-sol-2026-07-01"])
def test_accepted_returned_model_passes(monkeypatch, returned):
    endpoint = FakeResponsesEndpoint(response=valid_response(model=returned))
    client = make_client(monkeypatch, endpoint)
    result = client.parse(
        system_prompt="s", source_blocks=["x"], text_format=ProjectAnalysis,
        schema_version="1.0", max_source_chars=100,
    )
    assert result.metadata.returned_model == returned


# ---------------------------------------------------------------------------
# Schema guarantees: no numbers, no defaults, strict (Finding 3, 4)
# ---------------------------------------------------------------------------
def _find_default_keys(node, path="root"):
    """Return paths where a JSON-Schema ``default`` keyword appears (as a key)."""
    hits = []
    if isinstance(node, dict):
        if "default" in node:
            hits.append(path)
        for key, value in node.items():
            hits.extend(_find_default_keys(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            hits.extend(_find_default_keys(value, f"{path}[{i}]"))
    return hits


def _walk_strict_schema(node, path="root"):
    """Yield (kind, path) problems for a generated strict JSON schema."""
    problems = []
    if isinstance(node, dict):
        if "default" in node:
            problems.append(("default", path))
        if node.get("type") == "object":
            if node.get("additionalProperties") is not False:
                problems.append(("additionalProperties", path))
            props = set((node.get("properties") or {}).keys())
            required = set(node.get("required") or [])
            if props != required:
                problems.append(("required_mismatch", path))
        for key, value in node.items():
            problems.extend(_walk_strict_schema(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            problems.extend(_walk_strict_schema(value, f"{path}[{i}]"))
    return problems


@pytest.mark.parametrize(
    "model",
    [ProjectAnalysis, LiveSheetClassificationOutput, LiveScopeExtractionOutput, TinyProbe],
)
def test_generated_strict_schema_is_default_free_and_closed(model):
    """The SDK's real strict conversion must produce: no `default` anywhere, every
    object closed (additionalProperties=false), and required == all properties."""
    schema = to_strict_json_schema(model)
    problems = _walk_strict_schema(schema)
    assert problems == [], problems


def test_project_analysis_has_no_schema_version_field():
    """schema_version is injected into metadata after parse, never model output."""
    assert "schema_version" not in ProjectAnalysis.model_fields


def test_project_analysis_forbids_extra_fields():
    with pytest.raises(ValidationError):
        _full_analysis(total_price="123.45")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "model",
    [ProjectAnalysis, ScopeObservation, LiveScopeExtractionOutput, TinyProbe],
)
def test_schemas_have_no_measurement_or_price_fields(model):
    banned = {"price", "cost", "total", "quantity", "amount", "unit_cost", "rate", "value"}
    # ``value`` is banned for output models EXCEPT the sourced-text wrapper, which
    # holds a bounded verbatim string, not a number.
    for name in model.model_fields:
        if model is SourcedText and name == "value":
            continue
        assert not any(token in name for token in banned), (model.__name__, name)


def test_scope_observation_rejects_injected_quantity():
    with pytest.raises(ValidationError):
        ScopeObservation(
            description="Paint walls", observed_in_source=True,
            trade=None, source_reference=None, quantity="1000 SF",  # type: ignore[call-arg]
        )


def test_scope_observation_requires_observed_flag():
    """observed_in_source has no default: it must be supplied explicitly."""
    with pytest.raises(ValidationError):
        ScopeObservation(description="x", trade=None, source_reference=None)  # type: ignore[call-arg]


def test_source_reference_requires_a_locator():
    with pytest.raises(ValidationError):
        _ref(quote="a quote with no locator")
    ref = _ref(page_number=3, sheet_number="A-101")
    assert ref.page_number == 3


def test_sourced_text_requires_reference():
    with pytest.raises(ValidationError):
        SourcedText(value="Acme Tower")  # type: ignore[call-arg]
    sourced = SourcedText(value="Acme Tower", source_reference=_ref(document_id="D0"))
    assert sourced.value == "Acme Tower"


def test_scope_observation_observed_requires_reference():
    """A directly observed scope item MUST carry a source reference; an inferred
    item may omit it (observed_in_source false)."""
    with pytest.raises(ValidationError):
        ScopeObservation(
            trade="painting", description="Paint walls",
            observed_in_source=True, source_reference=None,
        )
    # observed with a reference is valid...
    obs = ScopeObservation(
        trade="painting", description="Paint walls",
        observed_in_source=True, source_reference=_ref(document_id="D0"),
    )
    assert obs.observed_in_source is True
    # ...and an inferred item may omit the reference.
    inferred = ScopeObservation(
        trade=None, description="Possibly repaint soffits",
        observed_in_source=False, source_reference=None,
    )
    assert inferred.observed_in_source is False


@pytest.mark.parametrize(
    "factory",
    [
        lambda ref: SheetIndexEntry(sheet_number="A-101", title=None, discipline=None, source_reference=ref),
        lambda ref: SpecificationSection(section_number="099000", title=None, source_reference=ref),
        lambda ref: Alternate(identifier="ALT-1", description="Alt roof", source_reference=ref),
        lambda ref: Allowance(identifier="ALW-1", description="Signage allowance", source_reference=ref),
        lambda ref: UnitRequirement(description="Unit price for rock excavation", source_reference=ref),
        lambda ref: BidInstruction(description="Bids due by 2pm", source_reference=ref),
        lambda ref: Exclusion(description="Hazmat abatement excluded", source_reference=ref),
    ],
)
def test_factual_item_requires_source_reference(factory):
    """Each factual output item requires a (non-null) source_reference."""
    with pytest.raises(ValidationError):
        factory(None)
    item = factory(_ref(document_id="D0"))
    assert item.source_reference is not None


def test_plan_spec_conflict_requires_both_references():
    """A conflict cannot be established without both plan and spec sides."""
    for plan, spec in ((None, _ref(document_id="D0")), (_ref(document_id="D0"), None), (None, None)):
        with pytest.raises(ValidationError):
            PlanSpecConflict(
                description="Door schedule disagrees with plan",
                severity="high", plan_reference=plan, spec_reference=spec,
            )
    conflict = PlanSpecConflict(
        description="Door schedule disagrees with plan", severity="high",
        plan_reference=_ref(document_id="D0"), spec_reference=_ref(document_id="D1"),
    )
    assert conflict.plan_reference is not None and conflict.spec_reference is not None


def test_project_type_is_a_sourced_nullable_value():
    """project_type is a sourced enum value or null — never a bare unsourced enum."""
    with pytest.raises(ValidationError):
        SourcedProjectType(value="commercial")  # type: ignore[call-arg]
    sourced = SourcedProjectType(value="commercial", source_reference=_ref(document_id="D0"))
    assert sourced.value == "commercial"
    # The top-level field accepts the sourced value or null.
    assert _full_analysis(project_type=sourced).project_type.value == "commercial"
    assert _full_analysis(project_type=None).project_type is None


def test_trades_and_plan_sheets_and_exclusions_are_sourced():
    """identified_trades / relevant_plan_sheets / exclusions carry source refs."""
    analysis = _full_analysis(
        identified_trades=[SourcedText(value="painting", source_reference=_ref(document_id="D0"))],
        relevant_plan_sheets=[SourcedText(value="A-101", source_reference=_ref(document_id="D0"))],
        exclusions=[Exclusion(description="Hazmat excluded", source_reference=_ref(document_id="D0"))],
        assumptions=["Reviewer assumption stays unsourced"],
    )
    assert analysis.identified_trades[0].source_reference is not None
    assert analysis.relevant_plan_sheets[0].source_reference is not None
    assert analysis.exclusions[0].source_reference is not None
    # assumptions remain bare strings (unsourced reviewer notes).
    assert analysis.assumptions == ["Reviewer assumption stays unsourced"]


# ---------------------------------------------------------------------------
# Client: contract + metadata (Finding 7)
# ---------------------------------------------------------------------------
def test_parse_uses_exact_model_effort_no_tools_no_store(monkeypatch):
    endpoint = FakeResponsesEndpoint(response=valid_response())
    client = make_client(monkeypatch, endpoint)
    result = client.parse(
        system_prompt="system",
        source_blocks=["source text"],
        text_format=ProjectAnalysis,
        schema_version="1.0",
        max_source_chars=1000,
    )
    call = endpoint.calls[0]
    assert call["model"] == "gpt-5.6"
    assert call["reasoning"] == {"effort": "medium"}
    assert call["tools"] == []
    assert call["store"] is False
    assert call["text_format"] is ProjectAnalysis
    md = result.metadata
    assert md.requested_model == "gpt-5.6"
    assert md.reasoning_effort == "medium"
    assert _is_accepted_returned_model(md.returned_model)
    assert md.parse_success is True
    assert md.response_id == "resp_test_123"
    assert md.request_id == "req_test_123"
    assert md.usage == {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19}
    # Schema version is injected server-side into metadata (never model output).
    assert md.schema_version == "1.0"


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


def _sdk_with_capture(captured, *, model, output_text):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, request=request, json=_responses_envelope(model=model, output_text=output_text)
        )

    return OpenAI(
        api_key="configured-provider-marker",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize(
    "text_format,instance",
    [
        (ProjectAnalysis, None),  # filled below
        (LiveSheetClassificationOutput, LiveSheetClassificationOutput(classifications=[])),
        (
            LiveScopeExtractionOutput,
            LiveScopeExtractionOutput(candidates=[]),
        ),
        (
            TinyProbe,
            TinyProbe(
                project_type="commercial",
                one_line_summary="synthetic probe",
                source_reference=_ProbeRef(document_id="D0", page_number=1),
            ),
        ),
    ],
)
def test_real_sdk_246_serializes_strict_schema_and_parses(monkeypatch, text_format, instance):
    """Exercise the installed SDK's real request serializer/parser (no network) for
    EVERY text_format schema: verify the on-wire body uses model gpt-5.6, reasoning
    medium, tools=[], store=false, and a strict json_schema, and that the response
    parses back into the expected model."""
    if instance is None:
        instance = _full_analysis()
    output_text = instance.model_dump_json()

    captured: dict = {}
    sdk = _sdk_with_capture(captured, model="gpt-5.6-sol-2026-07-01", output_text=output_text)
    client = GPT56ResponsesClient(
        api_key="configured-provider-marker",
        model="gpt-5.6",
        reasoning_effort="medium",
        timeout_seconds=30,
        live_enabled=True,
    )
    monkeypatch.setattr(client, "_new_client", lambda: sdk)

    result = client.parse(
        system_prompt="system",
        source_blocks=["synthetic source"],
        text_format=text_format,
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
    # The serialized schema itself must be default-free (checked by JSON key, not
    # a substring match — field descriptions legitimately mention "default").
    assert not _find_default_keys(body["text"]["format"]["schema"])
    assert isinstance(result.parsed, text_format)
    assert result.metadata.returned_model == "gpt-5.6-sol-2026-07-01"


def test_input_is_bounded_to_max_chars(monkeypatch):
    endpoint = FakeResponsesEndpoint(response=valid_response())
    client = make_client(monkeypatch, endpoint)
    client.parse(
        system_prompt="system",
        source_blocks=["A" * 5000],
        text_format=ProjectAnalysis,
        schema_version="1.0",
        max_source_chars=50,
    )
    user_message = endpoint.calls[0]["input"][1]
    assert user_message["role"] == "user"
    assert len(user_message["content"]) <= 50


def test_no_filesystem_paths_or_urls_in_input(monkeypatch):
    endpoint = FakeResponsesEndpoint(response=valid_response())
    client = make_client(monkeypatch, endpoint)
    client.parse(
        system_prompt="system",
        source_blocks=["just supplied source text"],
        text_format=ProjectAnalysis,
        schema_version="1.0",
        max_source_chars=1000,
    )
    messages = endpoint.calls[0]["input"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[1]["content"] == "just supplied source text"


# ---------------------------------------------------------------------------
# Client: fail-closed behavior
# ---------------------------------------------------------------------------
def test_live_disabled_is_unavailable(monkeypatch):
    endpoint = FakeResponsesEndpoint(response=valid_response())
    client = make_client(monkeypatch, endpoint, live_enabled=False)
    with pytest.raises(ResponsesUnavailable):
        client.parse(
            system_prompt="s", source_blocks=["x"], text_format=ProjectAnalysis,
            schema_version="1.0", max_source_chars=100,
        )
    assert endpoint.calls == []


def test_missing_key_is_unavailable(monkeypatch):
    endpoint = FakeResponsesEndpoint(response=valid_response())
    client = make_client(monkeypatch, endpoint, api_key=None)
    with pytest.raises(ResponsesUnavailable):
        client.parse(
            system_prompt="s", source_blocks=["x"], text_format=ProjectAnalysis,
            schema_version="1.0", max_source_chars=100,
        )
    assert endpoint.calls == []


def _run(monkeypatch, *, response=None, exc=None):
    endpoint = FakeResponsesEndpoint(response=response, exc=exc)
    client = make_client(monkeypatch, endpoint)
    return client.parse(
        system_prompt="s", source_blocks=["x"], text_format=ProjectAnalysis,
        schema_version="1.0", max_source_chars=100,
    )


def test_refusal_becomes_safe_error(monkeypatch):
    resp = FakeResponse(model="gpt-5.6", output_parsed=None, output=[_RefusalItem()])
    with pytest.raises(ResponsesRefused):
        _run(monkeypatch, response=resp)


def test_empty_output_becomes_safe_error(monkeypatch):
    resp = FakeResponse(model="gpt-5.6", output_parsed=None, output=[])
    with pytest.raises(ResponsesEmptyOutput):
        _run(monkeypatch, response=resp)


def test_schema_invalid_parse_rejected(monkeypatch):
    resp = FakeResponse(model="gpt-5.6", output_parsed={"not": "a model"})
    with pytest.raises(ResponsesSchemaInvalid):
        _run(monkeypatch, response=resp)


def test_model_mismatch_rejected(monkeypatch):
    resp = valid_response(model="gpt-4o-mini")
    with pytest.raises(ResponsesModelMismatch):
        _run(monkeypatch, response=resp)


@pytest.mark.parametrize(
    "exc_name,expected,retryable",
    [
        ("APITimeoutError", ResponsesTimeout, True),
        ("RateLimitError", ResponsesRateLimited, True),
        ("APIConnectionError", ResponsesProviderError, True),
        ("BadRequestError", ResponsesProviderError, False),
    ],
)
def test_sdk_exceptions_mapped(monkeypatch, exc_name, expected, retryable):
    exc_type = type(exc_name, (Exception,), {})
    with pytest.raises(expected) as excinfo:
        _run(monkeypatch, exc=exc_type("provider said boom"))
    err = excinfo.value
    assert err.retryable is retryable
    assert "boom" not in err.safe_message


def test_auth_error_is_unavailable(monkeypatch):
    exc_type = type("AuthenticationError", (Exception,), {})
    with pytest.raises(ResponsesUnavailable):
        _run(monkeypatch, exc=exc_type("bad key"))


def test_errors_never_leak_api_key(monkeypatch):
    exc_type = type("BadRequestError", (Exception,), {})
    with pytest.raises(ResponsesError) as excinfo:
        _run(monkeypatch, exc=exc_type("provider-secret-marker in payload"))
    assert "provider-secret-marker" not in excinfo.value.safe_message


# ---------------------------------------------------------------------------
# Service orchestration + grounding (Finding 5)
# ---------------------------------------------------------------------------
class StubClient:
    """Duck-typed client returning a scripted sequence of results/exceptions."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _request(docs=1, text="SECTION 099000 PAINTING. Commercial project."):
    return ProjectAnalysisRequest(
        tenant_id="tenant_a",
        company_id="company_a",
        project_id="project_a",
        documents=[
            AnalysisSourceDocument(
                document_id=f"D{i}",
                document_name=f"doc_{i}.txt",
                page_number=i + 1,
                text=text,
            )
            for i in range(docs)
        ],
    )


def _parsed_result(parsed=None, model="gpt-5.6"):
    return ParsedResult(
        parsed=parsed if parsed is not None else _full_analysis(confidence_level="low"),
        metadata=ProviderCallMetadata(
            requested_model=model,
            returned_model="gpt-5.6-sol",
            reasoning_effort="medium",
            schema_version="1.0",
        ),
    )


def test_service_returns_validated_analysis_and_metadata():
    result = analyze_project(_request(), client=StubClient([_parsed_result()]))
    assert isinstance(result.parsed, ProjectAnalysis)
    assert result.metadata.requested_model == "gpt-5.6"
    assert result.metadata.reasoning_effort == "medium"


def test_service_retries_retryable_then_succeeds():
    stub = StubClient([ResponsesTimeout(), _parsed_result()])
    result = analyze_project(_request(), client=stub)
    assert stub.calls == 2
    assert isinstance(result.parsed, ProjectAnalysis)


def test_service_does_not_retry_non_retryable():
    stub = StubClient([ResponsesRefused(), _parsed_result()])
    with pytest.raises(ResponsesRefused):
        analyze_project(_request(), client=stub)
    assert stub.calls == 1


def test_service_enforces_document_bound(monkeypatch):
    monkeypatch.setattr(settings, "project_analysis_max_source_documents", 1)
    stub = StubClient([_parsed_result()])
    with pytest.raises(ResponsesError) as excinfo:
        analyze_project(_request(docs=2), client=stub)
    assert excinfo.value.code == "analysis_input_too_large"
    assert stub.calls == 0


def test_service_forwards_only_bounded_source_text():
    class Recorder:
        def __init__(self):
            self.kwargs = None

        def parse(self, **kwargs):
            self.kwargs = kwargs
            return _parsed_result()

    rec = Recorder()
    analyze_project(_request(docs=2), client=rec)
    blocks = rec.kwargs["source_blocks"]
    assert len(blocks) == 2
    assert all(block.startswith("### SOURCE (") for block in blocks)
    assert "/" not in rec.kwargs["source_blocks"][0].split("\n", 1)[0]


# --- Grounding: adversarial -------------------------------------------------
def test_grounding_accepts_matching_reference_and_quote():
    analysis = _full_analysis(
        project_name=SourcedText(
            value="Acme Tower",
            source_reference=_ref(document_id="D0", quote="SECTION 099000 PAINTING"),
        ),
        source_references=[_ref(document_id="D0", page_number=1)],
    )
    result = analyze_project(_request(), client=StubClient([_parsed_result(analysis)]))
    assert result.parsed.project_name.value == "Acme Tower"


def test_grounding_rejects_unknown_document_id():
    analysis = _full_analysis(
        source_references=[_ref(document_id="NOT-A-REAL-DOC")],
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(_request(), client=StubClient([_parsed_result(analysis)]))


def test_grounding_rejects_unknown_document_name():
    analysis = _full_analysis(
        source_references=[_ref(document_name="fabricated.pdf")],
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(_request(), client=StubClient([_parsed_result(analysis)]))


def test_grounding_rejects_hallucinated_quote():
    analysis = _full_analysis(
        source_references=[
            _ref(document_id="D0", quote="THIS TEXT IS NOWHERE IN THE SOURCE")
        ],
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(_request(), client=StubClient([_parsed_result(analysis)]))


def test_grounding_rejects_quote_from_wrong_document():
    # Two docs with different text; quote belongs to doc D1 but cites D0.
    req = ProjectAnalysisRequest(
        tenant_id="t", company_id="c", project_id="p",
        documents=[
            AnalysisSourceDocument(document_id="D0", document_name="a.txt",
                                   page_number=1, text="ALPHA CONTENT ONLY"),
            AnalysisSourceDocument(document_id="D1", document_name="b.txt",
                                   page_number=2, text="BETA CONTENT ONLY"),
        ],
    )
    analysis = _full_analysis(
        source_references=[_ref(document_id="D0", quote="BETA CONTENT ONLY")]
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(req, client=StubClient([_parsed_result(analysis)]))


def test_grounding_rejects_nested_reference():
    """An ungrounded reference deep in the tree (not top-level) is still caught."""
    analysis = _full_analysis(
        scope_items=[
            ScopeObservation(
                trade="painting",
                description="Paint corridors",
                observed_in_source=True,
                source_reference=_ref(document_id="GHOST"),
            )
        ],
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(_request(), client=StubClient([_parsed_result(analysis)]))


def _request_no_locators(text="SECTION 099000 PAINTING."):
    """A whole-document request whose source has no page/sheet locator."""
    return ProjectAnalysisRequest(
        tenant_id="t", company_id="c", project_id="p",
        documents=[
            AnalysisSourceDocument(
                document_id="D0", document_name="spec.txt",
                page_number=None, sheet_number=None, text=text,
            )
        ],
    )


def test_grounding_rejects_invented_page_against_missing_source_page():
    """A source with no page must not act as a wildcard for a model-supplied page."""
    analysis = _full_analysis(
        source_references=[_ref(document_id="D0", page_number=7)],
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(_request_no_locators(), client=StubClient([_parsed_result(analysis)]))


def test_grounding_rejects_invented_sheet_against_missing_source_sheet():
    """A source with no sheet must not act as a wildcard for a model-supplied sheet."""
    analysis = _full_analysis(
        source_references=[_ref(document_id="D0", sheet_number="A-999")],
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(_request_no_locators(), client=StubClient([_parsed_result(analysis)]))


def test_grounding_rejects_mismatched_page_number():
    """A model-supplied page that differs from the source document's page fails."""
    # _request() builds D0 with page_number=1; cite a different page.
    analysis = _full_analysis(
        source_references=[_ref(document_id="D0", page_number=2)],
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(_request(), client=StubClient([_parsed_result(analysis)]))


def test_grounding_rejects_mismatched_sheet_number():
    """A model-supplied sheet that differs from the source document's sheet fails."""
    req = ProjectAnalysisRequest(
        tenant_id="t", company_id="c", project_id="p",
        documents=[
            AnalysisSourceDocument(
                document_id="D0", document_name="a.txt",
                page_number=1, sheet_number="A-101", text="ALPHA",
            )
        ],
    )
    analysis = _full_analysis(
        source_references=[_ref(document_id="D0", sheet_number="A-102")],
    )
    with pytest.raises(ResponsesGroundingError):
        analyze_project(req, client=StubClient([_parsed_result(analysis)]))


def test_grounding_accepts_matching_page_and_sheet():
    """When the model's page/sheet exactly match the source document, it passes."""
    req = ProjectAnalysisRequest(
        tenant_id="t", company_id="c", project_id="p",
        documents=[
            AnalysisSourceDocument(
                document_id="D0", document_name="a.txt",
                page_number=3, sheet_number="A-101", text="ALPHA",
            )
        ],
    )
    analysis = _full_analysis(
        source_references=[_ref(document_id="D0", page_number=3, sheet_number="A-101")],
    )
    result = analyze_project(req, client=StubClient([_parsed_result(analysis)]))
    assert isinstance(result.parsed, ProjectAnalysis)


def test_grounding_normalizes_whitespace_and_case_for_quotes():
    analysis = _full_analysis(
        source_references=[
            _ref(document_id="D0", quote="section 099000   painting")
        ],
    )
    result = analyze_project(_request(), client=StubClient([_parsed_result(analysis)]))
    assert isinstance(result.parsed, ProjectAnalysis)


def test_prompt_states_source_only_and_no_pricing_contract():
    prompt = service.SYSTEM_PROMPT.lower()
    assert "use only the supplied source text" in prompt
    assert "never" in prompt and "price" in prompt
    assert "measurement" in prompt
    assert "source-reference" in prompt
    assert "assumptions" in prompt


# ---------------------------------------------------------------------------
# Live verification probe: preflight makes zero SDK calls (Finding 6)
# ---------------------------------------------------------------------------
def test_probe_preflight_passes_for_exact_lock():
    assert _preflight_exact_model_effort("gpt-5.6", "medium") == []


@pytest.mark.parametrize(
    "model,effort",
    [("gpt-4o", "medium"), ("gpt-5.6", "high"), ("gpt-5.6-sol", "medium"), ("gpt-5.6", "none")],
)
def test_probe_preflight_flags_non_exact(model, effort):
    assert _preflight_exact_model_effort(model, effort)


def test_probe_tinyprobe_is_default_free():
    for model in (TinyProbe, _ProbeRef):
        assert not _walk_strict_schema(to_strict_json_schema(model))


def test_probe_constants_match_enforced_lock():
    assert EXPECTED_MODEL_ALIAS == "gpt-5.6"
    assert EXPECTED_REASONING_EFFORT == "medium"
