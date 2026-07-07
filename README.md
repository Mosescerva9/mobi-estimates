# Mobi Estimates — Client Portal

A self-service onboarding, project-submission, and estimate-delivery portal for
**Mobi Estimates** (M-O-B-I) — outsourced construction estimating for GCs, subs,
developers and builders.

> **Status: Milestone 1 — Foundation + app shell, now connected to a live
> Supabase project.** This folder holds the service-independent foundation
> (Supabase schema + RLS, env template, docs) **and** a runnable Next.js +
> Supabase app shell (auth, role-protected portal/admin layouts, middleware).
> The shell **type-checks (`tsc --noEmit`) and builds (`next build`) cleanly**.
>
> **Live Supabase project** `mobi-portal` (ref `kzgfcgzewmqwlxfadtgz`, org
> "Moni estimates", region us-east-1, free tier) has been created and the
> migrations applied: all 27 tables exist with RLS enabled, helper functions +
> policies + the signup trigger are in place (plus `0003` hardening: pinned
> `search_path` and revoked public EXECUTE on internal-only functions). The
> signup trigger was verified end-to-end — a new `auth.users` row auto-creates a
> `public.profiles` row with the default `client` role. Copy `.env.example` →
> `.env.local` with the project URL + anon key to run locally.
>
> **One value still to add:** `SUPABASE_SERVICE_ROLE_KEY` (server-only secret,
> from Dashboard → Project Settings → API). It's only needed for the admin
> client / Stripe webhooks (Milestone 2+); auth and RLS work without it.
>
> **Note on this build environment:** the dev container's network egress is
> restricted, so a *running* dev server here cannot reach `*.supabase.co`
> directly (DB work above was done over the Supabase management API). Run the app
> locally or on Vercel, where egress is open, to exercise the live auth flow in a
> browser.

---

## Architecture decision (recorded)

The customer-facing website and checkout entry point use the canonical public origin
`https://mobiestimates.com`. The Next.js + Supabase application is deployed through
Vercel and must generate customer-facing absolute links from that canonical origin,
not from preview, staging, portal-subdomain, or legacy static-host URLs.

**Architecture note:** this repository now carries both the app shell and the generated
marketing-site assets. Keep customer-facing routes, canonical URLs, Stripe success/cancel
URLs, billing-portal return URLs, and email claim links pointed at
`https://mobiestimates.com` unless Moses explicitly approves a different public domain.

**Stack:** Next.js 15 (App Router) + TypeScript · Supabase (Auth, Postgres, RLS,
Storage) · Stripe Checkout + Billing · Resend · React Hook Form + Zod · Tailwind +
shadcn/ui · Vercel. No GoHighLevel, no paid CRM, no hard-coded secrets.

## Current status (2026-07-04)

The runnable app now exists against Supabase. Working in code: sign-up, login,
logout, password-reset request, role-protected routing, company onboarding, Stripe
checkout/webhook scaffolding, private storage migrations, project intake with
direct uploads, client project list/detail, and the internal/admin Phase 1A
EstimateJob control plane. Still pending before launch: code review, migration
application in the target environment, production Stripe/Resend/legal/config
approval, and an end-to-end staff/client verification pass.

**Read these for the full picture:**
- `ROADMAP.md` — what to build next, in dependency order (Must / Should / Later).
- `TODO.md` — the working task list and blocked-on-owner items.
- `ARCHITECTURE.md` — stack, auth flow, the three Supabase clients, provisioning chain.
- `DATABASE_SCHEMA.md` — every table + the security/advisor findings.
- `ENVIRONMENT_VARIABLES.md` — every env var, what it's for, where to get it.
- `LAUNCH_CHECKLIST.md` — the gate before the first paying client.
- `OWNER_DECISIONS.md` — business/legal values only the owner can supply.

---

## What's in this folder (Milestone 1 foundation)

```
mobi-portal/
├── README.md                      ← this file
├── OWNER_DECISIONS.md             ← business/legal values only the owner can supply
├── .env.example                   ← full env contract (no secrets)
└── supabase/
    ├── migrations/
    │   ├── 0001_schema.sql        ← tables, enums, indexes, triggers, project numbering
    │   └── 0002_policies.sql      ← RLS helpers + policies, signup trigger, storage notes
    └── seed.sql                   ← LOCAL ONLY, clearly-labeled fictional/placeholder data
```

## Proposed app structure (next step)

