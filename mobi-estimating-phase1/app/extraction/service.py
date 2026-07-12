"""Trade-agnostic extraction orchestrator.

Loads behavior from the trade registry (never hardcodes a trade), calls a provider
for untrusted candidates, then validates everything server-side: schema → trade
module → shared rules. Evidence is rebuilt from verified database sheet records, and
derived quantities are recomputed in Python. Decoupled from FastAPI.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.config import settings
from app.database import get_project, list_sheets
from app.estimating.quantities import (
    DERIVED_BASES,
    TRANSCRIBED_BASES,
    FormulaError,
    QuantityBasis,
    QuantityInputError,
    formula_registry,
)
from app.extraction import cache as cache_mod
from app.extraction.base import ProviderError
from app.extraction.cache import ExtractionCacheKey, tenant_cache_identity
from app.extraction.provider_schemas import (
    PROVIDER_SCHEMA_VERSION,
    ProviderScopeCandidate,
    ScopeExtractionRequest,
    ScopeExtractionResponse,
)
from app.extraction.registry import get_provider
from app.extraction.schemas import (
    ConflictSeverity,
    EvidenceReference,
    ExtractionStatus,
    ReviewStatus,
    RoutingStatus,
    SharedConflictCode,
)
from app.extraction_db import (
    insert_conflict,
    insert_evidence,
    insert_quantity_derivation,
    insert_scope_item,
    list_routing,
    update_run,
    upsert_routing_decision,
)
from app.services import storage
from app.trades.base import CandidateContext, SheetContext, SheetRoutingResult
from app.trades.registry import trade_registry
from pydantic import ValidationError

logger = logging.getLogger("mobi.extraction")


class ExtractionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


def _read_sheet_text(sheet: dict) -> str:
    rel = sheet.get("text_path")
    if not rel:
        return ""
    try:
        return storage.resolve_within_data_root(rel).read_text(encoding="utf-8")
    except (ValueError, OSError):
        return ""


def _sheet_context(sheet: dict, text: str) -> SheetContext:
    text_char_count = sheet.get("text_char_count")
    if not isinstance(text_char_count, int):
        text_char_count = len((text or "").strip())
    return SheetContext(
        sheet_id=sheet["id"],
        project_id=sheet["project_id"],
        pdf_page_number=sheet["pdf_page_number"],
        verified_sheet_number=sheet.get("verified_sheet_number"),
        verified_sheet_title=sheet.get("verified_sheet_title"),
        detected_sheet_number=sheet.get("detected_sheet_number"),
        detected_sheet_title=sheet.get("detected_sheet_title"),
        embedded_text=text,
        requires_ocr=bool(sheet.get("requires_ocr")),
        requires_review=bool(sheet.get("requires_review")),
        text_char_count=text_char_count,
        text_layer_quality=_text_layer_quality(sheet, text),
    )


def _text_layer_quality(sheet: dict, text: str = "") -> str:
    """Classify whether embedded text is usable enough for trusted extraction."""
    if bool(sheet.get("requires_ocr")):
        return "ocr_required"
    text_char_count = sheet.get("text_char_count")
    if not isinstance(text_char_count, int):
        text_char_count = len((text or "").strip())
    if text_char_count < settings.very_low_information_text_chars:
        return "very_low_information_text_layer"
    if text_char_count < settings.low_information_text_chars:
        return "low_information_text_layer"
    return "usable_text_layer"


def _route_sheet_with_text_quality_gate(module: Any, sheet: dict, text: str) -> SheetRoutingResult:
    """Apply cross-trade low-information text routing before module-specific rules.

    This keeps sparse embedded-text pages from flowing into provider extraction as
    if they had trustworthy text evidence. The page remains processed and
    reviewable, but is routed toward OCR/vision/table follow-up first.
    """
    context = _sheet_context(sheet, text)
    module_result = module.route_sheet(context)
    if module_result.eligibility in {
        RoutingStatus.BLOCKED_UNVERIFIED,
        RoutingStatus.BLOCKED_OCR,
        RoutingStatus.EXCLUDED,
    }:
        return module_result
    if context.text_layer_quality in {
        "very_low_information_text_layer",
        "low_information_text_layer",
    }:
        return SheetRoutingResult(
            RoutingStatus.BLOCKED_OCR,
            (
                f"{context.text_layer_quality.replace('_', ' ')} "
                f"({context.text_char_count} chars); route to OCR/vision/table extraction before trusted scope extraction."
            ),
        )
    return module_result


def route_sheets(
    project_id: UUID, trade_code: str, *, run_id: UUID | None,
    selected_sheet_ids: set[str] | None, persist: bool,
) -> list[dict[str, Any]]:
    """Route every project sheet for a trade. Returns decision dicts (page-ordered).

    Honors any existing manual overrides stored for the sheet/trade.
    """
    module = trade_registry.get(trade_code, require_enabled=True)
    sheets, _ = list_sheets(project_id, limit=10_000, offset=0)
    existing = {d["sheet_id"]: d for d in list_routing(project_id, trade_code)}
    decisions: list[dict[str, Any]] = []
    for sheet in sheets:
        if selected_sheet_ids is not None and sheet["id"] not in selected_sheet_ids:
            continue
        text = _read_sheet_text(sheet)
        result = _route_sheet_with_text_quality_gate(module, sheet, text)
        prior = existing.get(sheet["id"])
        manual = prior.get("manual_override") if prior else None
        if persist:
            decision = upsert_routing_decision(
                project_id=project_id, sheet_id=UUID(sheet["id"]),
                trade_code=trade_code, extraction_run_id=run_id,
                eligibility=result.eligibility.value, reason=result.reason,
                automatic=True,
            )
        else:
            decision = {
                "sheet_id": sheet["id"], "pdf_page_number": sheet["pdf_page_number"],
                "trade_code": trade_code, "eligibility": result.eligibility.value,
                "reason": result.reason, "automatic": True,
                "manual_override": manual,
            }
        decision["effective_status"] = manual or decision["eligibility"]
        decisions.append(decision)
    decisions.sort(key=lambda d: d.get("pdf_page_number", 0))
    return decisions


def _eligible_sheet_ids(decisions: list[dict[str, Any]]) -> list[str]:
    return [
        d["sheet_id"] for d in decisions
        if d.get("effective_status") == RoutingStatus.ELIGIBLE.value
    ]


def _resolve_quantity(
    trade_code: str, candidate: ProviderScopeCandidate
) -> tuple[Decimal | None, str | None, dict | None, list[tuple[str, str]]]:
    """Return (value, unit, derivation, issues). Derived bases are computed in
    Python; transcribed bases use the provider's number; otherwise null."""
    basis = QuantityBasis(candidate.quantity.basis)
    issues: list[tuple[str, str]] = []

    if basis in DERIVED_BASES:
        formula_id = candidate.quantity.formula_id
        if not formula_id:
            issues.append((SharedConflictCode.UNSUPPORTED_FORMULA.value,
                           "Derived quantity requires a registered formula id"))
            return None, candidate.quantity.unit, None, issues
        try:
            formula = formula_registry.get_for_trade(formula_id, trade_code)
            result = formula.calculate(candidate.quantity.raw_inputs)
        except FormulaError:
            issues.append((SharedConflictCode.UNSUPPORTED_FORMULA.value,
                           f"Formula '{formula_id}' is not available for this trade"))
            return None, candidate.quantity.unit, None, issues
        except QuantityInputError:
            issues.append((SharedConflictCode.QUANTITY_NOT_REPRODUCIBLE.value,
                           "Quantity could not be deterministically reproduced"))
            return None, candidate.quantity.unit, None, issues
        derivation = {
            "formula_id": result.formula_id, "formula_version": result.formula_version,
            "inputs": result.inputs, "output_value": result.value,
            "output_unit": result.unit.value,
        }
        return result.value, result.unit.value, derivation, issues

    if basis in TRANSCRIBED_BASES:
        value = candidate.quantity.value
        if value is None:
            issues.append((SharedConflictCode.MISSING_QUANTITY.value,
                           "Transcribed quantity basis but no value supplied"))
        return value, candidate.quantity.unit, None, issues

    # manual_reviewer_entry / unknown → leave null at extraction time.
    return None, candidate.quantity.unit, None, issues


