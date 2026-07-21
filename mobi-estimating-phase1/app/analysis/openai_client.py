"""Thin, fail-closed wrapper around the OpenAI Responses API structured-output path.

Official pattern (docs verified 2026-07-21):

    response = client.responses.parse(
        model="gpt-5.6",
        input=[...],
        text_format=PydanticModel,
        reasoning={"effort": "medium"},
    )
    parsed = response.output_parsed

This wrapper is the single place that touches the OpenAI SDK. It:

* imports the SDK lazily (the app runs fully without it installed),
* passes NO tools and disables server-side storage of the request,
* bounds the model input to already-supplied source text,
* converts every failure — refusal, empty output, schema failure, timeout, rate
  limit, provider error, model mismatch — into a safe, typed error that never
  leaks plan text, credentials, raw provider payloads, or stack traces.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from app.analysis.schemas import ParsedResult, ProviderCallMetadata
from app.config import ENFORCED_MODEL_ALIAS, ENFORCED_REASONING_EFFORT

logger = logging.getLogger("mobi.analysis.openai")

# The exact model alias and reasoning effort this path is allowed to request.
# These mirror the config-level lock and are re-checked independently in the
# client (see ``_ensure_ready``) so a client constructed with the wrong model or
# effort — whatever its source — fails closed before any SDK/network dispatch.
EXPECTED_MODEL_ALIAS = ENFORCED_MODEL_ALIAS
EXPECTED_REASONING_EFFORT = ENFORCED_REASONING_EFFORT

# Backward-compatible alias constant (the bare requested alias). Retained for
# imports; returned-model acceptance now uses the strict pattern below, not a
# permissive prefix match.
EXPECTED_MODEL_PREFIX = ENFORCED_MODEL_ALIAS

# Strict acceptance pattern for the *returned* model name. ``gpt-5.6`` resolves to
# GPT-5.6 Sol (docs verified 2026-07-21), so we accept only:
#   * the exact alias ``gpt-5.6``
#   * the documented Sol model id ``gpt-5.6-sol``
#   * a date-pinned Sol snapshot ``gpt-5.6-sol-YYYY-MM-DD``.
# Anything else is a silent swap and fails closed: ``gpt-5.60`` (no delimiter —
# a different model number), ``gpt-5.6-terra`` / ``gpt-5.6-luna`` (non-Sol
# families the alias does not resolve to), etc.
_DATED_SOL_RE = re.compile(r"^gpt-5\.6-sol-([0-9]{4}-[0-9]{2}-[0-9]{2})$")


def _is_accepted_returned_model(returned_model: object) -> bool:
    """True only for the exact ``gpt-5.6`` alias or a GPT-5.6 Sol snapshot name."""

    if not isinstance(returned_model, str):
        return False
    if returned_model in {"gpt-5.6", "gpt-5.6-sol"}:
        return True
    match = _DATED_SOL_RE.fullmatch(returned_model)
    if match is None:
        return False
    try:
        parsed = date.fromisoformat(match.group(1))
    except ValueError:
        return False
    # Require the canonical zero-padded ISO spelling as well as a valid calendar
    # date; this rejects impossible dates and alternate/noncanonical forms.
    return parsed.isoformat() == match.group(1)


# --- Error taxonomy --------------------------------------------------------
class ResponsesError(Exception):
    """Safe, client-facing provider error. Carries a stable code, a sanitized
    message, and whether a retry could plausibly help."""

    def __init__(self, code: str, safe_message: str, *, retryable: bool) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable


class ResponsesUnavailable(ResponsesError):
    """Live path not usable (disabled, no key, SDK absent, auth/permission)."""

    def __init__(self, safe_message: str = "Live analysis is unavailable") -> None:
        super().__init__("analysis_unavailable", safe_message, retryable=False)


class ResponsesTimeout(ResponsesError):
    def __init__(self, safe_message: str = "Analysis provider call timed out") -> None:
        super().__init__("analysis_timeout", safe_message, retryable=True)


class ResponsesRateLimited(ResponsesError):
    def __init__(self, safe_message: str = "Analysis provider rate limited the request") -> None:
        super().__init__("analysis_rate_limited", safe_message, retryable=True)


class ResponsesProviderError(ResponsesError):
    def __init__(
        self,
        safe_message: str = "Analysis provider call failed",
        *,
        retryable: bool = True,
    ) -> None:
        super().__init__("analysis_provider_error", safe_message, retryable=retryable)


class ResponsesRefused(ResponsesError):
    def __init__(self, safe_message: str = "Model refused to answer") -> None:
        super().__init__("analysis_refused", safe_message, retryable=False)


class ResponsesEmptyOutput(ResponsesError):
    def __init__(self, safe_message: str = "Model returned no parsed output") -> None:
        super().__init__("analysis_empty_output", safe_message, retryable=False)


class ResponsesSchemaInvalid(ResponsesError):
    def __init__(self, safe_message: str = "Model output failed schema validation") -> None:
        super().__init__("analysis_schema_invalid", safe_message, retryable=False)


class ResponsesModelMismatch(ResponsesError):
    def __init__(self, safe_message: str = "Provider returned an unexpected model") -> None:
        super().__init__("analysis_model_mismatch", safe_message, retryable=False)


class ResponsesConfigInvalid(ResponsesError):
    """Client configured with a model/effort outside the enforced product lock.

    Fail closed BEFORE any SDK/network dispatch: a client that was somehow built
    with a model other than ``gpt-5.6`` or an effort other than ``medium`` must
    never reach a billable call.
    """

    def __init__(self, safe_message: str = "Live analysis is misconfigured") -> None:
        super().__init__("analysis_config_invalid", safe_message, retryable=False)


class ResponsesGroundingError(ResponsesError):
    """Model output referenced a source/quote not present in the supplied request.

    Non-retryable: an ungrounded reference is a correctness failure, not a
    transient one, and must never be silently downgraded into an accepted result.
    """

    def __init__(
        self, safe_message: str = "Model output failed source-grounding validation"
    ) -> None:
        super().__init__("analysis_grounding_failed", safe_message, retryable=False)


# --- SDK plumbing ----------------------------------------------------------
def _load_openai() -> Any:
    try:
        import openai  # optional dependency; imported lazily
    except Exception as exc:  # pragma: no cover - depends on env
        raise ResponsesUnavailable(
            "openai SDK is not installed in this environment"
        ) from exc
    return openai


def _classify_sdk_exception(exc: Exception) -> ResponsesError:
    """Map an SDK/runtime exception to a safe typed error.

    Classification is by class name so it stays robust whether the real SDK or a
    test double raised it. The original exception is intentionally not chained
    into the message so provider internals never reach a client.
    """

    name = type(exc).__name__
    if "Timeout" in name:
        return ResponsesTimeout()
    if "RateLimit" in name:
        return ResponsesRateLimited()
    if "Connection" in name or "InternalServer" in name:
        return ResponsesProviderError(retryable=True)
    if "Authentication" in name or "Permission" in name:
        return ResponsesUnavailable("Analysis provider rejected the credentials")
    if any(
        token in name
        for token in ("BadRequest", "InvalidRequest", "NotFound", "UnprocessableEntity", "Conflict")
    ):
        return ResponsesProviderError(retryable=False)
    # Unknown provider/runtime failure: conservatively retryable, but sanitized.
    logger.warning("unclassified analysis provider error: %s", name)
    return ResponsesProviderError(retryable=True)


def _find_refusal(response: Any) -> bool:
    """Best-effort detection of a structured-output refusal item."""

    output = getattr(response, "output", None) or []
    for item in output:
        content = getattr(item, "content", None) or []
        for part in content:
            if getattr(part, "type", None) == "refusal":
                return True
    return False


def _safe_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    counts: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, int):
            counts[key] = value
    return counts


def _bounded_user_content(source_blocks: list[str], max_chars: int) -> str:
    """Join already-supplied source blocks and hard-cap the total length.

    The model only ever sees this text. There is no filesystem/URL access, no
    tool, and no secret material in the input.
    """

    joined = "\n\n".join(block for block in source_blocks if block)
    if len(joined) > max_chars:
        joined = joined[:max_chars]
    return joined


class GPT56ResponsesClient:
    """Structured-output client bound to a single model alias + reasoning effort."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        reasoning_effort: str,
        timeout_seconds: int,
        live_enabled: bool,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._timeout = timeout_seconds
        self._live_enabled = live_enabled

    @property
    def model(self) -> str:
        return self._model

    @property
    def reasoning_effort(self) -> str:
        return self._reasoning_effort

    def _ensure_ready(self) -> None:
        # Independent, in-client enforcement of the exact model/effort lock. This
        # runs before any credential/SDK use so a client built with the wrong
        # model or effort fails closed with zero SDK/network calls, regardless of
        # what config validation did upstream.
        if self._model != EXPECTED_MODEL_ALIAS:
            raise ResponsesConfigInvalid(
                f"Analysis is locked to model {EXPECTED_MODEL_ALIAS!r}"
            )
        if self._reasoning_effort != EXPECTED_REASONING_EFFORT:
            raise ResponsesConfigInvalid(
                f"Analysis is locked to reasoning effort {EXPECTED_REASONING_EFFORT!r}"
            )
        if not self._live_enabled:
            raise ResponsesUnavailable(
                "Live analysis is disabled (requires explicit enablement)"
            )
        if not self._api_key:
            raise ResponsesUnavailable("No OpenAI API key configured")

    def _new_client(self) -> Any:
        openai = _load_openai()
        return openai.OpenAI(api_key=self._api_key, timeout=self._timeout)

    def parse(
        self,
        *,
        system_prompt: str,
        source_blocks: list[str],
        text_format: type,
        schema_version: str,
        max_source_chars: int,
    ) -> ParsedResult:
        """Call ``responses.parse`` and return the validated parse + metadata.

        Raises a :class:`ResponsesError` subclass on any failure. Never returns
        unvalidated output and never leaks provider internals.
        """

        self._ensure_ready()

        user_content = _bounded_user_content(source_blocks, max_source_chars)
        input_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        client = self._new_client()
        try:
            response = client.responses.parse(
                model=self._model,
                input=input_messages,
                text_format=text_format,
                reasoning={"effort": self._reasoning_effort},
                # No tools, no web/file search, no function calling.
                tools=[],
                # Do not let the provider retain the (customer) request payload.
                store=False,
                timeout=self._timeout,
            )
        except ResponsesError:
            raise
        except Exception as exc:
            raise _classify_sdk_exception(exc) from None

        return self._interpret(response, text_format=text_format, schema_version=schema_version)

    def _interpret(
        self, response: Any, *, text_format: type, schema_version: str
    ) -> ParsedResult:
        returned_model = getattr(response, "model", None)
        response_id = getattr(response, "id", None)
        request_id = getattr(response, "_request_id", None) or getattr(
            response, "request_id", None
        )

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            if _find_refusal(response):
                raise ResponsesRefused()
            raise ResponsesEmptyOutput()

        if not isinstance(parsed, text_format):
            raise ResponsesSchemaInvalid()

        # Fail closed if the provider answered with a different/legacy model. Only
        # the exact ``gpt-5.6`` alias or a GPT-5.6 Sol snapshot is accepted; a
        # broad prefix match (which would admit ``gpt-5.60``/``gpt-5.6-terra``)
        # is deliberately NOT used.
        if not _is_accepted_returned_model(returned_model):
            raise ResponsesModelMismatch(
                "Provider returned a model outside the accepted gpt-5.6 (Sol) set"
            )

        metadata = ProviderCallMetadata(
            requested_model=self._model,
            returned_model=returned_model,
            reasoning_effort=self._reasoning_effort,
            schema_version=schema_version,
            response_id=str(response_id) if response_id is not None else None,
            request_id=str(request_id) if request_id is not None else None,
            parse_success=True,
            usage=_safe_usage(response),
        )
        return ParsedResult(parsed=parsed, metadata=metadata)


def build_gpt56_client(
    *,
    api_key: str | None,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    live_enabled: bool,
) -> GPT56ResponsesClient:
    return GPT56ResponsesClient(
        api_key=api_key,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        live_enabled=live_enabled,
    )
