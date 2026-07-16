# OpenTakeoff Capability Benchmark
Updated: 2026-07-16T06:35Z
## Scope
Compact real-plan benchmark after PR #96. Uses public Golden Set fixtures only; no confidential customer files. The goal is engineering capability selection for the MVP worker, not customer-facing accuracy claims.
## Fixtures
| Plan set | Sheets/pages used | Scale sources |
|---|---|---|
| Lot 50 Accessibility Upgrades & EVCS | C011 / page 4 | Printed 15'-0" calibration dimension |
| San Gorgonio Pass Perimeter Fence | C011 / page 2 | Title block `1" = 20'` |

## Summary
| Metric | Value |
|---|---:|
| target_count | 12 |
| pass_count | 8 |
| partial_count | 0 |
| fail_count | 2 |
| safe_failure_count | 2 |
| median_error_pct | 0.00 |
| max_error_pct | 0.00 |
| median_human_time_seconds | 135.00 |
| ai_target_count | 3 |
| ai_acceptance_rate | 0.67 |
| median_manual_human_time_seconds | 130.00 |
| median_ai_assisted_human_time_seconds | 140.00 |

## Results by target
| ID | Category | Method | Qty | Truth | Error % | Class | Failure/review |
|---|---|---|---:|---:|---:|---|---|
| `lot50-c011-line-37_5` | linear_straight | measure_line | 37.50 LF | 37.50 LF | 0 | pass | Same verified PR #96 target; vision proposal identified the dimension line. |
| `lot50-c011-polyline-67_5` | linear_multisegment | measure_line | 90 LF | 90 LF | 0 | pass |  |
| `lot50-c011-rect-area-562_5` | area_simple_polygon | measure_polygon | 562.50 SF | 562.50 SF | 0 | pass |  |
| `lot50-c011-irregular-area` | area_irregular_manual_polygon | measure_polygon | 1340.29 SF | 1340.29 SF | 0.00 | pass |  |
| `lot50-c011-deduction-hole` | deduction | measure_polygon | 96.31 SF | 96.31 SF | 0.00 | pass | OpenTakeoff raw deduct primitive exists; current Mobi normalizer quarantines role=deduct pending production design. |
| `lot50-c011-oneclick-1` | one_click_area | one_click | n/a SF | 562.50 SF | n/a | fail | measurement_failed:That space isn't enclosed on the plan linework — the fill spilled through a gap or opening. |
| `lot50-c011-missing-scale` | failure_missing_scale | measure_line | n/a LF | n/a LF | n/a | expected_safe_failure | expected_scale_missing_safe_failure |
| `lot50-c011-count-unsupported` | count | record_count | n/a EA | 5 EA | n/a | expected_safe_failure | expected_safe_failure_no_mcp_count_primitive |
| `sgp-c011-line-100` | linear_different_scale | measure_line | 100 LF | 100 LF | 0 | pass |  |
| `sgp-c011-area-2400` | area_simple_polygon_different_plan | measure_polygon | 2400 SF | 2400 SF | 0 | pass |  |
| `sgp-c011-oneclick-ambiguous` | failure_ambiguous_one_click | one_click | 70261.59 SF | n/a SF | n/a | fail | trace_ambiguous_requires_review |
| `lot50-c012-line-30` | linear_third_sheet | measure_line | 30 LF | 30 LF | 0 | pass | Added to ensure the compact benchmark covers at least three sheets; not used for customer-facing accuracy claims. |

## Accuracy by method
| Method | Count | Pass | Partial | Fail | Safe failure | Median error % | Max error % | Median human sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| measure_line | 5 | 4 | 0 | 0 | 1 | 0.00 | 0.00 | 120.00 |
| measure_polygon | 4 | 4 | 0 | 0 | 0 | 0.00 | 0.00 | 160.00 |
| one_click | 2 | 0 | 0 | 2 | 0 | n/a | n/a | 100.00 |
| record_count | 1 | 0 | 0 | 0 | 1 | n/a | n/a | 20.00 |

## AI-assisted vs manual
AI was used for 3 target-selection/region-proposal checks. Acceptance rate: 0.67. Median AI-assisted human time: 140.00 sec. Median manual-only human time: 130.00 sec. This sample is too small to claim durable time savings; AI helped identify C011/SGP targets but did not reliably reduce human time on the one-click target because correction/review was still required.

## Failure taxonomy
- `one_click_area`: failed safely on Lot 50 C011 because the selected space was not enclosed; no silent evidence was committed.
- `failure_ambiguous_one_click`: produced a very large ambiguous SGP trace and was classified as fail/review, not accepted as evidence.
- `failure_missing_scale`: fresh-session `measure_line` failed with `Set the scale ... first — use set_scale.`
- `count`: current MCP has no actual `record_count` primitive; schedule counts stay `schedule_extracted`, not OpenTakeoff-measured.

## Marked region artifacts

- `mobi-estimating-phase1/data/opentakeoff_benchmark/lot50-c011-benchmark-marked.png`
- `mobi-estimating-phase1/data/opentakeoff_benchmark/sgp-c011-benchmark-marked.png`

## Supported worker operations selected
- `load_project_document`
- `inspect_sheet`
- `read_sheet_text`
- `confirm_scale`
- `measure_line`
- `measure_polygon_manual`
- `export_takeoff`
- `normalize_evidence_for_linear_and_floor_area`
- `persist_evidence`
- `generate_marked_artifact`

## Operations requiring fallback/review
- `one_click_area_on_non-room_or_gap_prone_geometry`
- `deduction_until_canonical_deduct_semantics_are_implemented`
- `record_count_until_OpenTakeoff_exposes_a_count primitive`
- `raster_or_scanned_plans`

## Recommendation
Build the MVP worker around demonstrated clean-vector `measure_line` and manual `measure_polygon` workflows with explicit scale confirmation, artifact capture, normalization, persistence, and estimator review. Keep one-click, deduction, count, and raster support behind review/fallback gates until the worker has explicit semantics and more benchmark coverage.
