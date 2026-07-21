# Painting public-PDF evidence-to-pricing proof — 2026-07-21

## Status

Verified internal proof. Not a final estimate, customer deliverable, production cost book, or production deployment.

## Source

- Official public source: City of Norman, Oklahoma — Ruby Grant Park specifications, Amendment One
- Tracked file: `mobi-estimating-phase1/data/golden_set/documents/norman_ruby_grant_park_specs_amendment_one.pdf`
- Verified SHA-256: `41fa4d685c8b5ccc66b14ff15815846e9823fd0faa8d4068e43da767393cd993`
- Pages used: PDF pages 258–259, Section 099000 Painting
- Explicit source quantity: minimum 100 SF vertical/horizontal paint-system mockup
- Coating evidence: gypsum-board three-coat system, including primer and Aquapon Epoxy finish coats

## Exercised pipeline

1. Upload the real 622-page public PDF into an isolated local tenant/project.
2. Process the PDF into the sheet/page register.
3. Manually verify pages 258–259 as `099000-1` and `099000-2`.
4. Route the verified pages to the opt-in deterministic `source_text` provider.
5. Emit one evidence-backed painting candidate only when both the explicit 100-SF requirement and the gypsum-board coating schedule are present.
6. Preserve exact evidence quotes and source-page lineage.
7. Require explicit scope review; no provider candidate silently becomes approved scope.
8. Map the reviewed scope to `PT-INT-WALL`.
9. Run `/pricing/preview` using a cost book labeled `FICTIONAL HARNESS TEST ONLY - NOT MARKET PRICING`.
10. Verify that no persistent estimate, estimate version, proposal, delivery, external message, payment, or final approval was created.

## Real run evidence

Command:

```bash
cd mobi-estimating-phase1
python scripts/painting_public_pdf_proof.py \
  --workdir /tmp/mobi-painting-public-proof-run-v4 \
  --output /tmp/mobi-painting-public-proof-report-v4.json
```

Observed result:

```text
status: pass
sheet_count: 622
scope_items_considered_count: 1
proposed_mapping_count: 1
missing_mapping_count: 0
blocking_exception_count: 0
estimate_version_created: false
estimated_api_cost: 0.00
customer_safe_preview: internal_preview_only
customer_safe_quantity_abstained_count: 1
customer_delivery/message/send/final-approval/payment flags: false
```

Machine-readable report:

`/tmp/mobi-painting-public-proof-report-v4.json`

## Regression coverage

- `tests/test_source_text_provider.py`
- `tests/test_painting_public_pdf_proof.py`
- `tests/test_painting_evidence_estimate_proof.py`
- `tests/test_golden_set_source_integrity.py`

Golden Set source integrity now checks that tracked artifact hashes, `sources.json`, and `manifest.real-v1.json` agree. Three stale manifest hashes were corrected from actual tracked-file/source-registry evidence.

## Safety and limitations

- The new provider is opt-in as `source_text`; the default provider remains unchanged.
- The provider is deliberately narrow and abstains unless both exact source conditions are present.
- The 100 SF quantity represents the specified mockup sub-scope only, never total project painting.
- Fixture pricing is fictional and internal-only. It is not market pricing and cannot support a final construction estimate.
- Customer delivery capability remains locked.
- This proof does not establish arbitrary-plan OCR, full-project painting quantities, all-trade takeoff accuracy, or production readiness.
