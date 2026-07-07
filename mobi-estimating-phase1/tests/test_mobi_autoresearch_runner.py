"""Tests for the Mobi AutoResearch experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import mobi_autoresearch_runner as runner


def _eval(score: float, *, ok: bool = True):
    return {
        "ok": ok,
        "score": {"score": score},
        "report_path": "/tmp/report.json",
        "workdir": "/tmp/workdir",
    }


def _install_eval_sequence(monkeypatch, scores):
    calls = []
    values = list(scores)

    def fake_eval(**kwargs):
        calls.append(kwargs)
        score = values.pop(0)
        if isinstance(score, dict):
            return score
        return _eval(score)

    monkeypatch.setattr(runner, "run_eval_for_experiment", fake_eval)
    return calls


def test_experiment_accepts_improved_score_and_keeps_change(tmp_path, monkeypatch):
    artifact = tmp_path / "prompt.md"
    artifact.write_text("base\n", encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    _install_eval_sequence(monkeypatch, [100, 125])
    monkeypatch.setattr(runner, "ensure_clean_worktree", lambda allow_dirty=False: None)
    monkeypatch.setattr(runner.ar, "collect_changed_paths", lambda base_ref: ["artifact.md"])
    monkeypatch.setattr(
        runner.ar,
        "evaluate_guard",
        lambda changed, allowed: {"ok": True, "changed_paths": changed, "locked_violations": [], "outside_allowed_violations": []},
    )
    restored = []
    monkeypatch.setattr(runner, "restore_paths", lambda paths: restored.extend(paths))

    result = runner.run_experiment(
        experiment_id="accept-1",
        allowed_paths=["artifact.md"],
        mutable_artifact=artifact,
        append_line="candidate improvement",
        patch_file=None,
        manifest=tmp_path / "manifest.json",
        ledger=ledger,
        run_root=tmp_path / "runs",
        python_executable="python3",
    )

    assert result["status"] == "accepted"
    assert result["accepted"] is True
    assert result["score_delta"] == 25
    assert restored == []
    assert "candidate improvement" in artifact.read_text(encoding="utf-8")
    assert json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])["status"] == "accepted"


def test_experiment_rejects_non_improved_score_and_reverts(tmp_path, monkeypatch):
    artifact = tmp_path / "prompt.md"
    artifact.write_text("base\n", encoding="utf-8")
    _install_eval_sequence(monkeypatch, [100, 95])
    monkeypatch.setattr(runner, "ensure_clean_worktree", lambda allow_dirty=False: None)
    monkeypatch.setattr(runner.ar, "collect_changed_paths", lambda base_ref: ["artifact.md"])
    monkeypatch.setattr(
        runner.ar,
        "evaluate_guard",
        lambda changed, allowed: {"ok": True, "changed_paths": changed, "locked_violations": [], "outside_allowed_violations": []},
    )
    restored = []
    monkeypatch.setattr(runner, "restore_paths", lambda paths: restored.extend(paths))

    result = runner.run_experiment(
        experiment_id="reject-1",
        allowed_paths=["artifact.md"],
        mutable_artifact=artifact,
        append_line="candidate worse",
        patch_file=None,
        manifest=tmp_path / "manifest.json",
        ledger=tmp_path / "ledger.jsonl",
        run_root=tmp_path / "runs",
        python_executable="python3",
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "score_not_improved"
    assert restored == [runner._repo_relative(artifact)]


def test_experiment_guard_failure_rejects_and_reverts(tmp_path, monkeypatch):
    artifact = tmp_path / "prompt.md"
    artifact.write_text("base\n", encoding="utf-8")
    calls = _install_eval_sequence(monkeypatch, [100])
    monkeypatch.setattr(runner, "ensure_clean_worktree", lambda allow_dirty=False: None)
    monkeypatch.setattr(
        runner.ar,
        "collect_changed_paths",
        lambda base_ref: ["mobi-estimating-phase1/data/golden_set_v2/manifest.real-v2.json"],
    )
    monkeypatch.setattr(
        runner.ar,
        "evaluate_guard",
        lambda changed, allowed: {
            "ok": False,
            "changed_paths": changed,
            "locked_violations": changed,
            "outside_allowed_violations": [],
        },
    )
    restored = []
    monkeypatch.setattr(runner, "restore_paths", lambda paths: restored.extend(paths))

    result = runner.run_experiment(
        experiment_id="guard-fail-1",
        allowed_paths=["artifact.md"],
        mutable_artifact=artifact,
        append_line="candidate",
        patch_file=None,
        manifest=tmp_path / "manifest.json",
        ledger=tmp_path / "ledger.jsonl",
        run_root=tmp_path / "runs",
        python_executable="python3",
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "guard_failed"
    assert result["candidate"] is None
    assert len(calls) == 1
    assert calls[0]["label"] == "baseline"
    assert restored == [runner._repo_relative(artifact)]


def test_dry_run_reverts_even_when_score_improves(tmp_path, monkeypatch):
    artifact = tmp_path / "prompt.md"
    artifact.write_text("base\n", encoding="utf-8")
    _install_eval_sequence(monkeypatch, [100, 125])
    monkeypatch.setattr(runner, "ensure_clean_worktree", lambda allow_dirty=False: None)
    monkeypatch.setattr(runner.ar, "collect_changed_paths", lambda base_ref: [runner._repo_relative(artifact)])
    monkeypatch.setattr(
        runner.ar,
        "evaluate_guard",
        lambda changed, allowed: {"ok": True, "changed_paths": changed, "locked_violations": [], "outside_allowed_violations": []},
    )
    restored = []
    monkeypatch.setattr(runner, "restore_paths", lambda paths: restored.extend(paths))

    result = runner.run_experiment(
        experiment_id="dry-run-improved",
        allowed_paths=[runner._repo_relative(artifact)],
        mutable_artifact=artifact,
        append_line="candidate improvement",
        patch_file=None,
        manifest=tmp_path / "manifest.json",
        ledger=tmp_path / "ledger.jsonl",
        run_root=tmp_path / "runs",
        python_executable="python3",
        dry_run=True,
    )

    assert result["status"] == "rejected"
    assert result["accepted"] is False
    assert result["reason"] == "dry_run_reverted"
    assert result["candidate_score"] == 125
    assert restored == [runner._repo_relative(artifact)]


def test_dirty_mode_cleanup_targets_only_runner_changed_paths(tmp_path, monkeypatch):
    artifact = tmp_path / "prompt.md"
    artifact.write_text("base\n", encoding="utf-8")
    preexisting_dirty = "preexisting-dirty.md"
    preexisting_untracked = "preexisting-untracked.md"
    _install_eval_sequence(monkeypatch, [100, 95])
    ensure_calls = []
    monkeypatch.setattr(runner, "ensure_clean_worktree", lambda allow_dirty=False: ensure_calls.append(allow_dirty))
    monkeypatch.setattr(
        runner.ar,
        "collect_changed_paths",
        lambda base_ref: [runner._repo_relative(artifact), preexisting_dirty, preexisting_untracked],
    )
    monkeypatch.setattr(
        runner.ar,
        "evaluate_guard",
        lambda changed, allowed: {"ok": True, "changed_paths": changed, "locked_violations": [], "outside_allowed_violations": []},
    )
    restored = []
    monkeypatch.setattr(runner, "restore_paths", lambda paths: restored.extend(paths))

    result = runner.run_experiment(
        experiment_id="dirty-mode",
        allowed_paths=[runner._repo_relative(artifact)],
        mutable_artifact=artifact,
        append_line="candidate worse",
        patch_file=None,
        manifest=tmp_path / "manifest.json",
        ledger=tmp_path / "ledger.jsonl",
        run_root=tmp_path / "runs",
        python_executable="python3",
        _allow_dirty=True,
    )

    assert ensure_calls == [True]
    assert result["status"] == "rejected"
    assert result["changed_paths"] == [runner._repo_relative(artifact), preexisting_dirty, preexisting_untracked]
    assert result["runner_changed_paths"] == [runner._repo_relative(artifact)]
    assert restored == [runner._repo_relative(artifact)]


def test_experiment_dry_run_no_mutation_writes_rejected_ledger(tmp_path, monkeypatch):
    artifact = tmp_path / "prompt.md"
    artifact.write_text("base\n", encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    _install_eval_sequence(monkeypatch, [100, 100])
    monkeypatch.setattr(runner, "ensure_clean_worktree", lambda allow_dirty=False: None)
    monkeypatch.setattr(runner.ar, "collect_changed_paths", lambda base_ref: [])
    monkeypatch.setattr(
        runner.ar,
        "evaluate_guard",
        lambda changed, allowed: {"ok": True, "changed_paths": [], "locked_violations": [], "outside_allowed_violations": []},
    )

    result = runner.run_experiment(
        experiment_id="dry-run-1",
        allowed_paths=["artifact.md"],
        mutable_artifact=artifact,
        append_line=None,
        patch_file=None,
        manifest=tmp_path / "manifest.json",
        ledger=ledger,
        run_root=tmp_path / "runs",
        python_executable="python3",
        dry_run=True,
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "dry_run_no_mutation"
    assert ledger.exists()


def test_experiment_requires_mutation_when_not_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ensure_clean_worktree", lambda allow_dirty=False: None)
    try:
        runner.run_experiment(
            experiment_id="bad",
            allowed_paths=["artifact.md"],
            mutable_artifact=tmp_path / "prompt.md",
            append_line=None,
            patch_file=None,
            manifest=tmp_path / "manifest.json",
            ledger=tmp_path / "ledger.jsonl",
            run_root=tmp_path / "runs",
            python_executable="python3",
        )
    except ValueError as exc:
        assert "require --append-line or --patch-file" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_runner_defaults_keep_generated_artifacts_outside_repo():
    assert str(runner.DEFAULT_LEDGER).startswith("/tmp/")
    assert str(runner.DEFAULT_RUN_ROOT).startswith("/tmp/")


def test_allow_dirty_is_not_a_cli_flag():
    parser = runner.build_parser()
    try:
        parser.parse_args(["experiment", "--experiment-id", "x", "--allow-dirty"])
    except SystemExit as exc:
        assert exc.code != 0
    else:  # pragma: no cover
        raise AssertionError("--allow-dirty should not be exposed as a CLI flag")


def test_paths_from_patch_extracts_touched_files(tmp_path):
    patch = tmp_path / "change.patch"
    patch.write_text(
        "\n".join(
            [
                "diff --git a/foo.md b/foo.md",
                "--- a/foo.md",
                "+++ b/foo.md",
                "@@ -1 +1 @@",
                "-old",
                "+new",
                "diff --git a/new.md b/new.md",
                "--- /dev/null",
                "+++ b/new.md",
            ]
        ),
        encoding="utf-8",
    )

    assert runner.paths_from_patch(patch) == ["foo.md", "new.md"]


def test_paths_from_patch_extracts_metadata_only_renames(tmp_path):
    patch = tmp_path / "rename.patch"
    patch.write_text(
        "\n".join(
            [
                "diff --git a/old.md b/new.md",
                "similarity index 100%",
                "rename from old.md",
                "rename to new.md",
            ]
        ),
        encoding="utf-8",
    )

    assert runner.paths_from_patch(patch) == ["old.md", "new.md"]


def test_experiment_cli_returns_zero_for_rejected_dry_run(tmp_path, monkeypatch, capsys):
    artifact = tmp_path / "prompt.md"
    artifact.write_text("base\n", encoding="utf-8")
    _install_eval_sequence(monkeypatch, [100, 100])
    monkeypatch.setattr(runner, "ensure_clean_worktree", lambda allow_dirty=False: None)
    monkeypatch.setattr(runner.ar, "collect_changed_paths", lambda base_ref: [])
    monkeypatch.setattr(
        runner.ar,
        "evaluate_guard",
        lambda changed, allowed: {"ok": True, "changed_paths": [], "locked_violations": [], "outside_allowed_violations": []},
    )

    exit_code = runner.main(
        [
            "experiment",
            "--experiment-id",
            "cli-dry",
            "--mutable-artifact",
            str(artifact),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
            "--run-root",
            str(tmp_path / "runs"),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "rejected"
