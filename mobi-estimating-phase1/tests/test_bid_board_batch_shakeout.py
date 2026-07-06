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
                    "clarification_candidate_count": 2,
                    "blocking_clarification_candidate_count": 1,
                    "critical_clarification_candidate_count": 1,
                    "customer_safe_clarification_candidate_count": 2,
                    "urgent_clarification_candidate_count": 1,
                    "high_clarification_candidate_count": 1,
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
    assert report["summary"]["total_clarification_candidate_count"] == 2
    assert report["summary"]["total_blocking_clarification_candidate_count"] == 1
    assert report["summary"]["total_critical_clarification_candidate_count"] == 1
    assert report["summary"]["total_customer_safe_clarification_candidate_count"] == 2
    assert report["summary"]["total_urgent_clarification_candidate_count"] == 1
    assert report["summary"]["total_high_clarification_candidate_count"] == 1


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
