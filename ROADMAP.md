# Launch Roadmap — Mobi Estimates Portal

_Ordered by dependency. Status legend: ✅ done · 🟡 in progress · ⬜ not started._
_Last updated: 2026-07-04._

## Current state (one paragraph)
The portal is a Next.js 15 app backed by Supabase Auth/Postgres/RLS/Storage.
**Working in code:** email/password auth, role-protected routing, company onboarding,
Stripe checkout/webhook scaffolding, private project/deliverable storage migrations,
project intake with direct-to-storage uploads, client project list/detail, and an
internal admin queue/detail with Phase 1A EstimateJob control-plane wiring. **Still
approval/config dependent:** public Vercel access, production Stripe prices/secrets,
Resend/email, legal pages, production deployment, and first-client E2E verification.

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
7. ✅ **Storage buckets** — private `project-files` + `deliverables` with member/
   staff policies and signed URLs only. _(migrations added; apply before launch)_
8. 🟡 **Project intake + EstimateJob control plane** — new-project form, structured
   scope/exclusions/open questions, requested completion date, direct file upload,
   upload sync recovery, and internal `estimate_jobs`/document register/event log.
   _Code built; pending review, migration application, and E2E verification._
9. ✅ **Project list + detail (client)** — status, client-safe timeline, files,
   deliverables, and structured scope details without internal notes.
10. 🟡 **Internal/admin dashboard (MVP)** — queue, assignment, status changes,
    deliverable upload, internal notes, and EstimateJob panel/actions. _Code built;
    pending review + production data verification._
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
The `project_status` enum already encodes the pipeline. Recommended automation is paused behind the GPT-5.6 Sol audit P0 final-delivery gate: no status label, upload, email, or in-app notification is proof that a construction estimate is complete or safe to deliver. Customer-facing final-estimate delivery requires complete evidence, supported scope, required reviews, and explicit owner approval before any customer link/message is exposed.

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
| ready_for_delivery | staff | — | — | ✅ internal owner-review candidate only |
| delivered | staff | Locked by P0 final-delivery gate | Locked by P0 final-delivery gate | — |
| revision_requested | client | — | ✅ | ✅ ops |
| revised | staff | Locked by P0 final-delivery gate | Locked by P0 final-delivery gate | — |
| approved / closed | client/staff | ✅ receipt/summary | ✅ | — |
| canceled | either | ✅ confirmation | ✅ | ✅ |

Principle: clients only ever see `client_note` + client-safe timeline; never `internal_note`.

## Stack decisions (see ARCHITECTURE.md for detail)
Keep: **Next.js + Vercel + Supabase (Auth/DB/RLS/Storage)**. Add only:
**Stripe** (payments) and **Resend** (email). Postpone: Sentry/analytics (free
tiers, week 2+), AI chatbot (later). Not needed: Firebase, Clerk, Auth0, SendGrid,
AWS S3, Cloudflare R2 — Supabase already covers auth + storage. This is the lean,
secure stack that scales to the first cohort without a rebuild.
