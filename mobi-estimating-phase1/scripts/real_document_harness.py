#!/usr/bin/env python3
"""Run a real construction PDF through the Mobi estimating engine smoke pipeline.

This is a local/test harness for bid-board document shakeouts. It uses FastAPI's
TestClient against the engine app, writes to an isolated temp database/upload dir
by default, and produces a JSON report with stage responses and blockers.

It does not send messages, create customer deliverables, process payments, or
approve/finalize construction estimates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))


def _configure_env(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MOBI_DB_PATH", str(workdir / "mobi.db"))
    os.environ.setdefault("MOBI_UPLOAD_DIR", str(workdir / "uploads"))
    # The real-document harness is an internal, local-only safety exercise. Make
    # that startup choice explicit so the P0 engine startup lock can continue to
    # fail closed for unlabeled containers/previews/releases.
    os.environ.setdefault("MOBI_DEPLOYMENT_ENVIRONMENT", "local")
    os.environ.setdefault("MOBI_ENGINE_AUTH_MODE", "local_dev_open")
    os.environ.setdefault("MOBI_ENABLED_TRADES", "painting,demo_concrete,general_trade")


def _json_response(response: Any, *, duration_ms: int | None = None) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception:
        data = {"raw_text": response.text[:4000]}
    result = {
        "status_code": response.status_code,
        "ok": 200 <= response.status_code < 300,
        "body": data,
    }
    if duration_ms is not None:
        result["duration_ms"] = duration_ms
    return result


def _post(client: Any, path: str, *, json_body: Any | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        if json_body is None:
            response = client.post(path, headers=HARNESS_TENANT_HEADERS)
        else:
            response = client.post(path, json=json_body, headers=HARNESS_TENANT_HEADERS)
    except TypeError:
        # Lightweight unit-test doubles may not implement FastAPI's headers kwarg.
        if json_body is None:
            response = client.post(path)
        else:
            response = client.post(path, json=json_body)
    return _json_response(response, duration_ms=int((time.perf_counter() - start) * 1000))


def _get(client: Any, path: str) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        response = client.get(path, headers=HARNESS_TENANT_HEADERS)
    except TypeError:
        # Lightweight unit-test doubles may not implement FastAPI's headers kwarg.
        response = client.get(path)
    return _json_response(response, duration_ms=int((time.perf_counter() - start) * 1000))


# The scope-items list endpoint caps ``limit`` at 200, so real packages with more
# than 200 scope items must be paged or the tail (including any trade/keyword/quantity
# that only appears there) is silently dropped from the harness report.
_SCOPE_ITEM_PAGE_LIMIT = 200
_SHEET_PAGE_LIMIT = 200
_LOW_INFORMATION_TEXT_CHAR_THRESHOLD = 300
_VERY_LOW_INFORMATION_TEXT_CHAR_THRESHOLD = 60
HARNESS_TENANT_HEADERS = {
    "X-Mobi-Tenant-Id": "harness_tenant",
    "X-Mobi-Company-Id": "harness_company",
}
_QUANTITY_CANDIDATE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ea|each|lf|ln\.?\s*ft|linear\s+feet|sf|sq\.?\s*ft|square\s+feet|sy|cy|cf|yds?|tons?|sheets?|fixtures?|doors?|windows?|panels?|outlets?|devices?)\b",
    re.IGNORECASE,
)


def _get_all_sheets_with_details(client: Any, base: str) -> dict[str, Any]:
    """Fetch sheet summaries and hydrate details needed for real-test quality metrics.

    The sheet-list API intentionally omits text length and artifact metadata for
    normal clients. Real-test reporting needs ``text_char_count`` so sparse or
    repeated PDF text layers do not look healthier than they are. Detail-fetch
    failures are recorded on the sheet row but do not fail the harness.
    """
    first = _get(client, f"{base}/sheets?limit={_SHEET_PAGE_LIMIT}&offset=0")
    body = first.get("body")
    if not first.get("ok") or not isinstance(body, dict):
        return first
    items = [item for item in (body.get("items") or []) if isinstance(item, dict)]
    total = body.get("total")
    offset = _SHEET_PAGE_LIMIT
    while isinstance(total, int) and len(items) < total:
        page = _get(client, f"{base}/sheets?limit={_SHEET_PAGE_LIMIT}&offset={offset}")
        page_body = page.get("body")
        if not page.get("ok") or not isinstance(page_body, dict):
            break
        page_items = [item for item in (page_body.get("items") or []) if isinstance(item, dict)]
        if not page_items:
            break
        items.extend(page_items)
        offset += _SHEET_PAGE_LIMIT

    detailed_items = []
    detail_failure_count = 0
    for item in items:
        sheet_id = item.get("sheet_id") or item.get("id")
        if not sheet_id:
            detailed_items.append(item)
            continue
        detail = _get(client, f"{base}/sheets/{sheet_id}")
        detail_body = detail.get("body")
        if detail.get("ok") and isinstance(detail_body, dict):
            merged = dict(item)
            merged.update(detail_body)
            detailed_items.append(merged)
        else:
            failed = dict(item)
            failed["detail_fetch_failed"] = True
            detail_failure_count += 1
            detailed_items.append(failed)
    merged_body = dict(body)
    merged_body["items"] = detailed_items
    merged_body["total"] = total if isinstance(total, int) else len(detailed_items)
    merged_body["detail_failure_count"] = detail_failure_count
    merged = dict(first)
    merged["body"] = merged_body
    return merged


def _get_all_scope_items(client: Any, base: str) -> dict[str, Any]:
    """Fetch every scope item for a project, paging past the API's per-request limit.

    Returns a stage dict shaped like a normal ``_get`` response whose ``body.items``
    holds all scope items across pages, so downstream scoring never truncates at 200.
    """
    first = _get(client, f"{base}/scope-items?limit={_SCOPE_ITEM_PAGE_LIMIT}&offset=0")
    body = first.get("body")
    if not first.get("ok") or not isinstance(body, dict):
        return first
    items = [item for item in (body.get("items") or []) if isinstance(item, dict)]
    total = body.get("total")
    offset = _SCOPE_ITEM_PAGE_LIMIT
    while isinstance(total, int) and len(items) < total:
        page = _get(client, f"{base}/scope-items?limit={_SCOPE_ITEM_PAGE_LIMIT}&offset={offset}")
        page_body = page.get("body")
        if not page.get("ok") or not isinstance(page_body, dict):
            break
        page_items = [item for item in (page_body.get("items") or []) if isinstance(item, dict)]
        if not page_items:
            break
        items.extend(page_items)
        offset += _SCOPE_ITEM_PAGE_LIMIT
    merged = dict(first)
    merged_body = dict(body)
    merged_body["items"] = items
    merged_body["fetched_item_count"] = len(items)
    merged["body"] = merged_body
    return merged


def _get_all_scope_items_with_details(
    client: Any,
    base: str,
    *,
    quantity_inputs_by_scope: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch all scope items and hydrate each item with read-only detail evidence.

    The list endpoint intentionally returns compact summaries. Real-test reports need
    the evidence quotes from the detail endpoint so reviewers can see why a draft
    scope item exists without opening raw engine artifacts. Detail failures are
    recorded on the item but do not fail the whole harness stage.
    """
    stage = _get_all_scope_items(client, base)
    body = stage.get("body")
    if not stage.get("ok") or not isinstance(body, dict):
        return stage
    detailed_items = []
    detail_failure_count = 0
    for item in body.get("items") or []:
        if not isinstance(item, dict) or not item.get("id"):
            detailed_items.append(item)
            continue
        detail = _get(client, f"{base}/scope-items/{item['id']}")
        detail_body = detail.get("body")
        if detail.get("ok") and isinstance(detail_body, dict):
            scope_item = detail_body.get("scope_item")
            if isinstance(scope_item, dict):
                merged_item = dict(scope_item)
                merged_item["trade_data"] = detail_body.get("trade_data") if isinstance(detail_body.get("trade_data"), dict) else {}
                raw_quantity_inputs = detail_body.get("raw_quantity_inputs") or merged_item.get("raw_quantity_inputs")
                if not isinstance(raw_quantity_inputs, dict):
                    raw_quantity_inputs = (quantity_inputs_by_scope or {}).get(str(merged_item.get("id")))
                if isinstance(raw_quantity_inputs, dict):
                    merged_item["raw_quantity_inputs"] = raw_quantity_inputs
                merged_item["evidence"] = detail_body.get("evidence") if isinstance(detail_body.get("evidence"), list) else []
                detailed_items.append(merged_item)
            else:
                detailed_items.append(detail_body)
        else:
            fallback = dict(item)
            fallback["detail_fetch_ok"] = False
            detailed_items.append(fallback)
            detail_failure_count += 1
    merged = dict(stage)
    merged_body = dict(body)
    merged_body["items"] = detailed_items
    merged_body["detail_fetched_item_count"] = len(detailed_items) - detail_failure_count
    merged_body["detail_fetch_failure_count"] = detail_failure_count
    merged["body"] = merged_body
    return merged


