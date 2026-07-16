# Current State Audit

Updated: 2026-07-16T00:35Z

Status vocabulary: `working`, `partially_working`, `broken`, `missing`, `not_verified`.

> Rule: Do not mark working because code exists. Statuses below are based only on tests, live-safe probes, or verified command output from this session.

| Area | Status | Evidence | Next verification |
|---|---|---|---|
| Main website | partially_working | `npm run typecheck`, `npm run lint`, and `npm run build` passed; Next generated `/`, `/pricing`, `/login`, `/signup`, `/start`, portal/admin routes. | Browser-safe live/preview smoke on canonical domain without checkout submission |
| Pricing page | partially_working | `/pricing` route built; checkout-flow/readiness/prefetch harnesses passed. | Browser read-only CTA verification; do not start live checkout without approval |
| Stripe checkout | partially_working | `npm run test:checkout-flow` passed 13/13 using in-memory fakes; no live credentials used. | Test-mode/staging or owner-approved live session validation |
| Payment webhooks | partially_working | Checkout harness covers webhook paid, duplicate delivery, mismatched claim/session protections. | Real Stripe test-mode webhook replay if credentials available |
| Account creation | partially_working | Checkout harness covers claim-account/link/finalize states; app build includes `/signup`, `/login`, `/onboarding`. | Auth E2E with test user |
| Login | not_verified | `/login` route builds. | Auth E2E with test user |
| Customer portal | partially_working | Portal routes build; customer revision portal safety check passed. | Authenticated portal E2E with fixture user/company/project |
| Staff/admin portal | partially_working | Admin routes build; admin revision workflow check passed. | Authenticated staff E2E with fixture data |
| Project creation | partially_working | `/api/projects` route builds; project-upload helper tests passed 14/14. | API integration/E2E with test auth and storage |
| File upload | partially_working | Upload helper tests cover type/size/name/path uniqueness; no storage E2E yet. | Storage/RLS upload E2E |
| Project status tracking | partially_working | EstimateJob/admin handoff safety tests exist; deliverable gate passed 36/36. | Full status workflow E2E |
| Database | partially_working | Local migrations tests passed in focused suite; Supabase migration `0024` not applied/verified in production. | Query applied production catalog if credentials/path available |
| Tenant isolation | partially_working | `npm run test:engine-tenant-context` passed; deliverable RLS gate passed. | Two-tenant production/staging E2E |
| Storage permissions | partially_working | Deliverable storage RLS gate passed; upload storage RLS not yet exercised live. | Project-files storage RLS E2E |
| Document-processing pipeline | partially_working | Mobi engine process active on `127.0.0.1:8000`; targeted Golden Set/real-document Python tests passed. | Engine health endpoint/API workflow E2E |
| Estimate generation | not_verified | No full estimate generation E2E run yet. | Golden Set estimate generation / assembly tests |
| Quantity evidence structures | working | Canonical evidence/provider/store/migration tests passed: `python -m pytest tests/test_takeoff_evidence.py tests/test_takeoff_store.py tests/test_migrations.py -q` → 108 passed. | Production migration application remains separate approval/verification |
| Pricing structures | not_verified | Checkout pricing readiness harness passed; estimate pricing engine not audited. | Assembly/pricing engine tests |
| Revision workflow | partially_working | Customer revision portal safety and admin revision workflow checks passed. | End-to-end revision request→preview→apply/version test |
| Bid-package exports | partially_working | Deliverable gate tests passed; actual PDF/Excel export not verified. | Generate fixture package and verify contents/download gate |
| Email notifications | not_verified | Not tested; no emails sent. | Static implementation review and safe email test harness |
| Production deployment | partially_working | Caddy active; ports 80/443 open; GitHub/Vercel checks exist on PRs. No production deploy performed. | Read-only live smoke + deployment status review |
| Open PRs | partially_working | 5 open PRs inventoried in `docs/mvp/open-pr-inventory.md`. | Close/supersede or reduce after MVP branch PR |
| Current branches | partially_working | Branch created from `origin/main`; many stale branches observed. | Clean branch policy after MVP PR opens |
| CI | partially_working | Current open PRs show Vercel status contexts; local build/tests passed. | Check new MVP PR status after push |
| Backups | partially_working | OS `dpkg-db-backup.timer` active; `/var/backups` recent. App/DB backups not yet verified. | Locate app/database backup system |
| Environment variables | not_verified | Repo `.env*` not present in checked paths; no secret values printed. | Deployment env-key inventory without values |
| Secrets handling | partially_working | Checkout readiness harness and deliverable/engine tenant checks passed; no full static secret scan yet. | Secret/client-bundle scan |

## Verification commands run
- `npm run typecheck` → passed.
- `npm run lint` → passed.
- `npm run build` → passed.
- `cd mobi-estimating-phase1 && python -m pytest tests/test_golden_set_extraction_eval.py tests/test_mobi_autoresearch.py tests/test_real_document_harness.py -q` → passed.
- `cd mobi-estimating-phase1 && python -m pytest tests/test_takeoff_evidence.py tests/test_takeoff_store.py tests/test_migrations.py -q` → 108 passed.
- Checkout/upload/deliverable/revision harnesses listed in progress doc → passed.

## System facts
- Repo remote: `https://github.com/Mosescerva9/mobi-estimates.git`.
- Branch: `mvp-opentakeoff-customer-launch` from `origin/main` at `2269b8a`.
- Essential services observed active: `caddy`, `docker`, `cron`, `ssh`, Mobi engine uvicorn on `127.0.0.1:8000`.
- Disk risk: `/` is 95% full; no cleanup performed.
