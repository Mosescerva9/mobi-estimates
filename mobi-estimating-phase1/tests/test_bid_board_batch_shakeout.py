"""Bid-board batch shakeout runner tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fitz


def _make_pdf(path: Path, *, number: str, title: str, body: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), body, fontsize=10)
    page.insert_text((480, 744), number, fontsize=11)
    page.insert_text((400, 768), title, fontsize=9)
    doc.save(path)
    doc.close()


def test_bid_board_batch_shakeout_runs_multiple_pdfs(tmp_path):
    input_dir = tmp_path / "bid_board_pdfs"
    input_dir.mkdir()
    _make_pdf(
        input_dir / "electrical.pdf",
        number="E-101",
        title="ELECTRICAL PLAN",
        body="ELECTRICAL LIGHTING PLAN\nPANEL SCHEDULE\nLIGHT FIXTURES AND OUTLETS",
    )
    _make_pdf(
        input_dir / "plumbing.pdf",
        number="P-201",
        title="PLUMBING PLAN",
        body="PLUMBING FIXTURE SCHEDULE\nSANITARY WATER GAS LINE",
    )
    output = tmp_path / "batch_report.json"
    workdir = tmp_path / "batch_workdir"
    script = Path(__file__).resolve().parents[1] / "scripts" / "bid_board_batch_shakeout.py"

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            str(input_dir),
            "--workdir",
            str(workdir),
            "--output",
            str(output),
            "--apply-test-inputs",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )

    assert output.exists(), proc.stdout + proc.stderr
    report = json.loads(output.read_text())
    assert report["safety"] == {
        "customer_delivery": False,
        "external_messages": False,
        "final_estimate_approval": False,
        "payments": False,
        "test_inputs_only": True,
    }
    assert report["summary"]["pdf_count"] == 2
    assert report["summary"]["ok_count"] == 2
    assert report["summary"]["failed_count"] == 0
    assert report["summary"]["customer_delivery_ready_count"] == 0
    assert report["summary"]["total_sheet_count"] == 2
    assert report["summary"]["document_source_type_counts"]["drawing"] == 2
    assert report["summary"]["sheet_processing_status_counts"]["complete"] == 2
    assert report["summary"]["total_sheet_requires_ocr_count"] >= 0
    assert report["summary"]["total_sheet_requires_review_count"] >= 0
    assert report["summary"]["total_sheet_low_information_text_layer_count"] >= 0
    assert report["summary"]["total_sheet_very_low_information_text_layer_count"] >= 0
    assert report["summary"]["total_sheet_text_detail_missing_count"] == 0
    assert report["summary"]["sheet_text_layer_quality_counts"]
    assert report["summary"]["sheet_recommended_extraction_route_counts"]
    assert report["summary"]["total_table_schedule_extraction_candidate_count"] >= 1
    assert report["summary"]["table_schedule_extraction_candidate_quality_counts"]
    assert report["summary"]["top_table_schedule_extraction_candidates"]
    assert report["summary"]["top_table_schedule_extraction_candidates"][0]["requires_human_review"] is True
    assert report["summary"]["top_table_schedule_extraction_candidates"][0]["final_quantity_extraction"] is False
    assert report["summary"]["min_sheet_text_char_count"] is not None
    assert report["summary"]["avg_sheet_text_char_count"] is not None
    assert report["summary"]["max_sheet_text_char_count"] is not None
    assert report["summary"]["avg_sheet_detection_confidence"] is not None
    assert report["summary"]["top_trade_quality_blockers"]
    assert report["summary"]["total_scope_items_with_evidence_quote_count"] >= 0
    assert report["summary"]["total_scope_items_missing_evidence_quote_count"] >= 0
    assert report["summary"]["total_evidence_quote_count"] >= 0
    assert report["summary"]["avg_evidence_quote_coverage_rate"] is not None
    assert isinstance(report["summary"]["top_evidence_quote_gaps_by_trade"], list)
    assert report["summary"]["total_quantity_present_count"] >= 0
    assert report["summary"]["total_quantity_missing_count"] >= 0
    assert report["summary"]["total_quantity_traceable_count"] >= 0
    assert report["summary"]["total_quantity_test_input_count"] >= 0
    assert report["summary"]["avg_quantity_traceable_rate"] is not None
    assert report["summary"]["top_quantity_confidence_by_trade"]
    assert report["summary"]["total_scope_item_count"] >= 2
    assert report["summary"]["total_generic_pricing_scope_item_count"] > 0
    assert report["summary"]["total_pricing_method_assigned_count"] > 0
    assert report["summary"]["total_pricing_method_unassigned_count"] == 0
    assert report["summary"]["total_pricing_ready_scope_item_count"] >= 0
    assert report["summary"]["total_pricing_not_ready_scope_item_count"] >= 0
    assert report["summary"]["total_priced_scope_item_count"] >= 0
    assert report["summary"]["total_unpriced_scope_item_count"] >= 0
    assert report["summary"]["total_formula_check_scope_item_count"] > 0
    assert (
        report["summary"]["total_formula_check_ready_count"]
        + report["summary"]["total_formula_check_blocked_count"]
        == report["summary"]["total_formula_check_scope_item_count"]
    )
    assert report["summary"]["avg_formula_check_ready_rate"] is not None
    assert "unit_rate_needed" in report["summary"]["formula_check_method_counts"]
    assert isinstance(report["summary"]["formula_check_blocker_counts"], dict)
    assert report["summary"]["top_formula_check_by_trade"]
    assert report["summary"]["total_missing_quantity_pricing_blocker_count"] >= 0
    assert report["summary"]["total_missing_unit_rate_pricing_blocker_count"] >= 0
    assert report["summary"]["total_missing_subcontract_quote_pricing_blocker_count"] >= 0
    assert report["summary"]["total_missing_allowance_basis_pricing_blocker_count"] >= 0
    assert report["summary"]["total_register_blocking_entry_count"] >= 0
    assert report["summary"]["total_clarification_candidate_count"] >= 0
    assert report["summary"]["total_blocking_clarification_candidate_count"] >= 0
    assert report["summary"]["total_customer_safe_clarification_candidate_count"] >= 0
    assert len(report["items"]) == 2
    for row in report["items"]:
        assert row["ok"] is True
        assert row["customer_delivery_ready"] is False
        assert row["report_path"]
        assert Path(row["report_path"]).exists()


def test_bid_board_batch_collect_pdfs_dedupes_and_limits(tmp_path):
    from scripts.bid_board_batch_shakeout import collect_pdfs

    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    txt = tmp_path / "notes.txt"
    pdf_a.write_bytes(b"%PDF-1.4\n%fake\n")
    pdf_b.write_bytes(b"%PDF-1.4\n%fake\n")
    txt.write_text("not a pdf")

    pdfs = collect_pdfs([tmp_path, pdf_a, txt], limit=1)

    assert pdfs == [pdf_a.resolve()]


def test_bid_board_batch_passes_project_names_to_harness(tmp_path, monkeypatch):
    from scripts import bid_board_batch_shakeout

    pdf = tmp_path / "plans.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")
    seen_project_names = []

    def fake_report(pdf, *, project_name, workdir, apply_test_inputs=False):
        seen_project_names.append(project_name)
        return {
            "project_id": "project",
            "workdir": str(workdir),
            "summary": {
                "failed_stage_count": 0,
                "stage_success_rate": 1.0,
                "outputs": {
                    "readiness_status": "blocked",
                    "customer_delivery_ready": False,
                },
            },
        }

    monkeypatch.setattr(bid_board_batch_shakeout, "run_harness", fake_report)

    report = bid_board_batch_shakeout.run_batch(
        [pdf],
        workdir=tmp_path / "work",
        project_names=["Lot 50 Accessibility Upgrades & EVCS - Plans"],
    )

    assert seen_project_names == ["Lot 50 Accessibility Upgrades & EVCS - Plans"]
    assert report["items"][0]["ok"] is True


def test_bid_board_batch_records_failures_without_delivery(tmp_path, monkeypatch):
    from scripts import bid_board_batch_shakeout

    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"not a valid pdf")

    def boom(*args, **kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(bid_board_batch_shakeout, "run_harness", boom)

    report = bid_board_batch_shakeout.run_batch([pdf], workdir=tmp_path / "work")

    assert report["summary"]["pdf_count"] == 1
    assert report["summary"]["failed_count"] == 1
    assert report["summary"]["customer_delivery_ready_count"] == 0
    assert report["items"][0]["ok"] is False
    assert "forced failure" in report["items"][0]["error"]
    assert report["safety"]["customer_delivery"] is False

def test_bid_board_batch_collect_pdfs_includes_uppercase_suffix(tmp_path):
    from scripts.bid_board_batch_shakeout import collect_pdfs

    upper = tmp_path / "BID_SET.PDF"
    lower = tmp_path / "plans.pdf"
    upper.write_bytes(b"%PDF-1.4\n%fake\n")
    lower.write_bytes(b"%PDF-1.4\n%fake\n")

    pdfs = collect_pdfs([tmp_path])

    assert pdfs == sorted([upper.resolve(), lower.resolve()])


def test_bid_board_batch_stop_on_stage_failed_report(tmp_path, monkeypatch):
    from scripts import bid_board_batch_shakeout

    pdfs = [tmp_path / "a.pdf", tmp_path / "b.pdf"]
    for pdf in pdfs:
        pdf.write_bytes(b"%PDF-1.4\n%fake\n")

    calls = []

    def failed_report(pdf, *, project_name, workdir, apply_test_inputs=False):
        calls.append(pdf)
        return {
            "project_id": "project",
            "workdir": str(workdir),
            "summary": {
                "failed_stage_count": 1,
                "stage_success_rate": 0.5,
                "outputs": {
                    "readiness_status": "blocked",
                    "customer_delivery_ready": False,
                    "document_source_type_counts": {"drawing": 1, "spec_or_schedule": 1},
                    "sheet_processing_status_counts": {"complete": 2},
                    "sheet_requires_ocr_count": 1,
                    "sheet_requires_review_count": 1,
                    "sheet_detection_confidence_avg": 0.8,
                    "quantity_present_count": 3,
                    "quantity_missing_count": 1,
                    "quantity_traceable_count": 1,
                    "quantity_unclear_basis_count": 1,
                    "quantity_test_input_count": 1,
                    "open_quantity_requirement_count": 1,
                    "resolved_quantity_requirement_count": 1,
                    "quantity_traceable_rate": 0.25,
                    "quantity_confidence_by_trade": [
                        {"trade_code": "plumbing", "scope_item_count": 2, "quantity_present_count": 2, "quantity_missing_count": 0, "quantity_traceable_count": 0, "quantity_unclear_basis_count": 1, "quantity_test_input_count": 1, "quantity_gap_count": 2},
                        {"trade_code": "electrical", "scope_item_count": 2, "quantity_present_count": 1, "quantity_missing_count": 1, "quantity_traceable_count": 1, "quantity_unclear_basis_count": 0, "quantity_test_input_count": 0, "quantity_gap_count": 1},
                    ],
                    "generic_pricing_scope_item_count": 4,
                    "pricing_method_assigned_count": 3,
                    "pricing_method_unassigned_count": 1,
                    "pricing_ready_scope_item_count": 1,
                    "pricing_not_ready_scope_item_count": 3,
                    "priced_scope_item_count": 1,
                    "unpriced_scope_item_count": 3,
                    "formula_check_scope_item_count": 4,
                    "formula_check_ready_count": 1,
                    "formula_check_blocked_count": 3,
                    "formula_check_ready_rate": 0.25,
                    "formula_check_method_counts": {"unit_rate_needed": 2, "quote_based": 1, "allowance": 1},
                    "formula_check_blocker_counts": {"missing_quantity": 2, "test_quantity_only": 1},
                    "formula_check_by_trade": [
                        {"trade_code": "plumbing", "formula_check_scope_item_count": 2, "formula_check_ready_count": 0, "formula_check_blocked_count": 2, "formula_check_test_input_count": 1},
                        {"trade_code": "electrical", "formula_check_scope_item_count": 2, "formula_check_ready_count": 1, "formula_check_blocked_count": 1, "formula_check_test_input_count": 0},
                    ],
                    "generic_estimate_draft_line_item_count": 1,
                    "generic_estimate_draft_ready_scope_item_count": 1,
                    "generic_estimate_draft_blocked_scope_item_count": 3,
                    "generic_estimate_draft_customer_delivery_ready": False,
                    "generic_estimate_draft_final_estimate_approved": False,
                    "generic_estimate_draft_external_messages": False,
                    "generic_estimate_draft_payments": False,
                    "generic_proposal_preview_scope_line_count": 1,
                    "generic_proposal_preview_blocked_scope_item_count": 3,
                    "generic_proposal_preview_customer_delivery_ready": False,
                    "generic_proposal_preview_final_estimate_approved": False,
                    "generic_proposal_preview_external_messages": False,
                    "generic_proposal_preview_payments": False,
                    "generic_proposal_preview_proposal_created": False,
                    "generic_proposal_preview_proposal_issued": False,
                    "missing_quantity_pricing_blocker_count": 2,
                    "missing_unit_rate_pricing_blocker_count": 1,
                    "missing_subcontract_quote_pricing_blocker_count": 1,
                    "missing_allowance_basis_pricing_blocker_count": 0,
                    "clarification_candidate_count": 2,
                    "blocking_clarification_candidate_count": 1,
                    "critical_clarification_candidate_count": 1,
                    "customer_safe_clarification_candidate_count": 2,
                    "urgent_clarification_candidate_count": 1,
                    "high_clarification_candidate_count": 1,
                    "scope_items_with_evidence_quote_count": 1,
                    "scope_items_missing_evidence_quote_count": 1,
                    "evidence_quote_count": 2,
                    "evidence_human_verification_required_count": 1,
                    "evidence_quote_coverage_rate": 0.5,
                    "evidence_quote_by_trade": [
                        {
                            "trade_code": "electrical",
                            "scope_item_count": 1,
                            "items_with_evidence_quote_count": 1,
                            "items_missing_evidence_quote_count": 0,
                            "evidence_quote_count": 2,
                            "human_verification_required_count": 1,
                        },
                        {
                            "trade_code": "plumbing",
                            "scope_item_count": 1,
                            "items_with_evidence_quote_count": 0,
                            "items_missing_evidence_quote_count": 1,
                            "evidence_quote_count": 0,
                            "human_verification_required_count": 0,
                        },
                    ],
                    "trade_quality_summary": [
                        {
                            "trade_code": "electrical",
                            "scope_item_count": 2,
                            "trusted_evidence_count": 1,
                            "missing_trusted_evidence_count": 1,
                            "low_confidence_item_count": 0,
                            "quantity_basis_unclear_count": 1,
                            "blocking_issue_count": 3,
                            "quality_blocker_count": 5,
                        }
                    ],
                },
            },
        }

    monkeypatch.setattr(bid_board_batch_shakeout, "run_harness", failed_report)

    report = bid_board_batch_shakeout.run_batch(pdfs, workdir=tmp_path / "work", stop_on_failure=True)

    assert len(calls) == 1
    assert report["summary"]["pdf_count"] == 1
    assert report["summary"]["failed_count"] == 1
    assert report["items"][0]["ok"] is False
    assert report["summary"]["customer_delivery_ready_count"] == 0
    assert report["summary"]["document_source_type_counts"] == {"drawing": 1, "spec_or_schedule": 1}
    assert report["summary"]["sheet_processing_status_counts"] == {"complete": 2}
    assert report["summary"]["total_sheet_requires_ocr_count"] == 1
    assert report["summary"]["total_sheet_requires_review_count"] == 1
    assert report["summary"]["avg_sheet_detection_confidence"] == 0.8
    assert report["summary"]["total_quantity_present_count"] == 3
    assert report["summary"]["total_quantity_missing_count"] == 1
    assert report["summary"]["total_quantity_traceable_count"] == 1
    assert report["summary"]["total_quantity_unclear_basis_count"] == 1
    assert report["summary"]["total_quantity_test_input_count"] == 1
    assert report["summary"]["total_open_quantity_requirement_count"] == 1
    assert report["summary"]["total_resolved_quantity_requirement_count"] == 1
    assert report["summary"]["avg_quantity_traceable_rate"] == 0.25
    assert report["summary"]["top_quantity_confidence_by_trade"][0]["trade_code"] == "plumbing"
    assert report["summary"]["top_quantity_confidence_by_trade"][0]["quantity_gap_count"] == 2
    assert report["summary"]["total_generic_pricing_scope_item_count"] == 4
    assert report["summary"]["total_pricing_method_assigned_count"] == 3
    assert report["summary"]["total_pricing_method_unassigned_count"] == 1
    assert report["summary"]["total_pricing_ready_scope_item_count"] == 1
    assert report["summary"]["total_pricing_not_ready_scope_item_count"] == 3
    assert report["summary"]["total_priced_scope_item_count"] == 1
    assert report["summary"]["total_unpriced_scope_item_count"] == 3
    assert report["summary"]["total_formula_check_scope_item_count"] == 4
    assert report["summary"]["total_formula_check_ready_count"] == 1
    assert report["summary"]["total_formula_check_blocked_count"] == 3
    assert report["summary"]["avg_formula_check_ready_rate"] == 0.25
    assert report["summary"]["formula_check_method_counts"] == {"allowance": 1, "quote_based": 1, "unit_rate_needed": 2}
    assert report["summary"]["formula_check_blocker_counts"] == {"missing_quantity": 2, "test_quantity_only": 1}
    assert report["summary"]["top_formula_check_by_trade"][0]["trade_code"] == "plumbing"
    assert report["summary"]["top_formula_check_by_trade"][0]["formula_check_blocked_count"] == 2
    assert report["summary"]["top_formula_check_by_trade"][0]["formula_check_test_input_count"] == 1
    assert report["summary"]["top_formula_check_by_trade"][1]["trade_code"] == "electrical"
    assert report["summary"]["total_generic_estimate_draft_line_item_count"] == 1
    assert report["summary"]["total_generic_estimate_draft_ready_scope_item_count"] == 1
    assert report["summary"]["total_generic_estimate_draft_blocked_scope_item_count"] == 3
    assert report["summary"]["generic_estimate_draft_customer_delivery_ready_count"] == 0
    assert report["summary"]["generic_estimate_draft_final_estimate_approved_count"] == 0
    assert report["summary"]["generic_estimate_draft_external_messages_count"] == 0
    assert report["summary"]["generic_estimate_draft_payments_count"] == 0
    assert report["summary"]["total_generic_proposal_preview_scope_line_count"] == 1
    assert report["summary"]["total_generic_proposal_preview_blocked_scope_item_count"] == 3
    assert report["summary"]["generic_proposal_preview_customer_delivery_ready_count"] == 0
    assert report["summary"]["generic_proposal_preview_final_estimate_approved_count"] == 0
    assert report["summary"]["generic_proposal_preview_external_messages_count"] == 0
    assert report["summary"]["generic_proposal_preview_payments_count"] == 0
    assert report["summary"]["generic_proposal_preview_proposal_created_count"] == 0
    assert report["summary"]["generic_proposal_preview_proposal_issued_count"] == 0
    assert report["summary"]["total_missing_quantity_pricing_blocker_count"] == 2
    assert report["summary"]["total_missing_unit_rate_pricing_blocker_count"] == 1
    assert report["summary"]["total_missing_subcontract_quote_pricing_blocker_count"] == 1
    assert report["summary"]["total_missing_allowance_basis_pricing_blocker_count"] == 0
    assert report["summary"]["total_scope_items_with_evidence_quote_count"] == 1
    assert report["summary"]["total_scope_items_missing_evidence_quote_count"] == 1
    assert report["summary"]["total_evidence_quote_count"] == 2
    assert report["summary"]["total_evidence_human_verification_required_count"] == 1
    assert report["summary"]["avg_evidence_quote_coverage_rate"] == 0.5
    assert report["summary"]["top_evidence_quote_gaps_by_trade"][0]["trade_code"] == "plumbing"
    assert report["summary"]["top_evidence_quote_gaps_by_trade"][0]["items_missing_evidence_quote_count"] == 1
    assert report["summary"]["top_evidence_quote_gaps_by_trade"][1]["trade_code"] == "electrical"
    assert report["summary"]["total_clarification_candidate_count"] == 2
    assert report["summary"]["total_blocking_clarification_candidate_count"] == 1
    assert report["summary"]["total_critical_clarification_candidate_count"] == 1
    assert report["summary"]["total_customer_safe_clarification_candidate_count"] == 2
    assert report["summary"]["total_urgent_clarification_candidate_count"] == 1
    assert report["summary"]["total_high_clarification_candidate_count"] == 1
    assert report["summary"]["top_trade_quality_blockers"][0]["trade_code"] == "electrical"
    assert report["summary"]["top_trade_quality_blockers"][0]["quality_blocker_count"] == 5


def test_bid_board_batch_main_returns_nonzero_when_any_pdf_fails(tmp_path, monkeypatch):
    from scripts import bid_board_batch_shakeout

    pdf = tmp_path / "broken.pdf"
    output = tmp_path / "report.json"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")

    def failed_batch(*args, **kwargs):
        return {
            "summary": {"failed_count": 1, "pdf_count": 1},
            "workdir": str(tmp_path / "work"),
            "safety": {"customer_delivery": False},
            "items": [],
        }

    monkeypatch.setattr(bid_board_batch_shakeout, "run_batch", failed_batch)
    monkeypatch.setattr(sys, "argv", ["bid_board_batch_shakeout.py", str(pdf), "--output", str(output)])

    assert bid_board_batch_shakeout.main() == 1
    assert output.exists()
