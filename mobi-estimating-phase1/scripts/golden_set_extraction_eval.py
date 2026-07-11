#!/usr/bin/env python3
"""Golden Set v1 + Extraction Evaluation Harness for the local Mobi estimating engine.

This script scores how well the local engine *reads* real bid packages: whether it
detects the trades and scope keywords a human estimator expects, and whether any
labeled key quantities land within tolerance. It reuses ``real_document_harness``
to run each project's primary document through the local FastAPI TestClient
pipeline in an isolated workdir, then evaluates the harness report.

It is a **local/internal testing** tool only. It does not send customer messages,
create customer deliverables, process payments, approve/finalize estimates, or
issue proposals. It asserts those safety locks stay closed and fails loudly if the
harness ever reports otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from scripts.real_document_harness import run_harness  # noqa: E402


# Safety flags that must remain closed in every harness report. Any truthy value
# here means a customer-facing/final/billing lock was opened and the evaluation
# must fail.
_SAFETY_TOP_LEVEL_KEYS = (
    "customer_delivery",
    "external_messages",
    "final_estimate_approval",
    "payments",
    "proposal_issue",
)
_SAFETY_OUTPUT_KEYS = (
    "customer_delivery_ready",
    "generic_estimate_draft_customer_delivery_ready",
    "generic_estimate_draft_final_estimate_approved",
    "generic_estimate_draft_external_messages",
    "generic_estimate_draft_payments",
    "generic_proposal_preview_customer_delivery_ready",
    "generic_proposal_preview_final_estimate_approved",
    "generic_proposal_preview_external_messages",
    "generic_proposal_preview_payments",
    "generic_proposal_preview_proposal_created",
    "generic_proposal_preview_proposal_issued",
    "clarification_send_ready",
    "clarification_customer_message_ready",
)

_VALID_SOURCE_AUTHORIZATIONS = {"public", "authorized", "internal"}


class ManifestError(ValueError):
    """Raised when a golden-set manifest is missing required fields or metadata."""


# ---------------------------------------------------------------------------
# Manifest loading and validation
# ---------------------------------------------------------------------------
def load_manifest(path: Path) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ManifestError(f"Manifest is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a JSON object.")
    return data


def _require_internal_testing_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise ManifestError("Manifest must include a top-level 'metadata' object.")
    if metadata.get("internal_testing_only") is not True:
        raise ManifestError("Manifest metadata must set internal_testing_only=true.")
    source_auth = metadata.get("source_authorization")
    if source_auth not in _VALID_SOURCE_AUTHORIZATIONS:
        raise ManifestError(
            "Manifest metadata.source_authorization must be one of "
            f"{sorted(_VALID_SOURCE_AUTHORIZATIONS)} (public/authorized/internal-testing)."
        )
    return metadata


def _validate_key_quantity(kq: Any, project_id: str, index: int) -> None:
    where = f"project '{project_id}' key_quantities[{index}]"
    if not isinstance(kq, dict):
        raise ManifestError(f"{where} must be an object.")
    for field in ("label", "expected_value", "unit"):
        if field not in kq or kq[field] in (None, ""):
            raise ManifestError(f"{where} is missing required field '{field}'.")
    if _to_float(kq["expected_value"]) is None:
        raise ManifestError(f"{where} expected_value must be numeric.")
    for tol_field in ("tolerance_pct", "tolerance_abs"):
        tol = kq.get(tol_field)
        if tol is None:
            continue
        tol_value = _to_float(tol)
        if tol_value is None:
            raise ManifestError(f"{where} {tol_field} must be numeric.")
        if tol_value < 0:
            raise ManifestError(f"{where} {tol_field} must not be negative.")
    if kq.get("tolerance_pct") is None and kq.get("tolerance_abs") is None:
        raise ManifestError(f"{where} must set either tolerance_pct or tolerance_abs.")
    confidence = kq.get("confidence_level")
    if confidence is not None and confidence not in {"high", "medium", "low"}:
        raise ManifestError(f"{where} confidence_level must be one of high, medium, low.")
    for bool_field in ("require_engine_quantity", "expected_source_text_present", "evidence_verified"):
        if bool_field in kq and not isinstance(kq[bool_field], bool):
            raise ManifestError(f"{where} {bool_field} must be a boolean.")
    assumptions = kq.get("assumptions")
    if assumptions is not None and not isinstance(assumptions, (str, list)):
        raise ManifestError(f"{where} assumptions must be a string or list of strings.")
    if isinstance(assumptions, list) and not all(isinstance(item, str) for item in assumptions):
        raise ManifestError(f"{where} assumptions list must contain only strings.")

def validate_manifest(manifest: dict[str, Any], *, allow_missing_documents: bool, manifest_dir: Path) -> None:
    """Validate manifest structure/metadata. Raises ManifestError on any problem."""
    _require_internal_testing_metadata(manifest)
    projects = manifest.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ManifestError("Manifest must include a non-empty 'projects' list.")

    seen_ids: set[str] = set()
    required_fields = (
        "project_id",
        "title",
        "agency",
        "location",
        "document_paths",
        "addenda_complete",
        "expected_trades",
        "expected_scope_keywords",
    )
    for i, project in enumerate(projects):
        if not isinstance(project, dict):
            raise ManifestError(f"projects[{i}] must be an object.")
        for field in required_fields:
            if field not in project:
                raise ManifestError(f"projects[{i}] is missing required field '{field}'.")
        project_id = str(project["project_id"])
        if not project_id:
            raise ManifestError(f"projects[{i}] project_id must be non-empty.")
        if project_id in seen_ids:
            raise ManifestError(f"Duplicate project_id '{project_id}'.")
        seen_ids.add(project_id)
        if project.get("internal_testing_only") is not True:
            raise ManifestError(f"project '{project_id}' must set internal_testing_only=true.")
        if not isinstance(project["addenda_complete"], bool):
            raise ManifestError(f"project '{project_id}' addenda_complete must be a boolean.")
        for list_field in ("document_paths", "expected_trades", "expected_scope_keywords"):
            if not isinstance(project[list_field], list):
                raise ManifestError(f"project '{project_id}' {list_field} must be a list.")
        for optional_list_field in ("allowed_extra_trades", "forbidden_trades"):
            if optional_list_field in project and not isinstance(project[optional_list_field], list):
                raise ManifestError(f"project '{project_id}' {optional_list_field} must be a list.")
        if "fail_on_unexpected_false_positives" in project and not isinstance(project["fail_on_unexpected_false_positives"], bool):
            raise ManifestError(f"project '{project_id}' fail_on_unexpected_false_positives must be a boolean.")
        doc_paths = project["document_paths"]
        if not doc_paths:
            raise ManifestError(f"project '{project_id}' has no document_paths.")
        for kq_index, kq in enumerate(project.get("key_quantities") or []):
            _validate_key_quantity(kq, project_id, kq_index)
        outcome_paths = project.get("outcome_paths")
        if outcome_paths is not None:
            if not isinstance(outcome_paths, list):
                raise ManifestError(f"project '{project_id}' outcome_paths must be a list.")
            if outcome_paths:
                raise ManifestError(
                    f"project '{project_id}' outcome_paths must be empty in v1. It is reserved "
                    "for later bid-outcome calibration and must not carry outcome data yet."
                )
        if not allow_missing_documents:
            primary = _resolve_primary_document(project, manifest_dir)
            if primary is None or not primary.exists():
                raise ManifestError(
                    f"project '{project_id}' primary document not found: {doc_paths[0]!r}. "
                    "Pass --allow-missing-documents to validate schema/fixtures without documents."
                )


def _resolve_primary_document(project: dict[str, Any], manifest_dir: Path) -> Path | None:
    doc_paths = project.get("document_paths") or []
    if not doc_paths:
        return None
    raw = str(doc_paths[0])
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (manifest_dir / candidate)
    return candidate


# ---------------------------------------------------------------------------
# Pure scoring helpers (operate on a harness report dict; no PDFs required)
# ---------------------------------------------------------------------------
def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_detected_scope_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return detected scope items from the harness report (base extraction preferred)."""
    stages = report.get("stages", {}) if isinstance(report, dict) else {}
    stage = stages.get("scope_items") or stages.get("scope_items_after_test_inputs") or {}
    body = stage.get("body") if isinstance(stage, dict) else {}
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def detected_trade_codes(items: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("trade_code")) for item in items if item.get("trade_code")}