```
src/
├── app/
│   ├── (marketing)/               ← optional: pricing/checkout entry if unified later
│   ├── (auth)/login, /signup, /reset, /verify
│   ├── checkout/success, /cancel
│   ├── onboarding/                ← required checklist (saves progress per section)
│   ├── portal/                    ← client dashboard, projects, questions, deliverables
│   ├── admin/                     ← estimator/reviewer/admin production dashboard
│   └── api/
│       ├── stripe/checkout        ← create Checkout Session (records agreement version)
│       └── stripe/webhook         ← verified events → subscriptions (idempotent)
├── lib/
│   ├── supabase/{client,server,admin}.ts   ← browser / RLS server / service-role
│   ├── stripe.ts, resend.ts, auth.ts (role guards)
│   └── validation/ (zod schemas)
├── components/ui (shadcn) + portal components
└── config/site.ts, plans.ts (reads from DB; OWNER_DECISIONS placeholders)
```

---

## Setup (when ready to run the app)

### 1. Supabase
1. Create a project at supabase.com. Copy URL, anon key, service-role key into `.env.local`.
2. Install CLI: `npm i -g supabase`. Link: `supabase link --project-ref <ref>`.
3. Apply schema + policies: `supabase db push` (runs `supabase/migrations/*`).
4. (Local dev only) load placeholders: `supabase db execute -f supabase/seed.sql`.
5. Storage: apply the storage migrations for **private** `project-files` and
   `deliverables` buckets. The app uses signed URLs and keeps project files private.

### 2. Stripe
1. Create one **Price** per plan (recurring monthly). Paste IDs into `.env.local`
   and/or the `plans.stripe_price_id` column.
2. Add a webhook endpoint → `https://mobiestimates.com/api/stripe/webhook`,
   subscribe to: `checkout.session.completed`, `customer.subscription.created`,
   `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`,
   `invoice.payment_failed`. Copy the signing secret to `STRIPE_WEBHOOK_SECRET`.
3. The webhook handler verifies signatures and is **idempotent** (stores processed
   event IDs in `webhook_events`). Success-page redirects are never trusted as proof
   of payment.

### 3. Resend
Verify your sending domain, set `RESEND_API_KEY` and `EMAIL_FROM`.

### 4. Vercel
Import the portal repo, add all `.env` vars (mark `SUPABASE_SERVICE_ROLE_KEY` and
Stripe secrets as server-only / not `NEXT_PUBLIC_`), deploy, point DNS.

---

## Security model (enforced in `0002_policies.sql`)
- **Default-deny RLS** on every table; clients see only rows for companies they
  belong to; staff (estimator/reviewer/admin) see operational data across companies.
- **Never trust the frontend** — RLS is the source of truth; route guards are UX only.
- **Service-role key is server-only** (webhooks/admin); never shipped to the browser.
- **Private file storage** + short-lived signed URLs; no public file URLs.
- **internal_note** on the project timeline is hidden from clients (clients read the
  `client_timeline()` RPC / a client-safe view, not the base table).
- Stripe is the only place card data lives; passwords are handled by Supabase Auth.

## Roles
`client` · `estimator` · `reviewer` · `admin`. A company has many users; users are
linked via `company_members`. Bootstrap the first admin by adding your email to
`ADMIN_BOOTSTRAP_EMAILS` (handled in the app's auth step) or by setting
`profiles.role = 'admin'` directly in Supabase.

## How to edit common things
- **Plans/prices:** `plans` table (or `config/plans.ts` defaults) — values are
  placeholders until OWNER_DECISIONS.md is confirmed.
- **FAQ / assistant knowledge:** `faq_entries` table (approved content only).
- **Training videos:** `training_modules.video_url`.
- **Agreement text:** `service_agreements` (versioned; acceptances are recorded).

## Launch checklist (high level)
- [ ] OWNER_DECISIONS.md completed
- [ ] Supabase migrations applied, including storage buckets/policies and Phase 1A EstimateJob tables
- [ ] Stripe prices + webhook live and verified
- [ ] Resend domain verified
- [ ] Legal drafts reviewed by an attorney
- [ ] First admin user created
- [ ] Cross-company access test passes (client A cannot see client B)
- [ ] Stripe test-mode end-to-end: checkout → webhook → subscription active → onboarding

## Roadmap (milestones)
M1 foundation → M2 Stripe/checkout/webhooks → M3 onboarding → M4 project intake +
files + validation + EstimateJob control plane → M5 admin dashboard → M6 questions
and email → M7 deliverables + revisions + capacity → M8 FAQ + assistant + tickets →
M9 security/testing/deploy. Each milestone ends with lint, type-check, tests, and a
summary.
