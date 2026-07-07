#!/usr/bin/env python3
"""Mobi AutoResearch experiment runner v1.

Runs a single controlled experiment cycle around the Golden Set v2 evaluator:

baseline -> mutate one allowed artifact -> guard -> candidate eval -> score -> accept/reject -> ledger

The runner is intentionally local/internal. It does not call Claude/Codex by
default, does not deploy, and does not touch customer-facing behavior. V1 accepts
only command-free local mutations (`--append-line`) or a caller-provided patch
file (`--patch-file`) so tests and first dry runs stay deterministic.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # allow direct execution: python scripts/mobi_autoresearch_runner.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import mobi_autoresearch as ar

DEFAULT_MUTABLE_ARTIFACT = (
    ar.ENGINE_ROOT / "app/extraction/prompts/golden_set_v2_drawing_text_extraction.md"
)
DEFAULT_LEDGER = Path("/tmp/mobi-autoresearch/experiments.jsonl")
DEFAULT_RUN_ROOT = Path("/tmp/mobi-autoresearch/runs")
PROPOSAL_SCHEMA_VERSION = "mobi-autoresearch-proposal-v1"
FORBIDDEN_PROPOSAL_FIELDS = frozenset(
    {"command", "commands", "cmd", "shell", "exec", "run", "script", "entrypoint", "argv"}
)


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ar.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _ensure_within_repo(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(ar.REPO_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the repository: {path}") from exc
    return resolved


def _resolve_repo_file(value: str, *, label: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ar.REPO_ROOT / candidate
    return _ensure_within_repo(candidate, label=label)


def _resolve_patch_file(value: str, *, proposal_file: Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        proposal_relative = (proposal_file.parent / candidate).resolve()
        candidate = proposal_relative if proposal_relative.exists() else (ar.REPO_ROOT / candidate)
    if not candidate.exists():
        raise ValueError(f"proposal patch_file does not exist: {value}")
    return candidate.resolve()


def _normalize_allowed_paths(values: list[str] | None, *, mutable_artifact: Path) -> list[str]:
    raw_values = [_repo_relative(mutable_artifact), *(values or [])]
    allowed: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("proposal allowed_paths entries must be non-empty strings")
        keeps_prefix = raw.replace("\\", "/").rstrip().endswith("/")
        candidate = Path(raw)
        if candidate.is_absolute():
            normalized = _repo_relative(_ensure_within_repo(candidate, label="allowed path"))
        else:
            resolved = (ar.REPO_ROOT / candidate).resolve()
            normalized = _repo_relative(_ensure_within_repo(resolved, label="allowed path"))
        if keeps_prefix and not normalized.endswith("/"):
            normalized += "/"
        if normalized not in seen:
            seen.add(normalized)
            allowed.append(normalized)
    return allowed


def _reject_forbidden_proposal_fields(value: Any, *, prefix: str = "proposal") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_str = str(key)
            if key_str in FORBIDDEN_PROPOSAL_FIELDS:
                raise ValueError(f"forbidden command-like field in proposal: {prefix}.{key_str}")
            _reject_forbidden_proposal_fields(child, prefix=f"{prefix}.{key_str}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_proposal_fields(child, prefix=f"{prefix}[{index}]")


def load_proposal(proposal_file: Path) -> dict[str, Any]:
    proposal_file = proposal_file.resolve()
    data = json.loads(proposal_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("proposal file must contain a JSON object")
    _reject_forbidden_proposal_fields(data)

    experiment_id = str(data.get("experiment_id") or "").strip()
    if not experiment_id:
        raise ValueError("proposal requires experiment_id")

    append_line = data.get("append_line")
    raw_patch_file = data.get("patch_file")
    if append_line is not None and raw_patch_file is not None:
        raise ValueError("proposal must choose either append_line or patch_file, not both")
    if append_line is not None and not isinstance(append_line, str):
        raise ValueError("proposal append_line must be a string")
    if raw_patch_file is not None and not isinstance(raw_patch_file, str):
        raise ValueError("proposal patch_file must be a string")

    mutable_artifact = _resolve_repo_file(
        str(data.get("mutable_artifact") or _repo_relative(DEFAULT_MUTABLE_ARTIFACT)),
        label="mutable_artifact",
    )
    patch_file = _resolve_patch_file(raw_patch_file, proposal_file=proposal_file) if raw_patch_file else None

    raw_allowed = data.get("allowed_paths")
    if raw_allowed is not None and not (
        isinstance(raw_allowed, list) and all(isinstance(item, str) for item in raw_allowed)
    ):
        raise ValueError("proposal allowed_paths must be a list of strings")
    allowed_paths = _normalize_allowed_paths(raw_allowed, mutable_artifact=mutable_artifact)
    metadata_keys = ("schema_version", "hypothesis", "author", "tool", "safety_notes")
    metadata = {key: data.get(key) for key in metadata_keys if data.get(key) not in (None, "")}
    metadata.setdefault("schema_version", PROPOSAL_SCHEMA_VERSION)
    metadata["proposal_file"] = str(proposal_file)

    return {
        "experiment_id": experiment_id,
        "allowed_paths": allowed_paths,
        "mutable_artifact": mutable_artifact,
        "append_line": append_line,
        "patch_file": patch_file,
        "proposal_metadata": metadata,
    }


def _completed_json(
    command: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def ensure_clean_worktree(*, allow_dirty: bool = False) -> None:
    if allow_dirty:
        return
    completed = ar._run(["git", "status", "--porcelain"], cwd=ar.REPO_ROOT)
    if completed.returncode != 0:
        raise RuntimeError(f"git status failed: {completed.stderr.strip()}")
    if completed.stdout.strip():
        raise RuntimeError("worktree is not clean; commit/stash changes or pass --allow-dirty for tests")


def restore_paths(paths: list[str]) -> None:
    for path in paths:
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError(f"refusing to restore non-repo-relative path: {path}")
        _ensure_within_repo(ar.REPO_ROOT / path, label="restore path")
        completed = ar._run(["git", "ls-files", "--error-unmatch", path], cwd=ar.REPO_ROOT)
        if completed.returncode == 0:
            ar._run(["git", "restore", "--staged", "--worktree", "--", path], cwd=ar.REPO_ROOT)
        else:
            target = ar.REPO_ROOT / path
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()


def apply_append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    separator = "" if existing.endswith("\n") or not existing else "\n"
    path.write_text(f"{existing}{separator}{line}\n", encoding="utf-8")


def apply_patch_file(patch_file: Path) -> None:
    completed = ar._run(["git", "apply", str(patch_file.resolve())], cwd=ar.REPO_ROOT)
    if completed.returncode != 0:
        raise RuntimeError(f"git apply failed: {completed.stderr.strip()}")


def _add_patch_path(paths: list[str], seen: set[str], raw: str) -> None:
    raw = raw.split("\t", 1)[0].strip()
    if raw == "/dev/null":
        return
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    if Path(raw).is_absolute() or ".." in Path(raw).parts:
        raise ValueError(f"patch path must be repo-relative: {raw}")
    if raw and raw not in seen:
        seen.add(raw)
        paths.append(raw)


def paths_from_patch(patch_file: Path) -> list[str]:
    """Return repo-relative paths touched by a unified git patch.

    Parse both content hunks (---/+++) and metadata-only git patches such as
    pure renames, which may contain only ``diff --git a/old b/new`` plus rename
    metadata. Cleanup must still know both paths so dry-runs cannot leak changes.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for line in patch_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                _add_patch_path(paths, seen, parts[2])
                _add_patch_path(paths, seen, parts[3])
            continue
        if line.startswith(("--- ", "+++ ")):
            _add_patch_path(paths, seen, line[4:])
    return paths


