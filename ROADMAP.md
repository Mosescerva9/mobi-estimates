# Launch Roadmap — Mobi Estimates Portal

_Ordered by dependency. Status legend: ✅ done · 🟡 in progress · ⬜ not started._
_Last updated: 2026-06-24._

## Current state (one paragraph)
The portal is a deployed Next.js 15 app on Vercel backed by a live Supabase
project with a complete, RLS-secured 27-table schema. **Working today:** email/
password sign-up, login, logout, password-reset request, role-protected routing,
and the signup→profile trigger. **Not built yet:** payments, company onboarding,
project intake, file storage, the internal/admin dashboard, email, and
notifications. A newly signed-up client currently lands in an empty portal
because they belong to no company — closing that gap is the active work.

---

## MUST HAVE — before the first paying client

> Goal: a contractor can pay, get access, onboard, submit a project with files,
> and Mobi can work it and deliver. Build in this order.

1. ✅ **Auth foundation** — signup, login, logout, reset, protected routes, roles. _(done)_
2. 🟡 **Company onboarding / account provisioning** — create `companies` +
   `company_members` + `company_preferences` after signup so RLS grants access.
   _First feature being implemented now. No external credentials required._
   - Dependency for: everything client-facing (RLS needs company membership).
3. ⬜ **Make the site publicly reachable** — turn off Vercel Deployment Protection
   (currently returns 401 to the public). _Config, 2 minutes._
4. ⬜ **Plans seeded + pricing confirmed** — insert real `plans` rows. _Blocked on
   confirmed pricing (OWNER_DECISIONS.md §2)._
5. 🟡 **Stripe payments** — Checkout, `subscriptions` write via verified idempotent
   webhook (`checkout.session.completed`, `customer.subscription.*`,
   `invoice.payment_failed`), `/billing` plan picker + success page. **Code done &
   building.** Remaining: create test-mode products + price IDs, set Vercel env
   (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`), add
   the Stripe webhook endpoint.
6. ✅ **Access gating by subscription** — portal redirects an inactive company to
   `/billing`; the paywall auto-activates once `STRIPE_SECRET_KEY` is set, so the
   app stays usable pre-Stripe. _(built with #5)_
7. ⬜ **Storage buckets** — private `project-files` + `deliverables` with member/
   staff policies; signed URLs only. _No credentials needed._
8. ⬜ **Project intake** — new-project form (details, deadlines, trade scope,
   location, special instructions) + multi-file upload of large construction docs.
   _Depends on #2, #7._
9. ⬜ **Project list + detail (client)** — status, timeline, files, deliverables.
   _Depends on #8._
10. ⬜ **Internal/admin dashboard (MVP)** — all projects, assign estimator, change
    status (writes `project_status_history`), upload deliverables, internal notes.
    _Depends on #8._
11. ⬜ **Transactional email (Resend)** — welcome, project received, status
    changes, deliverable ready, payment receipts/failures. Also wire Supabase Auth
    SMTP to Resend (the default email sender is rate-limited / not for production).
    _Blocked on Resend keys._
12. ⬜ **Core legal pages** — Terms, Privacy, Estimating Service Disclaimer,
    Subscription/Cancellation, Refund. Draft + attorney review. _Blocked on owner/legal._
13. ⬜ **End-to-end test pass** — see `LAUNCH_CHECKLIST.md` (cross-company isolation,
    Stripe test mode, file upload, mobile, email).

## SHOULD HAVE — within the first 30 days
- In-app notifications (bell + `notifications` table) and read state.
- Stripe Billing Portal (upgrade/downgrade/cancel/update card) + dunning for failed payments.
- Revision request flow (client requests → staff handles `revision_requests`).
- Estimator questions/RFI flow (`project_questions` / `question_responses`) with client answers.
- Account & company settings pages; subscription/capacity usage meter.
- Onboarding training modules + FAQ content; terms acceptance recorded in `agreement_acceptances`.
- Support tickets (`support_tickets`) + support email.
- Error monitoring (Sentry free tier) + basic analytics (Vercel Analytics / Plausible).
- Capacity tracking (bids used vs. plan `active_capacity`) surfaced to client and admin.
- Admin filtering/sorting, flag-missing-info, activity history views.

## CAN BE ADDED LATER
- AI support chatbot trained only on approved `faq_entries` content.
- Multi-user companies / invite teammates; granular per-company roles.
- Automated capacity overage → upsell / custom quote.
- Client-facing analytics, downloadable invoices archive, saved templates.
- Move `mobi-portal/` into its own repository with CI.
- SSO, audit-log UI, advanced reporting/BI.

---

## Project lifecycle (recommended) + automated triggers
The `project_status` enum already encodes the pipeline. Recommended automation:

| Status | Who sets it | Auto email to client | In-app notif | Internal alert |
|---|---|---|---|---|
| draft | client (saving) | — | — | — |
| submitted | client | ✅ "We received your project" | ✅ | ✅ new submission → ops |
| needs_information | staff | ✅ "We need documents/info" | ✅ | — |
| under_internal_review | staff | — | — | — |
| accepted / scheduled | staff | ✅ "Accepted — target date" | ✅ | — |
| document_review → pricing_in_progress | staff | optional digest | ✅ | — |
| clarification_required | staff | ✅ (RFI) | ✅ | — |
| qa_review | staff | — | — | ✅ reviewer |
| ready_for_delivery | staff | — | — | ✅ |
| delivered | staff | ✅ "Your estimate is ready" + link | ✅ | — |
| revision_requested | client | — | ✅ | ✅ ops |
| revised | staff | ✅ "Revised estimate ready" | ✅ | — |
| approved / closed | client/staff | ✅ receipt/summary | ✅ | — |
| canceled | either | ✅ confirmation | ✅ | ✅ |

Principle: clients only ever see `client_note` + client-safe timeline; never `internal_note`.

## Stack decisions (see ARCHITECTURE.md for detail)
Keep: **Next.js + Vercel + Supabase (Auth/DB/RLS/Storage)**. Add only:
**Stripe** (payments) and **Resend** (email). Postpone: Sentry/analytics (free
tiers, week 2+), AI chatbot (later). Not needed: Firebase, Clerk, Auth0, SendGrid,
AWS S3, Cloudflare R2 — Supabase already covers auth + storage. This is the lean,
secure stack that scales to the first cohort without a rebuild.
