# Golden Set v1 Real Public PDF Corpus

_Last updated: 2026-07-07_

This folder contains the first real public/authorized bid-document corpus for Mobi's Golden Set extraction evaluation harness.

## Safety / authorization

- Source class: public official agency/university/government PDF URLs.
- Use: internal testing only.
- Robots: checked before download; all selected source URLs were allowed for the Mobi internal-testing user agent at download time.
- No login, paywall, CAPTCHA bypass, form submission, customer data, private bid-board invitation data, bid outcomes, payments, messages, or customer deliverables were used.
- The manifest keeps `outcome_paths: []`; the v1 harness rejects populated outcome paths to prevent outcome leakage into extraction scoring.

## Files

| Project ID | Local PDF | Source | Notes |
|---|---|---|---|
| `usc-project-manual-s1459197637` | `documents/usc_s1459197637_project_manual.pdf` | University of South Carolina Purchasing | Longstreet Theatre Exterior Restoration project manual. Contains concrete and painting/coatings scope language. |
| `ca-dgs-22-130586-project-manual` | `documents/ca_dgs_22_130586_project_manual.pdf` | California DGS / CHP | San Gorgonio Pass Perimeter Fence project manual. Contains concrete and painting-related specification language. |
| `norman-ruby-grant-park-specs-amendment-one` | `documents/norman_ruby_grant_park_specs_amendment_one.pdf` | City of Norman, OK | Ruby Grant Park sealed bid specifications and contract documents, Amendment One. Contains cast-in-place concrete, painting, and exterior coatings sections. |

Full source metadata, robots URLs, content type, byte counts, and SHA256 values are in:

```text
sources.json
```

The real manifest is:

```text
manifest.real-v1.json
```

## Ground truth status

This is a **v1 extraction smoke/evaluation corpus**, not a final benchmark set.

Hand review confirmed that each project manual contains public construction bid/project-manual content and painting/concrete-related specification language. However, the downloaded documents are project manuals/specifications, not complete measured drawing sets with clean takeoff schedules. Therefore:

- expected trades are filled for the currently enabled local harness lanes: `painting`, `demo_concrete`, and `general_trade`;
- expected scope keywords are filled to exercise current extraction output matching;
- `key_quantities` are intentionally omitted for v1 because no reliable source-measured quantity schedule was found during hand review;
- every project is currently `addenda_complete: false`, so benchmark calibration is marked ineligible until full addenda/drawings are collected.

## Reproduce the real run

From the engine directory:

```bash
cd /home/hermes/work/mobi-estimates/mobi-estimating-phase1
mkdir -p data/golden_set/reports data/golden_set/workdirs
/tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set/manifest.real-v1.json \
  --output data/golden_set/reports/golden_set_real_v1_report.json \
  --workdir data/golden_set/workdirs/real-v1
```

Do **not** use `--allow-missing-documents` for the real run.

## Known limitations

- The current engine harness uses the offline mock extraction provider by default. It proves the pipeline can process real PDFs and score expected output, but it does not yet prove live OCR/vision/takeoff accuracy.
- The current real corpus is project-manual/specification-heavy. The next corpus should add complete drawing sets and source-measured quantity ground truth.
- Current projects are benchmark-ineligible because full addenda completeness was not established.
- Quantity scoring remains `0` until the manifest adds source-backed measured key quantities.