def _score_value(result: dict[str, Any]) -> float:
    try:
        return float(result["score"]["score"] if "score" in result and isinstance(result["score"], dict) else result["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing numeric score in result: {result}") from exc


def run_eval_for_experiment(
    *,
    label: str,
    manifest: Path,
    run_dir: Path,
    python_executable: str,
) -> dict[str, Any]:
    output = run_dir / f"{label}_report.json"
    workdir = run_dir / f"{label}_workdir"
    return ar.run_baseline(manifest, output, workdir, python_executable=python_executable)


def run_experiment(
    *,
    experiment_id: str,
    allowed_paths: list[str],
    mutable_artifact: Path,
    append_line: str | None,
    patch_file: Path | None,
    manifest: Path,
    ledger: Path,
    run_root: Path,
    python_executable: str,
    dry_run: bool = False,
    _allow_dirty: bool = False,
    proposal_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if bool(append_line) and patch_file is not None:
        raise ValueError("choose either --append-line or --patch-file, not both")
    if not dry_run and not append_line and patch_file is None:
        raise ValueError("non-dry-run experiments require --append-line or --patch-file")

    ensure_clean_worktree(allow_dirty=_allow_dirty)
    run_dir = (run_root / experiment_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    baseline = run_eval_for_experiment(
        label="baseline",
        manifest=manifest,
        run_dir=run_dir,
        python_executable=python_executable,
    )
    if not baseline.get("ok"):
        return {"ok": False, "status": "baseline_failed", "baseline": baseline}
    baseline_score = _score_value(baseline)

    changed_paths: list[str] = []
    runner_changed_paths: list[str] = []
    guard = {"ok": True, "changed_paths": [], "locked_violations": [], "outside_allowed_violations": []}
    candidate: dict[str, Any] | None = None
    candidate_score: float | None = None
    status = "rejected"
    accepted = False
    reason = "dry_run_no_mutation" if dry_run and not append_line and patch_file is None else "score_not_improved"

    try:
        if append_line:
            apply_append_line(mutable_artifact, append_line)
            runner_changed_paths = [_repo_relative(mutable_artifact)]
        elif patch_file is not None:
            runner_changed_paths = paths_from_patch(patch_file)
            apply_patch_file(patch_file)

        # Guard immediately after mutation and before running the candidate
        # evaluator. This keeps experiments from changing the answer key or
        # evaluator and then scoring themselves with the tainted evaluator.
        changed_paths = ar.collect_changed_paths("HEAD")
        guard = ar.evaluate_guard(changed_paths, allowed_paths)
        if not guard.get("ok"):
            reason = "guard_failed"
        else:
            candidate = run_eval_for_experiment(
                label="candidate",
                manifest=manifest,
                run_dir=run_dir,
                python_executable=python_executable,
            )
            if not candidate.get("ok"):
                reason = "candidate_eval_failed"
            candidate_score = _score_value(candidate) if candidate.get("ok") else float("-inf")

            if dry_run and (append_line or patch_file is not None):
                reason = "dry_run_reverted"
            elif candidate.get("ok") and candidate_score > baseline_score:
                accepted = True
                status = "accepted"
                reason = "score_improved"
            else:
                reason = "score_not_improved" if reason == "score_not_improved" else reason
    finally:
        if not accepted:
            restore_paths(runner_changed_paths)

    record = {
        "schema_version": "mobi-autoresearch-experiment-v1",
        "experiment_id": experiment_id,
        "status": status,
        "accepted": accepted,
        "reason": reason,
        "dry_run": dry_run,
        "baseline_score": baseline_score,
        "candidate_score": candidate_score,
        "score_delta": (
            round(candidate_score - baseline_score, 6) if candidate_score is not None and candidate_score != float("-inf") else None
        ),
        "allowed_paths": allowed_paths,
        "changed_paths": changed_paths,
        "runner_changed_paths": runner_changed_paths,
        "proposal": proposal_metadata,
        "guard": guard,
        "baseline": baseline,
        "candidate": candidate,
    }

    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def cmd_experiment(args: argparse.Namespace) -> int:
    proposal_metadata = None
    if args.proposal_file:
        if args.append_line or args.patch_file or args.allowed:
            raise ValueError("--proposal-file cannot be combined with --append-line, --patch-file, or --allowed")
        proposal = load_proposal(Path(args.proposal_file))
        experiment_id = proposal["experiment_id"]
        mutable_artifact = proposal["mutable_artifact"]
        allowed = proposal["allowed_paths"]
        append_line = proposal["append_line"]
        patch_file = proposal["patch_file"]
        proposal_metadata = proposal["proposal_metadata"]
    else:
        if not args.experiment_id:
            raise ValueError("--experiment-id is required unless --proposal-file is used")
        experiment_id = args.experiment_id
        mutable_artifact = Path(args.mutable_artifact)
        if not mutable_artifact.is_absolute():
            mutable_artifact = (ar.REPO_ROOT / mutable_artifact).resolve()
        allowed = args.allowed or [_repo_relative(mutable_artifact)]
        append_line = args.append_line
        patch_file = Path(args.patch_file) if args.patch_file else None
    result = run_experiment(
        experiment_id=experiment_id,
        allowed_paths=allowed,
        mutable_artifact=mutable_artifact,
        append_line=append_line,
        patch_file=patch_file,
        manifest=Path(args.manifest),
        ledger=Path(args.ledger),
        run_root=Path(args.run_root),
        python_executable=args.python,
        dry_run=args.dry_run,
        proposal_metadata=proposal_metadata,
    )
    ar._print_json(result)
    return 0 if result.get("status") in {"accepted", "rejected"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mobi AutoResearch experiment runner v1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    experiment = subparsers.add_parser("experiment", help="Run one controlled experiment")
    experiment.add_argument("--experiment-id")
    experiment.add_argument("--mutable-artifact", default=str(DEFAULT_MUTABLE_ARTIFACT))
    experiment.add_argument("--allowed", action="append", help="Allowed path. Defaults to mutable artifact.")
    experiment.add_argument("--append-line", help="Append one line to the mutable artifact as the candidate mutation.")
    experiment.add_argument("--patch-file", help="Apply a caller-provided git patch as the candidate mutation.")
    experiment.add_argument("--proposal-file", help="Read an approved agent proposal JSON file.")
    experiment.add_argument("--manifest", default=str(ar.DEFAULT_GOLDEN_SET_V2_MANIFEST))
    experiment.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    experiment.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    experiment.add_argument("--python", default=sys.executable)
    experiment.add_argument("--dry-run", action="store_true")
    experiment.set_defaults(func=cmd_experiment)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover - defensive CLI path
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
