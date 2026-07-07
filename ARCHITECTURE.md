# Architecture — Mobi Estimates Client Portal

_Last updated: 2026-07-04. Keep this current when the stack or data flow changes._

## Overview
Mobi Estimates is a self-service construction-estimating SaaS. Contractors sign
up, pay a monthly capacity-based plan, onboard their company, submit projects
with plan documents, and receive completed estimates. Mobi's internal team works
projects through a production pipeline in an admin dashboard.

## Stack (current)
| Concern | Technology | Status |
|---|---|---|
| Framework | Next.js 15 (App Router) + React 18 + TypeScript | ✅ in use |
| Styling | Tailwind CSS | ✅ in use |
| Hosting | Vercel (project `mobi-portal`, root dir `mobi-portal/`) | ✅ deployed |
| Auth | Supabase Auth (email + password) | ✅ working |
| Database | Supabase Postgres with RLS plus Phase 1A EstimateJob migration | 🟡 migration pending target apply |
| Authorization | Postgres Row Level Security + route guards | ✅ working |
| File storage | Supabase Storage private `project-files` + `deliverables` buckets | 🟡 migrations added; apply before launch |
| Payments | Stripe Checkout + Billing + webhooks | ❌ not built (needs keys) |
| Transactional email | Resend | ❌ not built (needs keys) |
| Validation | Zod | ✅ used on project intake/API paths |

## Repository layout
The Mobi Estimates app and generated marketing assets live in this repository and
are built/deployed through Vercel. Customer-facing absolute URLs must use the
canonical production origin `https://mobiestimates.com`; preview, staging, portal
subdomain, and legacy static-host URLs must not be used in marketing materials or
Stripe/email return paths.

## Request / auth flow
1. **Browser → Supabase Auth.** Login/signup/reset run client-side with the
   anon key (`src/lib/supabase/client.ts`). Supabase sets the session cookie.
2. **Middleware** (`src/middleware.ts`) refreshes the session on every request
   and redirects unauthenticated users away from `/portal`, `/onboarding`,
   `/admin`. This is UX only.
3. **Server components** read the verified user via `getSessionUser()`
   (`src/lib/auth.ts`), which calls `supabase.auth.getUser()` (never trusts a
   raw cookie) and joins `profiles` for the role.
4. **Row Level Security is the real security boundary.** Every table denies by
   default; clients can only touch rows for companies they belong to
   (`company_members`); staff roles see operational data across companies. See
   `DATABASE_SCHEMA.md` and `supabase/migrations/0002_policies.sql`.

## Three Supabase clients (do not mix them up)
- `lib/supabase/client.ts` — browser, anon key, RLS enforced.
- `lib/supabase/server.ts` — server components / route handlers, anon key, RLS
  enforced, bound to request cookies.
- `lib/supabase/admin.ts` — **service-role key, BYPASSES RLS, server-only.**
  Only for trusted server code (Stripe webhooks, admin automation). Never import
  into a client component. Requires `SUPABASE_SERVICE_ROLE_KEY` (not yet set).

## Roles
`client` · `estimator` · `reviewer` · `admin`. The global role lives on
`profiles.role`. A user joins a company via `company_members` (with a
company-scoped role). Staff = estimator/reviewer/admin.

## Provisioning chain (target end state)
`Stripe Checkout (pay)` → `checkout.session.completed` webhook (service role) →
create/find `companies` + `subscriptions(active)` + link `company_members` →
client logs in → **onboarding** (company profile) → **portal** (submit projects).

Until Stripe is wired, onboarding creates the company directly and an admin can
set a subscription to `active` manually. See `ROADMAP.md`.

## Key files
- `src/lib/auth.ts` — `getSessionUser`, `requireUser`, `requireStaff`, role helpers.
- `src/lib/company.ts` — `getPrimaryCompanyId` (membership lookup for routing).
- `src/middleware.ts` — session refresh + route gating.
- `src/app/onboarding/` — company creation flow (first buildable feature).
- `src/app/api/projects/route.ts` — server-validated project intake and internal EstimateJob creation.
- `src/app/api/projects/[id]/estimate-job-sync/route.ts` — post-upload sync/recovery for the internal document register.
- `src/app/portal/projects/new/NewProjectForm.tsx` — client intake form and direct private-storage upload flow.
- `src/app/admin/projects/[id]/EstimateJobPanel.tsx` — internal-only Phase 1A job/document/review panel.
- `src/lib/estimate-jobs.ts` and `src/lib/intake-review.ts` — EstimateJob constants, idempotent job/document helpers, and deterministic intake review packets.
- `supabase/migrations/` — schema (`0001`), RLS (`0002`), hardening (`0003`).

## Known gaps (see ROADMAP.md / TODO.md)
No production Stripe configuration, no email, no notifications, legal pages still
need owner/legal review, Phase 1A EstimateJob changes need review/migration apply,
plans/pricing require owner approval, and Vercel Deployment Protection may still
need to be turned off before public launch.
