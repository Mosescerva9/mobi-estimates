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


def build_batch_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("ok")]
    blocked_rows = [row for row in rows if row.get("readiness_status") == "blocked"]
    delivery_ready_rows = [row for row in rows if row.get("customer_delivery_ready")]
    return {
        "pdf_count": len(rows),
        "ok_count": len(ok_rows),
        "failed_count": len(rows) - len(ok_rows),
        "blocked_readiness_count": len(blocked_rows),
        "customer_delivery_ready_count": len(delivery_ready_rows),
        "total_sheet_count": _sum(rows, "sheet_count"),
        "total_scope_item_count": _sum(rows, "scope_item_count"),
        "total_generic_pricing_scope_item_count": _sum(rows, "generic_pricing_scope_item_count"),
        "total_pricing_method_assigned_count": _sum(rows, "pricing_method_assigned_count"),
        "total_pricing_method_unassigned_count": _sum(rows, "pricing_method_unassigned_count"),
        "total_pricing_ready_scope_item_count": _sum(rows, "pricing_ready_scope_item_count"),
        "total_pricing_not_ready_scope_item_count": _sum(rows, "pricing_not_ready_scope_item_count"),
        "total_priced_scope_item_count": _sum(rows, "priced_scope_item_count"),
        "total_unpriced_scope_item_count": _sum(rows, "unpriced_scope_item_count"),
        "total_generic_estimate_draft_line_item_count": _sum(rows, "generic_estimate_draft_line_item_count"),
        "total_generic_estimate_draft_ready_scope_item_count": _sum(rows, "generic_estimate_draft_ready_scope_item_count"),
        "total_generic_estimate_draft_blocked_scope_item_count": _sum(rows, "generic_estimate_draft_blocked_scope_item_count"),
        "generic_estimate_draft_customer_delivery_ready_count": _count_true(rows, "generic_estimate_draft_customer_delivery_ready"),
        "generic_estimate_draft_final_estimate_approved_count": _count_true(rows, "generic_estimate_draft_final_estimate_approved"),
        "generic_estimate_draft_external_messages_count": _count_true(rows, "generic_estimate_draft_external_messages"),
        "generic_estimate_draft_payments_count": _count_true(rows, "generic_estimate_draft_payments"),
        "total_missing_quantity_pricing_blocker_count": _sum(rows, "missing_quantity_pricing_blocker_count"),
        "total_missing_unit_rate_pricing_blocker_count": _sum(rows, "missing_unit_rate_pricing_blocker_count"),
        "total_missing_subcontract_quote_pricing_blocker_count": _sum(rows, "missing_subcontract_quote_pricing_blocker_count"),
        "total_missing_allowance_basis_pricing_blocker_count": _sum(rows, "missing_allowance_basis_pricing_blocker_count"),
        "total_coverage_finding_count": _sum(rows, "coverage_finding_count"),
        "total_scope_items_missing_trusted_evidence_count": _sum(rows, "scope_items_missing_trusted_evidence_count"),
        "total_low_confidence_item_count": _sum(rows, "low_confidence_item_count"),
        "total_quantity_basis_unclear_count": _sum(rows, "quantity_basis_unclear_count"),
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


def run_batch(
    pdfs: list[Path],
    *,
    workdir: Path,
    apply_test_inputs: bool = False,
    stop_on_failure: bool = False,
) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    reports_dir = workdir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()

    for idx, pdf in enumerate(pdfs, start=1):
        item_workdir = workdir / f"pdf_{idx:03d}"
        try:
            report = run_harness(
                pdf,
                project_name=f"Bid Board Shakeout {idx}: {pdf.stem}",
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
