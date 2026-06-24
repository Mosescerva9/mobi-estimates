# Launch Checklist — Mobi Estimates Portal

Gate to accepting the first paying client. Check every box. Status: ✅ / ⬜.

## Accounts & config
- ⬜ Vercel Deployment Protection **off** (site publicly reachable, no 401).
- ⬜ `SUPABASE_SERVICE_ROLE_KEY` set in Vercel (server-only).
- ⬜ Supabase Auth: email confirmation decision made; leaked-password protection on; Auth SMTP → Resend.
- ⬜ Storage buckets `project-files` + `deliverables` created (private) with member/staff policies.
- ⬜ `plans` rows seeded with **confirmed** pricing/capacity; `stripe_price_id` set on each.
- ⬜ Stripe live keys + webhook endpoint + signing secret configured.
- ⬜ Resend domain verified; `EMAIL_FROM` set.
- ⬜ Custom domain (e.g. `portal.mobiestimates.com`) pointed at Vercel + HTTPS.

## Authentication
- ⬜ Sign up → verify email (if enabled) → log in → log out.
- ⬜ Password reset email arrives and sets a new password.
- ⬜ Protected routes redirect when logged out; role routing correct (client→portal, staff→admin).
- ⬜ First admin account created (set `profiles.role='admin'` or via `ADMIN_BOOTSTRAP_EMAILS`).

## Payments (Stripe test mode first, then live)
- ⬜ Checkout completes for each plan.
- ⬜ Webhook creates/activates the `subscriptions` row; idempotent on retried events.
- ⬜ Failed payment → status `past_due`; access correctly restricted.
- ⬜ Cancellation → `canceled` and access ends at period end.
- ⬜ Receipt/invoice email sends.

## Onboarding & portal
- ⬜ After payment, client reaches onboarding, creates company, lands in portal.
- ⬜ New project submission saves; required fields validated.
- ⬜ Large file uploads succeed (test near the configured max size).
- ⬜ Files stored privately; downloads use signed URLs only.
- ⬜ Project list + detail show correct status, timeline, deliverables.
- ⬜ Subscription/capacity usage displays correctly.

## Internal/admin
- ⬜ Staff sees all clients/projects; can filter/sort.
- ⬜ Assign estimator; change status writes `project_status_history` + fires notifications/emails.
- ⬜ Upload deliverable; client can download it.
- ⬜ Revision request round-trip works.
- ⬜ Internal notes never visible to clients.

## Security
- ⬜ **Cross-company isolation**: client A cannot read/modify client B's data (manual test + RLS review).
- ⬜ Service-role key never shipped to browser (grep build output for the key — must be absent).
- ⬜ `internal_note` never returned to a client session.
- ⬜ Supabase advisors reviewed; no unexpected EXTERNAL warnings.
- ⬜ Rate limiting / abuse considerations for upload + auth endpoints noted.

## Email
- ⬜ All transactional emails render on mobile and deliver (not spam-foldered).

## Mobile & UX
- ⬜ Login, onboarding, submit-project, project detail usable on a phone.
- ⬜ No broken nav links (every sidebar item resolves).

## Operations
- ⬜ Database backups confirmed (Supabase daily backups on the plan; know restore steps).
- ⬜ Error monitoring receiving events (Sentry or equivalent).
- ⬜ Application logs reviewable (Vercel + Supabase logs).
- ⬜ Rollback plan: know how to redeploy a previous Vercel build.

## Soft launch
- ⬜ One real end-to-end run with a friendly/first client in production.
- ⬜ Owner sign-off on legal pages (attorney-reviewed) and pricing.