def _build_trusted_evidence(
    project_id: UUID, item_id: UUID, candidate: ProviderScopeCandidate,
    sheets_by_page: dict[int, dict],
) -> tuple[list[dict], bool]:
    """Build evidence from verified DB sheet records. Returns (evidence, had_valid)."""
    evidence: list[dict] = []
    for ev in candidate.evidence:
        sheet = sheets_by_page.get(ev.pdf_page_number)
        # Reject evidence that cannot be tied to a verified project sheet.
        if sheet is None or not sheet.get("verified_sheet_number"):
            continue
        model = EvidenceReference(
            project_id=project_id,
            sheet_id=UUID(sheet["id"]),
            pdf_page_number=ev.pdf_page_number,
            verified_sheet_number=sheet["verified_sheet_number"],  # from DB, not provider
            evidence_type=ev.evidence_type,
            description=ev.description,
            extracted_text_quote=ev.extracted_text_quote,
            # Logical reference only — never a raw filesystem path.
            source_artifact_ref=f"sheet:{sheet['id']}",
            provider_confidence=ev.confidence,
            requires_human_verification=True,
        )
        record = model.model_dump(mode="json")
        record["scope_item_id"] = str(item_id)
        evidence.append(record)
    return evidence, bool(evidence)


def run_extraction(project_id: UUID, trade_code: str, run_id: UUID) -> dict[str, Any]:
    """Execute an extraction run end-to-end. Idempotent w.r.t. approved items
    (it never modifies prior items; it only adds candidates for this run)."""
    started = time.perf_counter()
    module = trade_registry.get(trade_code, require_enabled=True)
    run = _get_run_or_raise(project_id, run_id)
    is_dry = bool(run["dry_run"])

    update_run(run_id, status=ExtractionStatus.RUNNING.value, started_at=_now())

    try:
        project = get_project(project_id)
        if project is None:
            raise ExtractionError("project_not_found", "Project not found")

        decisions = route_sheets(
            project_id, trade_code, run_id=run_id,
            selected_sheet_ids=None, persist=True,
        )
        eligible_ids = _eligible_sheet_ids(decisions)

        # Cost-control caps (per run + per trade).
        cap = min(settings.extraction_max_pages, settings.extraction_max_pages_per_trade)
        eligible_ids = eligible_ids[:cap]

        sheets, _ = list_sheets(project_id, limit=10_000, offset=0)
        sheets_by_id = {s["id"]: s for s in sheets}
        sheets_by_page = {s["pdf_page_number"]: s for s in sheets}
        blocked = sum(
            1 for d in decisions
            if d.get("effective_status") != RoutingStatus.ELIGIBLE.value
        )

        if is_dry:
            # Dry run: routing preview + caps only, no provider call, no candidates.
            update_run(
                run_id, status=ExtractionStatus.COMPLETED.value, completed_at=_now(),
                input_sheet_count=len(decisions),
                processed_sheet_count=len(eligible_ids), blocked_sheet_count=blocked,
                candidate_count=0,
            )
            return {"status": "completed", "dry_run": True,
                    "eligible_sheets": len(eligible_ids), "candidate_count": 0}

        # Build provider request from eligible, verified sheets only.
        provider_sheets = []
        for sid in eligible_ids:
            sheet = sheets_by_id[sid]
            text = _read_sheet_text(sheet)[: settings.extraction_max_text_chars_per_page]
            provider_sheets.append({
                "sheet_id": sheet["id"], "pdf_page_number": sheet["pdf_page_number"],
                "verified_sheet_number": sheet.get("verified_sheet_number"),
                "verified_sheet_title": sheet.get("verified_sheet_title"),
                "embedded_text": text,
            })

        prompt_version = module.get_prompt_version("scope_extractor")
        request = ScopeExtractionRequest(
            trade_code=trade_code, prompt_version=prompt_version,
            allowed_categories=module.get_scope_categories(),
            allowed_units=[u.value for u in module.get_allowed_units()],
            sheets=provider_sheets,
        )

        raw = _call_provider_with_cache(
            project, project_id, trade_code, module, run, request, eligible_ids, sheets_by_id
        )

        try:
            response = ScopeExtractionResponse.model_validate(raw)
        except ValidationError as exc:
            raise ExtractionError(
                "provider_response_invalid",
                "Provider returned a response that failed schema validation",
            ) from exc

        candidate_count = 0
        for candidate in response.candidates:
            self_persist_candidate(
                project_id, trade_code, run_id, module, candidate, sheets_by_page
            )
            candidate_count += 1

        usage = response.usage or {}
        duration_ms = int((time.perf_counter() - started) * 1000)
        status = (
            ExtractionStatus.NEEDS_REVIEW.value if candidate_count
            else ExtractionStatus.COMPLETED.value
        )
        update_run(
            run_id, status=status, completed_at=_now(),
            input_sheet_count=len(decisions), processed_sheet_count=len(eligible_ids),
            blocked_sheet_count=blocked, candidate_count=candidate_count,
            usage={**usage, "duration_ms": duration_ms}, estimated_cost=None,
        )
        logger.info(
            "extraction complete project_id=%s trade=%s run_id=%s candidates=%s "
            "eligible=%s duration_ms=%s", project_id, trade_code, run_id,
            candidate_count, len(eligible_ids), duration_ms,
        )
        return {"status": status, "candidate_count": candidate_count,
                "eligible_sheets": len(eligible_ids)}

    except ExtractionError as exc:
        _fail_run(run_id, exc.code, exc.safe_message)
        return {"status": "failed", "error_code": exc.code}
    except ProviderError as exc:
        _fail_run(run_id, exc.code, exc.safe_message)
        return {"status": "failed", "error_code": exc.code}
    except Exception:
        logger.exception("extraction crashed project_id=%s run_id=%s", project_id, run_id)
        _fail_run(run_id, "internal_error", "Extraction failed")
        return {"status": "failed", "error_code": "internal_error"}


