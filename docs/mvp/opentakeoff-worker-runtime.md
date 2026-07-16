# OpenTakeoff Worker Runtime

Updated: 2026-07-16T07:55Z

## Purpose

Implement the first real, locally executable OpenTakeoff MCP runtime behind Mobi's merged worker contract. This is an internal staff/runtime foundation, not a customer-facing automatic takeoff claim.

## Pinned OpenTakeoff dependency

| Field | Value |
|---|---|
| package | `opentakeoff-mcp` |
| version | `0.1.1` |
| npm integrity | `sha512-AEVE+dxJn3/YS/7xo8QC8g5mC+m1r0eq3lp/OWXeTehd2rg3YL4I2tJjP7VayQW3TcRW7p9VFmWzKhBdhLH3rg==` |
| source repository | `git+https://github.com/Kentucky-ai/opentakeoff.git` |
| license | `Apache-2.0` |
| build/install command | `npm install --save-exact opentakeoff-mcp@0.1.1` |
| runtime command | `node node_modules/opentakeoff-mcp/dist/server.js` |

The package is pinned in `package.json` and `package-lock.json`; runtime tests verify the lockfile version, integrity, and license.

## Supported MCP tools in this runtime PR

- `load_plan`
- `sheet_info`
- `read_sheet_text`
- `set_scale`
- `measure_line`
- `measure_polygon`
- `takeoff_summary`
- `export_takeoff`

## Explicitly not exposed as customer-ready

- `one_click` area
- deduction
- native count
- raster/scanned plan automation

## Runtime controls implemented

- Controlled executable/args: `node node_modules/opentakeoff-mcp/dist/server.js`.
- stdout reserved for newline-delimited MCP JSON-RPC protocol.
- stderr captured only as bounded diagnostics.
- startup timeout.
- per-tool timeout.
- process termination and forced termination path.
- temporary session directory cleanup.
- output line size limit.
- PDF byte-size limit.
- page-count limit after `load_plan`.
- structured error categories for startup failure, timeout, protocol error, crash, missing scale, document missing, unsupported document, and resource limits.
- operation timing capture.
- engine/package version capture.

## Job persistence

Adds SQLite migration v39: `opentakeoff_worker_jobs`.

Required status fields are represented:

- `job_id`
- `tenant_id`
- `company_id`
- `project_id`
- `document_id`
- `provider`
- `engine_version`
- `operation`
- `idempotency_key`
- `status`
- `requested_by`
- `started_at`
- `completed_at`
- `cancelled_at`
- `error_category`
- `safe_error_message`
- `artifact_ids`
- `evidence_ids`
- `attempt_count`
- `created_at`
- `updated_at`

The persistence helpers store status metadata only; they do not store raw customer document text or full provider payloads in general logs.

## Real runtime proof

`tests/test_opentakeoff_mcp_runtime.py` launches the actual pinned MCP subprocess and runs the PR #96 line target through the worker contract:

- load public Golden Set PDF
- set explicit calibrated scale
- measure line
- export OpenTakeoff payload
- normalize canonical evidence
- verify `37.5 LF` result with provider, sheet, page, scale, quantity, unit, and server-owned identity
- close runtime and verify temp cleanup

## Verification

```bash
cd mobi-estimating-phase1
MOBI_DEPLOYMENT_ENVIRONMENT=local python -m pytest \
  tests/test_opentakeoff_mcp_runtime.py \
  tests/test_opentakeoff_worker.py \
  tests/test_opentakeoff_adapter.py \
  tests/test_takeoff_store.py \
  tests/test_migrations.py \
  -q

MOBI_DEPLOYMENT_ENVIRONMENT=local python -m compileall app/takeoff tests/test_opentakeoff_mcp_runtime.py

git diff --check
```

## Remaining before production worker use

- overall job timeout across multi-operation work.
- persisted retry controller with at most one retry for transient provider/process failures.
- cancellation API wired to staff UI/job queue.
- concurrency/session limit enforcement across worker processes.
- CPU/memory monitoring beyond process lifecycle and size/page limits.
- artifact storage integration and marked-image generation.
- estimator workbench UI.
