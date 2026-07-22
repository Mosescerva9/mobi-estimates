"""OpenAI extraction provider (live path; disabled by default).

The first live provider. Live calls are OFF unless BOTH an API key is configured
AND ``MOBI_ENABLE_LIVE_EXTRACTION`` is true. This provider now uses the official
OpenAI Python SDK **Responses API + Structured Outputs** path (model alias
``gpt-5.6``, reasoning effort ``medium``) via the shared
:mod:`app.analysis.openai_client` wrapper — the legacy ``chat.completions`` JSON
mode / ``gpt-4o-mini`` path has been removed.

The provider returns *raw* dicts (from the parsed Pydantic model) which the
extraction service re-validates server-side; provider output is never trusted
directly. Any provider failure is converted into a safe extraction ``ProviderError``
so plan text, credentials, and raw payloads never reach a client. Nothing here runs
in the offline test suite unless a mocked SDK is injected.
"""

from __future__ import annotations

import logging
from typing import Any

from app.analysis.openai_client import (
    GPT56ResponsesClient,
    ResponsesError,
    ResponsesRateLimited,
    ResponsesTimeout,
    ResponsesUnavailable,
    build_gpt56_client,
)
from app.config import settings
from app.estimating.quantities import QuantityBasis
from app.extraction.base import (
    ExtractionProvider,
    LiveExtractionUnavailable,
    ProviderError,
    ProviderResponseInvalid,
    ProviderTimeout,
)
from app.extraction.live_schemas import (
    LiveScopeExtractionOutput,
    LiveSheetClassificationOutput,
)
from app.extraction.provider_schemas import (
    PROVIDER_SCHEMA_VERSION,
    ProviderEvidence,
    ProviderQuantity,
    ProviderScopeCandidate,
    ProviderSheetClassification,
    ScopeExtractionRequest,
    ScopeExtractionResponse,
    SheetClassificationRequest,
    SheetClassificationResponse,
)
from app.extraction.schemas import EvidenceType

logger = logging.getLogger("mobi.extraction.openai")

_CLASSIFY_PROMPT = (
    "You classify blueprint sheets for a single trade using ONLY the supplied "
    "sheet text. Never invent sheet relevance without textual support; when "
    "unsupported, mark relevance 'uncertain'. Return structured output only."
)
_SCOPE_PROMPT = (
    "You extract trade scope candidates using ONLY the supplied sheet text. Never "
    "invent measurements, quantities, dimensions, unit costs, prices, or totals. "
    "Every candidate must cite at least one evidence quote from the supplied text. "
    "Return structured output only."
)


def _sheet_blocks(sheets: list[Any]) -> list[str]:
    blocks: list[str] = []
    for sheet in sheets:
        header = (
            f"### SHEET (page={sheet.pdf_page_number}, "
            f"sheet_number={sheet.verified_sheet_number or 'unverified'})"
        )
        blocks.append(header + "\n" + (sheet.embedded_text or ""))
    return blocks


def _normalized_text(value: str) -> str:
    """Whitespace-collapsed, case-folded text for exact evidence anchoring."""

    return " ".join(value.split()).casefold()