def _call_provider_with_cache(
    project, project_id, trade_code, module, run, request, eligible_ids, sheets_by_id
) -> dict[str, Any]:
    provider = get_provider(run["provider"], use_live=settings.enable_live_extraction)
    checksums = tuple(
        sheets_by_id[sid].get("page_sha256") or "" for sid in eligible_ids
    )
    cache_identity = tenant_cache_identity(project)
    key = None
    if cache_identity is not None:
        tenant_id, company_id = cache_identity
        key = ExtractionCacheKey(
            tenant_id=tenant_id,
            company_id=company_id,
            project_id=str(project_id), trade_code=trade_code,
            provider=provider.provider_name, model=run.get("model_identifier") or "",
            prompt_version=request.prompt_version,
            trade_schema_version=module.schema_version,
            provider_schema_version=PROVIDER_SCHEMA_VERSION,
            page_checksums=checksums,
        )
    if settings.extraction_cache_enabled and key is not None:
        cached = cache_mod.extraction_cache.get(key)
        if cached is not None:
            return cached

    raw = _call_with_retries(provider, request)

    if settings.extraction_cache_enabled and key is not None:
        cache_mod.extraction_cache.set(key, raw)
    return raw


def _call_with_retries(provider, request) -> dict[str, Any]:
    attempts = settings.extraction_max_retries + 1
    last_exc: Exception | None = None
    for _ in range(attempts):
        try:
            return provider.extract_scope(request)
        except ProviderError as exc:
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def self_persist_candidate(
    project_id, trade_code, run_id, module, candidate: ProviderScopeCandidate,
    sheets_by_page,
) -> dict[str, Any]:
    item_id = uuid4()
    value, unit, derivation, quantity_issues = _resolve_quantity(trade_code, candidate)

    candidate_ctx = CandidateContext(
        category_code=candidate.category_code,
        description=candidate.description,
        location=candidate.location,
        quantity_basis=QuantityBasis(candidate.quantity.basis),
        quantity_value=value,
        unit=unit,
        raw_quantity_inputs=candidate.quantity.raw_inputs,
        trade_data=candidate.trade_data,
        evidence_count=len(candidate.evidence),
        confidence=float(candidate.confidence) if candidate.confidence is not None else None,
    )
    validation = module.validate_candidate(candidate_ctx)

    evidence, had_evidence = _build_trusted_evidence(
        project_id, item_id, candidate, sheets_by_page
    )

    blocking_issues = [bi.model_dump() for bi in validation.blocking_issues]
    if not had_evidence:
        blocking_issues.append({
            "code": SharedConflictCode.MISSING_VERIFIED_SHEET.value,
            "message": "No evidence could be tied to a verified project sheet",
        })

    # Conflicts: trade-specific + quantity issues.
    conflicts = module.detect_conflicts(candidate_ctx, [])
    conflict_rows = []
    for conflict in conflicts:
        row = conflict.model_dump(mode="json")
        row["scope_item_id"] = str(item_id)
        conflict_rows.append(row)
    for code, message in quantity_issues:
        conflict_rows.append({
            "id": str(uuid4()), "scope_item_id": str(item_id), "code": code,
            "severity": ConflictSeverity.BLOCKING.value, "description": message,
        })

    has_blocking = bool(blocking_issues) or any(
        c["severity"] == ConflictSeverity.BLOCKING.value for c in conflict_rows
    )
    review_status = ReviewStatus.BLOCKED.value if has_blocking else ReviewStatus.PENDING.value
    conflict_status = "blocking" if has_blocking else (
        "warning" if conflict_rows else "none"
    )

    item = {
        "id": str(item_id), "project_id": str(project_id),
        "extraction_run_id": str(run_id), "trade_code": trade_code,
        "trade_module_version": module.module_version,
        "trade_schema_version": module.schema_version,
        "category_code": candidate.category_code,
        "description": candidate.description, "location": candidate.location,
        "material_or_substrate": candidate.trade_data.get("substrate"),
        "quantity": value, "unit": unit,
        "quantity_basis": QuantityBasis(candidate.quantity.basis).value,
        "raw_quantity_inputs": candidate.quantity.raw_inputs,
        "extraction_confidence": (
            float(candidate.confidence) if candidate.confidence is not None else None
        ),
        "conflict_status": conflict_status, "review_status": review_status,
        "blocking_issues": blocking_issues,
        "assumptions": [{"text": a} for a in candidate.assumptions],
        "exclusions": [{"text": e} for e in candidate.exclusions],
        "trade_data": validation.normalized_trade_data or candidate.trade_data,
        "original_provider_candidate": candidate.model_dump(mode="json"),
        "calculation_id": derivation["formula_id"] if derivation else None,
        "calculation_version": derivation["formula_version"] if derivation else None,
    }
    insert_scope_item(item)
    for record in evidence:
        insert_evidence(record)
    if derivation is not None:
        insert_quantity_derivation({
            "id": str(uuid4()), "project_id": str(project_id), "scope_item_id": str(item_id),
            "trade_code": trade_code, **derivation,
        })
    for row in conflict_rows:
        row.setdefault("id", str(uuid4()))
        row["project_id"] = str(project_id)
        insert_conflict(row)
    return item


# ---------------------------------------------------------------------------
def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _get_run_or_raise(project_id: UUID, run_id: UUID) -> dict[str, Any]:
    from app.extraction_db import get_run
    run = get_run(project_id, run_id)
    if run is None:
        raise ExtractionError("run_not_found", "Extraction run not found")
    return run


def _fail_run(run_id: UUID, code: str, message: str) -> None:
    update_run(
        run_id, status=ExtractionStatus.FAILED.value, completed_at=_now(),
        error_code=code, error_message=message,
    )
