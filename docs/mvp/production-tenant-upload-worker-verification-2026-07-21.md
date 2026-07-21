# Production tenant upload and worker verification — 2026-07-21

## Scope and safety

This was an internal-only production verification using a newly created `example.invalid` identity, an official public USC drawing fixture, temporary company/project records, and no customer data.

No Stripe Checkout Session, charge, refund, proposal, customer delivery, or final estimate was created. Stripe remained read-only because the configured environment is live mode.

## Portal / Supabase upload lane

Verified against `https://portal.mobiestimates.com`:

- Temporary Auth user created: pass
- `POST /api/projects`: HTTP `200`
- Private `project-files` Storage upload: pass
- Authenticated client `project_files` insert through RLS: pass
- `POST /api/projects/{id}/estimate-job-sync`: HTTP `200`
- Tenant-scoped `estimate_jobs` record: present
- Linked `estimate_job_documents` record: present
- `document_registered` event: present
- Cross-tenant `project_files` insert: denied

Cleanup was executed in `finally` and verified:

- Storage object removed
- Temporary primary and cross-tenant companies removed
- Temporary Auth user removed
- Remaining rows for company, project, project file, estimate job, estimate document, event, and profile: all `0`

## Live OpenTakeoff worker boundary

Verified through `https://api.mobiestimates.com/internal/takeoff` using the existing public C011 worker fixture:

- Correct tenant job lookup: HTTP `200`
- Existing job status: `awaiting_review`
- Wrong tenant/company lookup: HTTP `403`
- Artifacts endpoint: HTTP `200`, four artifacts
- Duplicate idempotency submission: HTTP `201`, `created=false`
- Duplicate resolved to the original job ID
- Worker job row count and original row timestamp remained unchanged
- Existing failed `provider_crash` job was followed by a later successful `awaiting_review` job for the same public fixture, preserving recovery evidence

A mistaken first idempotency probe created one empty `awaiting_scale_confirmation` row because the client supplied the server-prefixed key rather than the caller suffix. Before removal, the row was verified to have no artifacts, no evidence, and no dependent rows. That temporary row was removed, verified absent, and the corrected suffix-only probe returned `created=false` without adding a row.

## Automated hardening coverage

The consolidated local regression command included Golden Set, trade census, generic scope, worker API/service, tenant-boundary, and customer-revision suites. Result: `190 passed`.

This includes revision-preservation coverage; no production estimator-entered value was modified for this proof.

## Remaining joined-topology blocker

The portal upload lane and OpenTakeoff worker lane are individually verified, but a single production upload was **not** truthfully demonstrated flowing into that worker database.

Current VPS topology uses separate engine and worker databases/data roots:

- Portal engine uploads route to the main estimating service.
- `/internal/takeoff/*` routes to the isolated worker service.
- The isolated worker resolves projects/sheets from its own tenant-scoped database.

Pointing both services at one database or changing reverse-proxy/service configuration could affect an existing production engine-project link and requires a planned migration, backup, rollback, and explicit production configuration approval. Until that migration is implemented and exercised, this evidence must not be represented as a fully joined upload-to-worker production E2E.
