"""Regression tests for compact OpenTakeoff capability benchmark artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "data" / "opentakeoff_benchmark"
RESULTS_PATH = BENCHMARK_DIR / "opentakeoff-capability-benchmark-results.json"
SUMMARY_PATH = BENCHMARK_DIR / "opentakeoff-capability-benchmark-summary.json"

REQUIRED_FIELDS = {
    "benchmark_id",
    "project_id",
    "document_id",
    "sheet_id",
    "page_number",
    "measurement_category",
    "OpenTakeoff_method",
    "scale_method",
    "scale_source",
    "ground_truth_quantity",
    "ground_truth_unit",
    "ground_truth_method",
    "OpenTakeoff_quantity",
    "absolute_error",
    "percentage_error",
    "region_coordinates",
    "AI_proposal_used",
    "AI_proposal_accepted",
    "AI_processing_time_ms",
    "OpenTakeoff_processing_time_ms",
    "human_selection_time_seconds",
    "human_correction_time_seconds",
    "final_classification",
    "failure_reason",
    "review_notes",
}


def _results() -> list[dict]:
    return json.loads(RESULTS_PATH.read_text())["results"]


def _summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text())


def test_benchmark_schema_and_required_coverage():
    rows = _results()
    assert len(rows) == 12
    assert all(REQUIRED_FIELDS <= row.keys() for row in rows)
    assert len({row["project_id"] for row in rows}) >= 2
    assert len({(row["project_id"], row["sheet_id"], row["page_number"]) for row in rows}) >= 3
    assert {"measure_line", "measure_polygon", "one_click", "record_count"} <= {
        row["OpenTakeoff_method"] for row in rows
    }
    assert any(row["measurement_category"] == "failure_missing_scale" for row in rows)
    assert any(row["measurement_category"] == "count" for row in rows)


def test_clean_vector_line_and_polygon_accuracy_targets():
    rows = _results()
    accurate = [
        row
        for row in rows
        if row["final_classification"] == "pass"
        and row["OpenTakeoff_method"] in {"measure_line", "measure_polygon"}
        and row["measurement_category"] != "deduction"
    ]
    errors = [float(row["percentage_error"]) for row in accurate]
    assert errors
    assert median(errors) <= 3
    assert max(errors) <= 5
    assert all(row["scale_confirmed"] is True for row in accurate)
    assert all(row["region_coordinates"] for row in accurate)


def test_one_click_failures_are_not_accepted_as_measured_evidence():
    one_click_rows = [row for row in _results() if row["OpenTakeoff_method"] == "one_click"]
    assert len(one_click_rows) == 2
    assert all(row["final_classification"] == "fail" for row in one_click_rows)
    assert any("enclosed" in str(row["failure_reason"]) for row in one_click_rows)
    assert any(row["failure_reason"] == "trace_ambiguous_requires_review" for row in one_click_rows)


def test_missing_scale_and_count_are_safe_failures():
    rows = {row["benchmark_id"]: row for row in _results()}
    missing = rows["lot50-c011-missing-scale"]
    assert missing["final_classification"] == "expected_safe_failure"
    assert missing["failure_reason"] == "expected_scale_missing_safe_failure"
    assert missing["mcp"]["measureResult"]["isError"] is True
    assert "Set the scale" in missing["mcp"]["measureResult"]["data"]["error"]

    count = rows["lot50-c011-count-unsupported"]
    assert count["final_classification"] == "expected_safe_failure"
    assert count["failure_reason"] == "expected_safe_failure_no_mcp_count_primitive"
    assert count["ground_truth_method"].startswith("schedule/table count kept separate")


def test_summary_selects_only_demonstrated_worker_operations():
    summary = _summary()
    supported = set(summary["supported_for_mvp_worker"])
    fallback = set(summary["human_fallback_or_review"])
    assert "measure_line" in supported
    assert "measure_polygon_manual" in supported
    assert "one_click_area" not in supported
    assert any("one_click" in item for item in fallback)
    assert any("record_count" in item for item in fallback)
    assert any("raster" in item for item in fallback)