def score_trade_coverage(
    expected_trades: list[str],
    detected: set[str],
    *,
    allowed_extra_trades: list[str] | None = None,
) -> dict[str, Any]:
    expected = {str(t) for t in expected_trades if t}
    detected_set = {str(t) for t in detected if t}
    allowed_extra = {str(t) for t in (allowed_extra_trades or []) if t}
    matched = sorted(expected & detected_set)
    missed = sorted(expected - detected_set)
    false_positives = sorted(detected_set - expected)
    allowed_extra_detected = sorted((detected_set - expected) & allowed_extra)
    unexpected_false_positives = sorted((detected_set - expected) - allowed_extra)
    recall = round(len(matched) / len(expected), 4) if expected else None
    precision = round(len(matched) / len(detected_set), 4) if detected_set else None
    strict_precision_denominator = len(matched) + len(unexpected_false_positives)
    strict_precision = (
        round(len(matched) / strict_precision_denominator, 4)
        if strict_precision_denominator
        else precision
    )
    return {
        "expected_trades": sorted(expected),
        "detected_trades": sorted(detected_set),
        "allowed_extra_trades": sorted(allowed_extra),
        "matched_trades": matched,
        "missed_required_trades": missed,
        "false_positive_trades": false_positives,
        "allowed_extra_trades_detected": allowed_extra_detected,
        "unexpected_false_positive_trades": unexpected_false_positives,
        "false_positive_count": len(false_positives),
        "unexpected_false_positive_count": len(unexpected_false_positives),
        "recall": recall,
        "precision": precision,
        "strict_precision": strict_precision,
    }

def _scope_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("description"),
        item.get("location"),
        item.get("material_or_substrate"),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def score_scope_keyword_coverage(
    expected_keywords: list[str], items: list[dict[str, Any]]
) -> dict[str, Any]:
    corpus = " \n ".join(_scope_text(item) for item in items)
    found: list[str] = []
    missing: list[str] = []
    for keyword in expected_keywords:
        text = str(keyword).lower().strip()
        if text and text in corpus:
            found.append(str(keyword))
        else:
            missing.append(str(keyword))
    total = len(expected_keywords)
    return {
        "expected_keyword_count": total,
        "found_keywords": found,
        "missing_keywords": missing,
        "coverage": round(len(found) / total, 4) if total else None,
    }