def _item_count(stage: dict[str, Any]) -> int | None:
    body = stage.get("body") if isinstance(stage, dict) else None
    if not isinstance(body, dict):
        return None
    items = body.get("items")
    if isinstance(items, list):
        return len(items)
    total = body.get("total")
    if isinstance(total, int):
        return total
    return None


def _error_summary(stage: dict[str, Any]) -> dict[str, Any] | None:
    if stage.get("ok"):
        return None
    body = stage.get("body") if isinstance(stage, dict) else None
    if not isinstance(body, dict):
        return {"message": "Stage failed without a JSON body."}
    detail = body.get("detail")
    if isinstance(detail, dict):
        return {
            "code": detail.get("code") or detail.get("error_code"),
            "message": detail.get("message") or detail.get("detail"),
        }
    if isinstance(detail, str):
        return {"message": detail}
    if isinstance(body.get("raw_text"), str):
        return {"message": body["raw_text"][:500]}
    return {"message": body.get("message") or body.get("error") or "Stage failed."}


def _scope_items(stage: dict[str, Any]) -> list[dict[str, Any]]:
    body = stage.get("body") if isinstance(stage, dict) else None
    if not isinstance(body, dict):
        return []
    items = body.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key) or "unknown"
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _scope_evidence_quote_summary(scope_stage: dict[str, Any]) -> dict[str, Any]:
    items = _scope_items(scope_stage)
    by_trade: dict[str, dict[str, Any]] = {}
    gap_candidates: list[dict[str, Any]] = []
    totals: dict[str, Any] = {
        "scope_items_with_evidence_quote_count": 0,
        "scope_items_missing_evidence_quote_count": 0,
        "evidence_quote_count": 0,
        "evidence_human_verification_required_count": 0,
    }
    for item in items:
        trade = str(item.get("trade_code") or "unknown")
        row = by_trade.setdefault(trade, {
            "trade_code": trade,
            "scope_item_count": 0,
            "items_with_evidence_quote_count": 0,
            "items_missing_evidence_quote_count": 0,
            "evidence_quote_count": 0,
            "human_verification_required_count": 0,
        })
        row["scope_item_count"] += 1
        evidence_refs = item.get("evidence") or []
        if not isinstance(evidence_refs, list):
            evidence_refs = []
        quote_count = 0
        verify_count = 0
        for evidence in evidence_refs:
            if not isinstance(evidence, dict):
                continue
            quote = evidence.get("extracted_text_quote")
            if isinstance(quote, str) and quote.strip():
                quote_count += 1
            if evidence.get("requires_human_verification"):
                verify_count += 1
        if quote_count:
            totals["scope_items_with_evidence_quote_count"] += 1
            row["items_with_evidence_quote_count"] += 1
        else:
            totals["scope_items_missing_evidence_quote_count"] += 1
            row["items_missing_evidence_quote_count"] += 1
            gap_candidates.append(_evidence_quote_gap_candidate(item, evidence_refs))
        totals["evidence_quote_count"] += quote_count
        totals["evidence_human_verification_required_count"] += verify_count
        row["evidence_quote_count"] += quote_count
        row["human_verification_required_count"] += verify_count

    totals["evidence_quote_coverage_rate"] = round(
        totals["scope_items_with_evidence_quote_count"] / len(items), 4
    ) if items else 0
    rows = sorted(by_trade.values(), key=lambda row: (-row["items_missing_evidence_quote_count"], row["trade_code"]))
    gap_candidates.sort(key=lambda candidate: (str(candidate.get("trade_code") or ""), str(candidate.get("scope_item_id") or "")))
    return {**totals, "evidence_quote_by_trade": rows[:10], "evidence_quote_gap_candidates": gap_candidates[:20]}


def _evidence_quote_gap_candidate(item: dict[str, Any], evidence_refs: list[Any]) -> dict[str, Any]:
    """Return a staff-review pointer for a scope item whose evidence lacks a quote.

    This is report-only triage. It exposes source page/sheet hints so staff can
    find the likely missing quote faster, but it does not approve scope,
    quantities, pricing, customer delivery, or final estimates.
    """
    evidence = next((ref for ref in evidence_refs if isinstance(ref, dict)), None)
    candidate: dict[str, Any] = {
        "scope_item_id": item.get("id"),
        "trade_code": item.get("trade_code") or "unknown",
        "description": item.get("description"),
        "location": item.get("location"),
        "evidence_ref_count": sum(1 for ref in evidence_refs if isinstance(ref, dict)),
        "requires_staff_review": True,
        "final_estimate_ready": False,
    }
    if evidence is None:
        candidate["gap_reason"] = "no_evidence_reference_with_quote"
        return candidate
    candidate.update({
        "gap_reason": "evidence_reference_missing_extracted_text_quote",
        "pdf_page_number": evidence.get("pdf_page_number"),
        "sheet_id": evidence.get("sheet_id"),
        "sheet_number": evidence.get("verified_sheet_number"),
        "evidence_type": evidence.get("evidence_type"),
        "evidence_description": evidence.get("description"),
        "source_artifact_ref": evidence.get("source_artifact_ref"),
        "requires_human_verification": bool(evidence.get("requires_human_verification", True)),
    })
    return candidate


def _source_type_for_sheet(sheet: dict[str, Any]) -> str:
    text = " ".join(
        str(sheet.get(key) or "")
        for key in ("verified_sheet_number", "detected_sheet_number", "verified_sheet_title", "detected_sheet_title")
    ).lower()
    if any(token in text for token in ("spec", "specification", "schedule", "submittal", "manual")):
        return "spec_or_schedule"
    if any(token in text for token in ("plan", "elevation", "section", "detail", "drawing")):
        return "drawing"
    if any(str(sheet.get(key) or "").upper().startswith(("A", "S", "C", "M", "P", "E", "FP", "T")) for key in ("verified_sheet_number", "detected_sheet_number")):
        return "drawing"
    return "unknown"


def _low_information_signature(
    *,
    quality: str,
    text_char_count: int | None,
    sheet_number: Any,
    sheet_title: str | None,
    route_keys: list[str],
) -> str | None:
    """Return a stable grouping key for repeated sparse table/OCR candidates.

    Low-information PDFs often expose the same jurisdiction stamp or metadata on
    every page while the real drawing content remains image-only. Grouping these
    candidates helps staff see whether a candidate is one isolated schedule page
    or part of a repeated text-layer failure pattern. This is review-only routing
    metadata; it is not extraction, pricing, or final estimate evidence.
    """
    if quality not in {"low_information_text_layer", "very_low_information_text_layer", "ocr_required"}:
        return None
    parts = [
        quality,
        str(text_char_count) if text_char_count is not None else "unknown_chars",
        str(sheet_number or "unknown_sheet_number").strip().lower(),
        str(sheet_title or "unknown_sheet_title").strip().lower(),
        ",".join(sorted(route_keys)),
    ]
    return "|".join(parts)


def _table_schedule_candidate_for_sheet(sheet: dict[str, Any]) -> dict[str, Any] | None:
    """Return a review-safe table/schedule extraction candidate for one sheet.

    This only reports candidate pages and why they need follow-up. It does not
    extract, price, approve, or deliver construction quantities.
    """
    routes = sheet.get("recommended_extraction_routes")
    route_keys = [str(route) for route in routes] if isinstance(routes, list) else []
    title = " ".join(
        str(sheet.get(key) or "")
        for key in ("verified_sheet_title", "detected_sheet_title")
    ).strip()
    title_lower = title.lower()
    reasons: list[str] = []
    if "table_schedule_extraction" in route_keys:
        reasons.append("recommended_route")
    if "schedule" in title_lower:
        reasons.append("title_contains_schedule")
    if "table" in title_lower:
        reasons.append("title_contains_table")
    if not reasons:
        return None
    sheet_number = sheet.get("verified_sheet_number") or sheet.get("detected_sheet_number")
    quality = str(sheet.get("text_layer_quality") or "unknown")
    text_char_count = sheet.get("text_char_count") if isinstance(sheet.get("text_char_count"), int) else None
    return {
        "pdf_page_number": sheet.get("pdf_page_number"),
        "sheet_id": sheet.get("sheet_id") or sheet.get("id"),
        "sheet_number": sheet_number,
        "sheet_title": title or None,
        "text_layer_quality": quality,
        "text_char_count": text_char_count,
        "recommended_extraction_routes": route_keys,
        "candidate_reasons": sorted(set(reasons)),
        "low_information_signature": _low_information_signature(
            quality=quality,
            text_char_count=text_char_count,
            sheet_number=sheet_number,
            sheet_title=title or None,
            route_keys=route_keys,
        ),
        "requires_human_review": True,
        "final_quantity_extraction": False,
    }


