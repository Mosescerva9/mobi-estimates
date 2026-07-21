"""Orchestration for the GPT-5.6 structured project-analysis layer.

The service takes bounded, tenant-scoped source text that the system has *already*
extracted, sends it to the GPT-5.6 Responses API structured-output path, and
returns a Pydantic-validated :class:`ProjectAnalysis` plus provenance metadata.

It is fully offline/fail-closed by default: with no key and no explicit live
enablement it makes zero network calls and raises a safe, non-retryable error.
"""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.analysis.openai_client import (
    GPT56ResponsesClient,
    ResponsesError,
    ResponsesGroundingError,
    build_gpt56_client,
)
from app.analysis.schemas import (
    PROJECT_ANALYSIS_SCHEMA_VERSION,
    AnalysisSourceReference,
    ParsedResult,
    ProjectAnalysis,
)
from app.config import settings
from pydantic import BaseModel as _PydanticBaseModel

logger = logging.getLogger("mobi.analysis")


# --- Bounded, tenant-scoped input contract ---------------------------------
class _AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisSourceDocument(_AnalysisModel):
    """One already-extracted source document/page passed to the model.

    ``text`` is the only content the model sees. It is bounded, and the id/name/
    page/sheet locators let the model ground findings without ever being able to
    open the underlying file itself.
    """

    document_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    document_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
    page_number: Annotated[int, Field(ge=1, le=100_000)] | None = None
    sheet_number: Annotated[str, StringConstraints(max_length=64)] | None = None
    text: Annotated[str, StringConstraints(min_length=1)]


class ProjectAnalysisRequest(_AnalysisModel):
    """Tenant-scoped analysis request. Identity is required so a call can never be
    made without a tenant/company/project context."""

    tenant_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    company_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    project_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    documents: list[AnalysisSourceDocument] = Field(min_length=1)


# --- Prompt contract -------------------------------------------------------
SYSTEM_PROMPT = """\
You are a construction pre-bid document reviewer for Mobi Estimates. You produce a \
structured analysis of a project from the supplied source text only.

Hard rules:
- Use ONLY the supplied source text below. You have no access to files, URLs, \
tools, prior projects, customer records, or outside knowledge. Do not browse or \
call any tool.
- If information is not supported by the supplied text, return null or an empty \
list for that field and, where relevant, record the gap in `missing_documents` or \
`risk_flags`. Never guess to fill a field.
- NEVER infer, author, compute, or state any measurement, quantity, dimension, \
unit cost, price, arithmetic result, subtotal, or final total. This schema has no \
numeric measurement or price fields; keep any figure that appears in the source as \
verbatim text inside a description/quote, paired with a source reference.
- NEVER approve an estimate, price a scope, or state delivery/approval status.
- Item-level grounding: every factual item carries its OWN source-reference, not \
just the top-level list. This is required on each sheet-index entry, specification \
section, identified trade, relevant plan sheet, alternate, allowance, unit \
requirement, bid instruction, and exclusion, on the sourced `project_type`, and on \
BOTH sides (plan and spec) of every plan/spec conflict. Each reference must point \
at a supplied document and only use a page/sheet locator that document actually \
has — never invent a page or sheet. Include the document id/name plus page and/or \
sheet whenever the source provides them.
- Distinguish observed facts from assumptions and recommended RFIs. A directly \
stated scope item sets `observed_in_source` true and MUST include a source \
reference; anything uncertain or inferred sets `observed_in_source` false and \
belongs in `assumptions`, `recommended_rfis`, or `risk_flags`, never presented as \
an established fact. `assumptions` are your own unsourced reviewer notes; \
`exclusions` are factual bid-document claims and must be sourced.
- Prefer returning less with grounding over more without it. When unsure, lower \
`confidence_level` and add a risk flag or RFI rather than inventing detail.
"""


def _build_source_blocks(request: ProjectAnalysisRequest, per_doc_chars: int) -> list[str]:
    blocks: list[str] = []
    for doc in request.documents:
        header_bits = [f"document_id={doc.document_id}", f"name={doc.document_name}"]
        if doc.page_number is not None:
            header_bits.append(f"page={doc.page_number}")
        if doc.sheet_number:
            header_bits.append(f"sheet={doc.sheet_number}")
        body = doc.text[:per_doc_chars]
        blocks.append("### SOURCE (" + ", ".join(header_bits) + ")\n" + body)
    return blocks


# --- Post-parse source grounding -------------------------------------------
def _normalize_text(text: str) -> str:
    """Whitespace-collapsed, case-folded form for robust substring matching."""

    return " ".join(text.split()).casefold()


def _iter_source_references(obj: object):
    """Yield every :class:`AnalysisSourceReference` reachable in a parsed model.

    Walks nested models and lists so a reference anywhere in the analysis tree
    (top-level list, sourced identity facts, scope items, conflicts, RFIs, …) is
    validated — not just the top-level ``source_references`` list.
    """

    if isinstance(obj, AnalysisSourceReference):
        yield obj
        return
    if isinstance(obj, _PydanticBaseModel):
        for field_name in type(obj).model_fields:
            yield from _iter_source_references(getattr(obj, field_name))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _iter_source_references(item)


