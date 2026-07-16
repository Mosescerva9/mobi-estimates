# OpenTakeoff Real Measurement Proof

Updated: 2026-07-16T01:10Z

## Purpose

Prove the smallest real OpenTakeoff-backed geometric measurement path on an approved public Mobi Golden Set fixture:

approved blueprint fixture → `load_plan` → sheet identification → scale check/confirmation → `measure_line` → `export_takeoff` → `OpenTakeoffProvider` normalization → canonical evidence validation → SQLite proof persistence → ground-truth comparison.

This proof is deliberately narrow. It does **not** prove raster support, production worker readiness, full trade takeoff coverage, or end-to-end estimate generation.

## Fixture

| Field | Value |
|---|---|
| Project | `ca-dgs-24-253614-lot-50-evcs-v2` |
| Source | California DGS public Golden Set v2 fixture |
| Plan | `mobi-estimating-phase1/data/golden_set_v2/documents/ca_dgs_24_253614_plans.pdf` |
| Sheet | `C011` |
| PDF page | `4` |
| Sheet title | Ground Level Existing Condition |
| Vector status | OpenTakeoff `sheet_info` reported `has_vector_linework=true`, `seg_count=463` |

## Schedule-derived evidence is separate

Sheet `C011` contains schedule/table counts, including Golden Set verified stall and EVCS counts. Those values are **not** represented as OpenTakeoff geometric measurement evidence in this proof.

If used later, table/schedule values should be recorded separately as:

| Source | evidence_class | measurement_method |
|---|---|---|
| table/schedule extraction | `schedule_extracted` | current enum: `schedule_count` |

## OpenTakeoff-measured evidence

| Field | Value |
|---|---|
| Measurement type | `linear_geometric_measurement` |
| OpenTakeoff method | `measure_line` |
| Scale source | Manual calibration from printed C011 dimension |
| Scale confirmation | Explicit `set_scale` with `calibrate` |
| Calibration dimension | Level GA vertical stall-depth dimension: `15'-0"` |
| Measured target | Level GA horizontal run: `5 EVCS TYPE 2 @ 7.5' = 37'-6"` |
| Verified quantity | `37.5 LF` |
| OpenTakeoff quantity | `37.5 LF` |
| Absolute error | `0 LF` |
| Percentage error | `0%` |
| Processing time | `1958 ms` |
| Human correction/selection time | `240 seconds` |
| Result classification | `PASS` |

## Pass/fail classification

PASS criteria met:

- Scale explicitly confirmed.
- Measurement completed without silent scale use.
- Evidence persisted correctly in proof-local SQLite and round-tripped.
- Source region preserved.
- Provider identity is `open_takeoff`.
- Evidence class is `measured`.
- Measurement method is `digital_measurement`.
- Percentage error is `0%`, below the 5% threshold.
- Human correction/selection time was under 5 minutes.

## Reviewable artifacts

| Artifact | Path |
|---|---|
| OpenTakeoff export JSON | `mobi-estimating-phase1/data/opentakeoff_proof/lot50-c011-opentakeoff-export.json` |
| Raw measurement result | `mobi-estimating-phase1/data/opentakeoff_proof/lot50-c011-measurement-result.raw.json` |
| Normalized canonical evidence JSON | `mobi-estimating-phase1/data/opentakeoff_proof/lot50-c011-normalized-canonical-evidence.json` |
| Machine-readable benchmark result | `mobi-estimating-phase1/data/opentakeoff_proof/lot50-c011-benchmark-result.json` |
| Marked region image | `mobi-estimating-phase1/data/opentakeoff_proof/lot50-c011-marked-region.png` |

## What this demonstrates

- OpenTakeoff can load a real public Mobi Golden Set plan sheet.
- Mobi can explicitly calibrate scale from a printed dimension.
- OpenTakeoff can produce a committed geometric line measurement on the sheet.
- The OpenTakeoff export can normalize through `OpenTakeoffProvider` into canonical evidence.
- The canonical evidence can persist and round-trip in the Mobi SQLite proof store.
- Server-owned tenant/company/project/document/sheet identity remains outside the OpenTakeoff payload.

## What this does not demonstrate

- Raster/scanned plan support.
- One-click area accuracy on real project geometry.
- Full assembly/pricing integration.
- Production MCP worker/service operation.
- Full estimator dashboard integration.
- Customer-facing estimate delivery.

## Remaining production blockers

- OpenTakeoff MCP raster/scanned-plan gap remains.
- A stable worker/service integration is still needed; production must not depend on a Claude/Hermes terminal session.
- Application/database backups remain not fully verified.
- Live Stripe checkout/payment verification remains pending and approval-gated.
- More real blueprint geometry benchmarks are needed across area, line, count, deduction, and marked-plan export workflows.
