# OpenTakeoff Technical Spike

Updated: 2026-07-16T00:35Z

## Environment
- Isolated clone: `/tmp/opentakeoff-eval`
- Commit: `36a9aa7ebe0a6dde116c0a3d68a16fe39a0c94bf`
- Published MCP package tested via: `npx -y opentakeoff-mcp`
- Node: current host Node reported `v22.23.1`; OpenTakeoff web package warns it wants Node `>=24`, but MCP tests still passed.

## Install/test results
Commands run:

```bash
cd /tmp/opentakeoff-eval/web && npm install
cd ../mcp && npm install
npm run typecheck
npm test
node /tmp/opentakeoff-npx-smoke.mjs
```

Results:
- `mcp` typecheck passed.
- `mcp` test suite passed: 20/20.
- `npx -y opentakeoff-mcp` smoke passed through an MCP client.
- `npm install` for MCP reported 1 moderate vulnerability; not fixed yet.

## MCP tools verified through npx
The npx smoke listed and exercised all required tools:

| Tool | Result |
|---|---|
| `load_plan` | passed on OpenTakeoff demo PDF |
| `sheet_info` | passed |
| `read_sheet_text` | passed |
| `set_scale` | passed; explicit detected-scale adoption |
| `one_click` | passed; demo room `437.98 SF` |
| `measure_polygon` | passed after scale; refused before scale |
| `measure_line` | passed after scale |
| `takeoff_summary` | passed |
| `export_takeoff` | passed; wrote `/tmp/opentakeoff-npx-export.json` |
| `delete_shape` | passed |

## Golden Set measurement attempt
Project: `ca-dgs-25-275745-patton-reroof-v2`  
Plan: `mobi-estimating-phase1/data/golden_set_v2/documents/ca_dgs_25_275745_plans.pdf`  
Ground truth: `New roofing project area = 19,337 SF`, source `G001`, PDF page 1, from Golden Set v2 human-verified building information table.

Result recorded in `/tmp/mobi-golden-opentakeoff-patton-result.json`:

| Field | Value |
|---|---|
| measurement_type | `schedule_extraction_via_OpenTakeoff_read_sheet_text` |
| verified_quantity | `19337 SF` |
| OpenTakeoff_quantity | `null` |
| percentage_error | `null` |
| processing_time_ms | `3449` |
| failure_mode | `expected_roofing_area_not_detected_or_mismatched` |
| sheet_info.has_vector_linework | `false` |
| sheet_info.seg_count | `0` |
| text_excerpt | `ISSUE DATE: SEPTEMBER 3 2025` |

Interpretation: this Golden Set plan is raster/scanned for MCP purposes. OpenTakeoff MCP loaded it but did not expose enough text/vector evidence to extract the verified quantity. This confirms the raster-gap warning in OpenTakeoff docs and is not launch-ready for this class of fixture without a raster/OCR fallback.

## Golden Set vector/raster probe
Probe across first five sheets of three Golden Set v2 plan PDFs:

| Plan | Pages | First-sheet vector status |
|---|---:|---|
| `ca_dgs_22_130586_plans.pdf` | 19 | vector linework present; first sheet `seg_count=838603` |
| `ca_dgs_24_253614_plans.pdf` | 20 | vector linework present; first sheet `seg_count=463` |
| `ca_dgs_25_275745_plans.pdf` | 8 | no vector linework; first five sheets all `seg_count=0` |

## Raster-gap report
OpenTakeoff MCP docs state v1 is “Vector + text sheets only” and scanned sheets are not yet supported by MCP; raster seam exists in `mcp/src/session.ts`. The Patton Golden Set attempt reproduced that gap.

MVP implication: Mobi must add a tested raster/OCR fallback at the Mobi adapter boundary or browser-engine layer before relying on OpenTakeoff for scanned customer plans.

## Initial success target status
- Clean vector demo area/linear/count/export: passed on OpenTakeoff sample.
- Golden Set raster schedule quantity: failed safely; no silent scale assumption.
- Scale gate: verified — `measure_polygon` refused before `set_scale`.
- JSON output normalization path: not yet built; canonical provider/schema slice started.
