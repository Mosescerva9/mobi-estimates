# TODO — Mobi Estimates Portal

Working task list. See `ROADMAP.md` for ordering/dependencies and
`LAUNCH_CHECKLIST.md` for the pre-launch gate. Status: ✅ done · 🟡 in progress · ⬜ todo.

## Active
- ✅ **Company onboarding flow** (`/onboarding`): create company + membership + preferences.
- 🟡 **Stripe payments** — code complete (checkout API, verified idempotent webhook,
  `/billing` plan picker, success page, auto-activating paywall on the portal). Plans
  seeded. **Remaining:** (1) create the 3 recurring products in **test mode** and write
  their price IDs into `plans.stripe_price_id`; (2) set `STRIPE_SECRET_KEY`,
  `STRIPE_WEBHOOK_SECRET`, `SUPABASE_SERVICE_ROLE_KEY` in Vercel; (3) add the Stripe
  webhook endpoint → `/api/stripe/webhook`. _Blocked only because the Stripe connection
  is in LIVE mode and we chose test-first._

## Blocked on info/credentials from owner
- ⬜ Confirm plan names, monthly prices, capacity, turnaround, revision policy → `OWNER_DECISIONS.md §2–4`.
- ⬜ Provide **Stripe** secret key + create one recurring Price per plan + webhook secret.
- ⬜ Provide **Resend** API key + verified sending domain + `EMAIL_FROM`.
- ⬜ Provide **`SUPABASE_SERVICE_ROLE_KEY`** in Vercel (server-only) for webhooks/admin.
- ⬜ Provide/approve **legal** text (Terms, Privacy, Estimating Disclaimer, Cancellation, Refund).
- ⬜ Confirm support email, file-size limits, refund/cancellation policy.

## Config (no code, do in dashboards)
- ⬜ Vercel: turn **off Deployment Protection** so the public can reach the site (currently 401).
- ⬜ Supabase Auth: enable **leaked-password protection**; confirm email-confirmation setting;
  point Auth SMTP at Resend for production-grade auth emails.
- ⬜ Supabase Storage: create private buckets `project-files` + `deliverables` with member/staff policies.
- ⬜ Seed `plans` rows once pricing is confirmed.

## Build queue (code)
- ⬜ Stripe: `/api/stripe/checkout` (create session) + `/api/stripe/webhook` (verified, idempotent).
- ⬜ Checkout success/cancel pages; gate `/portal/projects/new` on `subscription.status = active`.
- ⬜ Storage helpers + signed-URL upload/download utilities.
- ⬜ Project intake form (`/portal/projects/new`) with multi-file upload + Zod validation.
- ⬜ Client project list (`/portal/projects`) + detail (`/portal/projects/[id]`) with timeline.
- ⬜ Admin dashboard: submissions queue, assign, status change, deliverable upload, internal notes.
- ⬜ Email (Resend) templates + send-on-event wiring.
- ⬜ In-app notifications (bell, list, mark-read).
- ⬜ Remaining portal pages currently 404 from the nav: `questions`, `estimates`,
  `subscription`, `training`, `support`, `account`.
- ⬜ Legal pages routes + footer links.

## Known issues found in audit (2026-06-24)
- ⚠️ Portal sidebar links to 8 routes; only the dashboard exists → the rest 404. Build or hide.
- ⚠️ New client has no company → portal cards are all "—" and RLS blocks data. _(onboarding fixes the company gap.)_
- ⚠️ Several SECURITY DEFINER functions still callable via RPC (advisor WARN) — review in Security milestone.
- ⚠️ `plans` table empty; pricing on the marketing site is unconfirmed (do not hard-code).