def _sheet_source_summary(stage: dict[str, Any]) -> dict[str, Any]:
    sheets = _scope_items(stage)
    confidence_scores = [score for sheet in sheets if (score := _safe_float(sheet.get("detection_confidence"))) is not None]
    source_type_counts: dict[str, int] = {}
    ocr_required_count = 0
    requires_review_count = 0
    processing_status_counts: dict[str, int] = {}
    text_char_counts: list[int] = []
    low_information_text_layer_count = 0
    very_low_information_text_layer_count = 0
    text_detail_missing_count = 0
    text_layer_quality_counts: dict[str, int] = {}
    recommended_extraction_route_counts: dict[str, int] = {}
    table_schedule_candidates: list[dict[str, Any]] = []
    table_schedule_candidate_quality_counts: dict[str, int] = {}
    for sheet in sheets:
        source_type = _source_type_for_sheet(sheet)
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        if sheet.get("requires_ocr"):
            ocr_required_count += 1
        if sheet.get("requires_review"):
            requires_review_count += 1
        text_char_count = sheet.get("text_char_count")
        if isinstance(text_char_count, int):
            text_char_counts.append(text_char_count)
            if not sheet.get("requires_ocr") and text_char_count < _LOW_INFORMATION_TEXT_CHAR_THRESHOLD:
                low_information_text_layer_count += 1
            if not sheet.get("requires_ocr") and text_char_count < _VERY_LOW_INFORMATION_TEXT_CHAR_THRESHOLD:
                very_low_information_text_layer_count += 1
        else:
            text_detail_missing_count += 1
        quality = str(sheet.get("text_layer_quality") or "unknown")
        text_layer_quality_counts[quality] = text_layer_quality_counts.get(quality, 0) + 1
        routes = sheet.get("recommended_extraction_routes")
        if isinstance(routes, list):
            for route in routes:
                route_key = str(route)
                recommended_extraction_route_counts[route_key] = recommended_extraction_route_counts.get(route_key, 0) + 1
        candidate = _table_schedule_candidate_for_sheet(sheet)
        if candidate is not None:
            table_schedule_candidates.append(candidate)
            candidate_quality = str(candidate.get("text_layer_quality") or "unknown")
            table_schedule_candidate_quality_counts[candidate_quality] = table_schedule_candidate_quality_counts.get(candidate_quality, 0) + 1
        status = str(sheet.get("processing_status") or "unknown")
        processing_status_counts[status] = processing_status_counts.get(status, 0) + 1
    table_schedule_candidates.sort(
        key=lambda candidate: (
            candidate.get("pdf_page_number") if isinstance(candidate.get("pdf_page_number"), int) else 10**9,
            str(candidate.get("sheet_number") or ""),
        )
    )
    signature_counts: dict[str, int] = {}
    for candidate in table_schedule_candidates:
        signature = candidate.get("low_information_signature")
        if isinstance(signature, str) and signature:
            signature_counts[signature] = signature_counts.get(signature, 0) + 1
    repeated_low_information_table_candidate_count = 0
    for candidate in table_schedule_candidates:
        signature = candidate.get("low_information_signature")
        count = signature_counts.get(signature, 0) if isinstance(signature, str) else 0
        if count > 1:
            candidate["same_low_information_signature_candidate_count"] = count
            candidate["repeated_low_information_signature"] = True
            repeated_low_information_table_candidate_count += 1
        else:
            candidate["same_low_information_signature_candidate_count"] = count if count else None
            candidate["repeated_low_information_signature"] = False
    return {
        "document_source_type_counts": source_type_counts,
        "sheet_processing_status_counts": processing_status_counts,
        "sheet_requires_ocr_count": ocr_required_count,
        "sheet_requires_review_count": requires_review_count,
        "sheet_low_information_text_layer_count": low_information_text_layer_count,
        "sheet_very_low_information_text_layer_count": very_low_information_text_layer_count,
        "sheet_text_detail_missing_count": text_detail_missing_count,
        "sheet_text_layer_quality_counts": dict(sorted(text_layer_quality_counts.items())),
        "sheet_recommended_extraction_route_counts": dict(sorted(recommended_extraction_route_counts.items())),
        "table_schedule_extraction_candidate_count": len(table_schedule_candidates),
        "table_schedule_extraction_candidate_quality_counts": dict(sorted(table_schedule_candidate_quality_counts.items())),
        "repeated_low_information_table_schedule_candidate_count": repeated_low_information_table_candidate_count,
        "table_schedule_extraction_candidates": table_schedule_candidates[:20],
        "sheet_text_char_count_min": min(text_char_counts) if text_char_counts else None,
        "sheet_text_char_count_avg": round(sum(text_char_counts) / len(text_char_counts), 2) if text_char_counts else None,
        "sheet_text_char_count_max": max(text_char_counts) if text_char_counts else None,
        "sheet_detection_confidence_min": round(min(confidence_scores), 4) if confidence_scores else None,
        "sheet_detection_confidence_avg": round(sum(confidence_scores) / len(confidence_scores), 4) if confidence_scores else None,
        "sheet_detection_confidence_max": round(max(confidence_scores), 4) if confidence_scores else None,
    }


def _quantity_input_source(item: dict[str, Any]) -> str:
    raw_inputs = item.get("raw_quantity_inputs") or {}
    if not isinstance(raw_inputs, dict):
        return "unknown"
    verified = raw_inputs.get("verified_quantity_input_v1")
    if isinstance(verified, dict):
        return str(verified.get("source") or "verified_quantity_input_v1")
    if raw_inputs:
        return "raw_quantity_inputs"
    return "none"


def _quantity_candidate_quote(quote: str) -> str | None:
    """Return the first quantity-like text span from an evidence quote.

    This is report-only candidate detection for staff review. A regex match is
    not a takeoff, approved quantity, priced quantity, or deliverable estimate.
    """
    match = _QUANTITY_CANDIDATE_RE.search(quote)
    return match.group(0) if match else None


def _quantity_extraction_candidate_summary(scope_stage: dict[str, Any]) -> dict[str, Any]:
    """Surface review-only quantity-bearing evidence separate from manual/test inputs."""
    candidates: list[dict[str, Any]] = []
    by_trade: dict[str, dict[str, Any]] = {}
    manual_input_count = 0
    test_input_count = 0
    for item in _scope_items(scope_stage):
        trade = str(item.get("trade_code") or "unknown")
        row = by_trade.setdefault(trade, {
            "trade_code": trade,
            "candidate_count": 0,
            "manual_quantity_input_count": 0,
            "test_quantity_input_count": 0,
        })
        source = _quantity_input_source(item)
        if source.startswith("harness_test_only"):
            test_input_count += 1
            row["test_quantity_input_count"] += 1
            continue
        if source not in ("none", "unknown"):
            manual_input_count += 1
            row["manual_quantity_input_count"] += 1

        for evidence in item.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            quote = str(evidence.get("extracted_text_quote") or "").strip()
            quantity_text = _quantity_candidate_quote(quote)
            if not quantity_text:
                continue
            candidates.append({
                "scope_item_id": item.get("id"),
                "trade_code": trade,
                "quantity_candidate_text": quantity_text,
                "evidence_quote": quote[:240],
                "requires_human_review": True,
                "final_quantity_extraction": False,
                "estimate_ready": False,
                "candidate_reasons": ["quantity_like_evidence_text"],
            })
            row["candidate_count"] += 1
            break

    candidates.sort(key=lambda candidate: (str(candidate.get("trade_code") or ""), str(candidate.get("scope_item_id") or "")))
    rows = sorted(by_trade.values(), key=lambda row: (-row["candidate_count"], row["trade_code"]))
    return {
        "quantity_extraction_candidate_count": len(candidates),
        "quantity_extraction_candidates": candidates[:20],
        "quantity_extraction_candidate_by_trade": rows[:10],
        "manual_quantity_input_count": manual_input_count,
        "test_quantity_input_count": test_input_count,
    }


