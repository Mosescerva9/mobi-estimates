"""Provider-neutral extraction interface and provider errors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.extraction.provider_schemas import (
    ScopeExtractionRequest,
    SheetClassificationRequest,
)


class ProviderError(Exception):
    """Base class for provider failures with a safe, client-facing code/message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class ProviderTimeout(ProviderError):
    def __init__(self, message: str = "Provider call timed out") -> None:
        super().__init__("provider_timeout", message)


class ProviderResponseInvalid(ProviderError):
    def __init__(self, message: str = "Provider returned an invalid response") -> None:
        super().__init__("provider_response_invalid", message)


class LiveExtractionUnavailable(ProviderError):
    def __init__(self, message: str = "Live extraction is disabled") -> None:
        super().__init__("live_extraction_unavailable", message)


class ExtractionProvider(ABC):
    """A pluggable extraction provider. Returns *raw* dicts for the service to
    validate — implementations must never be trusted directly."""

    provider_name: str

    @abstractmethod
    def classify_sheets(self, request: SheetClassificationRequest) -> dict[str, Any]:
        ...

    @abstractmethod
    def extract_scope(self, request: ScopeExtractionRequest) -> dict[str, Any]:
        ...
