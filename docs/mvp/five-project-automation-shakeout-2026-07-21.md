# Five-project automation shakeout — 2026-07-21

## Status

Executed against five unique public projects across Golden Set v1 and v2. This is internal report-only evidence, not a release gate or final-estimate validation.

## Commands

```bash
cd mobi-estimating-phase1
python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set/manifest.real-v1.json \
  --output /tmp/mobi-golden-v1-shakeout.json \
  --workdir /tmp/mobi-golden-v1-shakeout \
  --report-only-baseline --no-fail-on-accuracy

python scripts/golden_set_extraction_eval.py \
  --manifest data/golden_set_v2/manifest.real-v2.json \
  --output /tmp/mobi-golden-v2-shakeout.json \
  --workdir /tmp/mobi-golden-v2-shakeout \
  --report-only-baseline --no-fail-on-accuracy
```

## Unique projects exercised

1. University of South Carolina Longstreet Theatre project manual
2. California DGS San Gorgonio Pass perimeter-fence package
3. City of Norman Ruby Grant Park specifications
4. California DGS Lot 50 EV charging-station plans
5. California DGS Patton roof-replacement plans

San Gorgonio appears in both manifest generations, producing six evaluated manifest rows across five unique projects.

## Results

### Golden Set v1

- Projects evaluated: 3
- Harness failures: 0
- Document text extraction: 3/3 pass
- Scope keyword coverage: 9/9
- Expected trade recall: 9/9 (`1.0`)
- Safety violations: 0
- Unexpected trade detections: 36
- Key quantities evaluated: 0
- Benchmark-eligible projects: 0

V1 project manuals detect broad trade references. With the intentionally narrow expected-trade lists, this produces low strict precision and 36 unexpected detections. These results are useful for census calibration but do not establish quantity accuracy.

### Golden Set v2

- Projects evaluated: 3
- Harness failures: 0
- Document text extraction: 3/3 pass
- Scope keyword coverage: 9/9
- Expected trade recall: 9/9 (`1.0`)
- Unexpected trade detections: 0
- Safety violations: 0
- Source-backed key-quantity records: 9/9 pass
- Benchmark-eligible projects: 0

The nine v2 quantities are human-verified source references with `require_engine_quantity=false`. They validate the source registry/ground-truth records, not autonomous engine quantity extraction.

## Release blockers exposed

Both commands exited `1` despite project-level report-only passes because every project is marked benchmark-ineligible. The common warning is:

```text
addenda_incomplete_benchmark_ineligible
```

Therefore this shakeout does **not** satisfy the strict Golden Set release gate. Remaining work:

1. Complete and verify authoritative bid/addenda packages for benchmark projects.
2. Promote at least one complete package to benchmark-eligible status.
3. Change selected v2 quantities to require real engine extraction only after the engine can reproduce them from source evidence.
4. Run `--release-gate` with no report-only accuracy bypass.
5. Calibrate v1 trade-census precision without suppressing legitimate project-manual scope.

## Safety

No final estimate approval, proposal issue, customer delivery, external message, or payment action was performed.
