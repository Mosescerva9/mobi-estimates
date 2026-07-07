# Golden Set v1 + Extraction Evaluation Harness

_Last updated: 2026-07-07_

## Purpose

The extraction evaluation harness measures whether the local Mobi estimating engine
can **read a real bid package**: does it detect the trades and scope keywords a human
estimator expects, and do any labeled key quantities land within tolerance?

It is the product-proof step before deeper bid-outcome calibration. You cannot trust
pricing/outcome models until you can show the engine reliably extracts the right scope
from real documents. This harness gives a repeatable, CI-friendly score for that.

The harness is **local/internal testing only**. It does **not** send customer messages,
create customer deliverables, process payments, approve/finalize estimates, or issue
proposals. It asserts those safety locks stay closed in every harness report and fails
loudly if any of them is ever reported open.

It reuses [`real_document_harness.py`](../scripts/real_document_harness.py) to run each
project's primary document through the local FastAPI TestClient pipeline in an isolated
workdir, then scores the resulting report.

## Golden Set manifest schema

A manifest is a single JSON file. See
[`data/golden_set/manifest.example.json`](../data/golden_set/manifest.example.json) for a
runnable example.

### Top-level

| Field | Required | Notes |
|---|---|---|
| `metadata` | yes | Object. Must set `internal_testing_only: true` and `source_authorization`. |
| `metadata.internal_testing_only` | yes | Must be exactly `true`. |
| `metadata.source_authorization` | yes | One of `public`, `authorized`, `internal`. Records that every referenced document is a public, authorized, or internal-testing source. |
| `projects` | yes | Non-empty list of project objects. |

### Per project

| Field | Required | Notes |
|---|---|---|
| `project_id` | yes | Unique, non-empty string. |
| `title` | yes | Human-readable project name (used as the engine project name). |
| `agency` | yes | Owning agency / source. |
| `location` | yes | Project location. |
| `document_paths` | yes | Non-empty list. v1 evaluates the **first** path (single primary document). Relative paths resolve against the manifest's directory. |
| `addenda_complete` | yes | Boolean. If `false`, the project is **benchmark-ineligible** but extraction eval still runs with a warning. |
| `expected_trades` | yes | List of expected trade codes (e.g. `painting`, `demo_concrete`, `general_trade`). |
| `expected_scope_keywords` | yes | List of keywords expected to appear in detected scope text. |
| `internal_testing_only` | yes | Must be exactly `true`. |
| `bid_date` | no | Informational. |
| `key_quantities` | no | List of labeled quantities to check (see below). |
| `outcome_paths` | no | Reserved for later bid-outcome calibration. **Must be empty in v1** — a populated list is rejected during manifest validation so no bid outcome can leak into extraction scoring. |
| `notes` | no | Freeform. |

### `key_quantities` entries

| Field | Required | Notes |
|---|---|---|
| `label` | yes | Substring matched (case-insensitive) against detected scope text to find the item. |
| `expected_value` | yes | Numeric expected quantity. |
| `unit` | yes | Expected unit. A detected/expected unit mismatch is scored `unknown`, never `pass`. |
| `tolerance_pct` **or** `tolerance_abs` | yes (one) | Percent-of-expected or absolute tolerance band. |
| `source_ref` | no | Where the expected value came from (e.g. a sheet number). |

## Commands

Run from the engine directory with the harness virtualenv:

```bash
cd /home/hermes/work/mobi-estimates/mobi-estimating-phase1
```

Validate a manifest / fixtures without needing the documents present:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set/manifest.example.json \
  --output /tmp/golden-set-report.json \
  --allow-missing-documents
```

Full run against real public/authorized local documents:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
  --manifest /path/to/golden_set_manifest.json \
  --output /tmp/golden-set-report.json \
  --workdir /tmp/golden-set-work
```

CI mode that also fails when any evaluated project misses a required trade:

```bash
/tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
  --manifest /path/to/golden_set_manifest.json \
  --output /tmp/golden-set-report.json \
  --fail-on-missed-required-trade
```

### CLI reference

```
--manifest PATH                     (required) golden-set JSON manifest
--output PATH                       (required) JSON evaluation report to write
--workdir PATH                      working directory (defaults to a temp dir)
--allow-missing-documents           validate schema/fixtures without the documents;
                                    projects with missing primary documents are skipped
--fail-on-missed-required-trade     exit nonzero when any evaluated project misses a
                                    required trade
--no-fail-on-accuracy               softer, report-only mode: do NOT exit nonzero on
                                    accuracy failures (missing expected keywords, a
                                    key-quantity fail, or a declared key-quantity unknown).
                                    Accuracy failures fail CI by default.
```

