"""Tests for the Mobi AutoResearch v1 helper script."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import mobi_autoresearch as ar


def _report(**aggregate_overrides):
    aggregate = {
        "scope_keyword_coverage_micro": 0.25,
        "trade_recall_micro": 0.5,
        "key_quantity_pass_count": 2,
        "key_quantity_evidence_pass_count": 3,
        "key_quantity_total": 4,
        "trade_unexpected_false_positive_total": 1,
        "safety_violation_count": 0,
        "harness_failed_count": 0,
        "evaluation_passed_count": 1,
        "evaluated_count": 3,
        "accuracy_failed_project_count": 2,
    }
    aggregate.update(aggregate_overrides)
    return {"aggregate": aggregate}


def _release_gate_report(**aggregate_overrides):
    aggregate = {
        "project_count": 1,
        "evaluated_count": 1,
        "evaluation_passed_count": 1,
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
        "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
        "scope_keyword_coverage_micro": 0.9,
        "trade_recall_micro": 1.0,
        "key_quantity_pass_count": 1,
        "key_quantity_evidence_pass_count": 1,
        "key_quantity_total": 1,
    }
    aggregate.update(aggregate_overrides)
    return {"aggregate": aggregate}


def test_validate_release_gate_report_accepts_strict_valid_counts():
    result = ar.validate_release_gate_report(_release_gate_report())

    assert result == {"ok": True, "reason": "release gate report passed wrapper validation"}


@pytest.mark.parametrize(
    "marker_payload",
    [
        {"internal_testing_only": True},
        {"manifest_metadata": {"internal_testing_only": True}},
        {"metadata": {"report_only_baseline": True}},
        {"metadata": {"command_flags": {"no_fail_on_accuracy": True}}},
        {"metadata": {"command_flags": {"no-fail-on-accuracy": True}}},
        {"projects": [{"accuracy_bypass_enabled": "true"}]},
        {"metadata": {"command": ["python", "golden_set_extraction_eval.py", "--no-fail-on-accuracy"]}},
        {"logs": "baseline run used --report-only-baseline for internal comparison"},
    ],
)
def test_validate_release_gate_report_rejects_test_only_or_accuracy_bypass_markers(marker_payload):
    report = _release_gate_report()
    report.update(marker_payload)

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": "release gate report is marked test-only or accuracy-bypass evidence",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_count", True),
        ("project_count", -1),
        ("project_count", 1.5),
        ("project_count", "1.0"),
        ("project_count", ""),
        ("project_count", None),
    ],
)
def test_validate_release_gate_report_rejects_malformed_counts(field, value):
    result = ar.validate_release_gate_report(_release_gate_report(**{field: value}))

    assert result["ok"] is False
    assert result["reason"] == "release gate report has malformed/missing counts"
    assert field in result["fields"]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {
                "benchmark_eligible_count": 0,
                "benchmark_ineligible_count": 1,
                "evaluated_benchmark_eligible_count": 0,
                "evaluated_benchmark_ineligible_count": 1,
            },
            "release gate has zero evaluated benchmark-eligible projects",
        ),
        ({"evaluated_benchmark_eligible_key_quantity_total": 0}, "release gate lacks complete key-quantity evidence"),
        ({"evaluation_passed_count": 0}, "release gate has unevaluated or failed project results"),
        ({"evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 0}, "release gate lacks complete key-quantity evidence"),
        ({"evaluated_benchmark_eligible_document_text_extraction_pass_count": 0}, "release gate document text extraction coverage is incomplete"),
        ({"evaluated_count": 2, "evaluation_passed_count": 2}, "release gate aggregate counts are inconsistent"),
    ],
)
def test_validate_release_gate_report_fails_closed_for_unsafe_release_evidence(overrides, reason):
    result = ar.validate_release_gate_report(_release_gate_report(**overrides))

    assert result["ok"] is False
    assert result["reason"] == reason


def test_compute_score_uses_weighted_formula():
    result = ar.compute_score(_report())
    # 100*.25 + 100*.5 + 50*(2/4) + 25*(3/4) - 20*1 = 98.75
    assert result["score"] == 98.75
    assert result["components"] == {
        "scope_keyword_coverage_micro": 25.0,
        "trade_recall_micro": 50.0,
        "key_quantity_pass_rate": 25.0,
        "key_quantity_evidence_pass_rate": 18.75,
        "unexpected_false_positive_penalty": -20.0,
        "safety_violation_penalty": -0.0,
        "harness_failed_penalty": -0.0,
    }
    assert result["metrics"]["key_quantity_pass_rate"] == 0.5
    assert result["metrics"]["aggregate_present"] is True
    assert result["schema_version"] == "mobi-autoresearch-score-v1"


def test_compute_score_missing_aggregate_is_flagged_but_safe():
    result = ar.compute_score({})
    assert result["metrics"]["aggregate_present"] is False
    assert result["score"] == 75.0


def test_compute_score_zero_quantity_denominator_defaults_to_not_penalized():
    result = ar.compute_score(
        _report(
            key_quantity_pass_count=0,
            key_quantity_evidence_pass_count=0,
            key_quantity_total=0,
            scope_keyword_coverage_micro=0,
            trade_recall_micro=0,
            trade_unexpected_false_positive_total=0,
        )
    )
    assert result["metrics"]["key_quantity_pass_rate"] == 1.0
    assert result["metrics"]["key_quantity_evidence_pass_rate"] == 1.0
    assert result["score"] == 75.0


def test_compute_score_penalizes_safety_and_harness_failures():
    result = ar.compute_score(_report(safety_violation_count=1, harness_failed_count=2))
    assert result["components"]["safety_violation_penalty"] == -1000.0
    assert result["components"]["harness_failed_penalty"] == -200.0
    assert result["score"] == -1101.25


def test_normalize_repo_path_preserves_dotfile_names():
    assert ar._normalize_repo_path("./.github/workflows/ci.yml") == ".github/workflows/ci.yml"


def test_evaluate_guard_allows_only_allowed_paths():
    result = ar.evaluate_guard(
        [
            "mobi-estimating-phase1/app/extraction/rules.json",
            "mobi-estimating-phase1/app/extraction/prompts/drawing.md",
        ],
        ["mobi-estimating-phase1/app/extraction/"],
    )
    assert result["ok"] is True
    assert result["locked_violations"] == []
    assert result["outside_allowed_violations"] == []


def test_evaluate_guard_rejects_outside_allowed_paths():
    result = ar.evaluate_guard(
        [
            "mobi-estimating-phase1/app/extraction/rules.json",
            "mobi-estimating-phase1/app/main.py",
        ],
        ["mobi-estimating-phase1/app/extraction/"],
    )
    assert result["ok"] is False
    assert result["outside_allowed_violations"] == ["mobi-estimating-phase1/app/main.py"]


def test_evaluate_guard_rejects_locked_paths_even_if_allowed():
    changed = [
        "mobi-estimating-phase1/data/golden_set_v2/manifest.real-v2.json",
        "mobi-estimating-phase1/scripts/golden_set_extraction_eval.py",
        "mobi-estimating-phase1/data/golden_set_v2/documents/example.pdf",
    ]
    result = ar.evaluate_guard(
        changed,
        [
            "mobi-estimating-phase1/data/golden_set_v2/",
            "mobi-estimating-phase1/scripts/",
        ],
    )
    assert result["ok"] is False
    assert result["locked_violations"] == changed
    assert result["outside_allowed_violations"] == []


def test_append_ledger_writes_jsonl_record(tmp_path):
    score_path = tmp_path / "score.json"
    score_payload = ar.compute_score(_report())
    score_path.write_text(json.dumps(score_payload), encoding="utf-8")
    ledger = tmp_path / "experiments.jsonl"

    record = ar.append_ledger(
        ledger,
        experiment_id="baseline-001",
        score_json=score_path,
        status="baseline",
        notes="initial score",
    )

    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed == record
    assert parsed["experiment_id"] == "baseline-001"
    assert parsed["status"] == "baseline"
    assert parsed["score"]["score"] == 98.75


def test_append_ledger_rejects_bad_status(tmp_path):
    score_path = tmp_path / "score.json"
    score_path.write_text(json.dumps(ar.compute_score(_report())), encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        ar.append_ledger(
            tmp_path / "ledger.jsonl",
            experiment_id="bad",
            score_json=score_path,
            status="kept",
            notes="bad status",
        )


def test_cli_score_writes_json_output(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    score_path = tmp_path / "score.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")

    exit_code = ar.main(["score", "--report", str(report_path), "--output", str(score_path)])

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out)
    written = json.loads(score_path.read_text(encoding="utf-8"))
    assert stdout["score"] == 98.75
    assert written["score"] == 98.75


def test_cli_guard_returns_nonzero_on_locked_violation(monkeypatch, capsys):
    monkeypatch.setattr(
        ar,
        "collect_changed_paths",
        lambda base_ref: ["mobi-estimating-phase1/data/golden_set_v2/sources.v2.json"],
    )
    exit_code = ar.main(
        [
            "guard",
            "--base-ref",
            "main",
            "--allowed",
            "mobi-estimating-phase1/data/golden_set_v2/",
        ]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["locked_violations"] == [
        "mobi-estimating-phase1/data/golden_set_v2/sources.v2.json"
    ]


def test_collect_changed_paths_reads_committed_staged_unstaged_and_untracked(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "committed.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, stdout=subprocess.PIPE)

    (repo / "committed.txt").write_text("head", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "head"], cwd=repo, check=True, stdout=subprocess.PIPE)

    (repo / "staged.txt").write_text("staged", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=repo, check=True)
    (repo / "unstaged.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "unstaged.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "unstaged base"], cwd=repo, check=True, stdout=subprocess.PIPE)
    (repo / "unstaged.txt").write_text("changed", encoding="utf-8")
    (repo / "untracked.txt").write_text("new", encoding="utf-8")

    changed = ar.collect_changed_paths("HEAD~2", repo_root=repo)

    assert changed == ["committed.txt", "staged.txt", "unstaged.txt", "untracked.txt"]


def test_baseline_cli_resolves_repo_relative_paths_and_scores(monkeypatch, tmp_path, capsys):
    report_payload = _report(
        scope_keyword_coverage_micro=1.0,
        trade_recall_micro=1.0,
        key_quantity_pass_count=1,
        key_quantity_evidence_pass_count=1,
        key_quantity_total=1,
        trade_unexpected_false_positive_total=0,
    )
    commands = []

    def fake_run(command, *, cwd):
        commands.append((command, cwd))
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report_payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="eval ok", stderr="")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = Path("reports/out.json")
    workdir = Path("work/run")

    exit_code = ar.main(
        [
            "baseline",
            "--manifest",
            "manifest.json",
            "--output",
            str(output),
            "--workdir",
            str(workdir),
            "--python",
            "python3",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["score"]["score"] == 275.0
    command, cwd = commands[0]
    assert cwd == ar.ENGINE_ROOT
    assert command[command.index("--manifest") + 1] == str(manifest.resolve())
    assert command[command.index("--output") + 1] == str((tmp_path / output).resolve())
    assert command[command.index("--workdir") + 1] == str((tmp_path / workdir).resolve())
    assert "--no-fail-on-accuracy" in command
    assert "--report-only-baseline" in command
    assert "--release-gate" not in command


def test_release_gate_uses_strict_evaluator_without_accuracy_bypass(tmp_path, monkeypatch, capsys):
    report_payload = _release_gate_report()
    commands: list[tuple[list[str], Path]] = []

    def fake_run(command, *, cwd):
        commands.append((command, cwd))
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report_payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="release gate ok", stderr="")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = Path("reports/release-gate.json")
    workdir = Path("work/release")

    exit_code = ar.main(
        [
            "release-gate",
            "--manifest",
            "manifest.json",
            "--output",
            str(output),
            "--workdir",
            str(workdir),
            "--python",
            "python3",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["release_gate"] is True
    command, cwd = commands[0]
    assert cwd == ar.ENGINE_ROOT
    assert command[command.index("--manifest") + 1] == str(manifest.resolve())
    assert command[command.index("--output") + 1] == str((tmp_path / output).resolve())
    assert command[command.index("--workdir") + 1] == str((tmp_path / workdir).resolve())
    assert "--release-gate" in command
    assert "--no-fail-on-accuracy" not in command
    assert "--report-only-baseline" not in command
    assert "--allow-missing-documents" not in command
    assert payload["release_gate_validation"]["ok"] is True


def test_release_gate_wrapper_rejects_zero_eligible_success_report(tmp_path, monkeypatch, capsys):
    """A stale/mocked evaluator exit 0 cannot promote zero eligible evidence."""
    report_payload = _release_gate_report(
        project_count=1,
        evaluated_count=1,
        benchmark_eligible_count=0,
        benchmark_ineligible_count=1,
        evaluated_benchmark_eligible_count=0,
        evaluated_benchmark_ineligible_count=1,
        evaluated_benchmark_eligible_key_quantity_total=0,
        evaluated_benchmark_eligible_key_quantity_pass_count=0,
        evaluated_benchmark_eligible_key_quantity_evidence_pass_count=0,
        evaluated_benchmark_eligible_document_text_extraction_pass_count=0,
    )

    def fake_run(command, *, cwd):
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report_payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="stale evaluator ok", stderr="")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")

    exit_code = ar.main(
        [
            "release-gate",
            "--manifest",
            "manifest.json",
            "--output",
            "reports/release-gate.json",
            "--workdir",
            "work/release",
            "--python",
            "python3",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["release_gate"] is True
    assert payload["release_gate_validation"]["ok"] is False
    assert payload["release_gate_validation"]["reason"] == "release gate has zero evaluated benchmark-eligible projects"


def test_release_gate_propagates_strict_failure_without_score_file(tmp_path, monkeypatch, capsys):
    commands: list[list[str]] = []

    def fake_run(command, *, cwd):
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="zero eligible projects")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    exit_code = ar.main(
        [
            "release-gate",
            "--manifest",
            "manifest.json",
            "--output",
            "reports/release-gate.json",
            "--workdir",
            "work/release",
            "--python",
            "python3",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["release_gate"] is True
    assert payload["exit_code"] == 1
    assert payload["stderr"] == "zero eligible projects"
    command = commands[0]
    assert "--release-gate" in command
    assert "--no-fail-on-accuracy" not in command
    assert not (tmp_path / "reports/release-gate.json").exists()
