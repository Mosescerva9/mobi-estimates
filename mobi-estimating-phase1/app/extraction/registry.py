"""Provider registry / factory.

Resolves a provider name (plus a per-request live flag) to a concrete
``ExtractionProvider``. The shared core selects providers only through here, so the
database and service code never depend on a specific vendor SDK.
"""

from __future__ import annotations

from app.config import settings
from app.extraction.base import ExtractionProvider, LiveExtractionUnavailable
from app.extraction.mock_provider import MockExtractionProvider
from app.extraction.openai_provider import OpenAIExtractionProvider
from app.extraction.source_text_provider import SourceTextExtractionProvider


def get_provider(name: str | None = None, *, use_live: bool = False) -> ExtractionProvider:
    """Return a provider instance.

    The mock provider is always available and offline. An explicitly named
    ``openai`` run is the *live* GPT-5.6 path: it is resolved here at execution
    time (which, for a queued/background run, happens after the run row was
    claimed and possibly after a restart). If live enablement or key readiness has
    since gone away, this **fails closed** with ``LiveExtractionUnavailable`` — it
    must NEVER silently return the mock for an OpenAI-labeled run, because a mock
    payload would otherwise be persisted as if it were the requested live result.

    Default/offline routes claim provider ``mock`` (or ``source_text``), so they
    are unaffected and continue to return the offline provider.
    """
    provider_name = name or settings.extraction_provider

    if provider_name == "mock":
        return MockExtractionProvider()

    if provider_name == "source_text":
        return SourceTextExtractionProvider()

    if provider_name == "openai":
        # Re-check the full live-readiness contract at dispatch time and fail
        # closed on any gap (flag flipped off, key removed) between claim and
        # execution. Do not fall back to the mock for an OpenAI-labeled run.
        if not use_live or not settings.enable_live_extraction:
            raise LiveExtractionUnavailable("Live extraction is not enabled")
        if not settings.openai_api_key:
            raise LiveExtractionUnavailable("No OpenAI API key configured")
        return OpenAIExtractionProvider()

    raise LiveExtractionUnavailable(f"Unknown extraction provider '{provider_name}'")
