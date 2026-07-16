# OpenTakeoff Worker Service Seed

Updated: 2026-07-16T06:50Z

## Purpose

Create the first production-oriented Mobi boundary around demonstrated OpenTakeoff workflows. This is not a public/customer-facing worker yet; it is the internal safety contract the real MCP subprocess adapter should plug into.

## Based on benchmark-supported operations

Supported for the MVP seed:

- `load_project_document`
- `inspect_sheet`
- `read_sheet_text`
- `confirm_scale`
- `measure_line`
- `measure_polygon`
- `export_takeoff`
- `normalize_evidence`
- `persist_evidence`
- `generate_marked_artifact`

Held behind fallback/review:

- one-click area on gap-prone/non-room geometry
- deduction until canonical deduct semantics are explicit
- record_count until OpenTakeoff exposes a count primitive
- raster/scanned plans

## Safety contract implemented

- One job object per project/document/session boundary.
- Tenant/company/project/document identity is supplied by Mobi `ResolvedProjectDocument` and `TakeoffContext`, never by OpenTakeoff export payloads.
- Worker accepts an already resolved server-side document path; it does not accept arbitrary customer-supplied local paths.
- Document hash is verified before job creation.
- Explicit scale confirmation is required before measurement.
- Structured error categories are defined for document, scale, measurement, provider, normalization, persistence, artifact, timeout, crash, cancellation, and raster unsupported states.
- Idempotency keys include tenant id, company id, project id, document id, operation, and payload hash.
- Provider/engine version fields and audit events are part of the job shape.
- Unsupported benchmark operations are named explicitly rather than exposed as production-ready.

## Still required before production use

- Real MCP subprocess/session adapter behind the `OpenTakeoffProviderClient` protocol.
- Per-operation process timeout and cancellation at subprocess level.
- Artifact storage through Mobi project/document storage, not only local paths.
- Marked-region artifact generation tied to the estimator UI.
- Job status persistence and concurrency limits.
- Log redaction tests for customer document paths/content.
- Estimator review UI/actions for approve, correct geometry, reject, and replace with human-verified measurement.

## Verification

- `cd mobi-estimating-phase1 && python -m pytest tests/test_opentakeoff_worker.py tests/test_opentakeoff_adapter.py tests/test_opentakeoff_capability_benchmark.py tests/test_takeoff_store.py tests/test_migrations.py -q`
- `cd mobi-estimating-phase1 && python -m compileall app/takeoff tests/test_opentakeoff_worker.py`
