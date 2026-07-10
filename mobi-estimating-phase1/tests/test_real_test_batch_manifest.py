"""Real-test batch manifest helper tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_real_test_batch_manifest_init_and_validate_template(tmp_path):
    from scripts import real_test_batch_manifest

    batch_dir = tmp_path / "batch-001"
    created = real_test_batch_manifest.init_batch(batch_dir)

    assert Path(created["manifest"]).exists()
    assert (batch_dir / "pdfs" / ".gitkeep").exists()
    assert (batch_dir / "reports" / ".gitkeep").exists()
    assert (batch_dir / "workdir" / ".gitkeep").exists()

    docs, issues = real_test_batch_manifest.validate_manifest(batch_dir / "manifest.json")
    assert len(docs) == 1
    assert issues == []

    _, runnable_issues = real_test_batch_manifest.validate_manifest(batch_dir / "manifest.json", require_files=True)
    assert any("PDF file not found" in issue for issue in runnable_issues)


def test_real_test_batch_manifest_blocks_private_planroom_sources(tmp_path):
    from scripts import real_test_batch_manifest

    manifest = real_test_batch_manifest.template_manifest()
    manifest["documents"] = [
        {
            "id": "private-source",
            "project_name": "Private Source",
            "local_path": "pdfs/private.pdf",
            "source_url": "https://private-planroom.example/project",
            "source_access": "private_planroom",
            "expected_trades": ["electrical"],
        }
    ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _, issues = real_test_batch_manifest.validate_manifest(manifest_path)

    assert any("blocked for automated tests" in issue for issue in issues)


def test_real_test_batch_manifest_requires_source_audit_trail(tmp_path):
    from scripts import real_test_batch_manifest

    manifest = real_test_batch_manifest.template_manifest()
    manifest["documents"] = [
        {
            "id": "missing-source-trail",
            "project_name": "Missing Source Trail",
            "local_path": "pdfs/missing-source-trail.pdf",
            "source_access": "public",
            "expected_trades": ["electrical"],
        }
    ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _, issues = real_test_batch_manifest.validate_manifest(manifest_path)

    assert any("source_url or source_notes" in issue for issue in issues)


def test_real_test_batch_manifest_rejects_paths_outside_batch_dir(tmp_path):
    from scripts import real_test_batch_manifest

    manifest = real_test_batch_manifest.template_manifest()
    manifest["documents"] = [
        {
            "id": "outside-path",
            "project_name": "Outside Path",
            "local_path": "../outside.pdf",
            "source_url": "https://example.gov/outside.pdf",
            "source_access": "public",
        }
    ]
    manifest_path = tmp_path / "batch-001" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _, issues = real_test_batch_manifest.validate_manifest(manifest_path)

    assert any("inside the batch pdfs/ directory" in issue for issue in issues)


def test_real_test_batch_manifest_rejects_zero_limit(tmp_path):
    from scripts import real_test_batch_manifest

    batch_dir = tmp_path / "batch-001"
    (batch_dir / "pdfs").mkdir(parents=True)
    pdf = batch_dir / "pdfs" / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")
    manifest = real_test_batch_manifest.template_manifest()
    manifest["documents"] = [
        {
            "id": "sample",
            "project_name": "Sample",
            "local_path": "pdfs/sample.pdf",
            "source_url": "https://example.gov/sample.pdf",
            "source_access": "public",
        }
    ]
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        real_test_batch_manifest.run_manifest(manifest_path, limit=0)
    except ValueError as exc:
        assert "limit must be greater than 0" in str(exc)
    else:
        raise AssertionError("run_manifest should reject limit=0")


def test_real_test_batch_manifest_rejects_absolute_and_outside_pdf_paths(tmp_path):
    from scripts import real_test_batch_manifest

    batch_dir = tmp_path / "batch-001"
    (batch_dir / "pdfs").mkdir(parents=True)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4\n%fake\n")
    manifest = real_test_batch_manifest.template_manifest()
    manifest["documents"] = [
        {
            "id": "absolute",
            "local_path": str(outside),
            "source_access": "public",
            "source_notes": "absolute path should be rejected",
        },
        {
            "id": "relative-outside",
            "local_path": "../outside.pdf",
            "source_access": "public",
            "source_notes": "relative path should stay under pdfs/",
        },
    ]
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _, issues = real_test_batch_manifest.validate_manifest(manifest_path, require_files=True)

    assert any("must be relative" in issue for issue in issues)
    assert any("must stay inside the batch pdfs/ directory" in issue for issue in issues)


def test_real_test_batch_manifest_requires_pdf_file_not_directory(tmp_path):
    from scripts import real_test_batch_manifest

    batch_dir = tmp_path / "batch-001"
    (batch_dir / "pdfs" / "folder.pdf").mkdir(parents=True)
    manifest = real_test_batch_manifest.template_manifest()
    manifest["documents"] = [
        {
            "id": "dir-pdf",
            "local_path": "pdfs/folder.pdf",
            "source_access": "public",
            "source_notes": "directory should not count as a PDF file",
        }
    ]
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _, issues = real_test_batch_manifest.validate_manifest(manifest_path, require_files=True)

    assert any("PDF file not found" in issue for issue in issues)


def test_real_test_batch_manifest_run_writes_report_and_review(tmp_path, monkeypatch):
    from scripts import real_test_batch_manifest

    batch_dir = tmp_path / "batch-001"
    (batch_dir / "pdfs").mkdir(parents=True)
    pdf = batch_dir / "pdfs" / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")
    manifest = real_test_batch_manifest.template_manifest()
    manifest["documents"] = [
        {
            "id": "sample",
            "project_name": "Sample",
            "local_path": "pdfs/sample.pdf",
            "source_url": "https://example.gov/sample.pdf",
            "source_access": "public",
            "expected_trades": ["electrical"],
            "expected_document_types": ["drawings"],
        }
    ]
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def fake_run_batch(pdfs, *, workdir, apply_test_inputs=False, stop_on_failure=False, project_names=None):
        assert pdfs == [pdf.resolve()]
        assert project_names == ["Sample"]
        return {
            "generated_at": "2026-07-08T00:00:00+00:00",
            "workdir": str(workdir),
            "safety": {
                "customer_delivery": False,
                "external_messages": False,
                "final_estimate_approval": False,
                "payments": False,
                "test_inputs_only": apply_test_inputs,
            },
            "summary": {
                "pdf_count": 1,
                "ok_count": 1,
                "failed_count": 0,
                "blocked_readiness_count": 1,
                "customer_delivery_ready_count": 0,
                "total_scope_item_count": 2,
                "total_scope_items_with_evidence_quote_count": 1,
                "total_scope_items_missing_evidence_quote_count": 1,
                "avg_evidence_quote_coverage_rate": 0.5,
                "total_quantity_missing_count": 1,
                "total_quantity_traceable_count": 0,
                "total_quantity_test_input_count": 0,
                "total_formula_check_blocked_count": 2,
            },
            "items": [
                {
                    "outputs": {
                        "trade_quality_summary": [{"trade_code": "electrical"}],
                        "quantity_confidence_by_trade": [{"trade_code": "general_trade"}],
                    }
                }
            ],
        }

    monkeypatch.setattr(real_test_batch_manifest, "run_batch", fake_run_batch)
    result = real_test_batch_manifest.run_manifest(manifest_path, apply_test_inputs=True)

    output = Path(result["output"])
    review = Path(result["review"])
    report = json.loads(output.read_text())
    assert output.exists()
    assert review.exists()
    assert report["manifest"]["batch_id"] == "batch-001"
    assert report["manifest"]["documents"][0]["expected_trades"] == ["electrical"]
    coverage = report["manifest"]["expected_trade_coverage"]
    assert coverage["total_expected_trade_count"] == 1
    assert coverage["total_matched_expected_trade_count"] == 1
    assert coverage["total_missing_expected_trade_count"] == 0
    assert coverage["overall_expected_trade_coverage_rate"] == 1.0
    assert coverage["documents"][0]["detected_trade_codes"] == ["electrical", "general_trade"]
    assert coverage["documents"][0]["unexpected_detected_trades"] == ["general_trade"]
    assert coverage["documents"][0]["customer_delivery_ready"] is False
    assert "Mobi Real-Test Batch Review" in review.read_text()
    assert "Expected trade coverage" in review.read_text()


def test_real_test_batch_manifest_cli_validate(tmp_path):
    from scripts import real_test_batch_manifest

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(real_test_batch_manifest.template_manifest()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "real_test_batch_manifest.py"

    proc = subprocess.run(
        [sys.executable, str(script), "validate", str(manifest_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    assert json.loads(proc.stdout)["ok"] is True