def _match_scope_item_for_label(label: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = str(label).lower().strip()
    if not text:
        return None
    # Prefer a matching item that actually carries a numeric quantity.
    fallback: dict[str, Any] | None = None
    for item in items:
        if text in _scope_text(item):
            if _to_float(item.get("quantity")) is not None:
                return item
            if fallback is None:
                fallback = item
    return fallback



def _normalize_evidence_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def extract_document_text(path: Path, *, timeout: int = 60) -> dict[str, Any]:
    """Extract text from a PDF with local pdftotext for evidence checks."""
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", "-nopgbrk", str(path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"ok": False, "text": "", "char_count": 0, "extraction_method": "pdftotext", "reason": "pdftotext_not_found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "", "char_count": 0, "extraction_method": "pdftotext", "reason": "pdftotext_timeout"}
    text = proc.stdout or ""
    if proc.returncode != 0 and not text.strip():
        return {"ok": False, "text": "", "char_count": 0, "extraction_method": "pdftotext", "reason": f"pdftotext_exit_{proc.returncode}"}
    return {"ok": True, "text": text, "char_count": len(text), "extraction_method": "pdftotext", "reason": None}


def _score_evidence_snippet(kq: dict[str, Any], source_text: str | None) -> dict[str, Any]:
    if kq.get("evidence_verified") is True:
        return {"status": "pass", "reason": "human_verified_source_reference", "found": None}
    snippet = str(kq.get("evidence_snippet") or "").strip()
    if not snippet:
        return {"status": "unknown", "reason": "no_evidence_snippet_declared", "found": False}
    if source_text is None:
        return {"status": "unknown", "reason": "source_text_unavailable", "found": False}
    found = _normalize_evidence_text(snippet) in _normalize_evidence_text(source_text)
    expected_present = kq.get("expected_source_text_present", True)
    if found == expected_present:
        return {"status": "pass", "reason": None, "found": found}
    return {"status": "fail", "reason": "evidence_snippet_not_found" if expected_present else "unexpected_evidence_snippet_found", "found": found}

def evaluate_key_quantity(kq: dict[str, Any], items: list[dict[str, Any]], *, source_text: str | None = None) -> dict[str, Any]:
    label = str(kq.get("label"))
    expected_value = _to_float(kq.get("expected_value"))
    expected_unit = kq.get("unit")
    result: dict[str, Any] = {
        "label": label,
        "item_name": kq.get("item_name"),
        "trade": kq.get("trade"),
        "expected_value": kq.get("expected_value"),
        "unit": expected_unit,
        "source_ref": kq.get("source_ref"),
        "source_document": kq.get("source_document"),
        "sheet_ref": kq.get("sheet_ref"),
        "page_ref": kq.get("page_ref"),
        "evidence_snippet": kq.get("evidence_snippet"),
        "evidence_verified": kq.get("evidence_verified"),
        "measurement_method": kq.get("measurement_method"),
        "confidence_level": kq.get("confidence_level"),
        "assumptions": kq.get("assumptions"),
        "require_engine_quantity": kq.get("require_engine_quantity", True),
        "evidence_status": _score_evidence_snippet(kq, source_text),
        "detected_value": None,
        "detected_unit": None,
        "status": "unknown",
        "reason": None,
    }
    match = _match_scope_item_for_label(label, items)
    if match is None:
        result["reason"] = "no_matching_scope_item"
        if result["require_engine_quantity"] is False and result["evidence_status"].get("status") == "pass":
            result["status"] = "pass"
            result["reason"] = "source_evidence_only_engine_quantity_not_required"
        return result
    result["matched_scope_item"] = {
        "trade_code": match.get("trade_code"),
        "description": match.get("description"),
        "location": match.get("location"),
        "quantity": match.get("quantity"),
        "unit": match.get("unit"),
    }
    detected_value = _to_float(match.get("quantity"))
    detected_unit = match.get("unit")
    result["detected_value"] = match.get("quantity")
    result["detected_unit"] = detected_unit
    if detected_value is None:
        result["reason"] = "matched_scope_item_has_no_quantity"
        if result["require_engine_quantity"] is False and result["evidence_status"].get("status") == "pass":
            result["status"] = "pass"
            result["reason"] = "source_evidence_only_engine_quantity_not_required"
        return result
    if expected_unit and detected_unit and str(expected_unit).lower() != str(detected_unit).lower():
        result["reason"] = "unit_mismatch"
        return result
    tolerance_pct = _to_float(kq.get("tolerance_pct"))
    tolerance_abs = _to_float(kq.get("tolerance_abs"))
    # Negative/non-numeric tolerances are rejected at manifest validation; guard here
    # so directly-invoked callers never silently coerce a bad band into a pass.
    if tolerance_abs is not None and tolerance_abs < 0:
        result["reason"] = "invalid_tolerance"
        return result
    if tolerance_pct is not None and tolerance_pct < 0:
        result["reason"] = "invalid_tolerance"
        return result
    if tolerance_abs is not None:
        tolerance = tolerance_abs
    elif tolerance_pct is not None and expected_value is not None:
        tolerance = abs(expected_value) * tolerance_pct / 100.0
    else:
        tolerance = 0.0
    if expected_value is None:
        result["reason"] = "expected_value_not_numeric"
        return result
    delta = abs(detected_value - expected_value)
    result["delta"] = round(delta, 6)
    result["variance_pct"] = round(delta / abs(expected_value) * 100.0, 6) if expected_value else None
    result["tolerance"] = round(tolerance, 6)
    if delta <= tolerance:
        result["status"] = "pass"
    else:
        result["status"] = "fail"
        result["reason"] = "outside_tolerance"
    return result