class OpenAIExtractionProvider(ExtractionProvider):
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        client: GPT56ResponsesClient | None = None,
    ) -> None:
        self._client = client or build_gpt56_client(
            api_key=api_key or settings.openai_api_key,
            model=model or settings.openai_model,
            reasoning_effort=reasoning_effort or settings.openai_reasoning_effort,
            timeout_seconds=settings.extraction_timeout_seconds,
            live_enabled=settings.enable_live_extraction,
        )

    def _map_error(self, exc: ResponsesError) -> ProviderError:
        if isinstance(exc, ResponsesUnavailable):
            return LiveExtractionUnavailable(exc.safe_message)
        if isinstance(exc, (ResponsesTimeout, ResponsesRateLimited)):
            return ProviderTimeout(exc.safe_message)
        # Refusal / empty / schema / mismatch / generic provider error.
        return ProviderResponseInvalid(exc.safe_message)

    def classify_sheets(self, request: SheetClassificationRequest) -> dict[str, Any]:
        try:
            result = self._client.parse(
                system_prompt=_CLASSIFY_PROMPT,
                source_blocks=_sheet_blocks(request.sheets),
                # Strict, numeric-free live schema — NOT the legacy contract.
                text_format=LiveSheetClassificationOutput,
                schema_version=PROVIDER_SCHEMA_VERSION,
                max_source_chars=settings.extraction_max_text_chars_per_page
                * max(len(request.sheets), 1),
            )
        except ResponsesError as exc:
            logger.warning("openai classify failed: %s", exc.code)
            raise self._map_error(exc) from None
        return self._adapt_classification(request, result.parsed).model_dump(mode="json")

    def extract_scope(self, request: ScopeExtractionRequest) -> dict[str, Any]:
        try:
            result = self._client.parse(
                system_prompt=_SCOPE_PROMPT,
                source_blocks=_sheet_blocks(request.sheets),
                # Strict, numeric-free live schema — NOT the legacy contract.
                text_format=LiveScopeExtractionOutput,
                schema_version=PROVIDER_SCHEMA_VERSION,
                max_source_chars=settings.extraction_max_text_chars_per_page
                * max(len(request.sheets), 1),
            )
        except ResponsesError as exc:
            logger.warning("openai extract failed: %s", exc.code)
            raise self._map_error(exc) from None
        return self._adapt_scope(request, result.parsed).model_dump(mode="json")

    # --- Server-side adaptation into the existing caller contract ----------
    # The live schemas are numeric-free and page-keyed. Here the SERVER (never the
    # model) reconstructs the legacy contract: it maps page → verified sheet id,
    # leaves every quantity null, and assigns evidence type/confidence itself. The
    # downstream extraction service still re-validates everything and re-anchors
    # evidence to DB sheet records, so nothing here is trusted as final.
    @staticmethod
    def _adapt_classification(
        request: SheetClassificationRequest,
        parsed: LiveSheetClassificationOutput,
    ) -> SheetClassificationResponse:
        sheet_id_by_page = {s.pdf_page_number: s.sheet_id for s in request.sheets}
        classifications: list[ProviderSheetClassification] = []
        for item in parsed.classifications:
            sheet_id = sheet_id_by_page.get(item.pdf_page_number)
            if sheet_id is None:
                # Drop a page reference that is not one of the supplied sheets;
                # the model's page mapping is never trusted to invent sheets.
                continue
            classifications.append(
                ProviderSheetClassification(
                    sheet_id=sheet_id,
                    relevance=item.relevance,
                    reason=item.reason or "",
                )
            )
        return SheetClassificationResponse(classifications=classifications)

    @staticmethod
    def _adapt_scope(
        request: ScopeExtractionRequest,
        parsed: LiveScopeExtractionOutput,
    ) -> ScopeExtractionResponse:
        source_text_by_page = {
            s.pdf_page_number: _normalized_text(s.embedded_text or "")
            for s in request.sheets
        }
        candidates: list[ProviderScopeCandidate] = []
        for cand in parsed.candidates:
            evidence: list[ProviderEvidence] = []
            for ev in cand.evidence:
                source_text = source_text_by_page.get(ev.pdf_page_number)
                # Page existence alone is insufficient: a hallucinated quote or a
                # quote copied from another page must never become persisted
                # evidence. Require the quote to occur on the SAME supplied page.
                if source_text is None or _normalized_text(ev.quote) not in source_text:
                    continue
                evidence.append(
                    ProviderEvidence(
                        pdf_page_number=ev.pdf_page_number,
                        # The model never authors the sheet number, evidence type,
                        # or any confidence — the server assigns safe values.
                        claimed_sheet_number=None,
                        evidence_type=EvidenceType.OTHER,
                        description=cand.description[:1000],
                        extracted_text_quote=ev.quote,
                        confidence=None,
                    )
                )
            if not evidence:
                # A candidate with no evidence tied to a supplied sheet is dropped;
                # the legacy contract requires at least one evidence entry.
                continue
            candidates.append(
                ProviderScopeCandidate(
                    category_code=cand.category_code,
                    description=cand.description,
                    location=cand.location,
                    # Quantity is left NULL: the live model never authors numbers.
                    quantity=ProviderQuantity(
                        basis=QuantityBasis.UNKNOWN, value=None, unit=None
                    ),
                    evidence=evidence,
                    confidence=None,
                    assumptions=list(cand.assumptions),
                    exclusions=list(cand.exclusions),
                )
            )
        return ScopeExtractionResponse(
            trade_code=request.trade_code, candidates=candidates
        )
