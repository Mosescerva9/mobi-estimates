# Real Bid-Board Document Shakeout Guide

_Last updated: 2026-07-06_

This guide explains how to run real contractor bid-board PDFs through the local Mobi estimating engine harness and how to interpret the report.

The harness is for **local automation readiness testing only**. It does **not** send customer messages, create customer deliverables, process payments, approve estimates, or authorize final construction estimate delivery.

## Safety contract

Every harness report must preserve these flags:

```json
{
  "customer_delivery": false,
  "external_messages": false,
  "final_estimate_approval": false,
  "payments": false
}
```

If any harness output suggests a final estimate was approved, sent, delivered, billed, or externally messaged, treat that as a blocker and stop using the report until the issue is fixed.

## Before running

1. Put bid-board PDFs in a local folder the agent can read.
2. Use copies of documents, not production-only originals.
3. Do not include secrets, credentials, private customer passwords, or payment data in the folder.
4. Run from the engine directory:

```bash
cd /home/hermes/work/mobi-estimates/mobi-estimating-phase1
```

The harness creates an isolated SQLite DB and upload directory per run unless you pass `--workdir`.

## Single PDF command

Use this for one bid-board plan/spec PDF:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/real_document_harness.py /path/to/project.pdf --project-name "Bid Board Test" --output /tmp/mobi-real-doc-report.json
```

Optional: add fictional local test inputs to exercise readiness flow after blockers are generated:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/real_document_harness.py /path/to/project.pdf --project-name "Bid Board Test" --apply-test-inputs --output /tmp/mobi-real-doc-report.json
```

`--apply-test-inputs` uses explicitly fictional quantity/pricing values such as `harness_test_only_quantity` and `harness_test_only_pricing`. These values are only for smoke testing readiness transitions. They are **not** market pricing, not a contractor estimate, and not customer-ready.

## Batch folder command

Use this for a folder of bid-board PDFs. The runner discovers `.pdf`, `.PDF`, and mixed-case PDF suffixes recursively.

```bash
/tmp/mobi-estimating-venv/bin/python scripts/bid_board_batch_shakeout.py /path/to/bid-board-folder --output /tmp/mobi-batch-report.json
```

Optional limit:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/bid_board_batch_shakeout.py /path/to/bid-board-folder --limit 5 --output /tmp/mobi-batch-report.json
```

Optional stop on first failed PDF:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/bid_board_batch_shakeout.py /path/to/bid-board-folder --stop-on-failure --output /tmp/mobi-batch-report.json
```

Optional apply fictional test inputs to every PDF:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/bid_board_batch_shakeout.py /path/to/bid-board-folder --apply-test-inputs --output /tmp/mobi-batch-report.json
```

## Exit codes

- Exit code `0`: every processed stage/PDF reported success.
- Exit code `1`: at least one stage or PDF failed, or the batch runner found no usable PDF input.

When a PDF is processed and a stage/PDF fails, the harness writes the JSON report before returning failure so the report can be inspected. If the batch runner finds no PDF files at all, it exits before creating a report because there was no project/document run to summarize.

## Report locations

Single PDF:

- The output path is whatever you pass to `--output`.
- If omitted, the report is written inside the generated workdir.

Batch:

- Aggregate report: `--output` path or `bid_board_batch_shakeout_report.json` inside the workdir.
- Per-PDF reports: `workdir/reports/pdf_###_report.json`.
- Per-PDF isolated engine data: `workdir/pdf_###/`.

## Key single-PDF report sections

| Path | Meaning |
|---|---|
| `safety` | Confirms no delivery/message/payment/final approval action occurred. |
| `project_id` | Local engine project id for this run. |
| `stages` | Raw per-stage API responses and status codes. |
| `summary.stage_count` | Number of stages attempted. |
| `summary.failed_stage_count` | Number of stages that failed. Must be `0` for a clean shakeout. |
| `summary.failed_stages` | Machine-readable list of failed stages and messages. |
| `summary.outputs` | Condensed readiness/extraction/clarification metrics. |

## Key output metrics

