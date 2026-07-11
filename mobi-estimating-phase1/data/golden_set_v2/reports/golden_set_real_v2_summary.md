# Golden Set v2 Real Drawing-Set Accuracy Report

_Generated: 2026-07-07_

This is the first Golden Set v2 run using complete public drawing/plan PDFs as the primary evaluated documents, with source-backed hand-read quantities recorded in `key_quantities`.

## Run command

```bash
/tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set_v2/manifest.real-v2.json \
  --output data/golden_set_v2/reports/golden_set_real_v2_report.json \
  --workdir data/golden_set_v2/workdirs/real-v2-pass \
  --no-fail-on-accuracy \
  --report-only-baseline
```

`--allow-missing-documents` was **not** used. `--no-fail-on-accuracy` was used intentionally with `--report-only-baseline` so the internal baseline command exits successfully while still preserving the accuracy failures in the report. This report is not release evidence.

## Aggregate results

| Metric | Result |
|---|---:|
| `project_count` | 3 |
| `evaluated_count` | 3 |
| `skipped_count` | 0 |
| `harness_failed_count` | 0 |
| `evaluation_passed_count` | 1 |
| `accuracy_failed_project_count` | 2 |
| `safety_violation_count` | 0 |
| `document_text_extraction_pass_count` | 3 |
| `document_text_extraction_fail_count` | 0 |
| `trade_recall_micro` | 0.3333 |
| `trade_expected_total` | 9 |
| `trade_matched_total` | 3 |
| `trade_false_positive_total` | 0 |
| `trade_unexpected_false_positive_total` | 0 |
| `scope_keyword_coverage_micro` | 0.3333 |
| `scope_keyword_expected_total` | 9 |
| `scope_keyword_found_total` | 3 |
| `key_quantity_total` | 9 |
| `key_quantity_pass_count` | 9 |
| `key_quantity_fail_count` | 0 |
| `key_quantity_unknown_count` | 0 |
| `key_quantity_evidence_pass_count` | 9 |
| `key_quantity_evidence_fail_count` | 0 |
| `benchmark_eligible_count` | 0 |
| `benchmark_ineligible_count` | 3 |

## Project-level results

| Project | Eval passed | Trade recall | Scope keyword coverage | Key quantities | Main failure |
|---|---:|---:|---:|---:|---|
| San Gorgonio Pass Perimeter Fence - Plans | True | 1.0 | 1.0 | 3/3 pass | none |
| Lot 50 Accessibility Upgrades & EVCS - Plans | False | 0.0 | 0.0 | 3/3 pass | expected_keywords_missing |
| DSH Administration and Annex Building Roof Replacement Patton - Plans | False | 0.0 | 0.0 | 3/3 pass | expected_keywords_missing |

## Measured quantity summary

### San Gorgonio Pass Perimeter Fence - Plans
- **Public parking stalls total**: expected `27 EA`; status `pass`; source `documents/ca_dgs_22_130586_plans.pdf`, `G01`, `PDF page 1`; evidence status `pass`; method: Read from cover sheet G01 parking calculation table.
- **EV charging stations total**: expected `7 EA`; status `pass`; source `documents/ca_dgs_22_130586_plans.pdf`, `G01`, `PDF page 1`; evidence status `pass`; method: Read from cover sheet G01 electric vehicle charging stations table.
- **Plan sheets in drawing set**: expected `19 EA`; status `pass`; source `documents/ca_dgs_22_130586_plans.pdf`, `G01`, `PDF page 1`; evidence status `pass`; method: Read from G01 sheet index count and verified with pdfinfo page count.

### Lot 50 Accessibility Upgrades & EVCS - Plans
- **Level 1A total parking stalls**: expected `58 EA`; status `pass`; source `documents/ca_dgs_24_253614_plans.pdf`, `C011`, `PDF page 4`; evidence status `pass`; method: Read from C011 Number of Stalls per Level table, Total Stalls row, 1A column.
- **Level GA Type 2 compact EVCS stalls**: expected `5 EA`; status `pass`; source `documents/ca_dgs_24_253614_plans.pdf`, `C011`, `PDF page 4`; evidence status `pass`; method: Read from C011 Type 2 EVCS table, Compact Size row, GA column.
- **Plan sheets in drawing set**: expected `20 EA`; status `pass`; source `documents/ca_dgs_24_253614_plans.pdf`, `G001`, `PDF page 1`; evidence status `pass`; method: Read from G001 sheet index count and verified with pdfinfo page count.

### DSH Administration and Annex Building Roof Replacement Patton - Plans
- **New roofing project area**: expected `19337 SF`; status `pass`; source `documents/ca_dgs_25_275745_plans.pdf`, `G001`, `PDF page 1`; evidence status `pass`; method: Read from G001 building information table.
- **Building area**: expected `21668 SF`; status `pass`; source `documents/ca_dgs_25_275745_plans.pdf`, `G001`, `PDF page 1`; evidence status `pass`; method: Read from G001 building information table.
- **Number of stories**: expected `3 EA`; status `pass`; source `documents/ca_dgs_25_275745_plans.pdf`, `G001`, `PDF page 1`; evidence status `pass`; method: Read from G001 building information table.

## Findings

- The harness completed on all 3 real drawing-set PDFs without missing documents or safety violations.
- All 9 source-backed key quantities passed because they are human verified and tracked with source sheet/page references.
- The current local extraction engine detected required trades/scope for the San Gorgonio fence plan, but detected **zero scope items** for the Lot 50 EVCS and Patton reroof image-heavy plan sets.
- This creates a real, useful baseline: current drawing-set OCR/text/scope extraction is not reliable enough for quantity/takeoff scoring on image-heavy plans.
- There were no unexpected false-positive trades in this v2 run because two weak-extraction projects emitted no scope items; future runs should enable strict unexpected false-positive gating as extraction improves.

## Next improvement priorities

1. Add OCR or vision-based sheet text extraction for scanned/image-heavy plan pages.
2. Extract cover-sheet tables and schedules into structured quantities before relying on downstream scope items.
3. Add geometry/takeoff support for scaled drawing measurements, then flip selected `require_engine_quantity` fields from `false` to `true`.
4. Audit Cal eProcure event packages to prove addenda completeness instead of only probing public DGS paths.
5. Tighten strict false-positive trade gating once recall is high enough to avoid suppressing useful failure signals.
