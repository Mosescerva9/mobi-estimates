# Golden Set authoritative package completion — 2026-07-21

## Status

The USC Longstreet Theatre Exterior Restoration package now has source-backed completeness evidence and is the first Golden Set project marked benchmark-eligible. The dedicated release manifest also proves one engine-required explicit source dimension. This does not establish arbitrary drawing takeoff, whole-project quantity accuracy, pricing accuracy, or final-estimate readiness.

## Authoritative source

- Project: Longstreet Theatre Exterior Restoration
- Solicitation: `H27-Z147-B`
- Agency: University of South Carolina
- Archived solicitation inventory: https://sc.edu/about/offices_and_divisions/purchasing/solicitations_awards/legacy_solicitations_awards/facilities_procurements/details.php?sid=2195

The archived inactive solicitation page explicitly lists the project manual, drawings, Addendum One, and Addendum Number Two. Both downloaded addenda identify project `H27-Z147-B` and contain their stated enclosures.

## Registered core package

| Artifact | Official URL | Bytes | SHA-256 |
|---|---|---:|---|
| Project manual | https://sc.edu/purchasing/solicitations/documents/s_1459197637.pdf | 6,133,132 | `fb577c5204a33630f617866643fb6d5f13a807db024a3aad713ed8d4b83c150a` |
| Drawings | https://sc.edu/purchasing/solicitations/documents/s_1459197670.pdf | 3,310,154 | `bb5bec82eb81b9cbe37af7d253c8d29b3d94766abdf913add10b07b0b8c3659e` |
| Addendum One, 2016-04-08 | https://sc.edu/purchasing/solicitations/documents/s_1460377831.pdf | 304,382 | `1ba5c5ec2d08edc5aa167a55aa4bcce4a200fe4226d866e3c84e456399da609d` |
| Addendum Two, 2016-04-13 | https://sc.edu/purchasing/solicitations/documents/s_1460566716.pdf | 1,575,188 | `51be5162765f1d0113b9bfc69228a601586c78797d2641cf9405d5fa4f2b8b75` |

Addendum One includes its pre-bid sign-in sheet, qualification summary, and lead-material requirements. Addendum Two includes its hazmat survey and A303 enlarged-detail enclosure.

## San Gorgonio correction

The previously registered generic DGS `Addendum-1.pdf` is not a San Gorgonio artifact. Its contents identify:

- Project: DSH Coalinga Road Repairs
- Project number: `000000000009928`
- Issue date: 2025-04-08

It has been removed from San Gorgonio evaluation inputs and marked `excluded_from_golden_set` in `sources.v2.json`. The tracked file remains in place pending explicit approval for deletion or rename. San Gorgonio remains benchmark-ineligible until an authoritative construction-event package cross-check is complete.

## Strict release-gate result

The dedicated authoritative release manifest is:

- `mobi-estimating-phase1/data/golden_set/manifest.release-v1.json`

Command:

```bash
python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set/manifest.release-v1.json \
  --output /tmp/mobi-golden-release-v1-provenance-v2.json \
  --workdir /tmp/mobi-golden-release-v1-provenance-v2 \
  --release-gate
```

Verified result: **exit 0**.

- Benchmark eligible/evaluated: `1/1`
- Document extraction: `1/1` passed
- Required trades: `9/9` matched
- Unexpected trade false positives: `0`
- Scope keywords: `4/4`
- Engine-required quantities: `1/1` passed
- Quantity evidence: `1/1` passed
- Harness failures: `0`
- Safety violations: `0`

The engine-produced benchmark quantity is the explicit nominal width labeled on drawing `A001`, PDF page 5:

> `4 FT. EMERGENCY EGRESS GATE - INSTALL "EMERGENCY EXIT ONLY" SIGN ON GATE`

The resulting internal scope candidate carries `4.0 LF` with basis `explicit_plan_quantity`, exact sheet/page text evidence, `explicit_subscope_only=true`, and human review still required. It is not a total fence takeoff and does not infer gate count, repeated callout count, or total fence length.

The false HVAC detection exposed by the first strict run was corrected at the detector: project number `H27-Z147-B` no longer qualifies as an HVAC sheet-index entry, and a standalone `HVAC` abbreviation on a legend is no longer treated as body-text scope evidence. No legitimate expected trade was suppressed or allowlisted to make the gate pass.

## Limits

- This proves one bounded, authoritative package and one explicit source dimension—not arbitrary drawing takeoff or whole-project estimating accuracy.
- The quantity remains internal and review-required.
- No pricing, proposal, customer delivery, or final-estimate action is authorized by this corpus result.
