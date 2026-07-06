"""Real document harness tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fitz


def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "ELECTRICAL LIGHTING PLAN\nPANEL SCHEDULE\nLIGHT FIXTURES AND OUTLETS", fontsize=10)
    page.insert_text((480, 744), "E-101", fontsize=11)
    page.insert_text((400, 768), "ELECTRICAL PLAN", fontsize=9)
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "PLUMBING FIXTURE SCHEDULE\nSANITARY WATER GAS LINE", fontsize=10)
    page.insert_text((480, 744), "P-201", fontsize=11)
    page.insert_text((400, 768), "PLUMBING PLAN", fontsize=9)
    doc.save(path)
    doc.close()


def test_real_document_harness_runs_pipeline(tmp_path):
    pdf_path = tmp_path / "sample_bid_set.pdf"
    output_path = tmp_path / "report.json"
    workdir = tmp_path / "harness"
    _make_pdf(pdf_path)

    script = Path(__file__).resolve().parents[1] / "scripts" / "real_document_harness.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            str(pdf_path),
            "--project-name",
            "Harness Test",
            "--workdir",
            str(workdir),
            "--output",
            str(output_path),
            "--apply-test-inputs",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    assert output_path.exists(), proc.stdout + proc.stderr
    report = json.loads(output_path.read_text())
    assert report["project_id"]
    assert report["stages"]["upload"]["ok"] is True
    assert report["stages"]["process"]["ok"] is True
    assert report["stages"]["coverage_draft"]["ok"] is True
    assert report["stages"]["readiness"]["ok"] is True
    assert report["stages"]["readiness"]["body"]["customer_delivery_ready"] is False
    assert report["stages"]["readiness_after_test_inputs"]["ok"] is True
    assert report["stages"]["readiness_after_test_inputs"]["body"]["status"] == "blocked"
    assert report["stages"]["owner_review_after_test_inputs"]["ok"] is True
    assert report["stages"]["owner_review_after_test_inputs"]["body"]["status"] == "blocked"
    assert report["stages"]["owner_review_after_test_inputs"]["body"]["customer_delivery_ready"] is False
    assert report["stages"]["readiness_after_test_inputs"]["body"]["customer_delivery_ready"] is False
    blocker_codes = {
        blocker["code"]
        for blocker in report["stages"]["readiness_after_test_inputs"]["body"]["blockers"]
    }
    assert "missing_extraction_provenance" in blocker_codes
    assert report["safety"]["customer_delivery"] is False
    assert report["safety"]["test_inputs_only"] is True
    assert report["summary"]["stage_count"] >= 10
    assert report["summary"]["failed_stage_count"] == 0
    assert report["summary"]["stage_success_rate"] == 1
    assert report["summary"]["outputs"]["sheet_count"] == 2
    assert report["summary"]["outputs"]["coverage_finding_count"] >= 0
    assert report["summary"]["outputs"]["scope_items_with_trusted_evidence_count"] >= 0
    assert report["summary"]["outputs"]["scope_items_missing_trusted_evidence_count"] >= 0
    assert report["summary"]["outputs"]["low_confidence_item_count"] >= 0
    assert report["summary"]["outputs"]["quantity_basis_unclear_count"] >= 0
    assert report["summary"]["outputs"]["trusted_evidence_coverage_rate"] >= 0
    assert report["summary"]["outputs"]["assumption_count"] >= 0
    assert report["summary"]["outputs"]["exclusion_count"] >= 0
    assert report["summary"]["outputs"]["open_question_count"] >= 0
    assert report["summary"]["outputs"]["register_blocking_entry_count"] >= 0
    assert "coverage_validate" in report["summary"]["per_stage"]
    assert report["summary"]["outputs"]["readiness_status"] == "blocked"
    assert report["summary"]["outputs"]["customer_delivery_ready"] is False
    assert report["summary"]["per_stage"]["process"]["duration_ms"] >= 0


def test_real_document_harness_summary_prefers_post_test_input_stages():
    from scripts import real_document_harness

    report = {
        "stages": {
            "readiness": {"ok": True, "status_code": 200, "body": {"status": "initial", "customer_delivery_ready": True, "details": {}}},
            "owner_review": {"ok": True, "status_code": 200, "body": {"status": "initial", "review_packet": {"assumptions_register": {"summary": {"assumption_count": 1, "exclusion_count": 1, "open_question_count": 1, "blocking_entry_count": 1}}}}},
            "readiness_after_test_inputs": {"ok": True, "status_code": 200, "body": {"status": "after", "customer_delivery_ready": False, "details": {}}},
            "owner_review_after_test_inputs": {"ok": True, "status_code": 200, "body": {"status": "after", "review_packet": {"assumptions_register": {"summary": {"assumption_count": 2, "exclusion_count": 3, "open_question_count": 4, "blocking_entry_count": 5}}}}},
        }
    }

    summary = real_document_harness._build_stage_summary(report)

    assert summary["outputs"]["readiness_status"] == "after"
    assert summary["outputs"]["owner_review_status"] == "after"
    assert summary["outputs"]["customer_delivery_ready"] is False
    assert summary["outputs"]["assumption_count"] == 2
    assert summary["outputs"]["exclusion_count"] == 3
    assert summary["outputs"]["open_question_count"] == 4
    assert summary["outputs"]["register_blocking_entry_count"] == 5
