# Mobi Real-Test Batch Kit

This folder is the staging area for no-client real-PDF testing.

## Safety rule

Use only public, sample, internal-owned, or customer-authorized PDFs. Do not use login-only/private plan-room/paywalled/CAPTCHA documents unless Moses has explicit authorization for that source.

The real-test harness creates internal readiness reports only. It does not send customer messages, approve final estimates, create customer deliverables, process payments, or change production data.

## Folder layout

```text
real_tests/
  README.md
  batch-001/
    manifest.json          # PDF list and source metadata
    review-template.md     # Manual failure-pattern review sheet
    pdfs/                  # Put test PDFs here (ignored by git)
    reports/               # JSON/Markdown reports (ignored by git)
    workdir/               # Isolated local engine data (ignored by git)
```

## Start a new batch

From the engine folder:

```bash
cd /home/hermes/work/mobi-estimates/mobi-estimating-phase1
/tmp/mobi-estimating-venv/bin/python scripts/real_test_batch_manifest.py init real_tests/batch-002
```

Then add PDFs under `real_tests/batch-002/pdfs/` and edit `real_tests/batch-002/manifest.json`.

## Validate a batch

```bash
/tmp/mobi-estimating-venv/bin/python scripts/real_test_batch_manifest.py validate real_tests/batch-001/manifest.json --require-files
```

## Run a batch

```bash
/tmp/mobi-estimating-venv/bin/python scripts/real_test_batch_manifest.py run real_tests/batch-001/manifest.json
```

The runner writes:

- a machine-readable JSON report in `batch-001/reports/`
- a reviewer-friendly `.review.md` next to the JSON report
- per-PDF workdirs/reports under `batch-001/workdir/`

## What to look for first

1. `failed_count` should be `0` for pipeline reliability.
2. `customer_delivery_ready_count` must stay `0`.
3. `total_scope_items_missing_evidence_quote_count` shows explainability gaps.
4. `top_evidence_quote_gaps_by_trade` shows trades that need better source text capture.
5. `total_quantity_missing_count` and `formula_check_blocker_counts` show quantity/pricing blockers.

## Pass/partial/fail rule

| Grade | Meaning |
|---|---|
| Pass | PDFs process cleanly and reports explain scope/evidence/blockers clearly. |
| Partial | Pipeline runs, but obvious trades/evidence/quantity paths are weak. |
| Fail | PDF processing/reporting breaks or output is not useful. |

## Improvement loop

```text
Add public/authorized PDFs → run batch → review failure patterns → fix top blocker → rerun same batch → compare report
```