def evaluate_key_quantities(
    key_quantities: list[dict[str, Any]],
    items: list[dict[str, Any]],
    *,
    source_text: str | None = None,
) -> dict[str, Any]:
    results = [evaluate_key_quantity(kq, items, source_text=source_text) for kq in key_quantities]
    counts = {"pass": 0, "fail": 0, "unknown": 0}
    evidence_counts = {"pass": 0, "fail": 0, "unknown": 0}
    unit_mismatch_count = 0
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        ev_status = (r.get("evidence_status") or {}).get("status", "unknown")
        evidence_counts[ev_status] = evidence_counts.get(ev_status, 0) + 1
        if r.get("reason") == "unit_mismatch":
            unit_mismatch_count += 1
    return {
        "results": results,
        "pass_count": counts["pass"],
        "fail_count": counts["fail"],
        "unknown_count": counts["unknown"],
        "evidence_pass_count": evidence_counts["pass"],
        "evidence_fail_count": evidence_counts["fail"],
        "evidence_unknown_count": evidence_counts["unknown"],
        "unit_mismatch_count": unit_mismatch_count,
        "total": len(results),
    }

def evaluate_safety(report: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    safety = report.get("safety", {}) if isinstance(report, dict) else {}
    if isinstance(safety, dict):
        for key in _SAFETY_TOP_LEVEL_KEYS:
            if safety.get(key):
                violations.append(f"safety.{key}")
    outputs = {}
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    if isinstance(summary, dict) and isinstance(summary.get("outputs"), dict):
        outputs = summary["outputs"]
    for key in _SAFETY_OUTPUT_KEYS:
        if outputs.get(key):
            violations.append(f"outputs.{key}")
    return {"ok": not violations, "violations": violations}



def _stage_ok(report: dict[str, Any], stage_name: str) -> bool:
    stages = report.get("stages", {}) if isinstance(report, dict) else {}
    stage = stages.get(stage_name) if isinstance(stages, dict) else None
    return bool(isinstance(stage, dict) and stage.get("ok") is True)


def build_extraction_quality(
    *,
    document_text_extraction: dict[str, Any],
    sheet_count: int,
    detected_scope_item_count: int,
    missed_required: bool,
    key_quantities: dict[str, Any],
    unexpected_false_positive_count: int,
    strict_false_positives: bool,
) -> dict[str, Any]:
    quantity_total = key_quantities.get("total", 0)
    if quantity_total == 0:
        quantity_status = "unknown"
    elif key_quantities.get("fail_count", 0) or key_quantities.get("unknown_count", 0):
        quantity_status = "fail"
    else:
        quantity_status = "pass"
    if quantity_total == 0:
        evidence_status = "unknown"
    elif key_quantities.get("evidence_fail_count", 0):
        evidence_status = "fail"
    elif key_quantities.get("evidence_pass_count", 0) == quantity_total:
        evidence_status = "pass"
    else:
        evidence_status = "unknown"
    if unexpected_false_positive_count and strict_false_positives:
        hallucination_status = "fail"
    elif unexpected_false_positive_count:
        hallucination_status = "warn"
    else:
        hallucination_status = "pass"
    return {
        "document_text_extraction": {
            "status": "pass" if document_text_extraction.get("ok") else "fail",
            "char_count": document_text_extraction.get("char_count", 0),
            "method": document_text_extraction.get("extraction_method"),
            "reason": document_text_extraction.get("reason"),
        },
        "sheet_detection": {"status": "pass" if sheet_count > 0 else "fail", "sheet_count": sheet_count},
        "scope_detection": {"status": "pass" if detected_scope_item_count > 0 else "fail", "detected_scope_item_count": detected_scope_item_count},
        "trade_classification": {"status": "pass" if not missed_required else "fail"},
        "quantity_extraction": {"status": quantity_status, "quantity_total": quantity_total},
        "unit_normalization": {"status": "pass" if not key_quantities.get("unit_mismatch_count", 0) else "fail"},
        "evidence_quality": {"status": evidence_status},
        "hallucination_guard": {"status": hallucination_status, "unexpected_false_positive_count": unexpected_false_positive_count},
    }

# ---------------------------------------------------------------------------
# Per-project evaluation
# ---------------------------------------------------------------------------
def evaluate_report(project: dict[str, Any], report: dict[str, Any], *, document_text_extraction: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a single harness report against a project's golden expectations."""
    items = extract_detected_scope_items(report)
    document_text_extraction = document_text_extraction or {"ok": False, "text": "", "char_count": 0, "extraction_method": None, "reason": "not_run"}
    trade_coverage = score_trade_coverage(
        project.get("expected_trades") or [],
        detected_trade_codes(items),
        allowed_extra_trades=project.get("allowed_extra_trades") or [],
    )
    keyword_coverage = score_scope_keyword_coverage(project.get("expected_scope_keywords") or [], items)
    key_quantities = evaluate_key_quantities(
        project.get("key_quantities") or [],
        items,
        source_text=document_text_extraction.get("text"),
    )
    safety = evaluate_safety(report)

    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    failed_stage_count = summary.get("failed_stage_count", 0) if isinstance(summary, dict) else 0
    harness_ok = bool(report) and failed_stage_count == 0

    addenda_complete = bool(project.get("addenda_complete"))
    warnings: list[str] = []
    if not addenda_complete:
        warnings.append("addenda_incomplete_benchmark_ineligible")

    missed_required = bool(trade_coverage["missed_required_trades"])

    # Accuracy gate: honest extraction quality, independent of safety/harness health.
    # Only enforced where the manifest actually declares expectations.
    expected_keywords = project.get("expected_scope_keywords") or []
    keyword_full_coverage = not expected_keywords or not keyword_coverage["missing_keywords"]
    declared_key_quantities = bool(project.get("key_quantities"))
    key_quantity_fail = key_quantities["fail_count"] > 0
    key_quantity_unknown = declared_key_quantities and key_quantities["unknown_count"] > 0
    evidence_fail = declared_key_quantities and key_quantities.get("evidence_fail_count", 0) > 0
    strict_false_positives = bool(project.get("fail_on_unexpected_false_positives"))
    unexpected_false_positive = bool(trade_coverage.get("unexpected_false_positive_trades"))
    accuracy_failures: list[str] = []
    if not keyword_full_coverage:
        accuracy_failures.append("expected_keywords_missing")
    if key_quantity_fail:
        accuracy_failures.append("key_quantity_fail")
    if key_quantity_unknown:
        accuracy_failures.append("key_quantity_unknown")
    if evidence_fail:
        accuracy_failures.append("evidence_snippet_missing")
    if strict_false_positives and unexpected_false_positive:
        accuracy_failures.append("unexpected_false_positive_trade")
    accuracy_passed = not accuracy_failures

    # Hard gate: harness ran clean, safety locks held, and no required trade was missed.
    hard_gate_passed = harness_ok and safety["ok"] and not missed_required
    evaluation_passed = hard_gate_passed and accuracy_passed
    stages = report.get("stages", {}) if isinstance(report, dict) else {}
    sheets_stage = stages.get("sheets") if isinstance(stages, dict) else {}
    sheets_body = sheets_stage.get("body") if isinstance(sheets_stage, dict) else {}
    sheet_count = 0
    if isinstance(sheets_body, dict):
        sheet_count = int(sheets_body.get("total") or len(sheets_body.get("items") or []))
    extraction_quality = build_extraction_quality(
        document_text_extraction=document_text_extraction,
        sheet_count=sheet_count,
        detected_scope_item_count=len(items),
        missed_required=missed_required,
        key_quantities=key_quantities,
        unexpected_false_positive_count=trade_coverage.get("unexpected_false_positive_count", 0),
        strict_false_positives=strict_false_positives,
    )

    return {
        "project_id": project.get("project_id"),
        "title": project.get("title"),
        "agency": project.get("agency"),
        "location": project.get("location"),
        "evaluation_status": "evaluated" if harness_ok else "harness_failed",
        "harness_ok": harness_ok,
        "failed_stage_count": failed_stage_count,
        "benchmark_eligible": addenda_complete,
        "benchmark_ineligible": not addenda_complete,
        "addenda_complete": addenda_complete,
        "detected_scope_item_count": len(items),
        "trade_coverage": trade_coverage,
        "scope_keyword_coverage": keyword_coverage,
        "key_quantities": key_quantities,
        "document_text_extraction": {k: v for k, v in document_text_extraction.items() if k != "text"},
        "extraction_quality": extraction_quality,
        "safety": safety,
        "missed_required_trade": missed_required,
        "accuracy_passed": accuracy_passed,
        "accuracy_failures": accuracy_failures,
        "hard_gate_passed": hard_gate_passed,
        "evaluation_passed": evaluation_passed,
        "warnings": warnings,
        "project_id_in_engine": report.get("project_id") if isinstance(report, dict) else None,
        "workdir": report.get("workdir") if isinstance(report, dict) else None,
    }


def _skipped_project_result(project: dict[str, Any], reason: str) -> dict[str, Any]:
    addenda_complete = bool(project.get("addenda_complete"))
    warnings = [reason]
    if not addenda_complete:
        warnings.append("addenda_incomplete_benchmark_ineligible")
    return {
        "project_id": project.get("project_id"),
        "title": project.get("title"),
        "agency": project.get("agency"),
        "location": project.get("location"),
        "evaluation_status": "skipped_missing_document",
        "harness_ok": None,
        "benchmark_eligible": addenda_complete,
        "benchmark_ineligible": not addenda_complete,
        "addenda_complete": addenda_complete,
        "detected_scope_item_count": 0,
        "trade_coverage": None,
        "scope_keyword_coverage": None,
        "key_quantities": None,
        "document_text_extraction": None,
        "extraction_quality": None,
        "safety": {"ok": True, "violations": []},
        "missed_required_trade": False,
        "accuracy_passed": None,
        "accuracy_failures": [],
        "hard_gate_passed": None,
        "evaluation_passed": None,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Manifest-level evaluation
# ---------------------------------------------------------------------------
def evaluate_manifest(
    manifest: dict[str, Any],
    *,
    manifest_dir: Path,
    workdir: Path,
    allow_missing_documents: bool = False,
    run_harness_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    validate_manifest(manifest, allow_missing_documents=allow_missing_documents, manifest_dir=manifest_dir)
    harness_runner = run_harness_fn or run_harness
    workdir.mkdir(parents=True, exist_ok=True)

    project_results: list[dict[str, Any]] = []
    for index, project in enumerate(manifest["projects"], start=1):
        project_id = str(project.get("project_id"))
        primary = _resolve_primary_document(project, manifest_dir)
        if allow_missing_documents and (primary is None or not primary.exists()):
            project_results.append(_skipped_project_result(project, "document_missing_schema_only"))
            continue
        project_workdir = workdir / f"project_{index:03d}"
        document_text_extraction = extract_document_text(primary)
        report = harness_runner(
            primary,
            project_name=str(project.get("title") or project_id),
            workdir=project_workdir,
            apply_test_inputs=False,
        )
        project_results.append(evaluate_report(project, report, document_text_extraction=document_text_extraction))

    aggregate = build_aggregate(project_results)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workdir": str(workdir.resolve()),
        "internal_testing_only": True,
        "safety": {
            "customer_delivery": False,
            "external_messages": False,
            "final_estimate_approval": False,
            "payments": False,
            "proposal_issue": False,
        },
        "manifest_metadata": manifest.get("metadata", {}),
        "aggregate": aggregate,
        "projects": project_results,
    }


def build_aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [r for r in results if r.get("evaluation_status") == "evaluated"]
    skipped = [r for r in results if r.get("evaluation_status") == "skipped_missing_document"]
    harness_failed = [r for r in results if r.get("evaluation_status") == "harness_failed"]
    safety_violations = [r for r in results if r.get("safety") and not r["safety"].get("ok", True)]
    missed_required = [r for r in evaluated if r.get("missed_required_trade")]
    accuracy_failed = [r for r in evaluated if r.get("accuracy_passed") is False]
    passed = [r for r in evaluated if r.get("evaluation_passed")]

    # Micro-averaged trade recall over evaluated projects.
    total_expected = 0
    total_matched = 0
    total_false_positive = 0
    keyword_total = 0
    keyword_found = 0
    kq_pass = kq_fail = kq_unknown = kq_total = 0
    kq_evidence_pass = kq_evidence_fail = kq_evidence_unknown = 0
    eligible_kq_pass = eligible_kq_fail = eligible_kq_unknown = eligible_kq_total = 0
    eligible_kq_evidence_pass = eligible_kq_evidence_fail = eligible_kq_evidence_unknown = 0
    unexpected_false_positive_total = 0
    text_extraction_pass = text_extraction_fail = 0
    for r in evaluated:
        tc = r.get("trade_coverage") or {}
        total_expected += len(tc.get("expected_trades") or [])
        total_matched += len(tc.get("matched_trades") or [])
        total_false_positive += len(tc.get("false_positive_trades") or [])
        unexpected_false_positive_total += len(tc.get("unexpected_false_positive_trades") or [])
        kc = r.get("scope_keyword_coverage") or {}
        keyword_total += kc.get("expected_keyword_count") or 0
        keyword_found += len(kc.get("found_keywords") or [])
        kq = r.get("key_quantities") or {}
        project_kq_pass = kq.get("pass_count", 0)
        project_kq_fail = kq.get("fail_count", 0)
        project_kq_unknown = kq.get("unknown_count", 0)
        project_kq_total = kq.get("total", 0)
        project_kq_evidence_pass = kq.get("evidence_pass_count", 0)
        project_kq_evidence_fail = kq.get("evidence_fail_count", 0)
        project_kq_evidence_unknown = kq.get("evidence_unknown_count", 0)
        kq_pass += project_kq_pass
        kq_fail += project_kq_fail
        kq_unknown += project_kq_unknown
        kq_total += project_kq_total
        kq_evidence_pass += project_kq_evidence_pass
        kq_evidence_fail += project_kq_evidence_fail
        kq_evidence_unknown += project_kq_evidence_unknown
        if r.get("benchmark_eligible"):
            eligible_kq_pass += project_kq_pass
            eligible_kq_fail += project_kq_fail
            eligible_kq_unknown += project_kq_unknown
            eligible_kq_total += project_kq_total
            eligible_kq_evidence_pass += project_kq_evidence_pass
            eligible_kq_evidence_fail += project_kq_evidence_fail
            eligible_kq_evidence_unknown += project_kq_evidence_unknown
        dte = r.get("document_text_extraction") or {}
        if dte.get("ok"):
            text_extraction_pass += 1
        else:
            text_extraction_fail += 1

    return {
        "project_count": len(results),
        "evaluated_count": len(evaluated),
        "skipped_count": len(skipped),
        "harness_failed_count": len(harness_failed),
        "safety_violation_count": len(safety_violations),
        "benchmark_eligible_count": sum(1 for r in results if r.get("benchmark_eligible")),
        "benchmark_ineligible_count": sum(1 for r in results if r.get("benchmark_ineligible")),
        "evaluated_benchmark_eligible_count": sum(1 for r in evaluated if r.get("benchmark_eligible")),
        "evaluated_benchmark_ineligible_count": sum(1 for r in evaluated if r.get("benchmark_ineligible")),
        "missed_required_trade_project_count": len(missed_required),
        "accuracy_failed_project_count": len(accuracy_failed),
        "evaluation_passed_count": len(passed),
        "trade_recall_micro": round(total_matched / total_expected, 4) if total_expected else None,
        "trade_expected_total": total_expected,
        "trade_matched_total": total_matched,
        "trade_false_positive_total": total_false_positive,
        "trade_unexpected_false_positive_total": unexpected_false_positive_total,
        "scope_keyword_coverage_micro": round(keyword_found / keyword_total, 4) if keyword_total else None,
        "scope_keyword_expected_total": keyword_total,
        "scope_keyword_found_total": keyword_found,
        "key_quantity_pass_count": kq_pass,
        "key_quantity_fail_count": kq_fail,
        "key_quantity_unknown_count": kq_unknown,
        "key_quantity_total": kq_total,
        "key_quantity_evidence_pass_count": kq_evidence_pass,
        "key_quantity_evidence_fail_count": kq_evidence_fail,
        "key_quantity_evidence_unknown_count": kq_evidence_unknown,
        "evaluated_benchmark_eligible_key_quantity_pass_count": eligible_kq_pass,
        "evaluated_benchmark_eligible_key_quantity_fail_count": eligible_kq_fail,
        "evaluated_benchmark_eligible_key_quantity_unknown_count": eligible_kq_unknown,
        "evaluated_benchmark_eligible_key_quantity_total": eligible_kq_total,
        "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": eligible_kq_evidence_pass,
        "evaluated_benchmark_eligible_key_quantity_evidence_fail_count": eligible_kq_evidence_fail,
        "evaluated_benchmark_eligible_key_quantity_evidence_unknown_count": eligible_kq_evidence_unknown,
        "document_text_extraction_pass_count": text_extraction_pass,
        "document_text_extraction_fail_count": text_extraction_fail,
    }


def _nonnegative_int_count(value: Any) -> int | None:
    """Return an exact non-negative integer count, or None for malformed data.

    Release evidence must not accept booleans, fractional floats, numeric strings
    with decimals, negative values, or missing fields as count metrics. Those
    malformed values can otherwise crash the gate or silently truncate.
    """
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    if isinstance(value, str):
        normalized = value.strip()
        if re.fullmatch(r"\d+", normalized):
            return int(normalized)
    return None


def compute_exit_code(
    report: dict[str, Any],
    *,
    fail_on_missed_required_trade: bool,
    fail_on_accuracy: bool = True,
    fail_on_unexpected_false_positive_trade: bool = False,
    fail_on_zero_benchmark_eligible: bool = True,
    require_evaluated_benchmark_eligible: bool = False,
    require_key_quantity_evidence: bool = False,
) -> int:
    """Return a CI/release-gate exit code for an evaluation report.

    Semantics (documented in golden-set-extraction-evaluation.md):

    * Harness failures and safety-lock violations **always** exit ``1``.
    * Any real evaluated run with zero benchmark-eligible projects exits ``1`` by
      default. This prevents a release path from passing on an all-ineligible
      corpus (for example, every project missing complete addenda).
    * Release-gate runs additionally require at least one *evaluated* benchmark-
      eligible project, so schema-only/skipped corpora cannot be promoted.
    * Release-gate runs also require at least one declared key quantity and 100%
      source-evidence pass coverage, preventing a quantityless corpus or
      unverified evidence snippets from being promoted as accuracy evidence.
    * Accuracy failures (an evaluated project with ``accuracy_passed=false`` because
      expected keywords are all missing, a declared key quantity failed, or a declared
      key quantity came back unknown) exit ``1`` by default. ``fail_on_accuracy=False``
      is allowed only for explicitly report-only baseline runs and must not be used
      as release evidence.
    * Release-gate runs treat missed required trades as unsafe even when legacy
      report-only callers leave ``fail_on_missed_required_trade`` unset.
    """
    aggregate = report.get("aggregate", {})
    strict_release_counts = require_evaluated_benchmark_eligible or require_key_quantity_evidence
    strict_count_fields = {
        "harness_failed_count",
        "safety_violation_count",
        "evaluated_count",
        "evaluated_benchmark_eligible_count",
    }
    if fail_on_accuracy:
        strict_count_fields.add("accuracy_failed_project_count")
    if fail_on_missed_required_trade or strict_release_counts:
        strict_count_fields.add("missed_required_trade_project_count")
    if fail_on_unexpected_false_positive_trade:
        strict_count_fields.add("trade_unexpected_false_positive_total")
    if require_key_quantity_evidence:
        strict_count_fields.update(
            {
                "evaluated_benchmark_eligible_key_quantity_total",
                "evaluated_benchmark_eligible_key_quantity_pass_count",
                "evaluated_benchmark_eligible_key_quantity_evidence_pass_count",
            }
        )

    parsed_counts: dict[str, int] = {}
    if strict_release_counts:
        for field in strict_count_fields:
            value = _nonnegative_int_count(aggregate.get(field))
            if value is None:
                return 1
            parsed_counts[field] = value

    def count(field: str, default: int = 0) -> int:
        if field in parsed_counts:
            return parsed_counts[field]
        value = _nonnegative_int_count(aggregate.get(field, default))
        return default if value is None else value

    if count("harness_failed_count"):
        return 1
    if count("safety_violation_count"):
        return 1
    evaluated_count = count("evaluated_count")
    evaluated_eligible_count = count("evaluated_benchmark_eligible_count")
    legacy_or_evaluated_eligible_count = _nonnegative_int_count(
        aggregate.get("evaluated_benchmark_eligible_count", aggregate.get("benchmark_eligible_count", 0))
    )
    if legacy_or_evaluated_eligible_count is None:
        return 1
    if require_evaluated_benchmark_eligible and evaluated_eligible_count == 0:
        return 1
    if fail_on_zero_benchmark_eligible and evaluated_count > 0 and legacy_or_evaluated_eligible_count == 0:
        return 1
    if require_key_quantity_evidence:
        scoped_quantity_fields = (
            "evaluated_benchmark_eligible_key_quantity_total",
            "evaluated_benchmark_eligible_key_quantity_pass_count",
            "evaluated_benchmark_eligible_key_quantity_evidence_pass_count",
        )
        scoped_counts: dict[str, int] = {
            field: count(field) for field in scoped_quantity_fields
        }

        key_quantity_total = scoped_counts["evaluated_benchmark_eligible_key_quantity_total"]
        key_quantity_pass = scoped_counts["evaluated_benchmark_eligible_key_quantity_pass_count"]
        key_quantity_evidence_pass = scoped_counts[
            "evaluated_benchmark_eligible_key_quantity_evidence_pass_count"
        ]
        if (
            key_quantity_total <= 0
            or key_quantity_pass != key_quantity_total
            or key_quantity_evidence_pass != key_quantity_total
        ):
            return 1
    if fail_on_accuracy and count("accuracy_failed_project_count"):
        return 1
    if (fail_on_missed_required_trade or strict_release_counts) and count("missed_required_trade_project_count"):
        return 1
    if fail_on_unexpected_false_positive_trade and count("trade_unexpected_false_positive_total"):
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the local Mobi engine's extraction against a golden-set manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True, help="Path to the golden-set JSON manifest")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the JSON evaluation report")
    parser.add_argument("--workdir", type=Path, default=None, help="Working directory; defaults to a temp dir")
    parser.add_argument(
        "--allow-missing-documents",
        action="store_true",
        help="Validate schema/fixtures without requiring the referenced documents to exist.",
    )
    parser.add_argument(
        "--fail-on-missed-required-trade",
        action="store_true",
        help="Exit nonzero when any evaluated project misses a required trade.",
    )
    parser.add_argument(
        "--fail-on-unexpected-false-positive-trade",
        action="store_true",
        help="Exit nonzero when any detected trade is neither expected nor allowed_extra_trades.",
    )
    parser.add_argument(
        "--no-fail-on-accuracy",
        dest="fail_on_accuracy",
        action="store_false",
        help=(
            "Softer mode: do not exit nonzero on accuracy failures (missing expected "
            "keywords, key-quantity fail, or key-quantity unknown). Requires "
            "--report-only-baseline and must not be used as release evidence."
        ),
    )
    parser.add_argument(
        "--report-only-baseline",
        action="store_true",
        help=(
            "Explicitly mark this run as internal report-only baseline evidence. Required "
            "with --no-fail-on-accuracy; release gates still fail on safety/harness errors "
            "and zero benchmark-eligible evaluated projects."
        ),
    )
    parser.add_argument(
        "--release-gate",
        action="store_true",
        help=(
            "Strict promotion gate: requires real documents, fails on any accuracy failure, "
            "and requires at least one evaluated benchmark-eligible project. This mode "
            "rejects report-only accuracy bypasses."
        ),
    )
    parser.set_defaults(fail_on_accuracy=True)
    args = parser.parse_args(argv)

    if args.release_gate and (args.allow_missing_documents or args.report_only_baseline or args.fail_on_accuracy is False):
        print(
            json.dumps(
                {
                    "error": (
                        "--release-gate requires real evaluated evidence: do not combine it "
                        "with --allow-missing-documents, --report-only-baseline, or "
                        "--no-fail-on-accuracy."
                    )
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    if args.fail_on_accuracy is False and not args.report_only_baseline:
        print(
            json.dumps(
                {
                    "error": (
                        "--no-fail-on-accuracy is report-only and requires "
                        "--report-only-baseline; do not use accuracy bypasses as release evidence."
                    )
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    manifest = load_manifest(args.manifest)
    manifest_dir = args.manifest.resolve().parent
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="mobi-golden-set-"))
    try:
        report = evaluate_manifest(
            manifest,
            manifest_dir=manifest_dir,
            workdir=workdir,
            allow_missing_documents=args.allow_missing_documents,
        )
    except ManifestError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    exit_code = compute_exit_code(
        report,
        fail_on_missed_required_trade=args.fail_on_missed_required_trade,
        fail_on_accuracy=args.fail_on_accuracy,
        fail_on_unexpected_false_positive_trade=args.fail_on_unexpected_false_positive_trade,
        require_evaluated_benchmark_eligible=args.release_gate,
        require_key_quantity_evidence=args.release_gate,
    )
    print(json.dumps({
        "output": str(args.output.resolve()),
        "workdir": str(workdir.resolve()),
        "aggregate": report["aggregate"],
        "exit_code": exit_code,
    }, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
