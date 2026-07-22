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
    ResponsesProviderError,
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
    LiveScopeEvidence,
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

# The live output schemas expose NO model-authored descriptive prose field: the
# model returns only a category/relevance verdict and verbatim source quotes, and
# the SERVER derives every description/location/assumption/exclusion. The prompts
# make that contract explicit so the model does not waste effort authoring prose
# that is neither requested nor persisted.
_CLASSIFY_PROMPT = (
    "You classify blueprint sheets for a single trade using ONLY the supplied "
    "sheet text. For each sheet return only its page number and a relevance "
    "verdict (relevant / not_relevant / uncertain). Never invent sheet relevance "
    "without textual support; when unsupported, mark relevance 'uncertain'. Do "
    "NOT author any reason, explanation, description, or other prose — the server "
    "derives all descriptive text; only the page number and relevance verdict are "
    "requested. Return structured output only."
)
_SCOPE_PROMPT = (
    "You extract trade scope candidates using ONLY the supplied sheet text. For "
    "each candidate return only its category code and one or more evidence quotes. "
    "Each evidence quote MUST be copied VERBATIM from the supplied text of the "
    "SAME page you cite — exact characters, case, whitespace, and punctuation, "
    "with no edits, normalization, or paraphrase. Do NOT author any description, "
    "location, assumption, exclusion, quantity, measurement, dimension, unit, "
    "price, cost, total, approval, or workflow-status text: all descriptive and "
    "quantitative values are server-derived from your verbatim source quotes and "
    "are NOT requested from you. Return structured output only."
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
        # Map the SDK's error taxonomy onto the extraction ProviderError taxonomy
        # while faithfully preserving its retryability so the service retries only
        # what could plausibly succeed on a second attempt.
        if isinstance(exc, ResponsesUnavailable):
            # Disabled / keyless / auth-rejected — terminal, never retryable.
            return LiveExtractionUnavailable(exc.safe_message)
        if isinstance(exc, (ResponsesTimeout, ResponsesRateLimited)):
            # Transient by nature — surfaced as a retryable ProviderTimeout.
            return ProviderTimeout(exc.safe_message)
        if isinstance(exc, ResponsesProviderError):
            # Generic provider failure: the SDK classifier already decided whether
            # this was transient (connection / 5xx -> retryable) or terminal (4xx
            # -> non-retryable). Mirror that flag EXACTLY so a transient connection
            # error is never collapsed into a non-retryable response-invalid error.
            return ProviderResponseInvalid(exc.safe_message, retryable=exc.retryable)
        # Refusal / empty output / schema-invalid / model-mismatch / config /
        # grounding: all correctness failures — non-retryable.
        return ProviderResponseInvalid(exc.safe_message, retryable=False)

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
    # The live schemas are numeric-free, prose-free, and page-keyed. Here the
    # SERVER (never the model) reconstructs the legacy contract: it maps page →
    # verified sheet id, leaves every quantity null, derives descriptions from the
    # sourced quote, and assigns evidence type/confidence itself. The downstream
    # extraction service still re-validates everything and re-anchors evidence to
    # DB sheet records, so nothing here is trusted as final.

    # Fixed, server-authored classification rationale. The model no longer emits a
    # reason field, so any rationale is a constant server value (empty by default).
    _CLASSIFICATION_REASON = ""

    @classmethod
    def _adapt_classification(
        cls,
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
                    # Fixed server value — never model-authored prose.
                    reason=cls._CLASSIFICATION_REASON,
                )
            )
        return SheetClassificationResponse(classifications=classifications)

    @staticmethod
    def _adapt_scope(
        request: ScopeExtractionRequest,
        parsed: LiveScopeExtractionOutput,
    ) -> ScopeExtractionResponse:
        # Raw (unnormalized) embedded text per page. Evidence quotes must be a
        # LITERAL exact substring of this raw text — case, whitespace, and
        # punctuation exact — so nothing normalized or paraphrased is ever
        # persisted; a normalized-but-not-literal quote is dropped.
        raw_source_by_page = {
            s.pdf_page_number: (s.embedded_text or "") for s in request.sheets
        }
        candidates: list[ProviderScopeCandidate] = []
        for cand in parsed.candidates:
            # Collect only quotes proven to be a literal substring of the SAME
            # supplied page's raw text. A hallucinated quote, a normalized quote,
            # or a quote copied from another page never becomes persisted evidence.
            sourced: list[LiveScopeEvidence] = []
            for ev in cand.evidence:
                raw_source = raw_source_by_page.get(ev.pdf_page_number)
                if raw_source is None or ev.quote not in raw_source:
                    continue
                sourced.append(ev)
            if not sourced:
                # A candidate with no literally-sourced evidence is dropped; the
                # legacy contract requires at least one evidence entry.
                continue
            # The candidate description is SERVER-DERIVED from the FIRST exact source
            # quote (bounded as the contract requires), never from model-authored
            # prose.
            derived_description = sourced[0].quote[:1000]
            evidence = [
                ProviderEvidence(
                    pdf_page_number=ev.pdf_page_number,
                    # The model never authors the sheet number, evidence type,
                    # description, or any confidence — the server assigns them.
                    claimed_sheet_number=None,
                    evidence_type=EvidenceType.OTHER,
                    # Each evidence description derives from its OWN exact sourced
                    # quote (bounded), never the candidate's first quote — so a
                    # multi-evidence candidate carries one description per quote.
                    description=ev.quote[:1000],
                    # Persist the exact literal source substring, proven present.
                    extracted_text_quote=ev.quote,
                    confidence=None,
                )
                for ev in sourced
            ]
            candidates.append(
                ProviderScopeCandidate(
                    category_code=cand.category_code,
                    description=derived_description,
                    # Location/assumptions/exclusions are not model-authored; the
                    # server leaves them empty for downstream human review.
                    location=None,
                    # Quantity is left NULL: the live model never authors numbers.
                    quantity=ProviderQuantity(
                        basis=QuantityBasis.UNKNOWN, value=None, unit=None
                    ),
                    evidence=evidence,
                    confidence=None,
                    assumptions=[],
                    exclusions=[],
                )
            )
        return ScopeExtractionResponse(
            trade_code=request.trade_code, candidates=candidates
        )
