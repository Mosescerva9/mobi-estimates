# Real Bid-Board Document Shakeout Guide

_Last updated: 2026-07-07_

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

1. Put bid-board PDFs in a local folder the agent can read. If you need public-source seed PDFs, use [`public-bid-board-pdf-collector.md`](public-bid-board-pdf-collector.md) to discover/import SAM.gov and allowlisted public agency bid documents safely.
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

## Real-test batch kit

Use the committed starter kit when creating repeatable no-client test batches:

```bash
cd /home/hermes/work/mobi-estimates/mobi-estimating-phase1
/tmp/mobi-estimating-venv/bin/python scripts/real_test_batch_manifest.py init real_tests/batch-001 --force
```

Then place public/authorized PDFs under `real_tests/batch-001/pdfs/`, edit `real_tests/batch-001/manifest.json`, validate it, and run it:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/real_test_batch_manifest.py validate real_tests/batch-001/manifest.json --require-files
/tmp/mobi-estimating-venv/bin/python scripts/real_test_batch_manifest.py run real_tests/batch-001/manifest.json
```

The manifest helper blocks source classes that are not approved for autonomous testing (`private_planroom`, `login_required`, `paywalled`, `captcha`, `unknown`) and writes both JSON and reviewer-friendly Markdown reports.

## Batch folder command

Use this lower-level command for a folder of bid-board PDFs when you do not need manifest/source metadata. The runner discovers `.pdf`, `.PDF`, and mixed-case PDF suffixes recursively.

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
| `document_source_type_counts` | Pages grouped as `drawing`, `spec_or_schedule`, or `unknown` from current sheet title/number signals. This helps triage whether a PDF is mostly drawings, specs, or mixed. |
| `sheet_processing_status_counts` | Sheet processing state counts, useful for spotting failed page extraction before estimating logic. |
| `sheet_requires_ocr_count` | Pages requiring OCR/text recovery. High values mean extraction quality may be provider/OCR-limited. |
| `sheet_requires_review_count` | Pages whose sheet identity/title/number needs review. |
| `sheet_detection_confidence_min` / `avg` / `max` | Sheet-number/title detection confidence range. Low values mean source identification may be unreliable. |
| `scope_item_count` | How many scope items the automation created. |
| `generic_pricing_scope_item_count` | Generic/all-trade scope items included in pricing readiness metrics. |
| `pricing_method_assigned_count` | Items assigned a deterministic pricing method such as unit-rate, quote-based, or allowance. |
| `pricing_method_unassigned_count` | Generic items still missing a pricing method assignment. |
| `pricing_ready_scope_item_count` | Items with a verified pricing basis recorded. |
| `pricing_not_ready_scope_item_count` | Items still blocked from pricing. |
| `priced_scope_item_count` | Items with a pricing-basis payload. These are not final estimate lines. |
| `unpriced_scope_item_count` | Items missing a pricing-basis payload. |
| `pricing_method_counts` | Count by pricing method. |
| `formula_check_scope_item_count` | Generic scope items evaluated for deterministic formula/check readiness. |
| `formula_check_ready_count` | Items whose pricing method maps to a supported deterministic check **and** have a clear, non-test quantity. Readiness signal only — not a final quantity, rate, price, or customer deliverable. |
| `formula_check_blocked_count` | Items blocked from a deterministic check (missing quantity, unclear basis, test-only quantity, or unsupported/unassigned method). |
| `formula_check_ready_rate` | Share of evaluated items that are formula/check ready. |
| `formula_check_method_counts` | Count of evaluated items by pricing method (`unassigned` for generic scope with no method). |
| `formula_check_blocker_counts` | Count of formula/check blockers by reason: `missing_quantity`, `unclear_quantity_basis`, `test_quantity_only`, `unsupported_pricing_method`. |
| `formula_check_by_trade` | Per-trade formula/check readiness, sorted by blocked count: ready, blocked, and test-only-input counts. |
| `generic_estimate_draft_ready_scope_item_count` | Ready generic scope items converted into internal draft estimate lines. |
| `generic_estimate_draft_blocked_scope_item_count` | Generic scope items excluded from the draft estimate because blockers remain. |
| `generic_estimate_draft_line_item_count` | Internal draft estimate line count. These are not approved/final customer proposal lines. Draft line items may carry `generic_cost_components_v1` component JSON for labor/material/equipment/subcontract/other direct plus overhead/profit/contingency/markup metadata. |
| `generic_estimate_draft_customer_delivery_ready` | Must remain `false`. |
| `generic_estimate_draft_final_estimate_approved` | Must remain `false`. |
| `generic_estimate_draft_external_messages` | Must remain `false`. |
| `generic_estimate_draft_payments` | Must remain `false`. |
| `generic_proposal_preview_scope_line_count` | Customer-safe preview line count generated from the internal generic draft estimate. Preview only; not a final proposal. |
| `generic_proposal_preview_blocked_scope_item_count` | Scope items still blocked/clarification-needed in the preview summary. |
| `generic_proposal_preview_customer_delivery_ready` | Must remain `false`. |
| `generic_proposal_preview_final_estimate_approved` | Must remain `false`. |
| `generic_proposal_preview_external_messages` | Must remain `false`. |
| `generic_proposal_preview_payments` | Must remain `false`. |
| `generic_proposal_preview_proposal_created` | Must remain `false`; preview does not create proposal records. |
| `generic_proposal_preview_proposal_issued` | Must remain `false`; preview does not issue proposal versions. |
| `missing_quantity_pricing_blocker_count` | Items blocked because a quantity is still missing. |
| `missing_unit_rate_pricing_blocker_count` | Unit-rate items blocked by missing verified rate. |
| `missing_subcontract_quote_pricing_blocker_count` | Quote-based items blocked by missing verified quote. |
| `missing_allowance_basis_pricing_blocker_count` | Allowance items blocked by missing documented allowance basis. |
| `coverage_finding_count` | Trade-coverage findings that may affect scope completeness. |
| `scope_items_with_trusted_evidence_count` | Scope items backed by verified evidence. |
| `scope_items_missing_trusted_evidence_count` | Scope items missing trusted evidence; high count means not ready. |
| `scope_items_with_evidence_quote_count` | Scope items whose detail evidence includes at least one exact extracted drawing-text quote for reviewer inspection. |
| `scope_items_missing_evidence_quote_count` | Scope items with no captured evidence quote; inspect these first when a real-test result is hard to explain. |
| `evidence_quote_count` | Total captured source quotes across scope-item evidence refs. |
| `evidence_human_verification_required_count` | Evidence refs explicitly marked as requiring human verification. |
| `evidence_quote_coverage_rate` | Share of scope items backed by at least one visible source quote. |
| `evidence_quote_by_trade` | Trade-level evidence-quote gaps, sorted by missing-quote count, so real-test reviewers can see which trades lack explainable source text. |
| `low_confidence_item_count` | Scope items with low or missing extraction confidence. |
| `quantity_basis_unclear_count` | Scope items with unclear quantity basis. |
| `trusted_evidence_coverage_rate` | Share of scope items backed by trusted verified-sheet evidence. |
| `trade_quality_summary` | Top trade-level weak spots, sorted by quality blockers: missing trusted evidence, low confidence, unclear quantity basis, and open blocking issues. Use this to prioritize first real-PDF fixes by trade. |
| `quantity_scope_item_count` | Scope items included in quantity-confidence scoring. |
| `quantity_present_count` | Scope items with a quantity value. |
| `quantity_missing_count` | Scope items missing a quantity value. |
| `quantity_traceable_count` | Scope items with a quantity and clear non-test quantity basis/source. |
| `quantity_unclear_basis_count` | Scope items with a quantity but unclear/unknown basis. |
| `quantity_test_input_count` | Scope items whose quantity came from fictional harness test inputs; useful for smoke tests but not real estimating readiness. |
| `open_quantity_requirement_count` | Quantity requirements still open after the selected stage set. |
| `resolved_quantity_requirement_count` | Quantity requirements resolved after the selected stage set. |
| `quantity_traceable_rate` | Share of scope items with traceable non-test quantities. |
| `quantity_confidence_by_trade` | Trade-level quantity weak spots sorted by missing/unclear/test quantities. |
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

## Generic formula/check readiness

The harness reports a deterministic formula/check readiness signal for common generic pricing scopes. It maps a supported pricing method to the check that would need to be satisfied before pricing, and confirms the item has a clear, non-test quantity to run that check against. Supported mappings:

| Pricing method | Formula/check | Meaning |
|---|---|---|
| `unit_rate_needed` | `quantity_times_unit_rate_check` | Quantity × verified unit rate. |
| `quote_based` | `lump_sum_or_scope_quantity_check` | Lump-sum/subcontract quote against defined scope quantity. |
| `allowance` | `allowance_basis_check` | Documented allowance basis for the scope. |

Any other method — unknown, unsupported, or an unassigned generic scope item — stays blocked with `unsupported_pricing_method` and is never reported as ready. Items are also blocked when the quantity is missing (`missing_quantity`), the quantity basis is unclear/unknown (`unclear_quantity_basis`), or the quantity came from fictional harness inputs (`test_quantity_only`).

**A `formula_check_ready` item is only a readiness signal.** It means the deterministic check *could* run once a real, verified quantity and pricing input exist. It is **not** a computed quantity, rate, price, approved estimate, or customer deliverable, and it does not authorize proposal issuance, external messages, billing, or payments. Ready items that depend on `harness_test_only_*` inputs are deliberately reported as blocked, not ready.

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

## Previewing test bid-package output

The harness can now create two separate internal/test artifacts when `--apply-test-inputs` is used:

1. `generic_estimate_draft_after_test_inputs` — an internal draft estimate/version with draft line items from ready generic scope.
2. `generic_proposal_preview_after_test_inputs` — a read-only `customer_safe_preview` from that draft version.

The preview is useful for checking whether scope, assumptions, exclusions, and clarifications can be shaped into a contractor-facing structure. It is **not** an issued proposal, not a final estimate, and not authorized for customer delivery.

To inspect it in a single-PDF report:

```bash
python - <<'PY'
import json
report = json.load(open('/tmp/mobi-real-doc-report.json'))
preview = report['stages']['generic_proposal_preview_after_test_inputs']['body']['customer_safe_preview']
print(json.dumps(preview, indent=2))
PY
```

The preview contract must not include internal cost/margin/rate/source/readiness/reviewer fields. If any of these appear in preview text, treat the run as blocked and fix the output contract before using the preview again.

### Approved-proposal exports are different

The existing proposal export endpoints are for approved estimate versions and proposal versions only:

```text
GET /api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.json
GET /api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.md
GET /api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.html
```

Those exports are still gated by the approved-estimate/proposal workflow. The generic draft preview endpoint does not create proposal records and does not issue proposal versions.

Before any test bid-package preview or export is shared outside the local engineering workflow, confirm all of these remain locked:

```text
customer_delivery_ready = false
final_estimate_approved = false
external_messages = false
payments = false
proposal_created = false
proposal_issued = false
```

## Batch report interpretation

Batch summary fields roll up all processed PDFs:

| Field | Meaning |
|---|---|
| `pdf_count` | PDFs discovered/processed. |
| `ok_count` | PDFs with no failed stages. |
| `failed_count` | PDFs with failed stages or harness errors. |
| `blocked_readiness_count` | PDFs where readiness is blocked. |
| `customer_delivery_ready_count` | Must be `0` in the current safety-gated harness. |
| `document_source_type_counts` | Batch-level drawing/spec/unknown source mix. |
| `sheet_processing_status_counts` | Batch-level sheet processing state counts. |
| `total_sheet_requires_ocr_count` | Total pages needing OCR/text recovery. |
| `total_sheet_requires_review_count` | Total pages needing sheet identity/title/number review. |
| `avg_sheet_detection_confidence` | Average of per-PDF sheet detection confidence averages. |
| `total_scope_item_count` | Total generated scope items across PDFs. |
| `total_generic_pricing_scope_item_count` | Total generic scope items included in pricing readiness. |
| `total_pricing_ready_scope_item_count` | Total scope items with verified pricing basis. |
| `total_pricing_not_ready_scope_item_count` | Total scope items still blocked from pricing. |
| `total_unpriced_scope_item_count` | Total items missing pricing-basis payloads. |
| `total_formula_check_scope_item_count` | Total generic scope items evaluated for formula/check readiness. |
| `total_formula_check_ready_count` | Total items that are formula/check ready. Readiness signal only; not final pricing or delivery. |
| `total_formula_check_blocked_count` | Total items blocked from a deterministic check. |
| `avg_formula_check_ready_rate` | Average per-PDF formula/check ready rate. |
| `formula_check_method_counts` | Batch-level count of evaluated items by pricing method. |
| `formula_check_blocker_counts` | Batch-level count of formula/check blockers by reason. |
| `top_formula_check_by_trade` | Batch-level trade formula/check weak spots sorted by blocked count. |
| `total_generic_estimate_draft_line_item_count` | Total internal generic draft estimate lines created. |
| `total_generic_estimate_draft_ready_scope_item_count` | Total ready generic scope items included in draft estimates. |
| `total_generic_estimate_draft_blocked_scope_item_count` | Total generic scope items blocked from draft estimate lines. |
| `generic_estimate_draft_customer_delivery_ready_count` | Must be `0`. |
| `generic_estimate_draft_final_estimate_approved_count` | Must be `0`. |
| `generic_estimate_draft_external_messages_count` | Must be `0`. |
| `generic_estimate_draft_payments_count` | Must be `0`. |
| `total_generic_proposal_preview_scope_line_count` | Total customer-safe internal preview lines generated from generic draft estimates. |
| `total_generic_proposal_preview_blocked_scope_item_count` | Total blocked scope items summarized in internal previews. |
| `generic_proposal_preview_customer_delivery_ready_count` | Must be `0`. |
| `generic_proposal_preview_final_estimate_approved_count` | Must be `0`. |
| `generic_proposal_preview_external_messages_count` | Must be `0`. |
| `generic_proposal_preview_payments_count` | Must be `0`. |
| `generic_proposal_preview_proposal_created_count` | Must be `0`. |
| `generic_proposal_preview_proposal_issued_count` | Must be `0`. |
| `total_missing_quantity_pricing_blocker_count` | Total pricing blockers caused by missing quantities. |
| `total_missing_unit_rate_pricing_blocker_count` | Total missing verified unit-rate blockers. |
| `total_missing_subcontract_quote_pricing_blocker_count` | Total missing quote blockers. |
| `total_missing_allowance_basis_pricing_blocker_count` | Total missing allowance-basis blockers. |
| `total_coverage_finding_count` | Total trade-coverage findings across PDFs. |
| `total_scope_items_missing_trusted_evidence_count` | Total scope items missing trusted evidence. |
| `total_scope_items_with_evidence_quote_count` | Total scope items across PDFs with at least one visible source quote. |
| `total_scope_items_missing_evidence_quote_count` | Total scope items across PDFs without a visible source quote. |
| `total_evidence_quote_count` | Total source quotes captured across all scope-item evidence refs. |
| `total_evidence_human_verification_required_count` | Total evidence refs requiring human verification across the batch. |
| `avg_evidence_quote_coverage_rate` | Average per-PDF evidence-quote coverage rate. |
| `top_evidence_quote_gaps_by_trade` | Batch-level trades with the most missing source quotes. Use this to prioritize the next extraction/provenance fix before real estimating tests. |
| `total_quantity_present_count` | Total scope items with quantity values. |
| `total_quantity_missing_count` | Total scope items missing quantities. |
| `total_quantity_traceable_count` | Total scope items with clear non-test quantity basis/source. |
| `total_quantity_unclear_basis_count` | Total scope items with quantity values but unclear/unknown basis. |
| `total_quantity_test_input_count` | Total scope items using fictional harness quantity inputs. These must not be treated as real estimating readiness. |
| `total_open_quantity_requirement_count` | Total open quantity requirements across PDFs. |
| `total_resolved_quantity_requirement_count` | Total resolved quantity requirements across PDFs. |
| `avg_quantity_traceable_rate` | Average per-PDF traceable non-test quantity rate. |
| `top_quantity_confidence_by_trade` | Batch-level trade quantity weak spots sorted by missing/unclear/test quantity gaps. |
| `total_clarification_candidate_count` | Total internal clarification questions generated. |
| `total_urgent_clarification_candidate_count` | Total urgent clarification items across PDFs. |
| `total_high_clarification_candidate_count` | Total high-priority clarification items across PDFs. |
| `top_trade_quality_blockers` | Batch-level trade weak spots sorted by missing evidence, low confidence, unclear quantity basis, and open blockers. |

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

## Scoring extraction against a golden set

Once you can run bid-board PDFs through the harness, use the
[Golden Set + Extraction Evaluation harness](golden-set-extraction-evaluation.md) to score,
per project, whether the engine detected the **expected trades, scope keywords, and key
quantities** for a curated set of real bid packages. It reuses this harness under the hood,
keeps the same safety locks closed, and produces a CI-friendly JSON report and exit code.
