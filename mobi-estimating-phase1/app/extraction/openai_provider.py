"""OpenAI extraction provider (live path; disabled by default).

The intended first live provider. Live calls are OFF unless BOTH an API key is
configured AND ``MOBI_ENABLE_LIVE_EXTRACTION`` is true. Even then the call path is
guarded: the OpenAI SDK is imported lazily and any failure is converted into a safe
``ProviderError``.

NOTE: This environment cannot reach the OpenAI documentation or API, so the live
call below could not be executed/verified here. It uses the widely-stable
``chat.completions.create`` JSON-output contract; the exact request shape should be
re-verified against the current official SDK before enabling in production. No
unstable/guessed SDK methods are used, and nothing here runs in the test suite.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.extraction.base import (
    ExtractionProvider,
    LiveExtractionUnavailable,
    ProviderError,
)
from app.extraction.provider_schemas import (
    ScopeExtractionRequest,
    SheetClassificationRequest,
)

logger = logging.getLogger("mobi.extraction.openai")


class OpenAIExtractionProvider(ExtractionProvider):
    provider_name = "openai"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_model

    def _ensure_available(self) -> None:
        if not settings.enable_live_extraction:
            raise LiveExtractionUnavailable(
                "Live extraction is disabled (set MOBI_ENABLE_LIVE_EXTRACTION=true)"
            )
        if not self._api_key:
            raise LiveExtractionUnavailable("No OpenAI API key configured")

    def _call_model(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_available()
        try:
            from openai import OpenAI  # lazy import; optional dependency
        except Exception as exc:  # pragma: no cover - depends on env
            raise LiveExtractionUnavailable(
                "openai SDK is not installed in this environment"
            ) from exc
        try:  # pragma: no cover - never executed without network + key
            client = OpenAI(api_key=self._api_key)
            completion = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
                response_format={"type": "json_object"},
                timeout=settings.extraction_timeout_seconds,
            )
            content = completion.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as exc:
            # Never leak provider internals/plan text to clients.
            logger.warning("openai call failed: %s", type(exc).__name__)
            raise ProviderError("provider_error", "Live provider call failed") from exc

    def classify_sheets(self, request: SheetClassificationRequest) -> dict[str, Any]:
        return self._call_model(
            "Classify sheets. Return JSON only.", request.model_dump(mode="json")
        )

    def extract_scope(self, request: ScopeExtractionRequest) -> dict[str, Any]:
        return self._call_model(
            "Extract scope. Return JSON only.", request.model_dump(mode="json")
        )