| Field | What it tells us |
|---|---|
| `sheet_count` | How many sheets/pages were processed. |
| `scope_item_count` | How many scope items the automation created. |
| `generic_pricing_scope_item_count` | Generic/all-trade scope items included in pricing readiness metrics. |
| `pricing_method_assigned_count` | Items assigned a deterministic pricing method such as unit-rate, quote-based, or allowance. |
| `pricing_method_unassigned_count` | Generic items still missing a pricing method assignment. |
| `pricing_ready_scope_item_count` | Items with a verified pricing basis recorded. |
| `pricing_not_ready_scope_item_count` | Items still blocked from pricing. |
| `priced_scope_item_count` | Items with a pricing-basis payload. These are not final estimate lines. |
| `unpriced_scope_item_count` | Items missing a pricing-basis payload. |
| `pricing_method_counts` | Count by pricing method. |
| `missing_quantity_pricing_blocker_count` | Items blocked because a quantity is still missing. |
| `missing_unit_rate_pricing_blocker_count` | Unit-rate items blocked by missing verified rate. |
| `missing_subcontract_quote_pricing_blocker_count` | Quote-based items blocked by missing verified quote. |
| `missing_allowance_basis_pricing_blocker_count` | Allowance items blocked by missing documented allowance basis. |
| `coverage_finding_count` | Trade-coverage findings that may affect scope completeness. |
| `scope_items_with_trusted_evidence_count` | Scope items backed by verified evidence. |
| `scope_items_missing_trusted_evidence_count` | Scope items missing trusted evidence; high count means not ready. |
| `low_confidence_item_count` | Scope items with low or missing extraction confidence. |
| `quantity_basis_unclear_count` | Scope items with unclear quantity basis. |
| `assumption_count` | Structured assumptions in the BOE/register. |
| `exclusion_count` | Structured exclusions in the BOE/register. |
| `open_question_count` | Open questions requiring clarification. |
| `register_blocking_entry_count` | Assumption/register entries that block readiness. |
| `clarification_candidate_count` | Internal candidate questions generated from blockers/open questions. |
| `blocking_clarification_candidate_count` | Candidate questions tied to delivery/readiness blockers. |
| `urgent_clarification_candidate_count` | Highest-priority questions to resolve first. |
| `high_clarification_candidate_count` | Important questions that should be resolved early. |
| `top_clarification_candidate_ids` | Stable candidate ids for the top questions in the report. |
| `top_clarification_groups_by_trade` | Top blocker/question groups by trade. |
| `top_clarification_groups_by_source_code` | Top blocker/question groups by source code, e.g. missing quantity/provenance. |
| `readiness_status` | `ready_for_owner_review`, `blocked`, or another internal readiness state. |
| `owner_review_status` | Internal owner-review packet status. Not customer delivery status. |
| `customer_delivery_ready` | Must remain `false` in the current test harness. |
| `clarification_customer_message_ready` | Must remain `false`; no external message is ready to send. |
| `clarification_send_ready` | Must remain `false`; no send action is authorized. |

## How to interpret readiness

### Clean infrastructure run

A clean infrastructure run has:

```text
summary.failed_stage_count = 0
summary.stage_success_rate = 1
```

That only means the pipeline ran successfully. It does **not** mean the estimate is complete or customer-ready.

### Blocked estimating run

A normal early real-document run may have:

```text
readiness_status = blocked
customer_delivery_ready = false
open_question_count > 0
clarification_candidate_count > 0
```

That is acceptable during development. It means the system is surfacing missing/uncertain data instead of guessing.

### Candidate prioritization

Use the clarification fields in this order:

1. `urgent_clarification_candidate_count`
2. `high_clarification_candidate_count`
3. `top_clarification_groups_by_source_code`
4. `top_clarification_groups_by_trade`
5. `top_clarification_candidate_ids`

Example interpretation:

```json
"top_clarification_groups_by_source_code": [
  {"key": "missing_quantity", "count": 8, "blocking_count": 8, "highest_priority_score": 150},
  {"key": "missing_extraction_provenance", "count": 5, "blocking_count": 5, "highest_priority_score": 141}
]
```

This means the current best next action is not final estimate generation. It is to improve or provide quantity/provenance inputs for the affected scope.

## Batch report interpretation

Batch summary fields roll up all processed PDFs:

| Field | Meaning |
|---|---|
| `pdf_count` | PDFs discovered/processed. |
| `ok_count` | PDFs with no failed stages. |
| `failed_count` | PDFs with failed stages or harness errors. |
| `blocked_readiness_count` | PDFs where readiness is blocked. |
| `customer_delivery_ready_count` | Must be `0` in the current safety-gated harness. |
| `total_scope_item_count` | Total generated scope items across PDFs. |
| `total_generic_pricing_scope_item_count` | Total generic scope items included in pricing readiness. |
| `total_pricing_ready_scope_item_count` | Total scope items with verified pricing basis. |
| `total_pricing_not_ready_scope_item_count` | Total scope items still blocked from pricing. |
| `total_unpriced_scope_item_count` | Total items missing pricing-basis payloads. |
| `total_missing_quantity_pricing_blocker_count` | Total pricing blockers caused by missing quantities. |
| `total_missing_unit_rate_pricing_blocker_count` | Total missing verified unit-rate blockers. |
| `total_missing_subcontract_quote_pricing_blocker_count` | Total missing quote blockers. |
| `total_missing_allowance_basis_pricing_blocker_count` | Total missing allowance-basis blockers. |
| `total_clarification_candidate_count` | Total internal clarification questions generated. |
| `total_urgent_clarification_candidate_count` | Total urgent clarification items across PDFs. |
| `total_high_clarification_candidate_count` | Total high-priority clarification items across PDFs. |

For real bid-board shakeouts, the most useful first pass is:

1. Confirm `failed_count`.
2. Inspect failed PDF reports first.
3. For successful but blocked PDFs, sort by urgent/high clarification counts.
4. Inspect top groups by source code/trade.
5. Decide whether the next engineering task is extraction, quantity derivation, pricing input, or customer clarification flow.

## What to send back for debugging

For a failed or blocked real-document run, provide:

- The aggregate JSON report.
- The per-PDF report JSON for the PDF being discussed.
- The PDF name/path, not private credentials.
- The top failed stage name or top clarification source-code group.
- Whether `--apply-test-inputs` was used.

Do **not** send API keys, passwords, Stripe/Supabase secrets, or payment information.

## What “ready for real-document testing” means

The system can start real-document testing when:

- Real PDFs are available locally.
- The single/batch harness commands run.
- Reports are written even on failures.
- Safety flags remain false.
- Blockers/clarifications are understandable enough to drive the next engineering pass.

The system is **not ready for customer-facing final estimate delivery** until the full estimate/proposal path is proven, output contracts are customer-safe, and explicit approval is given for delivery behavior.