def _quantity_confidence_summary(scope_stage: dict[str, Any], requirements_stage: dict[str, Any]) -> dict[str, Any]:
    items = _scope_items(scope_stage)
    requirements = _scope_items(requirements_stage)
    by_trade: dict[str, dict[str, Any]] = {}
    totals: dict[str, Any] = {
        "quantity_scope_item_count": len(items),
        "quantity_present_count": 0,
        "quantity_missing_count": 0,
        "quantity_traceable_count": 0,
        "quantity_unclear_basis_count": 0,
        "quantity_test_input_count": 0,
        "open_quantity_requirement_count": 0,
        "resolved_quantity_requirement_count": 0,
    }

    for req in requirements:
        status = req.get("status")
        if status == "open":
            totals["open_quantity_requirement_count"] += 1
        elif status == "resolved":
            totals["resolved_quantity_requirement_count"] += 1

    for item in items:
        trade = str(item.get("trade_code") or "unknown")
        row = by_trade.setdefault(trade, {
            "trade_code": trade,
            "scope_item_count": 0,
            "quantity_present_count": 0,
            "quantity_missing_count": 0,
            "quantity_traceable_count": 0,
            "quantity_unclear_basis_count": 0,
            "quantity_test_input_count": 0,
            "quantity_gap_count": 0,
        })
        row["scope_item_count"] += 1
        quantity = item.get("quantity")
        basis = item.get("quantity_basis")
        source = _quantity_input_source(item)
        has_quantity = quantity not in (None, "")
        unclear_basis = basis in (None, "", "unknown", "customer_revision_pending_rescope")
        is_test_input = source.startswith("harness_test_only")
        if has_quantity:
            totals["quantity_present_count"] += 1
            row["quantity_present_count"] += 1
        else:
            totals["quantity_missing_count"] += 1
            row["quantity_missing_count"] += 1
        if has_quantity and not unclear_basis and not is_test_input:
            totals["quantity_traceable_count"] += 1
            row["quantity_traceable_count"] += 1
        if has_quantity and unclear_basis:
            totals["quantity_unclear_basis_count"] += 1
            row["quantity_unclear_basis_count"] += 1
        if is_test_input:
            totals["quantity_test_input_count"] += 1
            row["quantity_test_input_count"] += 1
        row["quantity_gap_count"] = row["quantity_missing_count"] + row["quantity_unclear_basis_count"] + row["quantity_test_input_count"]

    trade_rows = sorted(by_trade.values(), key=lambda row: (-row["quantity_gap_count"], row["trade_code"]))
    totals["quantity_traceable_rate"] = round(totals["quantity_traceable_count"] / len(items), 4) if items else 0
    return {**totals, "quantity_confidence_by_trade": trade_rows[:10]}


def _generic_formula_check_for_item(item: dict[str, Any]) -> dict[str, Any]:
    trade_data = item.get("trade_data") or {}
    pricing_method = trade_data.get("pricing_method") or "unassigned"
    quantity = item.get("quantity")
    basis = item.get("quantity_basis")
    source = _quantity_input_source(item)
    has_quantity = quantity not in (None, "")
    unclear_basis = basis in (None, "", "unknown", "customer_revision_pending_rescope")
    is_test_input = source.startswith("harness_test_only")
    blockers: list[str] = []
    if not has_quantity:
        blockers.append("missing_quantity")
    if has_quantity and unclear_basis:
        blockers.append("unclear_quantity_basis")
    if is_test_input:
        blockers.append("test_quantity_only")
    supported_methods = {
        "unit_rate_needed": "quantity_times_unit_rate_check",
        "quote_based": "lump_sum_or_scope_quantity_check",
        "allowance": "allowance_basis_check",
    }
    formula_check = supported_methods.get(str(pricing_method))
    if formula_check is None:
        blockers.append("unsupported_pricing_method")
    ready = not blockers
    return {
        "scope_item_id": item.get("id"),
        "trade_code": item.get("trade_code") or "unknown",
        "pricing_method": pricing_method,
        "formula_check": formula_check or "unsupported",
        "ready": ready,
        "blockers": blockers,
        "quantity_basis": basis,
    }


def _generic_formula_check_summary(scope_stage: dict[str, Any]) -> dict[str, Any]:
    items = [
        item for item in _scope_items(scope_stage)
        if item.get("category_code") == "generic_scope" or (item.get("trade_data") or {}).get("pricing_method")
    ]
    checks = [_generic_formula_check_for_item(item) for item in items]
    by_trade: dict[str, dict[str, Any]] = {}
    method_counts: dict[str, int] = {}
    blocker_counts: dict[str, int] = {}
    for check in checks:
        trade = str(check["trade_code"])
        method = str(check["pricing_method"])
        method_counts[method] = method_counts.get(method, 0) + 1
        row = by_trade.setdefault(trade, {
            "trade_code": trade,
            "formula_check_scope_item_count": 0,
            "formula_check_ready_count": 0,
            "formula_check_blocked_count": 0,
            "formula_check_test_input_count": 0,
        })
        row["formula_check_scope_item_count"] += 1
        if check["ready"]:
            row["formula_check_ready_count"] += 1
        else:
            row["formula_check_blocked_count"] += 1
        for blocker in check["blockers"]:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
            if blocker == "test_quantity_only":
                row["formula_check_test_input_count"] += 1
    ready_count = sum(1 for check in checks if check["ready"])
    blocked_count = len(checks) - ready_count
    trade_rows = sorted(by_trade.values(), key=lambda row: (-row["formula_check_blocked_count"], row["trade_code"]))
    return {
        "formula_check_scope_item_count": len(checks),
        "formula_check_ready_count": ready_count,
        "formula_check_blocked_count": blocked_count,
        "formula_check_ready_rate": round(ready_count / len(checks), 4) if checks else 0,
        "formula_check_method_counts": dict(sorted(method_counts.items())),
        "formula_check_blocker_counts": dict(sorted(blocker_counts.items())),
        "formula_check_by_trade": trade_rows[:10],
    }


def _trade_quality_summary(scope_stage: dict[str, Any], provenance: dict[str, Any]) -> list[dict[str, Any]]:
    by_trade: dict[str, dict[str, Any]] = {}
    for item in _scope_items(scope_stage):
        trade = str(item.get("trade_code") or "unknown")
        row = by_trade.setdefault(trade, {
            "trade_code": trade,
            "scope_item_count": 0,
            "trusted_evidence_count": 0,
            "missing_trusted_evidence_count": 0,
            "low_confidence_item_count": 0,
            "quantity_basis_unclear_count": 0,
            "blocking_issue_count": 0,
            "avg_extraction_confidence": None,
            "_confidence_scores": [],
        })
        row["scope_item_count"] += 1
        score = _safe_float(item.get("extraction_confidence"))
        if score is not None:
            row["_confidence_scores"].append(score)
        row["blocking_issue_count"] += len(item.get("blocking_issues") or [])
    for field, target in (
        ("items_with_trusted_evidence", "trusted_evidence_count"),
        ("missing_extraction_provenance", "missing_trusted_evidence_count"),
        ("low_extraction_confidence", "low_confidence_item_count"),
        ("quantity_basis_unclear", "quantity_basis_unclear_count"),
    ):
        for item in provenance.get(field) or []:
            if not isinstance(item, dict):
                continue
            trade = str(item.get("trade_code") or "unknown")
            row = by_trade.setdefault(trade, {
                "trade_code": trade,
                "scope_item_count": 0,
                "trusted_evidence_count": 0,
                "missing_trusted_evidence_count": 0,
                "low_confidence_item_count": 0,
                "quantity_basis_unclear_count": 0,
                "blocking_issue_count": 0,
                "avg_extraction_confidence": None,
                "_confidence_scores": [],
            })
            row[target] += 1
    results = []
    for row in by_trade.values():
        scores = row.pop("_confidence_scores", [])
        if scores:
            row["avg_extraction_confidence"] = round(sum(scores) / len(scores), 4)
        row["quality_blocker_count"] = (
            row["missing_trusted_evidence_count"]
            + row["low_confidence_item_count"]
            + row["quantity_basis_unclear_count"]
            + row["blocking_issue_count"]
        )
        results.append(row)
    return sorted(results, key=lambda row: (-row["quality_blocker_count"], row["trade_code"]))


