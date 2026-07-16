# Paid-pilot onboarding / checkout / upload E2E status

Updated: 2026-07-16T13:20Z
Branch: `paid-pilot-onboarding-e2e`

Status vocabulary: `working`, `partially_working`, `broken`, `missing`, `not_verified`.

## Verification performed in this branch

Commands run:

```bash
npm run test:checkout-readiness
npm run test:checkout-prefetch
npm run test:checkout-flow
npm run test:project-upload
npm run typecheck
npm run build
```

Results:

- `test:checkout-readiness`: 6/6 passed.
- `test:checkout-prefetch`: passed, 2 `/start?plan` links checked with `prefetch={false}`.
- `test:checkout-flow`: 13/13 passed using in-memory fakes only; no Stripe/Supabase network calls.
- `test:project-upload`: 14/14 passed for helper validation/path generation.
- `typecheck`: passed.
- `build`: passed.

Environment/precondition check from this shell:

```text
STRIPE_SECRET_KEY=missing
STRIPE_WEBHOOK_SECRET=missing
STRIPE_FIRST_MONTH_COUPON_ID=missing
STRIPE_PRICE_STARTER=missing
STRIPE_PRICE_GROWTH=missing
STRIPE_PRICE_ESTIMATING_DEPARTMENT=missing
STRIPE_PRICE_PAY_PER_PROJECT=missing
NEXT_PUBLIC_SUPABASE_URL=missing
NEXT_PUBLIC_SUPABASE_ANON_KEY=missing
SUPABASE_SERVICE_ROLE_KEY=missing
SUPABASE_ACCESS_TOKEN=missing
SUPABASE_DB_URL=missing
DATABASE_URL=missing
```

Because the required Stripe/Supabase credentials are not present in this shell, no live Stripe test-mode checkout, webhook delivery, authenticated portal session, private Storage upload, Supabase RLS probe, or isolated restore test was executed here.

## Customer-facing flow classification

| Step | Status | Evidence / reason |
|---|---|---|
| visitor → pricing | partially_working | `/pricing` route builds. Prices are centralized in `src/lib/pricing.ts`. Not browser-verified live in this branch. |
| displayed approved prices | partially_working | Source shows Starter $995/mo ($497.50 first month), Growth $1,995/mo ($997.50 first month), Estimating Department $2,995/mo ($1,497.50 first month), Pay Per Project $599 one-time. No live browser assertion in this branch. |
| pricing CTA starts checkout safely | partially_working | Static prefetch guard passed: `/start?plan=...` links set `prefetch={false}`. No live/session checkout started. |
| Stripe test checkout session creation | not_verified | Required Stripe env vars missing. Offline harness validates state machine only. |
| Stripe success return | not_verified | No real Stripe test session available in this shell. |
| Stripe cancellation return | not_verified | No real Stripe test session available in this shell. |
| webhook signature verification | partially_working | Source verifies signature in `src/app/api/stripe/webhook/route.ts`; offline flow harness covers duplicate/idempotent logic but not an actual signed Stripe webhook request. |
| duplicate webhook handling | partially_working | Offline harness passed duplicate webhook scenario. No live/test-mode webhook delivery run. |
| payment/account linking | partially_working | Offline harness passed claim paid → auth user link → finalize paths. No live Supabase/Auth run. |
| failed payment access denial | partially_working | Source maps failed invoice to `past_due`; project API gates submission on active subscription or pay-per-project credit. No live failed-payment Stripe event run. |
| interrupted onboarding recovery | partially_working | Offline harness covers existing entitlement + paid claim finalization. Browser recovery not exercised. |
| customer billing portal | not_verified | API route exists, but no Stripe/Supabase env or authenticated live session in this shell. |
| subscription cancellation state | partially_working | Webhook source maps deleted subscription to `canceled`. No Stripe test event run. |
| pay-per-project entitlement | partially_working | Offline harness passed Pay Per Project entitlement/finalize; no live Stripe/Supabase run. |
| account creation/linking | not_verified | Auth flow not exercised with real Supabase credentials/session. |
| login | not_verified | Auth flow not exercised with real Supabase credentials/session. |
| customer portal | partially_working | Portal routes build. No authenticated browser/Supabase session exercised. |
| project creation | partially_working | `/api/projects` source validates input, checks entitlement server-side, creates project, and calls `ensureEstimateJobForProject`; no live Supabase write executed. |
| project questionnaire | partially_working | `NewProjectForm` source includes structured fields and server schema validation; no browser form submission executed. |
| approved public-plan upload | partially_working | Upload helper validation passed offline; no live private Storage upload executed. |
| tenant-scoped document storage | partially_working | Storage path helper retains `{company}/{project}/...` and sanitizes filename; Supabase RLS not live-tested here. |
| estimator queue entry | partially_working | `/api/projects` calls `ensureEstimateJobForProject`; no live DB insert verified. |

