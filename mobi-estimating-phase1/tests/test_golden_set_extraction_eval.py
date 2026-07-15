"""Golden Set v1 extraction evaluation harness tests.

These tests avoid needing real PDFs by driving the pure scoring helpers directly
and by monkeypatching ``run_harness`` with synthetic harness reports.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import golden_set_extraction_eval as gse


# ---------------------------------------------------------------------------
# Helpers to build fixtures
# ---------------------------------------------------------------------------
def _scope_item(trade_code, description, *, quantity=None, unit=None, location=None):
    return {
        "trade_code": trade_code,
        "category_code": "generic_scope",
        "description": description,
        "location": location,
        "quantity": quantity,
        "unit": unit,
        "quantity_basis": "takeoff" if quantity is not None else None,
    }


def _harness_report(scope_items, *, failed_stage_count=0, safety=None, outputs=None):
    return {
        "project_id": "engine-project-id",
        "workdir": "/tmp/example",
        "safety": safety
        or {
            "customer_delivery": False,
            "external_messages": False,
            "final_estimate_approval": False,
            "payments": False,
        },
        "stages": {"scope_items": {"ok": True, "body": {"items": scope_items}}},
        "summary": {
            "failed_stage_count": failed_stage_count,
            "outputs": outputs or {},
        },
    }


def _base_project(**overrides):
    project = {
        "project_id": "p1",
        "title": "Test Project",
        "agency": "Agency",
        "location": "City, ST",
        "document_paths": ["plans.pdf"],
        "addenda_complete": True,
        "expected_trades": ["painting", "demo_concrete"],
        "expected_scope_keywords": ["paint", "concrete"],
        "internal_testing_only": True,
    }
    project.update(overrides)
    return project


def _manifest(projects):
    return {
        "metadata": {"internal_testing_only": True, "source_authorization": "public"},
        "projects": projects,
    }


def test_extract_document_text_fails_closed_on_empty_pdftotext_output(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="   \n\t", stderr="")

    monkeypatch.setattr(gse.subprocess, "run", fake_run)
    result = gse.extract_document_text(tmp_path / "plans.pdf")

    assert result == {
        "ok": False,
        "text": "",
        "char_count": 0,
        "extraction_method": "pdftotext",
        "reason": "pdftotext_empty_text",
    }


def _run_cli_with_stubbed_report(monkeypatch, tmp_path, *args):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest([_base_project()])), encoding="utf-8")
    output_path = tmp_path / "report.json"

    def fake_evaluate_manifest(*_args, **_kwargs):
        return {
            "generated_at": "2026-07-13T00:00:00+00:00",
            "workdir": str(tmp_path / "work"),
            "aggregate": {
                "evaluated_count": 0,
                "skipped_count": 0,
                "harness_failed_count": 0,
                "safety_violation_count": 0,
                "missed_required_trade_project_count": 0,
                "accuracy_failed_project_count": 0,
                "trade_unexpected_false_positive_total": 0,
            },
            "projects": [],
        }

    monkeypatch.setattr(gse, "evaluate_manifest", fake_evaluate_manifest)
    exit_code = gse.main([
        "--manifest",
        str(manifest_path),
        "--output",
        str(output_path),
        "--workdir",
        str(tmp_path / "work"),
        *args,
    ])
    return exit_code, json.loads(output_path.read_text(encoding="utf-8"))


def test_cli_stamps_release_gate_run_mode(monkeypatch, tmp_path):
    exit_code, report = _run_cli_with_stubbed_report(monkeypatch, tmp_path, "--release-gate")

    assert exit_code == 1
    assert report["run_mode"] == {
        "release_gate": True,
        "fail_on_accuracy": True,
        "report_only_baseline": False,
        "allow_missing_documents": False,
    }


def test_cli_stamps_report_only_baseline_run_mode(monkeypatch, tmp_path):
    exit_code, report = _run_cli_with_stubbed_report(
        monkeypatch,
        tmp_path,
        "--allow-missing-documents",
        "--no-fail-on-accuracy",
        "--report-only-baseline",
    )

    assert exit_code == 0
    assert report["run_mode"] == {
        "release_gate": False,
        "fail_on_accuracy": False,
        "report_only_baseline": True,
        "allow_missing_documents": True,
    }
# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

def test_validate_manifest_rejects_missing_required_field(tmp_path):
    project = _base_project()
    del project["expected_trades"]
    with pytest.raises(gse.ManifestError, match="expected_trades"):
        gse.validate_manifest(
            _manifest([project]), allow_missing_documents=True, manifest_dir=tmp_path
        )


def test_validate_manifest_rejects_missing_internal_testing_metadata(tmp_path):
    manifest = {
        "metadata": {"source_authorization": "public"},
        "projects": [_base_project()],
    }
    with pytest.raises(gse.ManifestError, match="internal_testing_only"):
        gse.validate_manifest(manifest, allow_missing_documents=True, manifest_dir=tmp_path)


def test_validate_manifest_rejects_bad_source_authorization(tmp_path):
    manifest = {
        "metadata": {"internal_testing_only": True, "source_authorization": "scraped"},
        "projects": [_base_project()],
    }
    with pytest.raises(gse.ManifestError, match="source_authorization"):
        gse.validate_manifest(manifest, allow_missing_documents=True, manifest_dir=tmp_path)


def test_validate_manifest_rejects_missing_documents_unless_allowed(tmp_path):
    manifest = _manifest([_base_project()])
    with pytest.raises(gse.ManifestError, match="primary document not found"):
        gse.validate_manifest(manifest, allow_missing_documents=False, manifest_dir=tmp_path)
    # With allow_missing_documents it validates fine.
    gse.validate_manifest(manifest, allow_missing_documents=True, manifest_dir=tmp_path)


def test_validate_manifest_accepts_present_document(tmp_path):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")
    manifest = _manifest([_base_project()])
    gse.validate_manifest(manifest, allow_missing_documents=False, manifest_dir=tmp_path)


def test_validate_manifest_rejects_key_quantity_without_tolerance(tmp_path):
    project = _base_project(
        key_quantities=[{"label": "slab", "expected_value": 100, "unit": "SF"}]
    )
    with pytest.raises(gse.ManifestError, match="tolerance"):
        gse.validate_manifest(
            _manifest([project]), allow_missing_documents=True, manifest_dir=tmp_path
        )


def test_validate_manifest_rejects_nonnumeric_tolerance(tmp_path):
    project = _base_project(
        key_quantities=[
            {"label": "slab", "expected_value": 100, "unit": "SF", "tolerance_pct": "loose"}
        ]
    )
    with pytest.raises(gse.ManifestError, match="tolerance_pct must be numeric"):
        gse.validate_manifest(
            _manifest([project]), allow_missing_documents=True, manifest_dir=tmp_path
        )


def test_validate_manifest_rejects_negative_tolerance(tmp_path):
    project = _base_project(
        key_quantities=[
            {"label": "slab", "expected_value": 100, "unit": "SF", "tolerance_abs": -5}
        ]
    )
    with pytest.raises(gse.ManifestError, match="tolerance_abs must not be negative"):
        gse.validate_manifest(
            _manifest([project]), allow_missing_documents=True, manifest_dir=tmp_path
        )


def test_validate_manifest_rejects_populated_outcome_paths(tmp_path):
    project = _base_project(outcome_paths=["outcomes/award.json"])
    with pytest.raises(gse.ManifestError, match="outcome_paths must be empty"):
        gse.validate_manifest(
            _manifest([project]), allow_missing_documents=True, manifest_dir=tmp_path
        )


def test_validate_manifest_accepts_empty_outcome_paths(tmp_path):
    project = _base_project(outcome_paths=[])
    gse.validate_manifest(
        _manifest([project]), allow_missing_documents=True, manifest_dir=tmp_path
    )


# ---------------------------------------------------------------------------
# Trade coverage scoring
# ---------------------------------------------------------------------------
def test_trade_coverage_recall_precision_and_missed():
    result = gse.score_trade_coverage(
        ["painting", "demo_concrete", "general_trade"],
        {"painting", "demo_concrete", "unexpected_trade"},
    )
    assert result["matched_trades"] == ["demo_concrete", "painting"]
    assert result["missed_required_trades"] == ["general_trade"]
    assert result["false_positive_trades"] == ["unexpected_trade"]
    assert result["recall"] == round(2 / 3, 4)
    assert result["precision"] == round(2 / 3, 4)


def test_trade_coverage_reports_missing_required_trade():
    result = gse.score_trade_coverage(["painting"], {"demo_concrete"})
    assert result["missed_required_trades"] == ["painting"]
    assert result["recall"] == 0.0


def test_trade_coverage_reports_false_positive_trade():
    result = gse.score_trade_coverage(["painting"], {"painting", "electrical"})
    assert result["false_positive_trades"] == ["electrical"]
    assert result["missed_required_trades"] == []


# ---------------------------------------------------------------------------
# Scope keyword coverage
# ---------------------------------------------------------------------------
def test_scope_keyword_coverage_found_and_missing():
    items = [
        _scope_item("painting", "Paint interior walls, two coats"),
        _scope_item("demo_concrete", "Demolish and remove concrete sidewalk"),
    ]
    result = gse.score_scope_keyword_coverage(["paint", "concrete", "roofing"], items)
    assert result["found_keywords"] == ["paint", "concrete"]
    assert result["missing_keywords"] == ["roofing"]
    assert result["coverage"] == round(2 / 3, 4)


# ---------------------------------------------------------------------------
# Key quantity tolerance behavior
# ---------------------------------------------------------------------------
def test_key_quantity_pass_within_tolerance():
    items = [_scope_item("demo_concrete", "Sidewalk concrete flatwork", quantity=1250, unit="SF")]
    kq = {"label": "sidewalk concrete", "expected_value": 1200, "unit": "SF", "tolerance_pct": 10}
    result = gse.evaluate_key_quantity(kq, items)
    assert result["status"] == "pass"
    assert result["detected_value"] == 1250


def test_key_quantity_fail_outside_tolerance():
    items = [_scope_item("demo_concrete", "Sidewalk concrete flatwork", quantity=2000, unit="SF")]
    kq = {"label": "sidewalk concrete", "expected_value": 1200, "unit": "SF", "tolerance_abs": 50}
    result = gse.evaluate_key_quantity(kq, items)
    assert result["status"] == "fail"
    assert result["reason"] == "outside_tolerance"


def test_key_quantity_unknown_when_no_match():
    items = [_scope_item("painting", "Paint walls", quantity=100, unit="SF")]
    kq = {"label": "sidewalk concrete", "expected_value": 1200, "unit": "SF", "tolerance_pct": 10}
    result = gse.evaluate_key_quantity(kq, items)
    assert result["status"] == "unknown"
    assert result["reason"] == "no_matching_scope_item"


def test_key_quantity_unknown_when_no_quantity():
    items = [_scope_item("demo_concrete", "Sidewalk concrete flatwork", quantity=None, unit="SF")]
    kq = {"label": "sidewalk concrete", "expected_value": 1200, "unit": "SF", "tolerance_pct": 10}
    result = gse.evaluate_key_quantity(kq, items)
    assert result["status"] == "unknown"
    assert result["reason"] == "matched_scope_item_has_no_quantity"


def test_key_quantity_unit_mismatch_is_unknown():
    items = [_scope_item("demo_concrete", "Sidewalk concrete flatwork", quantity=1200, unit="CY")]
    kq = {"label": "sidewalk concrete", "expected_value": 1200, "unit": "SF", "tolerance_pct": 10}
    result = gse.evaluate_key_quantity(kq, items)
    assert result["status"] == "unknown"
    assert result["reason"] == "unit_mismatch"


def test_key_quantity_negative_tolerance_does_not_coerce_to_pass():
    items = [_scope_item("demo_concrete", "Sidewalk concrete flatwork", quantity=2000, unit="SF")]
    kq = {"label": "sidewalk concrete", "expected_value": 1200, "unit": "SF", "tolerance_abs": -50}
    result = gse.evaluate_key_quantity(kq, items)
    assert result["status"] != "pass"
    assert result["reason"] == "invalid_tolerance"


# ---------------------------------------------------------------------------
# Per-report evaluation: addenda, safety
# ---------------------------------------------------------------------------
def test_addenda_incomplete_makes_benchmark_ineligible():
    report = _harness_report([_scope_item("painting", "Paint walls")])
    project = _base_project(addenda_complete=False, expected_trades=["painting"], expected_scope_keywords=[])
    result = gse.evaluate_report(project, report)
    assert result["benchmark_ineligible"] is True
    assert result["benchmark_eligible"] is False
    assert "addenda_incomplete_benchmark_ineligible" in result["warnings"]
    # Extraction eval still runs and can pass.
    assert result["evaluation_passed"] is True


def test_safety_flag_true_fails_evaluation():
    report = _harness_report(
        [_scope_item("painting", "Paint walls")],
        outputs={"generic_proposal_preview_proposal_issued": True},
    )
    project = _base_project(expected_trades=["painting"], expected_scope_keywords=[])
    result = gse.evaluate_report(project, report)
    assert result["safety"]["ok"] is False
    assert "outputs.generic_proposal_preview_proposal_issued" in result["safety"]["violations"]
    assert result["evaluation_passed"] is False


def test_proposal_created_safety_flag_fails_evaluation():
    report = _harness_report(
        [_scope_item("painting", "Paint walls")],
        outputs={"generic_proposal_preview_proposal_created": True},
    )
    project = _base_project(expected_trades=["painting"], expected_scope_keywords=[])
    result = gse.evaluate_report(project, report)
    assert result["safety"]["ok"] is False
    assert "outputs.generic_proposal_preview_proposal_created" in result["safety"]["violations"]
    assert result["evaluation_passed"] is False


def test_top_level_proposal_issue_safety_flag_fails_evaluation():
    report = _harness_report(
        [_scope_item("painting", "Paint walls")],
        safety={
            "customer_delivery": False,
            "external_messages": False,
            "final_estimate_approval": False,
            "payments": False,
            "proposal_issue": True,
        },
    )
    project = _base_project(expected_trades=["painting"], expected_scope_keywords=[])
    result = gse.evaluate_report(project, report)
    assert result["safety"]["ok"] is False
    assert "safety.proposal_issue" in result["safety"]["violations"]
    assert result["evaluation_passed"] is False


def test_missing_expected_keywords_fails_accuracy_and_evaluation():
    # Trades all detected and safe, but the only expected keyword is absent.
    report = _harness_report([_scope_item("painting", "Generic wall work")])
    project = _base_project(expected_trades=["painting"], expected_scope_keywords=["roofing"])
    result = gse.evaluate_report(project, report)
    assert result["scope_keyword_coverage"]["missing_keywords"] == ["roofing"]
    assert result["accuracy_passed"] is False
    assert "expected_keywords_missing" in result["accuracy_failures"]
    assert result["hard_gate_passed"] is True
    assert result["evaluation_passed"] is False


def test_key_quantity_fail_fails_accuracy_and_evaluation():
    report = _harness_report(
        [_scope_item("demo_concrete", "Sidewalk concrete flatwork", quantity=5000, unit="SF")]
    )
    project = _base_project(
        expected_trades=["demo_concrete"],
        expected_scope_keywords=[],
        key_quantities=[
            {"label": "sidewalk concrete", "expected_value": 1200, "unit": "SF", "tolerance_pct": 5}
        ],
    )
    result = gse.evaluate_report(project, report)
    assert result["key_quantities"]["fail_count"] == 1
    assert result["accuracy_passed"] is False
    assert "key_quantity_fail" in result["accuracy_failures"]
    assert result["evaluation_passed"] is False


def test_declared_key_quantity_unknown_fails_accuracy_and_evaluation():
    # Declared key quantity has no matching scope item -> unknown -> accuracy fail.
    report = _harness_report(
        [_scope_item("demo_concrete", "Curb and gutter", quantity=100, unit="LF")]
    )
    project = _base_project(
        expected_trades=["demo_concrete"],
        expected_scope_keywords=[],
        key_quantities=[
            {"label": "sidewalk concrete", "expected_value": 1200, "unit": "SF", "tolerance_pct": 5}
        ],
    )
    result = gse.evaluate_report(project, report)
    assert result["key_quantities"]["unknown_count"] == 1
    assert result["accuracy_passed"] is False
    assert "key_quantity_unknown" in result["accuracy_failures"]
    assert result["evaluation_passed"] is False


def test_missed_required_trade_fails_evaluation_by_default():
    report = _harness_report([_scope_item("painting", "Paint walls")])
    project = _base_project(expected_trades=["painting", "demo_concrete"], expected_scope_keywords=[])
    result = gse.evaluate_report(project, report)
    assert result["missed_required_trade"] is True
    assert result["trade_coverage"]["missed_required_trades"] == ["demo_concrete"]
    assert result["evaluation_passed"] is False


def test_harness_failure_marks_evaluation_failed():
    report = _harness_report([_scope_item("painting", "Paint walls")], failed_stage_count=2)
    project = _base_project(expected_trades=["painting"], expected_scope_keywords=[])
    result = gse.evaluate_report(project, report)
    assert result["harness_ok"] is False
    assert result["evaluation_status"] == "harness_failed"
    assert result["evaluation_passed"] is False


# ---------------------------------------------------------------------------
# evaluate_manifest + aggregate + exit codes (monkeypatched harness)
# ---------------------------------------------------------------------------
def test_evaluate_manifest_with_monkeypatched_harness(tmp_path, monkeypatch):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")

    def fake_run_harness(pdf, *, project_name, workdir, apply_test_inputs=False):
        return _harness_report(
            [
                _scope_item("painting", "Paint interior walls", quantity=500, unit="SF"),
                _scope_item("demo_concrete", "Concrete sidewalk demolition", quantity=1200, unit="SF"),
            ]
        )

    monkeypatch.setattr(gse, "run_harness", fake_run_harness)

    project = _base_project(
        key_quantities=[
            {"label": "concrete sidewalk", "expected_value": 1200, "unit": "SF", "tolerance_pct": 5}
        ]
    )
    report = gse.evaluate_manifest(
        _manifest([project]), manifest_dir=tmp_path, workdir=tmp_path / "work"
    )
    agg = report["aggregate"]
    assert agg["evaluated_count"] == 1
    assert agg["harness_failed_count"] == 0
    assert agg["safety_violation_count"] == 0
    assert agg["missed_required_trade_project_count"] == 0
    assert agg["trade_recall_micro"] == 1.0
    assert agg["scope_keyword_coverage_micro"] == 1.0
    assert agg["key_quantity_pass_count"] == 1
    assert report["projects"][0]["evaluation_passed"] is True
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=True) == 0


def test_evaluate_manifest_allow_missing_documents_skips(tmp_path):
    report = gse.evaluate_manifest(
        _manifest([_base_project()]),
        manifest_dir=tmp_path,
        workdir=tmp_path / "work",
        allow_missing_documents=True,
    )
    assert report["aggregate"]["skipped_count"] == 1
    assert report["aggregate"]["evaluated_count"] == 0
    assert report["projects"][0]["evaluation_status"] == "skipped_missing_document"
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=True) == 0


def test_exit_code_nonzero_on_missed_trade_when_flag_set(tmp_path, monkeypatch):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")

    def fake_run_harness(pdf, *, project_name, workdir, apply_test_inputs=False):
        return _harness_report([_scope_item("painting", "Paint walls")])

    monkeypatch.setattr(gse, "run_harness", fake_run_harness)
    project = _base_project(expected_trades=["painting", "demo_concrete"], expected_scope_keywords=[])
    report = gse.evaluate_manifest(
        _manifest([project]), manifest_dir=tmp_path, workdir=tmp_path / "work"
    )
    assert report["aggregate"]["missed_required_trade_project_count"] == 1
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=False) == 0
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=True) == 1


def test_exit_code_nonzero_on_safety_violation(tmp_path, monkeypatch):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")

    def fake_run_harness(pdf, *, project_name, workdir, apply_test_inputs=False):
        return _harness_report(
            [_scope_item("painting", "Paint walls")],
            outputs={"customer_delivery_ready": True},
        )

    monkeypatch.setattr(gse, "run_harness", fake_run_harness)
    project = _base_project(expected_trades=["painting"], expected_scope_keywords=[])
    report = gse.evaluate_manifest(
        _manifest([project]), manifest_dir=tmp_path, workdir=tmp_path / "work"
    )
    assert report["aggregate"]["safety_violation_count"] == 1
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=False) == 1


def test_exit_code_nonzero_on_proposal_created_safety_violation(tmp_path, monkeypatch):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")

    def fake_run_harness(pdf, *, project_name, workdir, apply_test_inputs=False):
        return _harness_report(
            [_scope_item("painting", "Paint walls")],
            outputs={"generic_proposal_preview_proposal_created": True},
        )

    monkeypatch.setattr(gse, "run_harness", fake_run_harness)
    project = _base_project(expected_trades=["painting"], expected_scope_keywords=[])
    report = gse.evaluate_manifest(
        _manifest([project]), manifest_dir=tmp_path, workdir=tmp_path / "work"
    )
    assert report["aggregate"]["safety_violation_count"] == 1
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=False) == 1


def test_exit_code_nonzero_on_accuracy_failure_by_default(tmp_path, monkeypatch):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")

    def fake_run_harness(pdf, *, project_name, workdir, apply_test_inputs=False):
        # Trade detected, safe, but expected keyword absent and key quantity fails.
        return _harness_report(
            [_scope_item("demo_concrete", "Curb and gutter", quantity=9999, unit="SF")]
        )

    monkeypatch.setattr(gse, "run_harness", fake_run_harness)
    project = _base_project(
        expected_trades=["demo_concrete"],
        expected_scope_keywords=["sidewalk"],
        key_quantities=[
            {"label": "curb and gutter", "expected_value": 100, "unit": "SF", "tolerance_pct": 5}
        ],
    )
    report = gse.evaluate_manifest(
        _manifest([project]), manifest_dir=tmp_path, workdir=tmp_path / "work"
    )
    assert report["aggregate"]["accuracy_failed_project_count"] == 1
    assert report["projects"][0]["evaluation_passed"] is False
    # Default mode fails CI on accuracy failures.
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=False) == 1
    # Softer mode reports but does not fail when the run is still benchmark-eligible.
    assert (
        gse.compute_exit_code(
            report, fail_on_missed_required_trade=False, fail_on_accuracy=False
        )
        == 0
    )


def test_exit_code_nonzero_when_evaluated_run_has_zero_benchmark_eligible_projects(tmp_path, monkeypatch):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")

    def fake_run_harness(pdf, *, project_name, workdir, apply_test_inputs=False):
        return _harness_report([_scope_item("painting", "Paint walls")])

    monkeypatch.setattr(gse, "run_harness", fake_run_harness)
    project = _base_project(
        addenda_complete=False,
        expected_trades=["painting"],
        expected_scope_keywords=[],
    )
    report = gse.evaluate_manifest(
        _manifest([project]), manifest_dir=tmp_path, workdir=tmp_path / "work"
    )
    assert report["aggregate"]["evaluated_count"] == 1
    assert report["aggregate"]["benchmark_eligible_count"] == 0
    assert report["aggregate"]["evaluated_benchmark_eligible_count"] == 0
    assert report["projects"][0]["evaluation_passed"] is True
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=False) == 1
    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            fail_on_accuracy=False,
        )
        == 1
    )


def test_zero_eligible_gate_ignores_skipped_schema_only_projects(tmp_path, monkeypatch):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")

    def fake_run_harness(pdf, *, project_name, workdir, apply_test_inputs=False):
        return _harness_report([_scope_item("painting", "Paint walls")])

    monkeypatch.setattr(gse, "run_harness", fake_run_harness)
    evaluated_ineligible = _base_project(
        project_id="evaluated-ineligible",
        document_paths=["plans.pdf"],
        addenda_complete=False,
        expected_trades=["painting"],
        expected_scope_keywords=[],
    )
    skipped_eligible = _base_project(
        project_id="skipped-eligible",
        document_paths=["missing.pdf"],
        addenda_complete=True,
        expected_trades=["painting"],
        expected_scope_keywords=[],
    )
    report = gse.evaluate_manifest(
        _manifest([evaluated_ineligible, skipped_eligible]),
        manifest_dir=tmp_path,
        workdir=tmp_path / "work",
        allow_missing_documents=True,
    )
    assert report["aggregate"]["evaluated_count"] == 1
    assert report["aggregate"]["skipped_count"] == 1
    assert report["aggregate"]["benchmark_eligible_count"] == 1
    assert report["aggregate"]["evaluated_benchmark_eligible_count"] == 0
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=False) == 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_dry_run_with_allow_missing_documents(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest([_base_project()])), encoding="utf-8")
    output = tmp_path / "report.json"

    exit_code = gse.main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--workdir",
            str(tmp_path / "work"),
            "--allow-missing-documents",
        ]
    )
    assert exit_code == 0
    assert output.exists()
    report = json.loads(output.read_text())
    assert report["internal_testing_only"] is True
    assert report["safety"] == {
        "customer_delivery": False,
        "external_messages": False,
        "final_estimate_approval": False,
        "payments": False,
        "proposal_issue": False,
    }
    assert report["aggregate"]["skipped_count"] == 1


def test_cli_returns_2_on_invalid_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    bad = {"metadata": {"source_authorization": "public"}, "projects": [_base_project()]}
    manifest_path.write_text(json.dumps(bad), encoding="utf-8")
    output = tmp_path / "report.json"

    exit_code = gse.main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--workdir",
            str(tmp_path / "work"),
            "--allow-missing-documents",
        ]
    )
    assert exit_code == 2
    assert not output.exists()


def test_cli_rejects_accuracy_bypass_without_report_only_baseline(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest([_base_project()])), encoding="utf-8")
    output = tmp_path / "report.json"

    exit_code = gse.main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--workdir",
            str(tmp_path / "work"),
            "--allow-missing-documents",
            "--no-fail-on-accuracy",
        ]
    )
    assert exit_code == 2
    assert not output.exists()


def test_cli_allows_explicit_report_only_accuracy_bypass_for_schema_dry_run(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest([_base_project()])), encoding="utf-8")
    output = tmp_path / "report.json"

    exit_code = gse.main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--workdir",
            str(tmp_path / "work"),
            "--allow-missing-documents",
            "--no-fail-on-accuracy",
            "--report-only-baseline",
        ]
    )
    assert exit_code == 0
    assert output.exists()


def test_cli_release_gate_rejects_report_only_accuracy_bypass(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest([_base_project()])), encoding="utf-8")
    output = tmp_path / "report.json"

    exit_code = gse.main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--workdir",
            str(tmp_path / "work"),
            "--release-gate",
            "--no-fail-on-accuracy",
            "--report-only-baseline",
        ]
    )
    assert exit_code == 2
    assert not output.exists()


def test_cli_release_gate_rejects_schema_only_missing_document_mode(tmp_path):
    """Release evidence must not pass through the schema-only fixture path.

    The audit P0 release gate requires real evaluated projects. This regression
    test proves the CLI rejects ``--release-gate`` combined with
    ``--allow-missing-documents`` even when no accuracy-bypass flag is supplied.
    """
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest([_base_project()])), encoding="utf-8")
    output = tmp_path / "report.json"

    exit_code = gse.main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--workdir",
            str(tmp_path / "work"),
            "--release-gate",
            "--allow-missing-documents",
        ]
    )

    assert exit_code == 2
    assert not output.exists()


def test_release_gate_fails_schema_only_zero_evaluated_eligible_projects(tmp_path):
    report = {
        "aggregate": {
            "evaluated_count": 0,
            "evaluated_benchmark_eligible_count": 0,
            "harness_failed_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 0,
            "missed_required_trade_project_count": 0,
            "trade_unexpected_false_positive_total": 0,
        }
    }

    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
        )
        == 1
    )


def test_release_gate_fails_impossible_evaluated_eligible_counts():
    """Release evidence cannot claim more eligible projects than were evaluated."""
    report = {
        "aggregate": {
            "project_count": 1,
            "evaluated_count": 0,
            "skipped_count": 0,
            "benchmark_eligible_count": 1,
            "benchmark_ineligible_count": 0,
            "evaluated_benchmark_eligible_count": 1,
            "evaluated_benchmark_ineligible_count": 0,
            "harness_failed_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 0,
            "missed_required_trade_project_count": 0,
            "trade_unexpected_false_positive_total": 0,
            "evaluated_benchmark_eligible_key_quantity_total": 1,
            "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
        }
    }

    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_fails_inconsistent_project_and_eligibility_counts():
    """Release evidence must be internally consistent, not just non-zero."""
    aggregate = {
        "project_count": 2,
        "evaluated_count": 1,
        "evaluation_passed_count": 1,
        "skipped_count": 0,
        "harness_failed_count": 0,
        "benchmark_eligible_count": 1,
        "benchmark_ineligible_count": 1,
        "evaluated_benchmark_eligible_count": 1,
        "evaluated_benchmark_ineligible_count": 0,
        "safety_violation_count": 0,
        "accuracy_failed_project_count": 0,
        "missed_required_trade_project_count": 0,
        "trade_unexpected_false_positive_total": 0,
        "evaluated_benchmark_eligible_key_quantity_total": 1,
        "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
    }

    assert (
        gse.compute_exit_code(
            {"aggregate": aggregate},
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )

    aggregate["skipped_count"] = 1
    assert (
        gse.compute_exit_code(
            {"aggregate": aggregate},
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 0
    )

    aggregate["benchmark_eligible_count"] = 0
    aggregate["benchmark_ineligible_count"] = 2
    assert (
        gse.compute_exit_code(
            {"aggregate": aggregate},
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_fails_quantityless_benchmark_even_when_trade_scope_passes(tmp_path, monkeypatch):
    (tmp_path / "plans.pdf").write_bytes(b"%PDF-1.4\n")

    def fake_run_harness(pdf, *, project_name, workdir, apply_test_inputs=False):
        return _harness_report([_scope_item("painting", "Paint walls")])

    monkeypatch.setattr(gse, "run_harness", fake_run_harness)
    project = _base_project(
        addenda_complete=True,
        expected_trades=["painting"],
        expected_scope_keywords=["paint"],
        key_quantities=[],
    )
    report = gse.evaluate_manifest(
        _manifest([project]), manifest_dir=tmp_path, workdir=tmp_path / "work"
    )

    assert report["aggregate"]["evaluated_benchmark_eligible_count"] == 1
    assert report["aggregate"]["key_quantity_total"] == 0
    # Normal internal evaluation can still report a pass for trade/scope-only evidence.
    assert gse.compute_exit_code(report, fail_on_missed_required_trade=False) == 0
    # Release evidence must include source-backed measured quantity checks.
    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_fails_key_quantities_without_full_source_evidence_or_quantity_pass():
    report = {
        "aggregate": {
            "project_count": 1,
            "evaluated_count": 1,
            "evaluation_passed_count": 1,
            "skipped_count": 0,
            "harness_failed_count": 0,
            "benchmark_eligible_count": 1,
            "benchmark_ineligible_count": 0,
            "evaluated_benchmark_eligible_count": 1,
            "evaluated_benchmark_ineligible_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 0,
            "missed_required_trade_project_count": 0,
            "trade_unexpected_false_positive_total": 0,
            "key_quantity_total": 2,
            "key_quantity_pass_count": 2,
            "key_quantity_evidence_pass_count": 2,
            "evaluated_benchmark_eligible_key_quantity_total": 2,
            "evaluated_benchmark_eligible_key_quantity_pass_count": 2,
            "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
        }
    }

    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )

    report["aggregate"]["evaluated_benchmark_eligible_key_quantity_evidence_pass_count"] = 2
    report["aggregate"]["evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count"] = 2
    report["aggregate"]["evaluated_benchmark_eligible_key_quantity_pass_count"] = 1
    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )

    report["aggregate"]["evaluated_benchmark_eligible_key_quantity_pass_count"] = 2
    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 0
    )


def test_release_gate_rejects_legacy_global_key_quantity_counters_only():
    report = {
        "aggregate": {
            "evaluated_count": 1,
            "evaluated_benchmark_eligible_count": 1,
            "harness_failed_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 0,
            "missed_required_trade_project_count": 0,
            "trade_unexpected_false_positive_total": 0,
            "key_quantity_total": 2,
            "key_quantity_pass_count": 2,
            "key_quantity_evidence_pass_count": 2,
        }
    }

    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_fails_textless_evaluated_benchmark_eligible_project():
    report = {
        "aggregate": {
            "evaluated_count": 1,
            "evaluated_benchmark_eligible_count": 1,
            "harness_failed_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 0,
            "missed_required_trade_project_count": 0,
            "trade_unexpected_false_positive_total": 0,
            "evaluated_benchmark_eligible_key_quantity_total": 1,
            "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_pass_count": 0,
            "evaluated_benchmark_eligible_document_text_extraction_fail_count": 1,
        }
    }

    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_fails_missed_required_trades_without_extra_flag():
    report = {
        "aggregate": {
            "evaluated_count": 1,
            "evaluated_benchmark_eligible_count": 1,
            "harness_failed_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 0,
            "missed_required_trade_project_count": 1,
            "trade_unexpected_false_positive_total": 0,
            "evaluated_benchmark_eligible_key_quantity_total": 1,
            "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
        }
    }

    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_fails_unexpected_false_positive_trades_without_extra_flag():
    """Strict release evidence must not pass with unsupported trade detections.

    Report-only evaluations can still choose whether to fail unexpected trade false
    positives, but the P0 release gate is an abstention gate: every detected trade
    must be expected or explicitly allowlisted for the benchmark stratum.
    """
    report = {
        "aggregate": {
            "evaluated_count": 1,
            "evaluated_benchmark_eligible_count": 1,
            "harness_failed_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 0,
            "missed_required_trade_project_count": 0,
            "trade_unexpected_false_positive_total": 1,
            "evaluated_benchmark_eligible_key_quantity_total": 1,
            "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
        }
    }

    assert gse.compute_exit_code(report, fail_on_missed_required_trade=False) == 0
    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("evaluated_benchmark_eligible_key_quantity_total", None),
        ("evaluated_benchmark_eligible_key_quantity_pass_count", "not-a-number"),
        ("evaluated_benchmark_eligible_key_quantity_pass_count", "1.0"),
        ("evaluated_benchmark_eligible_key_quantity_evidence_pass_count", True),
        ("evaluated_benchmark_eligible_key_quantity_evidence_pass_count", 1.5),
        ("evaluated_benchmark_eligible_key_quantity_evidence_pass_count", -1),
        ("evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count", None),
        ("evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count", False),
        ("evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count", "1.0"),
    ],
)
def test_release_gate_rejects_missing_or_invalid_scoped_key_quantity_counters(field, bad_value):
    aggregate = {
        "evaluated_count": 1,
        "evaluated_benchmark_eligible_count": 1,
        "harness_failed_count": 0,
        "safety_violation_count": 0,
        "accuracy_failed_project_count": 0,
        "missed_required_trade_project_count": 0,
        "trade_unexpected_false_positive_total": 0,
        "evaluated_benchmark_eligible_key_quantity_total": 1,
        "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
    }
    aggregate[field] = bad_value

    assert (
        gse.compute_exit_code(
            {"aggregate": aggregate},
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_rejects_missing_or_invalid_core_count_fields():
    aggregate = {
        "evaluated_count": 1,
        "evaluated_benchmark_eligible_count": 1,
        "harness_failed_count": 0,
        "safety_violation_count": 0,
        "accuracy_failed_project_count": 0,
        "missed_required_trade_project_count": 0,
        "trade_unexpected_false_positive_total": 0,
        "evaluated_benchmark_eligible_key_quantity_total": 1,
        "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
    }
    for field, bad_value in (
        ("evaluated_count", "not-a-number"),
        ("evaluated_count", -1),
        ("evaluated_benchmark_eligible_count", True),
        ("evaluated_benchmark_eligible_count", 1.5),
        ("evaluated_benchmark_eligible_count", "1.0"),
        ("harness_failed_count", False),
        ("safety_violation_count", None),
        ("accuracy_failed_project_count", False),
        ("evaluation_passed_count", None),
        ("evaluation_passed_count", False),
    ):
        malformed = {**aggregate, field: bad_value}
        assert (
            gse.compute_exit_code(
                {"aggregate": malformed},
                fail_on_missed_required_trade=False,
                require_evaluated_benchmark_eligible=True,
                require_key_quantity_evidence=True,
            )
            == 1
        ), field


def test_release_gate_fails_if_evaluation_passed_count_does_not_match_evaluated_count():
    """Strict release evidence cannot pass when evaluated projects failed internally.

    Accuracy/count fields may all look green in a stale or mocked report, but the
    evaluator's explicit evaluation_passed_count is the canonical all-projects
    success counter. Require it to equal evaluated_count before promotion.
    """
    aggregate = {
        "project_count": 1,
        "evaluated_count": 1,
        "evaluation_passed_count": 0,
        "skipped_count": 0,
        "harness_failed_count": 0,
        "safety_violation_count": 0,
        "benchmark_eligible_count": 1,
        "benchmark_ineligible_count": 0,
        "evaluated_benchmark_eligible_count": 1,
        "evaluated_benchmark_ineligible_count": 0,
        "accuracy_failed_project_count": 0,
        "missed_required_trade_project_count": 0,
        "trade_unexpected_false_positive_total": 0,
        "evaluated_benchmark_eligible_key_quantity_total": 1,
        "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
    }

    assert (
        gse.compute_exit_code(
            {"aggregate": aggregate},
            fail_on_missed_required_trade=False,
            fail_on_accuracy=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_scopes_quantity_evidence_to_evaluated_benchmark_eligible_projects():
    eligible_without_quantity = {
        "evaluation_status": "evaluated",
        "benchmark_eligible": True,
        "key_quantities": {
            "total": 1,
            "pass_count": 0,
            "fail_count": 0,
            "unknown_count": 1,
            "evidence_pass_count": 0,
            "evidence_fail_count": 0,
            "evidence_unknown_count": 1,
        },
    }
    ineligible_with_passing_quantity = {
        "evaluation_status": "evaluated",
        "benchmark_eligible": False,
        "benchmark_ineligible": True,
        "key_quantities": {
            "total": 1,
            "pass_count": 1,
            "fail_count": 0,
            "unknown_count": 0,
            "evidence_pass_count": 1,
            "evidence_fail_count": 0,
            "evidence_unknown_count": 0,
        },
    }
    aggregate = gse.build_aggregate([eligible_without_quantity, ineligible_with_passing_quantity])
    report = {"aggregate": aggregate}

    assert aggregate["evaluated_benchmark_eligible_count"] == 1
    assert aggregate["key_quantity_total"] == 2
    assert aggregate["key_quantity_pass_count"] == 1
    assert aggregate["key_quantity_evidence_pass_count"] == 1
    assert aggregate["evaluated_benchmark_eligible_key_quantity_total"] == 1
    assert aggregate["evaluated_benchmark_eligible_key_quantity_pass_count"] == 0
    assert aggregate["evaluated_benchmark_eligible_key_quantity_evidence_pass_count"] == 0
    assert aggregate["evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count"] == 0
    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_example_manifest_validates_with_allow_missing_documents():
    manifest_path = (
        Path(__file__).resolve().parents[1] / "data" / "golden_set" / "manifest.example.json"
    )
    manifest = gse.load_manifest(manifest_path)
    gse.validate_manifest(
        manifest, allow_missing_documents=True, manifest_dir=manifest_path.parent
    )


def test_release_gate_fails_legacy_report_without_evaluated_eligible_count():
    """Strict release mode must not fall back to manifest eligibility counts.

    Older/report-only summaries may have benchmark_eligible_count without proving a
    real evaluated eligible project. Release evidence must require the explicit
    evaluated_benchmark_eligible_count field produced by the current evaluator.
    """
    report = {
        "aggregate": {
            "evaluated_count": 0,
            "benchmark_eligible_count": 1,
            "harness_failed_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 0,
            "missed_required_trade_project_count": 0,
            "trade_unexpected_false_positive_total": 0,
            "key_quantity_total": 1,
            "key_quantity_evidence_pass_count": 1,
        }
    }

    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_release_gate_fails_accuracy_failures_even_if_programmatic_bypass_flag_is_passed():
    report = {
        "aggregate": {
            "evaluated_count": 1,
            "evaluated_benchmark_eligible_count": 1,
            "harness_failed_count": 0,
            "safety_violation_count": 0,
            "accuracy_failed_project_count": 1,
            "missed_required_trade_project_count": 0,
            "trade_unexpected_false_positive_total": 0,
            "evaluated_benchmark_eligible_key_quantity_total": 1,
            "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
            "evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
            "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
        }
    }

    assert (
        gse.compute_exit_code(
            report,
            fail_on_missed_required_trade=False,
            fail_on_accuracy=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


# ---------------------------------------------------------------------------
# Golden Set v2 evidence and false-positive scoring
# ---------------------------------------------------------------------------
def test_key_quantity_preserves_v2_evidence_fields_and_human_verified_passes_without_engine_quantity():
    items = []
    kq = {
        "label": "roofing area",
        "item_name": "New roofing area",
        "trade": "roofing_waterproofing",
        "expected_value": 19337,
        "unit": "SF",
        "tolerance_abs": 0,
        "source_document": "documents/plans.pdf",
        "sheet_ref": "G001",
        "page_ref": "1",
        "evidence_snippet": "AREA OF PROJECT IN SQUARE FEET:19,337 OF NEW ROOFING",
        "evidence_verified": True,
        "measurement_method": "Read from cover sheet building information table",
        "confidence_level": "high",
        "assumptions": ["Cover sheet value is treated as authoritative."],
        "require_engine_quantity": False,
    }
    result = gse.evaluate_key_quantity(kq, items, source_text="")
    assert result["status"] == "pass"
    assert result["reason"] == "source_evidence_only_engine_quantity_not_required"
    assert result["sheet_ref"] == "G001"
    assert result["evidence_status"]["status"] == "pass"
    assert result["evidence_status"]["reason"] == "human_verified_source_reference"
    assert result["evidence_status"]["machine_snippet_matched"] is False


def test_evidence_snippet_matches_source_text():
    kq = {
        "label": "parking stalls",
        "expected_value": 27,
        "unit": "EA",
        "tolerance_abs": 0,
        "evidence_snippet": "PUBLIC PARKING 25 2 totals 27",
        "require_engine_quantity": False,
    }
    result = gse.evaluate_key_quantity(
        kq,
        [],
        source_text="The parking table reads: Public Parking 25 2 totals 27.",
    )
    assert result["evidence_status"]["status"] == "pass"
    assert result["evidence_status"]["machine_snippet_matched"] is True
    assert result["status"] == "pass"


def test_release_gate_rejects_human_verified_only_key_quantity_evidence():
    """Strict release evidence needs machine-matched source text, not self-asserted flags."""
    key_quantities = gse.evaluate_key_quantities(
        [
            {
                "label": "roofing area",
                "expected_value": 19337,
                "unit": "SF",
                "tolerance_abs": 0,
                "evidence_verified": True,
                "require_engine_quantity": False,
            }
        ],
        [],
        source_text="",
    )
    assert key_quantities["pass_count"] == 1
    assert key_quantities["evidence_pass_count"] == 1
    assert key_quantities["evidence_snippet_matched_pass_count"] == 0

    aggregate = gse.build_aggregate([
        {
            "evaluation_status": "evaluated",
            "evaluation_passed": True,
            "benchmark_eligible": True,
            "benchmark_ineligible": False,
            "missed_required_trade": False,
            "accuracy_passed": True,
            "trade_coverage": {
                "expected_trades": ["roofing_waterproofing"],
                "matched_trades": ["roofing_waterproofing"],
                "false_positive_trades": [],
                "unexpected_false_positive_trades": [],
            },
            "scope_keyword_coverage": {"expected_keyword_count": 0, "found_keywords": []},
            "key_quantities": key_quantities,
            "document_text_extraction": {"ok": True},
        }
    ])

    assert aggregate["evaluated_benchmark_eligible_key_quantity_evidence_pass_count"] == 1
    assert aggregate["evaluated_benchmark_eligible_key_quantity_evidence_snippet_matched_pass_count"] == 0
    assert (
        gse.compute_exit_code(
            {"aggregate": aggregate},
            fail_on_missed_required_trade=False,
            require_evaluated_benchmark_eligible=True,
            require_key_quantity_evidence=True,
        )
        == 1
    )


def test_trade_coverage_separates_allowed_and_unexpected_false_positives():
    result = gse.score_trade_coverage(
        ["concrete"],
        {"concrete", "electrical", "plumbing"},
        allowed_extra_trades=["electrical"],
    )
    assert result["false_positive_trades"] == ["electrical", "plumbing"]
    assert result["allowed_extra_trades_detected"] == ["electrical"]
    assert result["unexpected_false_positive_trades"] == ["plumbing"]
    assert result["unexpected_false_positive_count"] == 1


def test_compute_exit_code_can_fail_on_unexpected_false_positive_trade():
    report = {"aggregate": {"trade_unexpected_false_positive_total": 1}}
    assert gse.compute_exit_code(
        report,
        fail_on_missed_required_trade=False,
        fail_on_accuracy=False,
        fail_on_unexpected_false_positive_trade=False,
    ) == 0
    assert gse.compute_exit_code(
        report,
        fail_on_missed_required_trade=False,
        fail_on_accuracy=False,
        fail_on_unexpected_false_positive_trade=True,
    ) == 1


def test_evaluate_report_includes_v2_quality_and_aggregate_counts():
    project = _base_project(
        expected_trades=["painting"],
        allowed_extra_trades=["electrical"],
        fail_on_unexpected_false_positives=False,
        key_quantities=[{
            "label": "paint walls",
            "expected_value": 100,
            "unit": "SF",
            "tolerance_abs": 0,
            "evidence_verified": True,
            "require_engine_quantity": False,
        }],
    )
    report = _harness_report([
        _scope_item("painting", "Paint walls"),
        _scope_item("electrical", "Electrical scope detected"),
        _scope_item("plumbing", "Plumbing scope detected"),
    ])
    result = gse.evaluate_report(
        project,
        report,
        document_text_extraction={"ok": True, "text": "paint walls", "char_count": 11, "extraction_method": "fixture", "reason": None},
    )
    assert result["trade_coverage"]["allowed_extra_trades_detected"] == ["electrical"]
    assert result["trade_coverage"]["unexpected_false_positive_trades"] == ["plumbing"]
    assert result["extraction_quality"]["document_text_extraction"]["status"] == "pass"
    aggregate = gse.build_aggregate([result])
    assert aggregate["trade_unexpected_false_positive_total"] == 1
    assert aggregate["key_quantity_evidence_pass_count"] == 1
    assert aggregate["key_quantity_evidence_snippet_matched_pass_count"] == 0
    assert aggregate["document_text_extraction_pass_count"] == 1