def _pricing_readiness_summary(stage: dict[str, Any]) -> dict[str, Any]:
    items = _scope_items(stage)
    method_counts: dict[str, int] = {}
    missing_blocker_counts = {
        "missing_quantity": 0,
        "missing_unit_rate": 0,
        "missing_subcontract_quote": 0,
        "missing_allowance_basis": 0,
    }
    generic_count = 0
    priced_count = 0
    pricing_ready_count = 0
    pricing_not_ready_count = 0
    unassigned_count = 0
    for item in items:
        trade_data = item.get("trade_data") or {}
        method = trade_data.get("pricing_method")
        is_generic = item.get("category_code") == "generic_scope" or bool(method)
        if not is_generic:
            continue
        generic_count += 1
        if method:
            method_counts[str(method)] = method_counts.get(str(method), 0) + 1
        else:
            unassigned_count += 1
        if trade_data.get("pricing_ready") is True:
            pricing_ready_count += 1
        else:
            pricing_not_ready_count += 1
        if isinstance(trade_data.get("pricing_basis"), dict):
            priced_count += 1
        for blocker in item.get("blocking_issues") or []:
            if not isinstance(blocker, dict):
                continue
            code = blocker.get("code")
            if code in missing_blocker_counts:
                missing_blocker_counts[code] += 1
    return {
        "generic_pricing_scope_item_count": generic_count,
        "pricing_method_assigned_count": sum(method_counts.values()),
        "pricing_method_unassigned_count": unassigned_count,
        "pricing_ready_scope_item_count": pricing_ready_count,
        "pricing_not_ready_scope_item_count": pricing_not_ready_count,
        "priced_scope_item_count": priced_count,
        "unpriced_scope_item_count": max(generic_count - priced_count, 0),
        "pricing_method_counts": method_counts,
        **missing_blocker_counts,
    }


def _automation_review_package_from_outputs(outputs: dict[str, Any], *, failed_stage_count: int) -> dict[str, Any]:
    """Consolidate automation signals into a staff review/readiness package.

    This package is review-assistive only. It does not mark customer delivery,
    final estimate approval, external messaging, or payments as ready.
    """
    readiness_blockers = outputs.get("readiness_blockers") or []
    readiness_blocker_count = len(readiness_blockers) if isinstance(readiness_blockers, list) else 0
    human_review_count = sum(
        count for count in (
            outputs.get("sheet_requires_ocr_count", 0),
            outputs.get("sheet_requires_review_count", 0),
            outputs.get("table_schedule_extraction_candidate_count", 0),
            outputs.get("quantity_extraction_candidate_count", 0),
            outputs.get("evidence_human_verification_required_count", 0),
            outputs.get("clarification_candidate_count", 0),
        )
        if isinstance(count, int)
    )
    blocked_count = sum(
        count for count in (
            failed_stage_count,
            readiness_blocker_count,
            outputs.get("pricing_not_ready_scope_item_count", 0),
            outputs.get("formula_check_blocked_count", 0),
            outputs.get("quantity_missing_count", 0),
            outputs.get("quantity_unclear_basis_count", 0),
            outputs.get("open_quantity_requirement_count", 0),
            outputs.get("generic_estimate_draft_blocked_scope_item_count", 0),
            outputs.get("register_blocking_entry_count", 0),
        )
        if isinstance(count, int)
    )
    if failed_stage_count:
        status = "system_failure_blocked"
    elif blocked_count or outputs.get("readiness_status") == "blocked":
        status = "blocked_before_customer_delivery"
    elif human_review_count:
        status = "staff_review_required"
    else:
        status = "ready_for_staff_review"
    return {
        "status": status,
        "customer_delivery_ready": False,
        "final_estimate_approved": False,
        "external_messages": False,
        "payments": False,
        "ready": {
            "sheet_count": outputs.get("sheet_count", 0),
            "scope_item_count": outputs.get("scope_item_count", 0),
            "evidence_quote_count": outputs.get("evidence_quote_count", 0),
            "generic_estimate_draft_line_item_count": outputs.get("generic_estimate_draft_line_item_count", 0),
            "generic_proposal_preview_scope_line_count": outputs.get("generic_proposal_preview_scope_line_count", 0),
        },
        "human_review_needed": {
            "sheet_requires_ocr_count": outputs.get("sheet_requires_ocr_count", 0),
            "sheet_requires_review_count": outputs.get("sheet_requires_review_count", 0),
            "table_schedule_extraction_candidate_count": outputs.get("table_schedule_extraction_candidate_count", 0),
            "quantity_extraction_candidate_count": outputs.get("quantity_extraction_candidate_count", 0),
            "evidence_human_verification_required_count": outputs.get("evidence_human_verification_required_count", 0),
            "clarification_candidate_count": outputs.get("clarification_candidate_count", 0),
        },
        "blocked": {
            "failed_stage_count": failed_stage_count,
            "readiness_blocker_count": readiness_blocker_count,
            "pricing_not_ready_scope_item_count": outputs.get("pricing_not_ready_scope_item_count", 0),
            "formula_check_blocked_count": outputs.get("formula_check_blocked_count", 0),
            "quantity_missing_count": outputs.get("quantity_missing_count", 0),
            "quantity_unclear_basis_count": outputs.get("quantity_unclear_basis_count", 0),
            "open_quantity_requirement_count": outputs.get("open_quantity_requirement_count", 0),
            "generic_estimate_draft_blocked_scope_item_count": outputs.get("generic_estimate_draft_blocked_scope_item_count", 0),
            "register_blocking_entry_count": outputs.get("register_blocking_entry_count", 0),
        },
        "top_followups": {
            "table_schedule_candidates": outputs.get("table_schedule_extraction_candidates", []),
            "quantity_extraction_candidates": outputs.get("quantity_extraction_candidates", []),
            "quantity_gaps_by_trade": outputs.get("quantity_confidence_by_trade", []),
            "pricing_formula_blockers_by_trade": outputs.get("formula_check_by_trade", []),
            "evidence_quote_gaps_by_trade": outputs.get("evidence_quote_by_trade", []),
            "trade_quality_blockers": outputs.get("trade_quality_summary", []),
            "clarification_candidate_ids": outputs.get("top_clarification_candidate_ids", []),
        },
    }


