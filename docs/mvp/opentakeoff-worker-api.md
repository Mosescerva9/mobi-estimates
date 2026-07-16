# Deployable OpenTakeoff worker API

Status: internal VPS worker API foundation, not production-deployed by this PR.

## Target topology

```text
Vercel portal/admin UI
→ authenticated server-to-server request
→ Mobi estimating engine on VPS `/internal/takeoff/*`
→ server resolves tenant/project/document
→ OpenTakeoff MCP subprocess on VPS
→ canonical evidence + worker artifacts
→ tenant-scoped database/storage
→ portal polls job status/result
```

The Vercel frontend/runtime must **not** execute `node`, `pdfinfo`, or the OpenTakeoff MCP subprocess. The browser submits project/document IDs and geometry only. The VPS worker resolves the document from server-side data.

## API surface

Mounted router: `app.routers_opentakeoff_worker.opentakeoff_worker_router`

Endpoints:

- `POST /internal/takeoff/jobs`
- `GET /internal/takeoff/jobs/{job_id}`
- `POST /internal/takeoff/jobs/{job_id}/confirm-scale`
- `POST /internal/takeoff/jobs/{job_id}/measure-line`
- `POST /internal/takeoff/jobs/{job_id}/measure-polygon`
- `POST /internal/takeoff/jobs/{job_id}/cancel`
- `GET /internal/takeoff/jobs/{job_id}/artifacts`

## Authentication and authorization

The worker API reuses the existing engine middleware boundary:

- `MOBI_API_KEY` shared secret, accepted only through server-to-server headers.
- `X-Mobi-Tenant-Id` and `X-Mobi-Company-Id` are required when the key is configured.
- Worker operations also require:
  - `X-Mobi-Actor-Role`: `estimator`, `reviewer`, or `admin`
  - `X-Mobi-Actor-Id`: nonblank staff actor identifier

Customer/client roles are denied. The secret must never appear in browser bundles; Vercel should call this API only from server-side code or a backend route that has already authenticated/authorized staff.

A deployable worker service can start only with:

```text
MOBI_DEPLOYMENT_ENVIRONMENT=worker_service
MOBI_ENGINE_AUTH_MODE=worker_service_shared_key
MOBI_API_KEY configured as a rotatable nonblank secret
```

This is still a temporary service-to-service boundary, not the final workload-identity/JWT model.

## Document resolution

The API never accepts a filesystem path from the browser.

For this first engine-compatible slice, the local Phase 1 project model treats the project PDF as the first supported document and requires:

```text
document_id == project_id
```

Before launching OpenTakeoff, the worker:

1. loads the project row,
2. verifies tenant/company headers match the project row,
3. resolves `stored_file_path` strictly inside `settings.data_root`,
4. verifies the file exists,
5. verifies SHA256 matches `projects.file_sha256`.

If a future project-document table is added, this resolver should be narrowed to that table and should keep the same no-path-from-client contract.

## Job lifecycle

Persistent statuses now support:

- `queued`
- `starting`
- `document_loaded`
- `awaiting_scale_confirmation`
- `awaiting_geometry`
- `running_measurement`
- `awaiting_review`
- `completed`
- `failed`
- `cancelled`

Legacy values `running` and `awaiting_geometry_confirmation` remain accepted for compatibility with the PR #99 in-process worker contract.

Important behavior:

- duplicate idempotent job creation returns the existing row;
- wrong tenant and wrong document/project relationship are denied;
- provider sheet selectors are derived server-side from the verified document and page; client-supplied `sheet_key` is rejected as an unknown field;
- `sheet_id` must reference an existing tenant/project sheet row and its `pdf_page_number` must match the requested page;
- scale is required before measurement;
- invalid geometry is rejected before provider launch;
- timeout/provider crash is persisted as `failed` and never `completed`;
- cancellation marks `cancelled` and closes any tracked runtime session;
- successful provider measurement persists canonical evidence with `review_status=pending` and moves the job to `awaiting_review` only.

Customer-ready delivery remains blocked. Staff approval/final estimate delivery is a separate approval-gated workflow.

## Artifacts

The worker writes tenant/company/project scoped artifact files under the engine data root:

- `opentakeoff_export` JSON
- `canonical_evidence` JSON
- `marked_region_metadata` JSON
- `worker_metadata` JSON

The first PR returns artifact metadata with opaque artifact IDs plus type/hash/size only, not absolute VPS paths or relative storage keys. Storage keys remain server-side. Signed URLs are not implemented in this engine slice, so responses set:

```json
{ "signed_url": null, "expires_at": null }
```

`marked_region_metadata` is deterministic geometry/scale metadata only. It is **not** a rendered plan image and contains no plan pixels. Rendering a marked image/PDF remains a follow-up.

## Migration application and rollback notes

This PR adds:

- SQLite migration v40 in `mobi-estimating-phase1/app/migrations.py`.
- Supabase/Postgres forward migration `supabase/migrations/0027_opentakeoff_worker_job_api_statuses.sql`.

Operational application:

1. Apply only through the normal reviewed migration/deployment path after this PR is approved and merged.
2. Do not apply to production from an interactive shell during PR review.
3. Apply the Supabase migration before relying on the new worker API statuses in a deployed environment.
4. Verify the `opentakeoff_worker_jobs_status_check` constraint includes every application status listed above.

Rollback posture:

- The Supabase migration is forward-only SQL that relaxes the status constraint; it does not drop data.
- If rollback is required before jobs use the new statuses, restore the prior constraint from migration `0026` through an approved rollback migration.
- If any rows already use the new statuses, first quiesce the worker API and either complete/cancel/archive those rows or restore from a verified backup/non-production restore plan before narrowing the constraint.
- Do not treat `/var/backups` or OS package timers as Mobi DB rollback coverage.

## Verification

Focused suite:

```bash
cd mobi-estimating-phase1
MOBI_DEPLOYMENT_ENVIRONMENT=local PYTHONPATH=. python -m pytest \
  tests/test_opentakeoff_worker_api.py \
  tests/test_opentakeoff_mcp_runtime.py \
  tests/test_migrations.py \
  -q
MOBI_DEPLOYMENT_ENVIRONMENT=local PYTHONPATH=. python -m compileall \
  app/takeoff app/routers_opentakeoff_worker.py tests/test_opentakeoff_worker_api.py
```

The API test suite includes a real FastAPI → worker API → actual pinned OpenTakeoff MCP subprocess line measurement on the approved public C011 fixture and verifies the expected `37.5 LF` canonical evidence row.