## Metrics

Per project the report records:

- **Trade coverage** — matched / missed-required / false-positive trades, plus recall and
  precision. Recall is over `expected_trades`; a false positive is a detected trade not in
  the expected list.
- **Scope keyword coverage** — which `expected_scope_keywords` were found in detected scope
  text (description + location + material/substrate), and a coverage rate.
- **Key quantities** — each labeled quantity is `pass`, `fail`, or `unknown`. `unknown`
  covers "no matching scope item", "matched item has no quantity", and "unit mismatch" — the
  harness reports these honestly instead of claiming a pass.
- **Benchmark eligibility** — `benchmark_ineligible` when `addenda_complete` is `false`.
- **Safety** — asserts customer-delivery / final-approval / external-message / payment /
  proposal-issue / proposal-created flags are all closed.
- **`accuracy_passed`** — `true` only when extraction quality holds where the manifest
  declares expectations: full expected-keyword coverage when keywords are listed, no
  key-quantity `fail`, and no declared key-quantity `unknown`. `accuracy_failures` lists the
  reasons (`expected_keywords_missing`, `key_quantity_fail`, `key_quantity_unknown`).
- **`hard_gate_passed`** — `true` only when the harness ran clean, safety held, and no
  required trade was missed.
- **`evaluation_passed`** — `true` only when **both** `hard_gate_passed` and
  `accuracy_passed` are `true`. It is never `true` when expected keywords are all missing or
  a declared key quantity fails or comes back unknown.

The aggregate section micro-averages trade recall and keyword coverage over evaluated
projects and rolls up pass/fail/unknown quantity counts and safety/harness/benchmark counts.

## Exit codes and CI semantics

| Exit | Meaning |
|---|---|
| `0` | Report written; no hard failures under the chosen flags. |
| `1` | A project's harness failed, a safety lock was violated, an accuracy failure occurred (default), or `--fail-on-missed-required-trade` was set and a required trade was missed. |
| `2` | Manifest failed validation (nothing was evaluated). |

- **Harness failures and safety violations always exit `1`**, regardless of flags.
- **Accuracy failures exit `1` by default.** An evaluated project fails accuracy when its
  expected keywords are all missing, a declared key quantity fails tolerance, or a declared
  key quantity comes back `unknown`. Pass `--no-fail-on-accuracy` for a softer, report-only
  mode that still records the failures but exits `0`.
- A **missed required trade** always marks the project `evaluation_passed=false` in the
  report, but only fails the process when `--fail-on-missed-required-trade` is set.

## Safety rules

- Every referenced document must be public, authorized, or an internal-testing copy
  (`metadata.source_authorization`). No gated/paywalled/scraped material.
- The harness never contacts external services; tests use synthetic reports and fixtures.
- The evaluation asserts these stay closed and fails otherwise:
  `customer_delivery`, `external_messages`, `final_estimate_approval`, `payments`,
  `customer_delivery_ready`, generic-estimate/proposal delivery/approval/message/payment
  flags, `proposal_created`, `proposal_issued`, and clarification send/message-ready flags.

## v1 limitations

- **Single primary document per project.** Only `document_paths[0]` is evaluated; multi-file
  packages and addenda merging are out of scope for v1.
- **Keyword/substring matching** for scope keywords and key-quantity labels — not semantic
  matching. Choose distinctive labels.
- **Enabled trades are limited** by the harness (`painting`, `demo_concrete`,
  `general_trade`), so trades outside that set will read as missed until more trade modules
  are enabled.
- Quantity checks depend on the engine actually producing a quantity for the matched item;
  otherwise the result is `unknown`, not a failure.
- `outcome_paths` is reserved and not yet scored; bid-outcome calibration is a later track.
  In v1 it must be empty — a populated list is rejected at manifest validation so no bid
  outcome can leak into extraction scoring.

## Related

- [`real-bid-board-shakeout-guide.md`](real-bid-board-shakeout-guide.md) — the single-PDF and
  batch harnesses this evaluation builds on.
- [`public-bid-board-pdf-collector.md`](public-bid-board-pdf-collector.md) — building a
  compliant internal test corpus from public sources.
