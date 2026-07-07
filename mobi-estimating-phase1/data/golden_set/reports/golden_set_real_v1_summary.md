# Golden Set Real v1 Accuracy Report

_Generated: 2026-07-07_

This is the first real-public-PDF run of Mobi's Golden Set extraction evaluation harness.

## Inputs

Manifest:

```text
data/golden_set/manifest.real-v1.json
```

Report JSON:

```text
data/golden_set/reports/golden_set_real_v1_report.json
```

Local PDFs:

```text
data/golden_set/documents/usc_s1459197637_project_manual.pdf
data/golden_set/documents/ca_dgs_22_130586_project_manual.pdf
data/golden_set/documents/norman_ruby_grant_park_specs_amendment_one.pdf
```

## Command run

```bash
cd /home/hermes/work/mobi-estimates/mobi-estimating-phase1
/tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set/manifest.real-v1.json \
  --output data/golden_set/reports/golden_set_real_v1_report.json \
  --workdir data/golden_set/workdirs/real-v1-pass
```

The real run did **not** use `--allow-missing-documents`.

The generated workdir was intentionally not committed because it contains generated SQLite/upload artifacts and rendered page files. It can be recreated by rerunning the command above.

## Aggregate result

| Metric | Value |
|---|---:|
| Projects in manifest | 3 |
| Evaluated projects | 3 |
| Skipped projects | 0 |
| Harness-failed projects | 0 |
| Evaluation-passed projects | 3 |
| Accuracy-failed projects | 0 |
| Safety violations | 0 |
| Benchmark-eligible projects | 0 |
| Benchmark-ineligible projects | 3 |
| Trade recall micro | 1.0 |
| Trade expected total | 9 |
| Trade matched total | 9 |
| Trade false-positive total | 36 |
| Scope keyword coverage micro | 1.0 |
| Scope keyword expected total | 9 |
| Scope keyword found total | 9 |
| Key quantity total | 0 |

## Interpretation

This proves the local harness can process three real public project-manual PDFs and produce a real Golden Set JSON report with no missing documents, no harness crashes, and safety locks closed.

It does **not** prove final estimating accuracy yet. The current run is a v1 extraction smoke/evaluation baseline because:

- the current engine path is automatic trade census + generic scope, not live OCR/vision/takeoff;
- the selected PDFs are project manuals/specifications, not complete measured drawing sets;
- every project is marked `addenda_complete: false`, so benchmark calibration is ineligible;
- no source-backed measured quantity schedule was available during v1 hand review, so `key_quantities` are intentionally omitted;
- the run produced 36 false-positive trade detections across 3 projects, which should be triaged before claiming strong scope accuracy.

## Immediate failure/weakness triage

| Weakness | Meaning | Next fix |
|---|---|---|
| `benchmark_ineligible_count = 3` | Full addenda/drawing completeness was not established. | Collect complete bid packages, addenda, and source completeness evidence. |
| `key_quantity_total = 0` | No source-backed measured quantity ground truth yet. | Add drawing sets and hand-measured quantities for 3–5 scope items per project. |
| `trade_false_positive_total = 36` | Engine detects many broad generic trade lanes. | Tighten automatic trade census scoring and add per-trade evidence/keyword thresholds. |
| Project-manual-heavy corpus | Mostly specs, limited takeoff value. | Add drawings/plans PDFs or combined plan/spec packages. |

## Next improvement priorities

1. Add complete drawing sets for the same or new public projects.
2. Hand-measure/source 3–5 key quantities per project.
3. Add per-trade expected/forbidden scope rules so false positives can fail separately from recall.
4. Make trade-census output include source evidence snippets in the Golden Set report.
5. Add a `--summarize-report` CLI mode to write this Markdown summary directly from the JSON report.