def _beta_flow_dry_run_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Summarize upload -> process -> review package -> safe draft readiness.

    This is a local/staff-only beta flow signal. It records whether the harness
    exercised the end-to-end automation path and whether the generated draft and
    preview stayed behind safety gates. It must not be interpreted as customer
    delivery or final-estimate approval.
    """
    per_stage = summary.get("per_stage", {}) if isinstance(summary.get("per_stage"), dict) else {}
    outputs = summary.get("outputs", {}) if isinstance(summary.get("outputs"), dict) else {}
    review_package = outputs.get("automation_review_package", {}) if isinstance(outputs.get("automation_review_package"), dict) else {}

    stage_names = {
        "upload": "upload",
        "process": "process",
        "automation_review_package": "owner_review_after_test_inputs",
        "safe_draft_output": "generic_estimate_draft_after_test_inputs",
        "safe_proposal_preview": "generic_proposal_preview_after_test_inputs",
    }
    stages = {
        key: bool((per_stage.get(stage_name) or {}).get("ok"))
        for key, stage_name in stage_names.items()
    }
    draft_safety_flags_clear = all(
        outputs.get(key) is False
        for key in (
            "generic_estimate_draft_customer_delivery_ready",
            "generic_estimate_draft_final_estimate_approved",
            "generic_estimate_draft_external_messages",
            "generic_estimate_draft_payments",
        )
    )
    preview_safety_flags_clear = all(
        outputs.get(key) is False
        for key in (
            "generic_proposal_preview_customer_delivery_ready",
            "generic_proposal_preview_final_estimate_approved",
            "generic_proposal_preview_external_messages",
            "generic_proposal_preview_payments",
            "generic_proposal_preview_proposal_created",
            "generic_proposal_preview_proposal_issued",
        )
    )
    review_safety_flags_clear = all(
        review_package.get(key) is False
        for key in ("customer_delivery_ready", "final_estimate_approved", "external_messages", "payments")
    )
    raw_readiness_blockers = outputs.get("readiness_blockers")
    readiness_blockers = raw_readiness_blockers if isinstance(raw_readiness_blockers, list) else []
    blocked_count = sum(
        count for count in (
            len(readiness_blockers),
            outputs.get("pricing_not_ready_scope_item_count", 0),
            outputs.get("quantity_missing_count", 0),
            outputs.get("quantity_unclear_basis_count", 0),
            outputs.get("generic_estimate_draft_blocked_scope_item_count", 0),
            outputs.get("generic_proposal_preview_blocked_scope_item_count", 0),
        )
        if isinstance(count, int)
    )
    human_review_count = sum(
        count for count in (
            outputs.get("sheet_requires_ocr_count", 0),
            outputs.get("sheet_requires_review_count", 0),
            outputs.get("table_schedule_extraction_candidate_count", 0),
            outputs.get("quantity_extraction_candidate_count", 0),
            outputs.get("evidence_human_verification_required_count", 0),
            outputs.get("clarification_candidate_count", 0),
        )
        if isinstance(count, int)
    )
    flow_exercised = all(stages.values())
    safety_flags_clear = draft_safety_flags_clear and preview_safety_flags_clear and review_safety_flags_clear
    if not flow_exercised:
        status = "flow_incomplete"
    elif not safety_flags_clear:
        status = "safety_violation_blocked"
    elif blocked_count:
        status = "flow_exercised_blocked_before_delivery"
    elif human_review_count:
        status = "flow_exercised_staff_review_required"
    else:
        status = "flow_exercised_ready_for_staff_review"

    return {
        "status": status,
        "flow_exercised": flow_exercised,
        "stages": stages,
        "safety_flags_clear": safety_flags_clear,
        "customer_delivery_ready": False,
        "final_estimate_approved": False,
        "external_messages": False,
        "payments": False,
        "safe_draft": {
            "line_item_count": outputs.get("generic_estimate_draft_line_item_count", 0),
            "blocked_scope_item_count": outputs.get("generic_estimate_draft_blocked_scope_item_count", 0),
            "safety_flags_clear": draft_safety_flags_clear,
        },
        "safe_proposal_preview": {
            "scope_line_count": outputs.get("generic_proposal_preview_scope_line_count", 0),
            "blocked_scope_item_count": outputs.get("generic_proposal_preview_blocked_scope_item_count", 0),
            "proposal_created": False,
            "proposal_issued": False,
            "safety_flags_clear": preview_safety_flags_clear,
        },
        "review_package_status": review_package.get("status"),
        "human_review_signal_count": human_review_count,
        "blocked_signal_count": blocked_count,
    }


def _build_stage_summary(report: dict[str, Any]) -> dict[str, Any]:
    stages = report.get("stages", {})
    per_stage: dict[str, Any] = {}
    failed: list[dict[str, Any]] = []
    for name, stage in stages.items():
        if not isinstance(stage, dict):
            continue
        summary = {
            "ok": bool(stage.get("ok")),
            "status_code": stage.get("status_code"),
            "duration_ms": stage.get("duration_ms"),
        }
        count = _item_count(stage)
        if count is not None:
            summary["item_count"] = count
        error = _error_summary(stage)
        if error:
            summary["error"] = error
            failed.append({"stage": name, **error})
        per_stage[name] = summary

    readiness_stage = stages.get("readiness_after_test_inputs") or stages.get("readiness")
    owner_review_stage = stages.get("owner_review_after_test_inputs") or stages.get("owner_review")
    clarification_stage = stages.get("clarification_package_after_test_inputs") or stages.get("clarification_package")
    generic_estimate_draft_stage = stages.get("generic_estimate_draft_after_test_inputs", {})
    generic_proposal_preview_stage = stages.get("generic_proposal_preview_after_test_inputs", {})
    readiness = readiness_stage.get("body", {}) if isinstance(readiness_stage, dict) else {}
    owner_review = owner_review_stage.get("body", {}) if isinstance(owner_review_stage, dict) else {}
    register = owner_review.get("review_packet", {}).get("assumptions_register", {}) if isinstance(owner_review, dict) else {}
    register_summary = register.get("summary", {}) if isinstance(register, dict) else {}
    clarification = clarification_stage.get("body", {}) if isinstance(clarification_stage, dict) else {}
    if not isinstance(clarification, dict) or not isinstance(clarification.get("summary"), dict):
        clarification = owner_review.get("review_packet", {}).get("clarification_package", {}) if isinstance(owner_review, dict) else {}
    clarification_summary = clarification.get("summary", {}) if isinstance(clarification, dict) else {}
    generic_estimate_draft = generic_estimate_draft_stage.get("body", {}) if isinstance(generic_estimate_draft_stage, dict) else {}
    generic_estimate_summary = generic_estimate_draft.get("summary", {}) if isinstance(generic_estimate_draft, dict) else {}
    generic_proposal_preview = generic_proposal_preview_stage.get("body", {}) if isinstance(generic_proposal_preview_stage, dict) else {}
    generic_preview = generic_proposal_preview.get("customer_safe_preview", {}) if isinstance(generic_proposal_preview, dict) else {}
    generic_preview_summary = generic_preview.get("summary", {}) if isinstance(generic_preview, dict) else {}
    generic_preview_flags = generic_preview.get("safety_flags", {}) if isinstance(generic_preview, dict) else {}
    clarification_groups = clarification.get("groups", {}) if isinstance(clarification, dict) else {}
    sheets = stages.get("sheets", {})
    coverage_validate = stages.get("coverage_validate", {})
    scope_items = stages.get("scope_items_after_test_inputs") or stages.get("scope_items", {})
    pricing_summary = _pricing_readiness_summary(scope_items if isinstance(scope_items, dict) else {})
    quantity_requirements = stages.get("quantity_requirements_after_test_inputs") or stages.get("quantity_requirements", {})
    qa_findings = stages.get("qa_findings", {})
    provenance = readiness.get("details", {}).get("provenance_confidence", {}) if isinstance(readiness, dict) else {}
    if not isinstance(provenance, dict):
        provenance = {}
    sheet_source_summary = _sheet_source_summary(sheets if isinstance(sheets, dict) else {})
    trade_quality_summary = _trade_quality_summary(scope_items if isinstance(scope_items, dict) else {}, provenance)
    quantity_confidence_summary = _quantity_confidence_summary(
        scope_items if isinstance(scope_items, dict) else {},
        quantity_requirements if isinstance(quantity_requirements, dict) else {},
    )
    quantity_extraction_candidate_summary = _quantity_extraction_candidate_summary(
        scope_items if isinstance(scope_items, dict) else {}
    )
    formula_check_summary = _generic_formula_check_summary(scope_items if isinstance(scope_items, dict) else {})
    evidence_quote_summary = _scope_evidence_quote_summary(scope_items if isinstance(scope_items, dict) else {})
    successful = sum(1 for item in per_stage.values() if item.get("ok"))
    total = len(per_stage)
    failed_stage_count = total - successful
    summary = {
        "stage_count": total,
        "ok_stage_count": successful,
        "failed_stage_count": failed_stage_count,
        "stage_success_rate": round(successful / total, 4) if total else 0,
        "failed_stages": failed,
        "per_stage": per_stage,
        "outputs": {
            "sheet_count": _item_count(sheets) or 0,
            "document_source_type_counts": sheet_source_summary["document_source_type_counts"],
            "sheet_processing_status_counts": sheet_source_summary["sheet_processing_status_counts"],
            "sheet_requires_ocr_count": sheet_source_summary["sheet_requires_ocr_count"],
            "sheet_requires_review_count": sheet_source_summary["sheet_requires_review_count"],
            "sheet_low_information_text_layer_count": sheet_source_summary["sheet_low_information_text_layer_count"],
            "sheet_very_low_information_text_layer_count": sheet_source_summary["sheet_very_low_information_text_layer_count"],
            "sheet_text_detail_missing_count": sheet_source_summary["sheet_text_detail_missing_count"],
            "sheet_text_layer_quality_counts": sheet_source_summary["sheet_text_layer_quality_counts"],
            "sheet_recommended_extraction_route_counts": sheet_source_summary["sheet_recommended_extraction_route_counts"],
            "table_schedule_extraction_candidate_count": sheet_source_summary["table_schedule_extraction_candidate_count"],
            "table_schedule_extraction_candidate_quality_counts": sheet_source_summary["table_schedule_extraction_candidate_quality_counts"],
            "repeated_low_information_table_schedule_candidate_count": sheet_source_summary[
                "repeated_low_information_table_schedule_candidate_count"
            ],
            "table_schedule_extraction_candidates": sheet_source_summary["table_schedule_extraction_candidates"],
            "sheet_text_char_count_min": sheet_source_summary["sheet_text_char_count_min"],
            "sheet_text_char_count_avg": sheet_source_summary["sheet_text_char_count_avg"],
            "sheet_text_char_count_max": sheet_source_summary["sheet_text_char_count_max"],
            "sheet_detection_confidence_min": sheet_source_summary["sheet_detection_confidence_min"],
            "sheet_detection_confidence_avg": sheet_source_summary["sheet_detection_confidence_avg"],
            "sheet_detection_confidence_max": sheet_source_summary["sheet_detection_confidence_max"],
            "coverage_finding_count": len(coverage_validate.get("body", {}).get("findings", [])) if isinstance(coverage_validate.get("body"), dict) else 0,
            "scope_item_count": _item_count(scope_items) or 0,
            "generic_pricing_scope_item_count": pricing_summary["generic_pricing_scope_item_count"],
            "pricing_method_assigned_count": pricing_summary["pricing_method_assigned_count"],
            "pricing_method_unassigned_count": pricing_summary["pricing_method_unassigned_count"],
            "pricing_ready_scope_item_count": pricing_summary["pricing_ready_scope_item_count"],
            "pricing_not_ready_scope_item_count": pricing_summary["pricing_not_ready_scope_item_count"],
            "priced_scope_item_count": pricing_summary["priced_scope_item_count"],
            "unpriced_scope_item_count": pricing_summary["unpriced_scope_item_count"],
            "pricing_method_counts": pricing_summary["pricing_method_counts"],
            "formula_check_scope_item_count": formula_check_summary["formula_check_scope_item_count"],
            "formula_check_ready_count": formula_check_summary["formula_check_ready_count"],
            "formula_check_blocked_count": formula_check_summary["formula_check_blocked_count"],
            "formula_check_ready_rate": formula_check_summary["formula_check_ready_rate"],
            "formula_check_method_counts": formula_check_summary["formula_check_method_counts"],
            "formula_check_blocker_counts": formula_check_summary["formula_check_blocker_counts"],
            "formula_check_by_trade": formula_check_summary["formula_check_by_trade"],
            "generic_estimate_draft_ready_scope_item_count": generic_estimate_summary.get("ready_scope_item_count", 0),
            "generic_estimate_draft_blocked_scope_item_count": generic_estimate_summary.get("blocked_scope_item_count", 0),
            "generic_estimate_draft_line_item_count": generic_estimate_summary.get("line_item_count", 0),
            "generic_estimate_draft_customer_delivery_ready": bool(generic_estimate_summary.get("customer_delivery_ready")),
            "generic_estimate_draft_final_estimate_approved": bool(generic_estimate_summary.get("final_estimate_approved")),
            "generic_estimate_draft_external_messages": bool(generic_estimate_summary.get("external_messages")),
            "generic_estimate_draft_payments": generic_estimate_summary.get("payments", False),
            "generic_proposal_preview_scope_line_count": generic_preview_summary.get("scope_line_count", 0),
            "generic_proposal_preview_blocked_scope_item_count": generic_preview_summary.get("blocked_scope_item_count", 0),
            "generic_proposal_preview_customer_delivery_ready": generic_preview_summary.get("customer_delivery_ready", False),
            "generic_proposal_preview_final_estimate_approved": generic_preview_summary.get("final_estimate_approved", False),
            "generic_proposal_preview_external_messages": generic_preview_summary.get("external_messages", False),
            "generic_proposal_preview_payments": generic_preview_summary.get("payments", False),
            "generic_proposal_preview_proposal_created": generic_preview_flags.get("proposal_created", False),
            "generic_proposal_preview_proposal_issued": generic_preview_flags.get("proposal_issued", False),
            "missing_quantity_pricing_blocker_count": pricing_summary["missing_quantity"],
            "missing_unit_rate_pricing_blocker_count": pricing_summary["missing_unit_rate"],
            "missing_subcontract_quote_pricing_blocker_count": pricing_summary["missing_subcontract_quote"],
            "missing_allowance_basis_pricing_blocker_count": pricing_summary["missing_allowance_basis"],
            "scope_items_with_trusted_evidence_count": provenance.get("items_with_trusted_evidence_count", 0) if isinstance(provenance, dict) else 0,
            "scope_items_missing_trusted_evidence_count": provenance.get("items_missing_trusted_evidence_count", 0) if isinstance(provenance, dict) else 0,
            "low_confidence_item_count": provenance.get("low_confidence_item_count", 0) if isinstance(provenance, dict) else 0,
            "quantity_basis_unclear_count": provenance.get("quantity_basis_unclear_count", 0) if isinstance(provenance, dict) else 0,
            "trusted_evidence_coverage_rate": provenance.get("trusted_evidence_coverage_rate", 0),
            "scope_items_with_evidence_quote_count": evidence_quote_summary["scope_items_with_evidence_quote_count"],
            "scope_items_missing_evidence_quote_count": evidence_quote_summary["scope_items_missing_evidence_quote_count"],
            "evidence_quote_count": evidence_quote_summary["evidence_quote_count"],
            "evidence_human_verification_required_count": evidence_quote_summary["evidence_human_verification_required_count"],
            "evidence_quote_coverage_rate": evidence_quote_summary["evidence_quote_coverage_rate"],
            "evidence_quote_by_trade": evidence_quote_summary["evidence_quote_by_trade"],
            "evidence_quote_gap_candidates": evidence_quote_summary["evidence_quote_gap_candidates"],
            "trade_quality_summary": trade_quality_summary[:10],
            "assumption_count": register_summary.get("assumption_count", 0),
            "exclusion_count": register_summary.get("exclusion_count", 0),
            "open_question_count": register_summary.get("open_question_count", 0),
            "register_blocking_entry_count": register_summary.get("blocking_entry_count", 0),
            "clarification_candidate_count": clarification_summary.get("candidate_count", 0),
            "blocking_clarification_candidate_count": clarification_summary.get("blocking_candidate_count", 0),
            "critical_clarification_candidate_count": clarification_summary.get("critical_candidate_count", 0),
            "customer_safe_clarification_candidate_count": clarification_summary.get("customer_safe_candidate_count", 0),
            "urgent_clarification_candidate_count": clarification_summary.get("urgent_candidate_count", 0),
            "high_clarification_candidate_count": clarification_summary.get("high_candidate_count", 0),
            "top_clarification_candidate_ids": clarification_summary.get("top_candidate_ids", []),
            "top_clarification_groups_by_trade": (clarification_groups.get("by_trade") or [])[:5] if isinstance(clarification_groups, dict) else [],
            "top_clarification_groups_by_source_code": (clarification_groups.get("by_source_code") or [])[:5] if isinstance(clarification_groups, dict) else [],
            "clarification_customer_message_ready": bool(clarification.get("customer_message_ready")) if isinstance(clarification, dict) else False,
            "clarification_send_ready": bool(clarification.get("send_ready")) if isinstance(clarification, dict) else False,
            "quantity_requirement_count": _item_count(quantity_requirements) or 0,
            "quantity_scope_item_count": quantity_confidence_summary["quantity_scope_item_count"],
            "quantity_present_count": quantity_confidence_summary["quantity_present_count"],
            "quantity_missing_count": quantity_confidence_summary["quantity_missing_count"],
            "quantity_traceable_count": quantity_confidence_summary["quantity_traceable_count"],
            "quantity_unclear_basis_count": quantity_confidence_summary["quantity_unclear_basis_count"],
            "quantity_test_input_count": quantity_confidence_summary["quantity_test_input_count"],
            "open_quantity_requirement_count": quantity_confidence_summary["open_quantity_requirement_count"],
            "resolved_quantity_requirement_count": quantity_confidence_summary["resolved_quantity_requirement_count"],
            "quantity_traceable_rate": quantity_confidence_summary["quantity_traceable_rate"],
            "quantity_confidence_by_trade": quantity_confidence_summary["quantity_confidence_by_trade"],
            "quantity_extraction_candidate_count": quantity_extraction_candidate_summary["quantity_extraction_candidate_count"],
            "quantity_extraction_candidates": quantity_extraction_candidate_summary["quantity_extraction_candidates"],
            "quantity_extraction_candidate_by_trade": quantity_extraction_candidate_summary["quantity_extraction_candidate_by_trade"],
            "manual_quantity_input_count": quantity_extraction_candidate_summary["manual_quantity_input_count"],
            "quantity_extraction_test_input_count": quantity_extraction_candidate_summary["test_quantity_input_count"],
            "qa_finding_count": _item_count(qa_findings) or 0,
            "readiness_status": readiness.get("status") if isinstance(readiness, dict) else None,
            "readiness_blockers": readiness.get("blockers") if isinstance(readiness, dict) else None,
            "owner_review_status": owner_review.get("status") if isinstance(owner_review, dict) else None,
            "customer_delivery_ready": bool(readiness.get("customer_delivery_ready")) if isinstance(readiness, dict) else False,
        },
    }
    summary["outputs"]["automation_review_package"] = _automation_review_package_from_outputs(
        summary["outputs"],
        failed_stage_count=failed_stage_count,
    )
    summary["outputs"]["beta_flow_dry_run"] = _beta_flow_dry_run_from_summary(summary)
    return summary


def _finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    report["summary"] = _build_stage_summary(report)
    return report


def _apply_test_quantity_and_pricing_inputs(client: Any, project_id: str, report: dict[str, Any]) -> None:
    """Apply explicit fictional inputs so the harness can test readiness flow.

    These values are only for local smoke testing. They are marked in the source
    fields and must never be treated as market pricing or final estimate data.
    """
    base = f"/api/v1/projects/{project_id}"
    reqs = _get(client, f"{base}/quantity-requirements")
    report["stages"]["test_input_quantity_requirements_before"] = reqs
    quantity_inputs_by_scope: dict[str, dict[str, Any]] = {}
    if reqs["ok"]:
        for req in reqs["body"].get("items", []):
            if req.get("status") != "open":
                continue
            apply_stage = _post(
                client,
                f"{base}/quantity-requirements/{req['id']}/apply",
                json_body={
                    "quantity": "10",
                    "unit": req.get("suggested_unit") or "EA",
                    "source": "harness_test_only_quantity",
                },
            )
            report["stages"][f"test_apply_quantity_{req['id']}"] = apply_stage
            applied_scope_item = (apply_stage.get("body") or {}).get("scope_item") if apply_stage.get("ok") else None
            if isinstance(applied_scope_item, dict) and isinstance(applied_scope_item.get("raw_quantity_inputs"), dict):
                quantity_inputs_by_scope[str(applied_scope_item.get("id"))] = applied_scope_item["raw_quantity_inputs"]

    scope = _get_all_scope_items(client, base)
    report["stages"]["test_input_scope_items_before_pricing"] = scope
    if scope["ok"]:
        for item in scope["body"].get("items", []):
            detail = _get(client, f"{base}/scope-items/{item['id']}")
            trade_data = detail.get("body", {}).get("trade_data") or {}
            method = trade_data.get("pricing_method")
            if not method or trade_data.get("pricing_ready"):
                continue
            report["stages"][f"test_apply_pricing_{item['id']}"] = _post(
                client,
                f"{base}/pricing/generic-inputs/{item['id']}/apply",
                json_body={
                    "pricing_method": method,
                    "amount": "100",
                    "source": "harness_test_only_pricing",
                },
            )

    after_scope = _get_all_scope_items_with_details(client, base, quantity_inputs_by_scope=quantity_inputs_by_scope)
    report["stages"]["scope_items_after_test_inputs"] = after_scope
    report["stages"]["quantity_requirements_after_test_inputs"] = _get(client, f"{base}/quantity-requirements")
    report["stages"]["qa_findings_after_test_inputs"] = _post(client, f"{base}/qa/findings/draft")
    report["stages"]["readiness_after_test_inputs"] = _get(client, f"{base}/estimate-readiness")
    report["stages"]["generic_estimate_draft_after_test_inputs"] = _post(
        client,
        f"{base}/estimates/generic-draft",
        json_body={"name": "Harness Generic Draft Estimate"},
    )
    draft_stage = report["stages"]["generic_estimate_draft_after_test_inputs"]
    if draft_stage.get("ok"):
        draft_body = draft_stage.get("body") or {}
        estimate_id = (draft_body.get("estimate") or {}).get("id")
        version_id = (draft_body.get("version") or {}).get("id")
        if estimate_id and version_id:
            report["stages"]["generic_proposal_preview_after_test_inputs"] = _get(
                client,
                f"{base}/estimates/{estimate_id}/versions/{version_id}/proposal-preview",
            )
    report["stages"]["owner_review_after_test_inputs"] = _get(client, f"{base}/owner-review/package")
    report["stages"]["clarification_package_after_test_inputs"] = _get(client, f"{base}/clarifications/package")


def run_harness(pdf_path: Path, *, project_name: str, workdir: Path, apply_test_inputs: bool = False) -> dict[str, Any]:
    _configure_env(workdir)

    # Import after env is configured so settings point at the harness DB/files.
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.database import init_db
    from app.main import app

    settings.db_path = workdir / "mobi.db"
    settings.upload_dir = workdir / "uploads"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.enabled_trades = ["painting", "demo_concrete", "general_trade"]
    init_db()

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_pdf": str(pdf_path.resolve()),
        "project_name": project_name,
        "workdir": str(workdir.resolve()),
        "safety": {
            "customer_delivery": False,
            "external_messages": False,
            "final_estimate_approval": False,
            "payments": False,
            "test_inputs_only": apply_test_inputs,
        },
        "project_id": None,
        "stages": {},
    }

    with TestClient(app, raise_server_exceptions=False) as client:
        with pdf_path.open("rb") as fh:
            start = time.perf_counter()
            upload = client.post(
                "/api/v1/projects/upload",
                data={"project_name": project_name},
                files={"plan": (pdf_path.name, fh, "application/pdf")},
                headers=HARNESS_TENANT_HEADERS,
            )
        report["stages"]["upload"] = _json_response(upload, duration_ms=int((time.perf_counter() - start) * 1000))
        if not report["stages"]["upload"]["ok"]:
            return _finalize_report(report)
        project_id = report["stages"]["upload"]["body"]["project_id"]
        report["project_id"] = project_id
        base = f"/api/v1/projects/{project_id}"

        stage_calls: list[tuple[str, str, Any | None]] = [
            ("process", f"{base}/process", None),
            ("coverage_draft", f"{base}/coverage/draft", None),
            ("generic_scope_draft", f"{base}/coverage/generic-scope/draft", None),
            ("pricing_methods_draft", f"{base}/pricing/generic-methods/draft", {}),
            ("quantity_requirements_draft", f"{base}/quantity-requirements/draft", None),
            ("qa_findings_draft", f"{base}/qa/findings/draft", None),
        ]
        for name, path, body in stage_calls:
            report["stages"][name] = _post(client, path, json_body=body)

        report["stages"]["scope_items"] = _get_all_scope_items_with_details(client, base)
        report["stages"]["sheets"] = _get_all_sheets_with_details(client, base)
        for name, path in [
            ("coverage", f"{base}/coverage"),
            ("coverage_validate", f"{base}/coverage/validate"),
            ("quantity_requirements", f"{base}/quantity-requirements"),
            ("qa_findings", f"{base}/qa/findings"),
            ("boe", f"{base}/boe/draft"),
            ("readiness", f"{base}/estimate-readiness"),
            ("owner_review", f"{base}/owner-review/package"),
            ("clarification_package", f"{base}/clarifications/package"),
        ]:
            report["stages"][name] = _get(client, path)

        if apply_test_inputs:
            _apply_test_quantity_and_pricing_inputs(client, project_id, report)

    return _finalize_report(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real PDF through the Mobi estimating smoke pipeline.")
    parser.add_argument("pdf", type=Path, help="Path to a PDF plan/spec set")
    parser.add_argument("--project-name", default="Harness Project", help="Project name to use in the engine")
    parser.add_argument("--workdir", type=Path, default=None, help="Harness working directory; defaults to a temp dir")
    parser.add_argument("--output", type=Path, default=None, help="JSON report path")
    parser.add_argument(
        "--apply-test-inputs",
        action="store_true",
        help="Apply explicit fictional quantity/pricing inputs to exercise readiness flow.",
    )
    args = parser.parse_args()

    if not args.pdf.exists() or not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="mobi-real-doc-"))
    report = run_harness(
        args.pdf,
        project_name=args.project_name,
        workdir=workdir,
        apply_test_inputs=args.apply_test_inputs,
    )
    output = args.output or (workdir / "real_document_harness_report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    initial_readiness = report.get("stages", {}).get("readiness", {}).get("body", {}).get("status")
    after_test_inputs = report.get("stages", {}).get("readiness_after_test_inputs", {}).get("body", {}).get("status")
    owner_review = report.get("stages", {}).get("owner_review_after_test_inputs", {}).get("body", {}).get("status")
    failed_stage_count = report.get("summary", {}).get("failed_stage_count", 0)
    print(json.dumps({
        "output": str(output.resolve()),
        "project_id": report.get("project_id"),
        "readiness": initial_readiness,
        "readiness_after_test_inputs": after_test_inputs,
        "owner_review_after_test_inputs": owner_review,
        "failed_stage_count": failed_stage_count,
        "workdir": str(workdir.resolve()),
    }, indent=2, sort_keys=True))
    return 1 if failed_stage_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
