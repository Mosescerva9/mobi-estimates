# Golden Set AutoResearch v1

_Last updated: 2026-07-07_

## Purpose

Mobi AutoResearch v1 is an internal/local harness for running Karpathy-style experiment loops against the Golden Set v2 evaluator.

It adds the missing control layer between:

- a **locked evaluator**: Golden Set v2 source PDFs, manifest, source log, and evaluator; and
- one **mutable experiment artifact**: a prompt, config, parser rule, OCR setting, or other controlled target.

The first real target is the Golden Set v2 blocker: image-heavy drawing PDFs that process successfully but produce zero scope items. AutoResearch should improve OCR/sheet text extraction, drawing table extraction, scope detection, trade classification, and quantity extraction before it touches pricing or customer-facing behavior.

## Safety and scope

This tool is internal testing only. It does not:

- deliver customer estimates;
- send external messages or email;
- process payments/refunds;
- change pricing/legal/DNS;
- issue proposals;
- deploy anything.

## Locked files

The guard rejects experiment diffs that change any of these evaluator/ground-truth paths:

```text
mobi-estimating-phase1/data/golden_set_v2/documents/
mobi-estimating-phase1/data/golden_set_v2/manifest.real-v2.json
mobi-estimating-phase1/data/golden_set_v2/sources.v2.json
mobi-estimating-phase1/scripts/golden_set_extraction_eval.py
```

The evaluator can still be intentionally improved in a separate normal PR, but not inside an AutoResearch experiment where the score is being judged.

## Commands

Run from the repo root unless noted.

### Run one controlled experiment

```bash
python3 mobi-estimating-phase1/scripts/mobi_autoresearch_runner.py experiment \
  --experiment-id first-dry-run \
  --mutable-artifact mobi-estimating-phase1/app/extraction/prompts/golden_set_v2_drawing_text_extraction.md \
  --append-line "Experiment hypothesis: recover sheet index and scope notes before classifying trades." \
  --ledger /tmp/mobi-autoresearch/experiments.jsonl \
  --run-root /tmp/mobi-autoresearch/runs \
  --python /tmp/mobi-estimating-venv/bin/python
```

The runner performs:

```text
baseline -> mutate one allowed artifact -> guard -> candidate eval -> score -> accept/reject -> ledger
```

It accepts only command-free local mutations (`--append-line`) or caller-provided patch files (`--patch-file`). It can also read an approved agent proposal JSON through `--proposal-file`; proposals only describe metadata and a patch/append-line candidate and cannot contain command-like fields. The runner does not call Claude/Codex by default, does not commit, does not deploy, and rejects experiments that touch locked evaluator/source paths before the candidate evaluator runs. Generated run outputs and the default ledger live under `/tmp/mobi-autoresearch/` so repeated local runs do not dirty the repo.

### Run an approved agent proposal

Proposal files let Claude/Codex/Hermes produce a candidate patch plus audit metadata while the runner remains the referee.

```json
{
  "schema_version": "mobi-autoresearch-proposal-v1",
  "experiment_id": "ocr-table-hypothesis-001",
  "hypothesis": "Improve drawing text extraction before trade classification.",
  "author": "Hermes",
  "tool": "claude-code",
  "safety_notes": "Local patch only; no commands, deploys, messages, or customer-facing changes.",
  "mutable_artifact": "mobi-estimating-phase1/app/extraction/prompts/golden_set_v2_drawing_text_extraction.md",
  "allowed_paths": ["mobi-estimating-phase1/app/extraction/prompts/"],
  "patch_file": "candidate.patch"
}
```

```bash
python3 mobi-estimating-phase1/scripts/mobi_autoresearch_runner.py experiment \
  --proposal-file /tmp/mobi-autoresearch/proposals/ocr-table-hypothesis-001.json \
  --ledger /tmp/mobi-autoresearch/experiments.jsonl \
  --run-root /tmp/mobi-autoresearch/runs \
  --python /tmp/mobi-estimating-venv/bin/python
```

Proposal JSON must not contain command-like fields such as `command`, `commands`, `shell`, `exec`, `run`, `script`, `entrypoint`, or `argv`. Patch paths may be relative to the proposal file directory. Repo paths are normalized and bounded to the repository before the existing guard/score/keep-revert path runs.

### Score an existing report

```bash
cd /home/hermes/work/mobi-estimates
python3 mobi-estimating-phase1/scripts/mobi_autoresearch.py score \
  --report mobi-estimating-phase1/data/golden_set_v2/reports/golden_set_real_v2_report.json \
  --output /tmp/mobi-autoresearch-score.json
```

### Run baseline Golden Set v2 eval and score it

```bash
python3 mobi-estimating-phase1/scripts/mobi_autoresearch.py baseline \
  --manifest mobi-estimating-phase1/data/golden_set_v2/manifest.real-v2.json \
  --output mobi-estimating-phase1/data/golden_set_v2/reports/autoresearch_baseline_report.json \
  --workdir mobi-estimating-phase1/data/golden_set_v2/workdirs/autoresearch-baseline \
  --python /tmp/mobi-estimating-venv/bin/python
```

The baseline subcommand runs `golden_set_extraction_eval.py` with `--no-fail-on-accuracy --report-only-baseline`. Command success means the report completed; extraction failures are still recorded in the report and score. This baseline mode is not release evidence, and it still fails when zero evaluated projects are benchmark-eligible.

### Guard an experiment diff

Example for an experiment that is allowed to edit only extraction prompt/config files:

```bash
python3 mobi-estimating-phase1/scripts/mobi_autoresearch.py guard \
  --base-ref HEAD~1 \
  --allowed mobi-estimating-phase1/app/extraction/
```

The guard fails if any changed path is outside the allowed path or under a locked evaluator/source path.

### Append an experiment ledger row

```bash
python3 mobi-estimating-phase1/scripts/mobi_autoresearch.py append-ledger \
  --ledger mobi-estimating-phase1/data/golden_set_v2/autoresearch/experiments.jsonl \
  --experiment-id baseline-001 \
  --score-json /tmp/mobi-autoresearch-score.json \
  --status baseline \
  --notes "Initial Golden Set v2 score"
```

Ledger records are JSONL so future loops can append accepted/rejected experiments without rewriting history.

## Score formula

```text
score =
  100 * scope_keyword_coverage_micro
+ 100 * trade_recall_micro
+  50 * key_quantity_pass_rate
+  25 * key_quantity_evidence_pass_rate
-  20 * trade_unexpected_false_positive_total
-1000 * safety_violation_count
- 100 * harness_failed_count
```

Quantity rates are denominator-safe. If a corpus has no key quantities, the quantity/evidence rate defaults to `1.0` so old trade-only corpora are not penalized for lacking quantity rows. That is a scoring convention only; it is not proof of takeoff accuracy.

## Intended first loop

1. Start from a clean branch.
2. Run baseline score.
3. Allow exactly one mutable target, such as an OCR/sheet-text extraction config.
4. Ask the agent to propose and implement one hypothesis.
5. Run Golden Set v2 eval and score.
6. Run guard.
7. If score improves and guard/safety pass, commit.
8. If score worsens, guard fails, or safety fails, reset.
9. Append the accepted/rejected result to the ledger.

## Current limitation

V1 now includes the first single-experiment runner, but it is still deliberately conservative. It can mutate one provided artifact, evaluate, score, guard, accept/reject, revert rejected changes, and write a ledger row. It does not yet autonomously invoke Claude/Codex or perform production merge/deploy decisions. Agent-driven experiment generation should be added only after this local runner proves stable.
