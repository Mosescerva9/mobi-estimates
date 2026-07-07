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


def score_trade_coverage(expected_trades: list[str], detected: set[str]) -> dict[str, Any]:
    expected = {str(t) for t in expected_trades if t}
    detected_set = {str(t) for t in detected if t}
    matched = sorted(expected & detected_set)
    missed = sorted(expected - detected_set)
    false_positives = sorted(detected_set - expected)
    recall = round(len(matched) / len(expected), 4) if expected else None
    precision = round(len(matched) / len(detected_set), 4) if detected_set else None
    return {
        "expected_trades": sorted(expected),
        "detected_trades": sorted(detected_set),
        "matched_trades": matched,
        "missed_required_trades": missed,
        "false_positive_trades": false_positives,
        "recall": recall,
        "precision": precision,
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


def evaluate_key_quantity(kq: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    label = str(kq.get("label"))
    expected_value = _to_float(kq.get("expected_value"))
    expected_unit = kq.get("unit")
    result: dict[str, Any] = {
        "label": label,
        "expected_value": kq.get("expected_value"),
        "unit": expected_unit,
        "source_ref": kq.get("source_ref"),
        "detected_value": None,
        "detected_unit": None,
        "status": "unknown",
        "reason": None,
    }
    match = _match_scope_item_for_label(label, items)
    if match is None:
        result["reason"] = "no_matching_scope_item"
        return result
    detected_value = _to_float(match.get("quantity"))
    detected_unit = match.get("unit")
    result["detected_value"] = match.get("quantity")
    result["detected_unit"] = detected_unit
    if detected_value is None:
        result["reason"] = "matched_scope_item_has_no_quantity"
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
    result["tolerance"] = round(tolerance, 6)
    if delta <= tolerance:
        result["status"] = "pass"
    else:
        result["status"] = "fail"
        result["reason"] = "outside_tolerance"
    return result


def evaluate_key_quantities(
    key_quantities: list[dict[str, Any]], items: list[dict[str, Any]]
) -> dict[str, Any]:
    results = [evaluate_key_quantity(kq, items) for kq in key_quantities]
    counts = {"pass": 0, "fail": 0, "unknown": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "results": results,
        "pass_count": counts["pass"],
        "fail_count": counts["fail"],
        "unknown_count": counts["unknown"],
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


# ---------------------------------------------------------------------------
# Per-project evaluation
# ---------------------------------------------------------------------------
def evaluate_report(project: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Score a single harness report against a project's golden expectations."""
    items = extract_detected_scope_items(report)
    trade_coverage = score_trade_coverage(project.get("expected_trades") or [], detected_trade_codes(items))
    keyword_coverage = score_scope_keyword_coverage(project.get("expected_scope_keywords") or [], items)
    key_quantities = evaluate_key_quantities(project.get("key_quantities") or [], items)
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
    accuracy_failures: list[str] = []
    if not keyword_full_coverage:
        accuracy_failures.append("expected_keywords_missing")
    if key_quantity_fail:
        accuracy_failures.append("key_quantity_fail")
    if key_quantity_unknown:
        accuracy_failures.append("key_quantity_unknown")
    accuracy_passed = not accuracy_failures

    # Hard gate: harness ran clean, safety locks held, and no required trade was missed.
    hard_gate_passed = harness_ok and safety["ok"] and not missed_required
    evaluation_passed = hard_gate_passed and accuracy_passed

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
        report = harness_runner(
            primary,
            project_name=str(project.get("title") or project_id),
            workdir=project_workdir,
            apply_test_inputs=False,
        )
        project_results.append(evaluate_report(project, report))

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
    for r in evaluated:
        tc = r.get("trade_coverage") or {}
        total_expected += len(tc.get("expected_trades") or [])
        total_matched += len(tc.get("matched_trades") or [])
        total_false_positive += len(tc.get("false_positive_trades") or [])
        kc = r.get("scope_keyword_coverage") or {}
        keyword_total += kc.get("expected_keyword_count") or 0
        keyword_found += len(kc.get("found_keywords") or [])
        kq = r.get("key_quantities") or {}
        kq_pass += kq.get("pass_count", 0)
        kq_fail += kq.get("fail_count", 0)
        kq_unknown += kq.get("unknown_count", 0)
        kq_total += kq.get("total", 0)

    return {
        "project_count": len(results),
        "evaluated_count": len(evaluated),
        "skipped_count": len(skipped),
        "harness_failed_count": len(harness_failed),
        "safety_violation_count": len(safety_violations),
        "benchmark_eligible_count": sum(1 for r in results if r.get("benchmark_eligible")),
        "benchmark_ineligible_count": sum(1 for r in results if r.get("benchmark_ineligible")),
        "missed_required_trade_project_count": len(missed_required),
        "accuracy_failed_project_count": len(accuracy_failed),
        "evaluation_passed_count": len(passed),
        "trade_recall_micro": round(total_matched / total_expected, 4) if total_expected else None,
        "trade_expected_total": total_expected,
        "trade_matched_total": total_matched,
        "trade_false_positive_total": total_false_positive,
        "scope_keyword_coverage_micro": round(keyword_found / keyword_total, 4) if keyword_total else None,
        "scope_keyword_expected_total": keyword_total,
        "scope_keyword_found_total": keyword_found,
        "key_quantity_pass_count": kq_pass,
        "key_quantity_fail_count": kq_fail,
        "key_quantity_unknown_count": kq_unknown,
        "key_quantity_total": kq_total,
    }


def compute_exit_code(
    report: dict[str, Any],
    *,
    fail_on_missed_required_trade: bool,
    fail_on_accuracy: bool = True,
) -> int:
    """Return a CI exit code for an evaluation report.

    Semantics (documented in golden-set-extraction-evaluation.md):

    * Harness failures and safety-lock violations **always** exit ``1``.
    * Accuracy failures (an evaluated project with ``accuracy_passed=false`` because
      expected keywords are all missing, a declared key quantity failed, or a declared
      key quantity came back unknown) exit ``1`` by default. Pass
      ``fail_on_accuracy=False`` (``--no-fail-on-accuracy``) for a softer, report-only
      mode.
    * Missed required trades exit ``1`` only when ``fail_on_missed_required_trade`` is set.
    """
    aggregate = report.get("aggregate", {})
    if aggregate.get("harness_failed_count", 0):
        return 1
    if aggregate.get("safety_violation_count", 0):
        return 1
    if fail_on_accuracy and aggregate.get("accuracy_failed_project_count", 0):
        return 1
    if fail_on_missed_required_trade and aggregate.get("missed_required_trade_project_count", 0):
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
        "--no-fail-on-accuracy",
        dest="fail_on_accuracy",
        action="store_false",
        help=(
            "Softer mode: do not exit nonzero on accuracy failures (missing expected "
            "keywords, key-quantity fail, or key-quantity unknown). Report-only."
        ),
    )
    parser.set_defaults(fail_on_accuracy=True)
    args = parser.parse_args(argv)

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