## Secure upload classification

| Requirement | Status | Evidence / reason |
|---|---|---|
| file type validation | working | `test:project-upload` passed allowed/disallowed extension checks. |
| size validation | working | `test:project-upload` passed zero-byte/negative/oversize checks. |
| ZIP/PDF handling | partially_working | Helper allows configured document extensions; no live ZIP/PDF upload run. |
| unique tenant/company/project scoped paths | partially_working | Path helper passed uniqueness/prefix tests. Live RLS/storage isolation not exercised. |
| signed URL expiration | partially_working | Source uses signed URLs with 300-second expiry on project detail/admin pages; not live-tested. |
| duplicate file behavior | partially_working | Storage upload uses `upsert:false`, unique generated paths. No live duplicate Storage run. |
| failed-upload recovery | partially_working | `NewProjectForm` redirects partial uploads to project page; `AddProjectFilesForm` supports retry/add documents. Not live-tested. |
| addendum/version handling | partially_working | File category support exists; no version chain/live addendum run. |
| document database record | partially_working | Source inserts `project_files` metadata after Storage upload. No live DB insert. |
| queue creation | partially_working | API creates/updates EstimateJob via `ensureEstimateJobForProject`. No live DB verification. |
| worker access via server-resolved document identity | not_verified | Runtime worker path exists after PR #99, but customer upload → worker document identity has not been integrated/tested end-to-end. |

## Two-tenant isolation status

| Probe | Status | Evidence / reason |
|---|---|---|
| Tenant A cannot list Tenant B projects | not_verified | Requires Supabase test users/session/RLS live test. Credentials missing. |
| Tenant A cannot view Tenant B documents | not_verified | Requires Supabase test users/session/RLS live test. Credentials missing. |
| Tenant A cannot download Tenant B files | not_verified | Requires Storage signed URL/RLS live test. Credentials missing. |
| Tenant A cannot start Tenant B worker jobs | not_verified | Upload-to-worker integration is not wired/tested yet. |
| Tenant A cannot view Tenant B evidence | not_verified | Requires canonical evidence API/UI/RLS live test. |
| Tenant A cannot view Tenant B job statuses | not_verified | Requires worker-job API/RLS live test. |

## Estimator project queue connection

Current app source uses existing EstimateJob states:

- `intake_received`
- `intake_review_pending`
- `intake_needs_info`
- `ready_for_document_processing`
- `document_processing`
- `document_review_pending`
- `takeoff_ready`
- `takeoff_in_progress`
- `pricing_review_pending`
- `qa_pending`
- `ready_for_owner_approval`
- `blocked`
- `canceled`
- `closed`

The prompt's desired queue labels (`new_project`, `documents_processing`, `needs_clarification`, etc.) now exist in the estimator workbench model PR, but the customer upload path still uses the existing EstimateJob state machine. Mapping/unifying these labels remains a follow-up.

## Backup status investigation

Observed current system state:

- OS timers active: `dpkg-db-backup.timer`, `logrotate.timer`, `apt-daily.timer`, `apt-daily-upgrade.timer`.
- `/var/backups` contains recent OS package metadata backups such as `dpkg.status.*`, `apt.extended_states.*`, and `alternatives.tar.*`.
- Repo search found no tracked Mobi app/database/customer-file backup scripts.
- Repo docs already state app/database backups beyond OS package backups are not fully verified.
- Supabase credentials / DB URL / Supabase access token are missing in this shell, so Supabase/Postgres backup configuration and restore cannot be verified here.

| Backup area | Status | Evidence / reason |
|---|---|---|
| OS package metadata backups | partially_working | System timers and `/var/backups` files present. This is not Mobi app/data backup. |
| application/database backup process | not_verified | No repo backup script found; no DB credentials available. |
| Supabase/Postgres backup | not_verified | No Supabase credentials/PAT/DB URL available in this shell. |
| customer file recovery strategy | not_verified | No tracked restore procedure verified. |
| isolated restore test | not_verified | Not possible here without DB/storage backup source and credentials. |
| retention/encryption/responsible automation | not_verified | Not evidenced beyond OS package backup timers. |

## Launch-impacting blockers from this verification

1. Live Stripe test-mode checkout cannot be verified until Stripe test secret, webhook secret, coupon id, and every offer price id are available in a safe test/staging environment.
2. Live Supabase/Auth/Storage/RLS E2E cannot be verified until Supabase URL/anon/service role or approved test access is available.
3. Upload → EstimateJob queue creation is source-backed but not live-verified.
4. Upload → OpenTakeoff worker document identity is not yet integrated end-to-end.
5. Two-tenant isolation is not yet live-verified.
6. Mobi app/DB/storage backups and an isolated restore are not yet verified.
