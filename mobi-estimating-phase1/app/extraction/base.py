"""Provider-neutral extraction interface and provider errors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.extraction.provider_schemas import (
    ScopeExtractionRequest,
    SheetClassificationRequest,
)


class ProviderError(Exception):
    """Base class for provider failures with a safe, client-facing code/message.

    Every instance carries a ``retryable`` flag so the extraction service can
    decide whether a retry could plausibly help. It defaults to ``False`` (fail
    closed): an unclassified failure is never silently retried, and a subclass
    must opt in explicitly.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


class ProviderTimeout(ProviderError):
    # Timeouts are transient by nature — a retry could plausibly succeed.
    def __init__(self, message: str = "Provider call timed out") -> None:
        super().__init__("provider_timeout", message, retryable=True)


class ProviderResponseInvalid(ProviderError):
    # An invalid response is non-retryable by default (a malformed/refused/
    # off-schema response will not fix itself). Callers that know the underlying
    # failure was transient (e.g. a connection error surfaced as a generic
    # provider error) may pass ``retryable=True`` explicitly.
    def __init__(
        self,
        message: str = "Provider returned an invalid response",
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__("provider_response_invalid", message, retryable=retryable)


class LiveExtractionUnavailable(ProviderError):
    # Live extraction being disabled/keyless is a terminal config state, not a
    # transient one — never retryable.
    def __init__(self, message: str = "Live extraction is disabled") -> None:
        super().__init__("live_extraction_unavailable", message, retryable=False)


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
