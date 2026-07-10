#!/usr/bin/env python3
"""Run multiple bid-board PDFs through the local Mobi estimating harness.

This batch runner is for real-data shakeouts before customer-facing release. It
uses the same local FastAPI TestClient harness as ``real_document_harness.py`` and
writes isolated workdirs per PDF. It does not send messages, create customer
deliverables, process payments, or approve/finalize construction estimates.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from scripts.real_document_harness import run_harness  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_pdfs(inputs: list[Path], *, limit: int | None = None) -> list[Path]:
    """Expand files/directories into a deterministic list of PDF paths."""
    pdfs: list[Path] = []
    seen: set[Path] = set()
    for item in inputs:
        if item.is_dir():
            candidates = sorted(
                path for path in item.rglob("*")
                if path.is_file() and path.suffix.lower() == ".pdf"
            )
        elif item.is_file() and item.suffix.lower() == ".pdf":
            candidates = [item]
        else:
            candidates = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            pdfs.append(resolved)
            if limit is not None and len(pdfs) >= limit:
                return pdfs
    return pdfs


def _report_outputs(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("summary", {}).get("outputs", {}) if isinstance(report.get("summary"), dict) else {}


def _report_row(index: int, pdf: Path, report: dict[str, Any] | None, error: str | None = None) -> dict[str, Any]:
    if report is None:
        return {
            "index": index,
            "input_pdf": str(pdf),
            "ok": False,
            "error": error or "Harness failed before producing a report.",
            "project_id": None,
            "workdir": None,
            "readiness_status": None,
            "owner_review_status": None,
            "customer_delivery_ready": False,
            "stage_success_rate": 0,
            "failed_stage_count": None,
            "outputs": {},
        }
    outputs = _report_outputs(report)
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    return {
        "index": index,
        "input_pdf": str(pdf),
        "ok": error is None and summary.get("failed_stage_count", 0) == 0,
        "error": error,
        "project_id": report.get("project_id"),
        "workdir": report.get("workdir"),
        "readiness_status": outputs.get("readiness_status"),
        "owner_review_status": outputs.get("owner_review_status"),
        "customer_delivery_ready": bool(outputs.get("customer_delivery_ready")),
        "stage_success_rate": summary.get("stage_success_rate", 0),
        "failed_stage_count": summary.get("failed_stage_count"),
        "outputs": outputs,
        "beta_flow_dry_run": outputs.get("beta_flow_dry_run") if isinstance(outputs.get("beta_flow_dry_run"), dict) else {},
    }


def _sum(rows: list[dict[str, Any]], key: str) -> int:
    total = 0
    for row in rows:
        value = row.get("outputs", {}).get(key, 0)
        if isinstance(value, int):
            total += value
    return total


def _count_true(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if bool(row.get("outputs", {}).get(key)))


def _merge_count_maps(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    merged: dict[str, int] = {}
    for row in rows:
        values = row.get("outputs", {}).get(key, {})
        if not isinstance(values, dict):
            continue
        for name, count in values.items():
            if isinstance(count, int):
                merged[str(name)] = merged.get(str(name), 0) + count
    return dict(sorted(merged.items()))


def _avg_number(rows: list[dict[str, Any]], key: str) -> float | None:
    values = []
    for row in rows:
        value = row.get("outputs", {}).get(key)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return round(sum(values) / len(values), 4) if values else None


def _aggregate_trade_quality(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _aggregate_trade_rows(rows, "trade_quality_summary", "quality_blocker_count", (
        "scope_item_count",
        "trusted_evidence_count",
        "missing_trusted_evidence_count",
        "low_confidence_item_count",
        "quantity_basis_unclear_count",
        "blocking_issue_count",
        "quality_blocker_count",
    ))


def _aggregate_formula_check(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _aggregate_trade_rows(rows, "formula_check_by_trade", "formula_check_blocked_count", (
        "formula_check_scope_item_count",
        "formula_check_ready_count",
        "formula_check_blocked_count",
        "formula_check_test_input_count",
    ))


def _aggregate_quantity_confidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _aggregate_trade_rows(rows, "quantity_confidence_by_trade", "quantity_gap_count", (
        "scope_item_count",
        "quantity_present_count",
        "quantity_missing_count",
        "quantity_traceable_count",
        "quantity_unclear_basis_count",
        "quantity_test_input_count",
        "quantity_gap_count",
    ))


def _aggregate_quantity_extraction_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _aggregate_trade_rows(rows, "quantity_extraction_candidate_by_trade", "candidate_count", (
        "candidate_count",
        "manual_quantity_input_count",
        "test_quantity_input_count",
    ))


def _aggregate_evidence_quotes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _aggregate_trade_rows(rows, "evidence_quote_by_trade", "items_missing_evidence_quote_count", (
        "scope_item_count",
        "items_with_evidence_quote_count",
        "items_missing_evidence_quote_count",
        "evidence_quote_count",
        "human_verification_required_count",
    ))


def _top_evidence_quote_gap_candidates(rows: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    """Collect review-only source pointers for scope items missing evidence quotes."""
    candidates: list[dict[str, Any]] = []
    for row in rows:
        values = row.get("outputs", {}).get("evidence_quote_gap_candidates") or []
        if not isinstance(values, list):
            continue
        for candidate in values:
            if not isinstance(candidate, dict):
                continue
            candidates.append({
                "input_pdf": row.get("input_pdf"),
                "project_id": row.get("project_id"),
                **candidate,
            })
    candidates.sort(key=lambda candidate: (
        str(candidate.get("trade_code") or ""),
        str(candidate.get("input_pdf") or ""),
        str(candidate.get("scope_item_id") or ""),
    ))
    return candidates[:limit]


def _aggregate_trade_rows(
    rows: list[dict[str, Any]],
    source_key: str,
    sort_key: str,
    numeric_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    by_trade: dict[str, dict[str, Any]] = {}
    for row in rows:
        values = row.get("outputs", {}).get(source_key, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            trade = str(item.get("trade_code") or "unknown")
            target = by_trade.setdefault(trade, {"trade_code": trade, **{key: 0 for key in numeric_keys}})
            for key in numeric_keys:
                value = item.get(key)
                if isinstance(value, int):
                    target[key] += value
    return sorted(by_trade.values(), key=lambda item: (-item.get(sort_key, 0), item["trade_code"]))[:10]


def _batch_beta_flow_dry_run(rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    """Aggregate per-PDF beta flow dry-run status for staff review."""
    flow_rows: list[dict[str, Any]] = []
    for row in rows:
        flow = row.get("beta_flow_dry_run")
        if isinstance(flow, dict):
            flow_rows.append(flow)
    flow_exercised_count = sum(1 for flow in flow_rows if flow.get("flow_exercised") is True)
    safety_clear_count = sum(1 for flow in flow_rows if flow.get("safety_flags_clear") is True)
    status_counts: dict[str, int] = {}
    stage_totals: dict[str, int] = {}
    for flow in flow_rows:
        status = str(flow.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        raw_stages = flow.get("stages")
        stages = raw_stages if isinstance(raw_stages, dict) else {}
        for name, ok in stages.items():
            if ok is True:
                stage_totals[str(name)] = stage_totals.get(str(name), 0) + 1
    safety_violation_count = len(flow_rows) - safety_clear_count
    if not flow_rows or flow_exercised_count < len(rows):
        status = "flow_incomplete"
    elif safety_violation_count:
        status = "safety_violation_blocked"
    elif summary.get("failed_count", 0):
        status = "system_failure_blocked"
    elif summary.get("blocked_readiness_count", 0) or summary.get("total_generic_estimate_draft_blocked_scope_item_count", 0):
        status = "flow_exercised_blocked_before_delivery"
    elif summary.get("total_clarification_candidate_count", 0) or summary.get("total_sheet_requires_review_count", 0):
        status = "flow_exercised_staff_review_required"
    else:
        status = "flow_exercised_ready_for_staff_review"
    return {
        "status": status,
        "pdf_count": len(rows),
        "flow_exercised_count": flow_exercised_count,
        "safety_flags_clear_count": safety_clear_count,
        "safety_violation_count": safety_violation_count,
        "customer_delivery_ready": False,
        "final_estimate_approved": False,
        "external_messages": False,
        "payments": False,
        "stage_success_counts": dict(sorted(stage_totals.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "safe_draft_line_item_count": summary.get("total_generic_estimate_draft_line_item_count", 0),
        "safe_draft_blocked_scope_item_count": summary.get("total_generic_estimate_draft_blocked_scope_item_count", 0),
        "safe_proposal_preview_scope_line_count": summary.get("total_generic_proposal_preview_scope_line_count", 0),
        "safe_proposal_preview_blocked_scope_item_count": summary.get("total_generic_proposal_preview_blocked_scope_item_count", 0),
    }


def _batch_automation_review_package(summary: dict[str, Any]) -> dict[str, Any]:
    """Build a staff-ready batch review package from aggregate harness metrics."""
    failed_count = summary.get("failed_count", 0) if isinstance(summary.get("failed_count"), int) else 0
    blocked_readiness_count = summary.get("blocked_readiness_count", 0) if isinstance(summary.get("blocked_readiness_count"), int) else 0
    human_review_count = sum(
        count for count in (
            summary.get("total_sheet_requires_ocr_count", 0),
            summary.get("total_sheet_requires_review_count", 0),
            summary.get("total_table_schedule_extraction_candidate_count", 0),
            summary.get("total_quantity_extraction_candidate_count", 0),
            summary.get("total_evidence_human_verification_required_count", 0),
            summary.get("total_clarification_candidate_count", 0),
        )
        if isinstance(count, int)
    )
    blocked_count = sum(
        count for count in (
            failed_count,
            blocked_readiness_count,
            summary.get("total_pricing_not_ready_scope_item_count", 0),
            summary.get("total_formula_check_blocked_count", 0),
            summary.get("total_quantity_missing_count", 0),
            summary.get("total_quantity_unclear_basis_count", 0),
            summary.get("total_open_quantity_requirement_count", 0),
            summary.get("total_generic_estimate_draft_blocked_scope_item_count", 0),
            summary.get("total_register_blocking_entry_count", 0),
        )
        if isinstance(count, int)
    )
    if failed_count:
        status = "system_failure_blocked"
    elif blocked_count:
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
            "pdf_count": summary.get("pdf_count", 0),
            "processed_ok_count": summary.get("ok_count", 0),
            "scope_item_count": summary.get("total_scope_item_count", 0),
            "evidence_quote_count": summary.get("total_evidence_quote_count", 0),
            "generic_estimate_draft_line_item_count": summary.get("total_generic_estimate_draft_line_item_count", 0),
        },
        "human_review_needed": {
            "sheet_requires_ocr_count": summary.get("total_sheet_requires_ocr_count", 0),
            "sheet_requires_review_count": summary.get("total_sheet_requires_review_count", 0),
            "table_schedule_extraction_candidate_count": summary.get("total_table_schedule_extraction_candidate_count", 0),
            "quantity_extraction_candidate_count": summary.get("total_quantity_extraction_candidate_count", 0),
            "evidence_human_verification_required_count": summary.get("total_evidence_human_verification_required_count", 0),
            "clarification_candidate_count": summary.get("total_clarification_candidate_count", 0),
        },
        "blocked": {
            "failed_pdf_count": failed_count,
            "blocked_readiness_count": blocked_readiness_count,
            "pricing_not_ready_scope_item_count": summary.get("total_pricing_not_ready_scope_item_count", 0),
            "formula_check_blocked_count": summary.get("total_formula_check_blocked_count", 0),
            "quantity_missing_count": summary.get("total_quantity_missing_count", 0),
            "quantity_unclear_basis_count": summary.get("total_quantity_unclear_basis_count", 0),
            "open_quantity_requirement_count": summary.get("total_open_quantity_requirement_count", 0),
            "generic_estimate_draft_blocked_scope_item_count": summary.get("total_generic_estimate_draft_blocked_scope_item_count", 0),
            "register_blocking_entry_count": summary.get("total_register_blocking_entry_count", 0),
        },
        "top_followups": {
            "table_schedule_candidates": summary.get("top_table_schedule_extraction_candidates", []),
            "quantity_extraction_candidates": summary.get("top_quantity_extraction_candidates", []),
            "quantity_gaps_by_trade": summary.get("top_quantity_confidence_by_trade", []),
            "pricing_formula_blockers_by_trade": summary.get("top_formula_check_by_trade", []),
            "evidence_quote_gaps_by_trade": summary.get("top_evidence_quote_gaps_by_trade", []),
            "evidence_quote_gap_candidates": summary.get("top_evidence_quote_gap_candidates", []),
            "trade_quality_blockers": summary.get("top_trade_quality_blockers", []),
        },
    }


def build_batch_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("ok")]
    blocked_rows = [row for row in rows if row.get("readiness_status") == "blocked"]
    delivery_ready_rows = [row for row in rows if row.get("customer_delivery_ready")]
    summary = {
        "pdf_count": len(rows),
        "ok_count": len(ok_rows),
        "failed_count": len(rows) - len(ok_rows),
        "blocked_readiness_count": len(blocked_rows),
        "customer_delivery_ready_count": len(delivery_ready_rows),
        "total_sheet_count": _sum(rows, "sheet_count"),
        "document_source_type_counts": _merge_count_maps(rows, "document_source_type_counts"),
        "sheet_processing_status_counts": _merge_count_maps(rows, "sheet_processing_status_counts"),
        "total_sheet_requires_ocr_count": _sum(rows, "sheet_requires_ocr_count"),
        "total_sheet_requires_review_count": _sum(rows, "sheet_requires_review_count"),
        "total_sheet_low_information_text_layer_count": _sum(rows, "sheet_low_information_text_layer_count"),
        "total_sheet_very_low_information_text_layer_count": _sum(rows, "sheet_very_low_information_text_layer_count"),
        "total_sheet_text_detail_missing_count": _sum(rows, "sheet_text_detail_missing_count"),
        "sheet_text_layer_quality_counts": _merge_count_maps(rows, "sheet_text_layer_quality_counts"),
        "sheet_recommended_extraction_route_counts": _merge_count_maps(rows, "sheet_recommended_extraction_route_counts"),
        "total_table_schedule_extraction_candidate_count": _sum(rows, "table_schedule_extraction_candidate_count"),
        "table_schedule_extraction_candidate_quality_counts": _merge_count_maps(rows, "table_schedule_extraction_candidate_quality_counts"),
        "top_table_schedule_extraction_candidates": [
            candidate
            for row in rows
            for candidate in (row.get("outputs", {}).get("table_schedule_extraction_candidates") or [])
            if isinstance(candidate, dict)
        ][:20],
        "min_sheet_text_char_count": min(
            (row.get("outputs", {}).get("sheet_text_char_count_min") for row in rows
             if isinstance(row.get("outputs", {}).get("sheet_text_char_count_min"), int)),
            default=None,
        ),
        "avg_sheet_text_char_count": _avg_number(rows, "sheet_text_char_count_avg"),
        "max_sheet_text_char_count": max(
            (row.get("outputs", {}).get("sheet_text_char_count_max") for row in rows
             if isinstance(row.get("outputs", {}).get("sheet_text_char_count_max"), int)),
            default=None,
        ),
        "avg_sheet_detection_confidence": _avg_number(rows, "sheet_detection_confidence_avg"),
        "total_scope_item_count": _sum(rows, "scope_item_count"),
        "total_generic_pricing_scope_item_count": _sum(rows, "generic_pricing_scope_item_count"),
        "total_pricing_method_assigned_count": _sum(rows, "pricing_method_assigned_count"),
        "total_pricing_method_unassigned_count": _sum(rows, "pricing_method_unassigned_count"),
        "total_pricing_ready_scope_item_count": _sum(rows, "pricing_ready_scope_item_count"),
        "total_pricing_not_ready_scope_item_count": _sum(rows, "pricing_not_ready_scope_item_count"),
        "total_priced_scope_item_count": _sum(rows, "priced_scope_item_count"),
        "total_unpriced_scope_item_count": _sum(rows, "unpriced_scope_item_count"),
        "total_formula_check_scope_item_count": _sum(rows, "formula_check_scope_item_count"),
        "total_formula_check_ready_count": _sum(rows, "formula_check_ready_count"),
        "total_formula_check_blocked_count": _sum(rows, "formula_check_blocked_count"),
        "avg_formula_check_ready_rate": _avg_number(rows, "formula_check_ready_rate"),
        "formula_check_method_counts": _merge_count_maps(rows, "formula_check_method_counts"),
        "formula_check_blocker_counts": _merge_count_maps(rows, "formula_check_blocker_counts"),
        "top_formula_check_by_trade": _aggregate_formula_check(rows),
        "total_generic_estimate_draft_line_item_count": _sum(rows, "generic_estimate_draft_line_item_count"),
        "total_generic_estimate_draft_ready_scope_item_count": _sum(rows, "generic_estimate_draft_ready_scope_item_count"),
        "total_generic_estimate_draft_blocked_scope_item_count": _sum(rows, "generic_estimate_draft_blocked_scope_item_count"),
        "generic_estimate_draft_customer_delivery_ready_count": _count_true(rows, "generic_estimate_draft_customer_delivery_ready"),
        "generic_estimate_draft_final_estimate_approved_count": _count_true(rows, "generic_estimate_draft_final_estimate_approved"),
        "generic_estimate_draft_external_messages_count": _count_true(rows, "generic_estimate_draft_external_messages"),
        "generic_estimate_draft_payments_count": _count_true(rows, "generic_estimate_draft_payments"),
        "total_generic_proposal_preview_scope_line_count": _sum(rows, "generic_proposal_preview_scope_line_count"),
        "total_generic_proposal_preview_blocked_scope_item_count": _sum(rows, "generic_proposal_preview_blocked_scope_item_count"),
        "generic_proposal_preview_customer_delivery_ready_count": _count_true(rows, "generic_proposal_preview_customer_delivery_ready"),
        "generic_proposal_preview_final_estimate_approved_count": _count_true(rows, "generic_proposal_preview_final_estimate_approved"),
        "generic_proposal_preview_external_messages_count": _count_true(rows, "generic_proposal_preview_external_messages"),
        "generic_proposal_preview_payments_count": _count_true(rows, "generic_proposal_preview_payments"),
        "generic_proposal_preview_proposal_created_count": _count_true(rows, "generic_proposal_preview_proposal_created"),
        "generic_proposal_preview_proposal_issued_count": _count_true(rows, "generic_proposal_preview_proposal_issued"),
        "total_missing_quantity_pricing_blocker_count": _sum(rows, "missing_quantity_pricing_blocker_count"),
        "total_missing_unit_rate_pricing_blocker_count": _sum(rows, "missing_unit_rate_pricing_blocker_count"),
        "total_missing_subcontract_quote_pricing_blocker_count": _sum(rows, "missing_subcontract_quote_pricing_blocker_count"),
        "total_missing_allowance_basis_pricing_blocker_count": _sum(rows, "missing_allowance_basis_pricing_blocker_count"),
        "total_coverage_finding_count": _sum(rows, "coverage_finding_count"),
        "total_scope_items_missing_trusted_evidence_count": _sum(rows, "scope_items_missing_trusted_evidence_count"),
        "total_scope_items_with_evidence_quote_count": _sum(rows, "scope_items_with_evidence_quote_count"),
        "total_scope_items_missing_evidence_quote_count": _sum(rows, "scope_items_missing_evidence_quote_count"),
        "total_evidence_quote_count": _sum(rows, "evidence_quote_count"),
        "total_evidence_human_verification_required_count": _sum(rows, "evidence_human_verification_required_count"),
        "avg_evidence_quote_coverage_rate": _avg_number(rows, "evidence_quote_coverage_rate"),
        "top_evidence_quote_gaps_by_trade": _aggregate_evidence_quotes(rows),
        "top_evidence_quote_gap_candidates": _top_evidence_quote_gap_candidates(rows),
        "total_low_confidence_item_count": _sum(rows, "low_confidence_item_count"),
        "total_quantity_basis_unclear_count": _sum(rows, "quantity_basis_unclear_count"),
        "total_quantity_present_count": _sum(rows, "quantity_present_count"),
        "total_quantity_missing_count": _sum(rows, "quantity_missing_count"),
        "total_quantity_traceable_count": _sum(rows, "quantity_traceable_count"),
        "total_quantity_unclear_basis_count": _sum(rows, "quantity_unclear_basis_count"),
        "total_quantity_test_input_count": _sum(rows, "quantity_test_input_count"),
        "total_open_quantity_requirement_count": _sum(rows, "open_quantity_requirement_count"),
        "total_resolved_quantity_requirement_count": _sum(rows, "resolved_quantity_requirement_count"),
        "avg_quantity_traceable_rate": _avg_number(rows, "quantity_traceable_rate"),
        "top_quantity_confidence_by_trade": _aggregate_quantity_confidence(rows),
        "total_quantity_extraction_candidate_count": _sum(rows, "quantity_extraction_candidate_count"),
        "total_repeated_low_information_table_schedule_candidate_count": _sum(
            rows, "repeated_low_information_table_schedule_candidate_count"
        ),
        "total_manual_quantity_input_count": _sum(rows, "manual_quantity_input_count"),
        "total_quantity_extraction_test_input_count": _sum(rows, "quantity_extraction_test_input_count"),
        "top_quantity_extraction_candidates": [
            candidate
            for row in rows
            for candidate in (row.get("outputs", {}).get("quantity_extraction_candidates") or [])
            if isinstance(candidate, dict)
        ][:20],
        "top_quantity_extraction_candidate_by_trade": _aggregate_quantity_extraction_candidates(rows),
        "top_trade_quality_blockers": _aggregate_trade_quality(rows),
        "total_assumption_count": _sum(rows, "assumption_count"),
        "total_exclusion_count": _sum(rows, "exclusion_count"),
        "total_open_question_count": _sum(rows, "open_question_count"),
        "total_register_blocking_entry_count": _sum(rows, "register_blocking_entry_count"),
        "total_clarification_candidate_count": _sum(rows, "clarification_candidate_count"),
        "total_blocking_clarification_candidate_count": _sum(rows, "blocking_clarification_candidate_count"),
        "total_critical_clarification_candidate_count": _sum(rows, "critical_clarification_candidate_count"),
        "total_customer_safe_clarification_candidate_count": _sum(rows, "customer_safe_clarification_candidate_count"),
        "total_urgent_clarification_candidate_count": _sum(rows, "urgent_clarification_candidate_count"),
        "total_high_clarification_candidate_count": _sum(rows, "high_clarification_candidate_count"),
    }
    summary["automation_review_package"] = _batch_automation_review_package(summary)
    summary["beta_flow_dry_run"] = _batch_beta_flow_dry_run(rows, summary)
    return summary


def run_batch(
    pdfs: list[Path],
    *,
    workdir: Path,
    apply_test_inputs: bool = False,
    stop_on_failure: bool = False,
    project_names: list[str | None] | None = None,
) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    reports_dir = workdir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()

    for idx, pdf in enumerate(pdfs, start=1):
        item_workdir = workdir / f"pdf_{idx:03d}"
        project_name = None
        if project_names and idx <= len(project_names):
            project_name = project_names[idx - 1]
        project_name = str(project_name).strip() if project_name else f"Bid Board Shakeout {idx}: {pdf.stem}"
        try:
            report = run_harness(
                pdf,
                project_name=project_name,
                workdir=item_workdir,
                apply_test_inputs=apply_test_inputs,
            )
            report_path = reports_dir / f"pdf_{idx:03d}_report.json"
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            row = _report_row(idx, pdf, report)
            row["report_path"] = str(report_path.resolve())
            rows.append(row)
            if stop_on_failure and not row["ok"]:
                break
        except Exception as exc:  # pragma: no cover - defensive for real-data shakeouts
            row = _report_row(idx, pdf, None, error=f"{type(exc).__name__}: {exc}")
            rows.append(row)
            if stop_on_failure:
                break

    return {
        "generated_at": _now(),
        "workdir": str(workdir.resolve()),
        "safety": {
            "customer_delivery": False,
            "external_messages": False,
            "final_estimate_approval": False,
            "payments": False,
            "test_inputs_only": apply_test_inputs,
        },
        "duration_ms": int((time.perf_counter() - start) * 1000),
        "summary": build_batch_summary(rows),
        "items": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Mobi harness against a batch of bid-board PDFs.")
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF files or directories containing PDFs")
    parser.add_argument("--workdir", type=Path, default=None, help="Batch working directory; defaults to a temp dir")
    parser.add_argument("--output", type=Path, default=None, help="Aggregate JSON report path")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of PDFs to process")
    parser.add_argument("--apply-test-inputs", action="store_true", help="Apply fictional local quantity/pricing inputs per PDF")
    parser.add_argument("--stop-on-failure", action="store_true", help="Stop processing after first failed PDF")
    args = parser.parse_args()

    pdfs = collect_pdfs(args.inputs, limit=args.limit)
    if not pdfs:
        raise SystemExit("No PDF files found in provided inputs.")
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="mobi-bid-board-batch-"))
    report = run_batch(
        pdfs,
        workdir=workdir,
        apply_test_inputs=args.apply_test_inputs,
        stop_on_failure=args.stop_on_failure,
    )
    output = args.output or (workdir / "bid_board_batch_shakeout_report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "output": str(output.resolve()),
        "workdir": str(workdir.resolve()),
        "summary": report["summary"],
    }, indent=2, sort_keys=True))
    return 1 if report["summary"].get("failed_count", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
