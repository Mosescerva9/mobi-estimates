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
    assert report["safety"]["customer_delivery"] is False