def _reference_is_grounded(
    ref: AnalysisSourceReference, request: ProjectAnalysisRequest
) -> bool:
    """True iff a single supplied document satisfies every locator + quote in ref.

    Every locator the model *supplies* (document id, document name, page, sheet)
    must EXACTLY equal the corresponding locator on the SAME request document, and
    any quote must be an exact normalized substring of that document's text. A
    locator the model omits (``None``) is simply not constrained. Critically, an
    omitted locator on the *source* document is NOT a wildcard: if the model
    supplies a page or sheet that the matched source document does not have (its
    locator is ``None``), the values differ and the reference fails closed. This
    prevents an invented page/sheet from passing against a source that has no such
    locator.
    """

    normalized_quote = _normalize_text(ref.quote) if ref.quote else None
    for doc in request.documents:
        if ref.document_id is not None and ref.document_id != doc.document_id:
            continue
        if ref.document_name is not None and ref.document_name != doc.document_name:
            continue
        if ref.page_number is not None and ref.page_number != doc.page_number:
            continue
        if ref.sheet_number is not None and ref.sheet_number != doc.sheet_number:
            continue
        if normalized_quote is not None and normalized_quote not in _normalize_text(
            doc.text
        ):
            continue
        return True
    return False


def _validate_grounding(
    analysis: ProjectAnalysis, request: ProjectAnalysisRequest
) -> None:
    """Reject the parse if any source reference is not grounded in the request.

    Raises a non-retryable :class:`ResponsesGroundingError` on the first
    ungrounded reference. This never leaks the offending quote/locator (which
    could contain plan text) into the client-facing message.
    """

    for ref in _iter_source_references(analysis):
        if not _reference_is_grounded(ref, request):
            raise ResponsesGroundingError()


def build_client_from_settings() -> GPT56ResponsesClient:
    """Construct the GPT-5.6 client from configuration.

    Live use still requires BOTH ``enable_live_project_analysis`` AND a key; the
    client itself enforces this at call time.
    """

    return build_gpt56_client(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
        timeout_seconds=settings.project_analysis_timeout_seconds,
        live_enabled=settings.enable_live_project_analysis,
    )


def readiness() -> dict[str, object]:
    """Safe readiness snapshot (no key material)."""

    return settings.project_analysis_readiness()


def analyze_project(
    request: ProjectAnalysisRequest,
    *,
    client: GPT56ResponsesClient | None = None,
) -> ParsedResult:
    """Run the GPT-5.6 structured analysis for a tenant-scoped request.

    Returns a :class:`ParsedResult` whose ``parsed`` is a validated
    :class:`ProjectAnalysis` and whose ``metadata`` proves the model alias,
    reasoning effort, and request/response ids. Raises a
    :class:`ResponsesError` subclass on any failure; ``.retryable`` says whether a
    retry could help.
    """

    # Enforce input bounds independently of the caller.
    max_docs = settings.project_analysis_max_source_documents
    if len(request.documents) > max_docs:
        raise ResponsesError(
            "analysis_input_too_large",
            "Too many source documents for a single analysis request",
            retryable=False,
        )

    client = client or build_client_from_settings()
    source_blocks = _build_source_blocks(
        request, settings.project_analysis_max_chars_per_document
    )

    attempts = settings.project_analysis_max_retries + 1
    last_error: ResponsesError | None = None
    for attempt in range(attempts):
        try:
            result = client.parse(
                system_prompt=SYSTEM_PROMPT,
                source_blocks=source_blocks,
                text_format=ProjectAnalysis,
                schema_version=PROJECT_ANALYSIS_SCHEMA_VERSION,
                max_source_chars=settings.project_analysis_max_source_chars,
            )
            # Grounding is enforced AFTER a successful schema parse and BEFORE the
            # result is returned: every source reference the model produced must
            # resolve to a supplied document (and any quote must be an exact
            # normalized substring). An ungrounded reference fails closed and is
            # non-retryable — we never silently downgrade it.
            _validate_grounding(result.parsed, request)
            return result
        except ResponsesError as exc:
            last_error = exc
            if not exc.retryable:
                logger.warning(
                    "project analysis failed (non-retryable) code=%s tenant=%s project=%s",
                    exc.code,
                    request.tenant_id,
                    request.project_id,
                )
                raise
            logger.info(
                "project analysis retryable failure code=%s attempt=%s/%s",
                exc.code,
                attempt + 1,
                attempts,
            )

    assert last_error is not None
    logger.warning(
        "project analysis exhausted retries code=%s tenant=%s project=%s",
        last_error.code,
        request.tenant_id,
        request.project_id,
    )
    raise last_error
