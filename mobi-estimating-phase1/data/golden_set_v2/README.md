# Golden Set v2 Real Drawing Corpus

_Last updated: 2026-07-07_

This folder contains the first Golden Set v2 corpus for Mobi's real drawing-set / measured-quantity evaluation.

## Purpose

Golden Set v1 proved the local harness could run real public PDFs and produce a safe extraction report. Golden Set v2 moves the evaluation closer to real estimating work by adding:

- complete drawing/plan PDFs as the primary evaluated documents
- matching project manuals and known addenda when found
- source logs with public access notes and SHA-256 hashes
- 3 source-backed hand-read quantities per project
- sheet/page references, evidence snippets, assumptions, and confidence levels
- report fields for OCR/text extraction, sheet detection, trade classification, quantity extraction, unit normalization, evidence quality, and hallucinated/unsupported trade outputs

## Corpus

| Project | Primary plan PDF | Supporting docs | Addenda status | Hand-read quantities |
|---|---|---|---|---|
| San Gorgonio Pass Perimeter Fence | `documents/ca_dgs_22_130586_plans.pdf` | project manual + Addendum 1 | Addendum 1 saved; package still marked incomplete until full Cal eProcure event audit | public parking count, EV charging station count, drawing sheet count |
| Lot 50 Accessibility Upgrades & EVCS | `documents/ca_dgs_24_253614_plans.pdf` | project manual | no addenda found by direct public-folder probes; marked incomplete | Level 1A stall count, Type 2 EVCS compact stall count, drawing sheet count |
| DSH Administration and Annex Building Roof Replacement Patton | `documents/ca_dgs_25_275745_plans.pdf` | project manual | no addenda found by direct public-folder probes; marked incomplete | new roofing area, building area, number of stories |

All documents are official California Department of General Services public PDFs downloaded from public `dgs.ca.gov` URLs. See `sources.v2.json` for source URLs, hashes, byte sizes, access notes, and robots checks.

## Important limitations

- The v2 quantities are hand-read from plan cover sheets/tables and verified by visual review. They are not yet independent takeoff measurements from scaled geometry.
- `evidence_verified=true` records that a human reviewed the source sheet/page reference. Some plan PDFs have weak embedded text extraction, so exact evidence snippets may not always be discoverable by `pdftotext`.
- `require_engine_quantity=false` is intentional for this first v2 baseline. It allows the report to separate verified ground truth from current engine quantity limitations. Future v2/v3 cycles should flip selected quantities to `true` once the extraction pipeline can reliably emit measured quantities.
- All projects are conservatively marked `addenda_complete=false` until Cal eProcure event packages are audited end-to-end.
- This corpus is internal testing only. It must not be used to deliver customer estimates or marketing accuracy claims.

## Manifest

```text
manifest.real-v2.json
```

Each project includes:

- `document_paths`: primary plan PDF first, then project manual/addenda
- `expected_trades`
- `allowed_extra_trades`
- `expected_scope_keywords`
- `addenda_complete` and `addenda_notes`
- `ground_truth_scope_notes`
- `key_quantities`

Each `key_quantities[]` item includes:

- `item_name` / `label`
- `trade`
- `expected_value`
- `unit`
- `source_document`
- `sheet_ref`
- `page_ref`
- `evidence_snippet`
- `evidence_verified`
- `measurement_method`
- `confidence_level`
- `assumptions` when needed
- `require_engine_quantity`
- tolerance (`tolerance_abs` or `tolerance_pct`)

## Running the v2 eval

From `mobi-estimating-phase1`:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set_v2/manifest.real-v2.json \
  --output data/golden_set_v2/reports/golden_set_real_v2_report.json \
  --workdir data/golden_set_v2/workdirs/real-v2 \
  --no-fail-on-accuracy \
  --report-only-baseline
```

Do **not** use `--allow-missing-documents` for real v2 evaluation. `--no-fail-on-accuracy` is allowed only with `--report-only-baseline` for the current internal baseline: the report can be written while extraction accuracy failures remain visible. This is not release evidence, and zero benchmark-eligible evaluated projects still fail the command.

## Ignored/generated files

Generated local debugging artifacts are ignored and can be regenerated:

```text
workdirs/
text_extracts/
previews/
```

The committed source of truth is the PDFs, manifest, source log, reports, and docs.
