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


def get_provider(name: str | None = None, *, use_live: bool = False) -> ExtractionProvider:
    """Return a provider instance.

    The mock provider is always available and offline. The OpenAI provider is only
    returned when live extraction is explicitly requested *and* enabled in config.
    """
    provider_name = name or settings.extraction_provider

    if provider_name == "mock":
        return MockExtractionProvider()

    if provider_name == "openai":
        if not (use_live and settings.enable_live_extraction):
            # Default/safe path: never make live calls implicitly.
            return MockExtractionProvider()
        if not settings.openai_api_key:
            raise LiveExtractionUnavailable("No OpenAI API key configured")
        return OpenAIExtractionProvider()

    raise LiveExtractionUnavailable(f"Unknown extraction provider '{provider_name}'")
