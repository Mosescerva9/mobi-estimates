# Public bid test — USC H27-Z147-B (painting scope)

Status: **offline public-document gate passed; one bounded paid GPT painting-scope run approved but not yet executed.**

## Authorized package
The pilot uses the existing public **USC H27-Z147-B — Longstreet Theatre Exterior Restoration** solicitation package from the University of South Carolina Purchasing archive:

- authoritative archived solicitation page;
- complete drawing set;
- project manual/specifications;
- Addendum One; and
- Addendum Two.

The repository golden-set manifest records public source authorization and document provenance. The package is used for internal testing only. Unnecessary bidder/contact data must not be reused or redistributed.

## Completed no-cost document evaluation
Command:

```bash
cd mobi-estimating-phase1
.venv/bin/python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set/manifest.release-v1.json \
  --output /tmp/mobi-usc-public-job-current-report.json \
  --workdir /tmp/mobi-usc-public-job-current-workdir \
  --release-gate
```

Verified report evidence generated at `2026-07-22T12:25:30.947652+00:00`:

- projects evaluated: `1`;
- evaluation passed: `1`;
- document extraction: `1/1` passed (`pdftotext`, 393,727 characters);
- expected trades: `9`;
- matched trades: `9`;
- unexpected trade false positives: `0`;
- scope keywords: `4/4`;
- source-backed key quantity: `1/1` passed;
- safety violations: `0`;
- hard gate: passed.

The bounded quantity evidence is the explicit `4.0 LF` temporary emergency-egress-gate nominal width on drawing A001. It is sub-scope evidence only—not a whole-project fence takeoff, gate count, painting quantity, price, or final estimate.

Evidence:

- `/tmp/mobi-usc-public-job-current-report.json`
- `/tmp/mobi-usc-public-job-current-run.log`

## Approved paid live scope test
The owner approved one bounded paid GPT test in this conversation. Execute only after the reviewed customer-flow release is deployed and healthy:

1. Use the normal tenant/project upload path with the complete public package.
2. Select the supported `painting` trade only.
3. Run one staff-triggered live GPT-5.6 Medium scope analysis following `docs/operations/gpt56-live-scope-activation-runbook.md`.
4. Keep provider retries at `0` for a one-dispatch proof boundary.
5. Require exact same-page source quotations and authoritative painting categories.
6. Keep every result `needs_review`; AI-authored quantities remain null.
7. Do not price, approve, issue a proposal, message a customer, process payment, or deliver an estimate.
8. Retain sanitized evidence with dispatch count, project/trade count, review status, grounding result, and prohibited-effect counts.

## Acceptance boundary
Passing the live scope test proves only that Mobi can assist staff with evidence-grounded painting scope from an authorized real package. It does not prove a complete takeoff, deterministic price, bid accuracy, customer delivery, or bid award.
