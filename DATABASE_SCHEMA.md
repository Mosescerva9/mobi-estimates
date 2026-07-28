# Database Schema — Mobi Estimates Portal

Source of truth: `supabase/migrations/0001_schema.sql` (tables/enums/indexes),
`0002_policies.sql` (RLS + helper functions + signup trigger), `0003_harden_functions.sql`.
All 27 tables are applied to the live project and have **RLS enabled**.

## Enums
- `user_role`: client, estimator, reviewer, admin
- `subscription_status`: pending, active, past_due, canceled, suspended
- `company_type`: general_contractor, subcontractor, developer, owner, supplier, other
- `project_type`: residential, commercial, industrial, civil, infrastructure, mixed
- `project_status`: draft, submitted, needs_information, under_internal_review, accepted,
  scheduled, document_review, takeoff_in_progress, pricing_in_progress, clarification_required,
  qa_review, ready_for_delivery, delivered, revision_requested, revised, approved, closed, canceled
- `question_status`: open, answered, resolved, assumption_required, overdue
- `ticket_status`: open, in_progress, waiting_on_client, resolved, closed
- `revision_category`: mobi_correction, minor_clarification, client_repricing, new_addendum,
  design_change, scope_change, full_re_estimate

## Tables (grouped)

### Identity & company
- **profiles** — 1:1 with `auth.users`. `id, full_name, email, phone, role`. Auto-created on
  signup by the `handle_new_user` trigger (default role `client`). _RLS: self or staff read._
- **companies** — `legal_name, preferred_name, website, address, company_type, created_by`,
  plus `intake_slug` (migration 0036) — the unguessable local part of the company's forwarded-bid
  address, `{intake_slug}@{NEXT_PUBLIC_INTAKE_EMAIL_DOMAIN}`. Assigned by the
  `companies_set_intake_slug` BEFORE INSERT trigger so no code path can create a company without
  one; unique via a partial index.
- **company_members** — links `user_id` ↔ `company_id` with company-scoped `role`, `is_primary`.
  **This membership is what RLS uses to grant clients access to their data.**

### Plans, billing, agreements
- **plans** — `code, name, price_cents, active_capacity, max_active_projects, stripe_price_id, …`.
  _Currently empty — must be seeded before checkout._
- **subscriptions** — `company_id, plan_id, status, stripe_customer_id, stripe_subscription_id,
  current_period_start/end, cancel_at_period_end`. Written by the Stripe webhook (service role).
- **service_agreements** / **agreement_acceptances** — versioned legal text + recorded acceptances.
  _Empty — real legal text is an OWNER_DECISIONS / Legal task._
- **dfy_orders** (migration 0038) — education/community "Estimator Business Setup" ($997 one-time)
  orders: `order_token, stripe_checkout_session_id, email, stripe ids, amount_cents, status
  (pending → paid → intake_submitted → fulfilled | refunded), intake jsonb`. Buyers are course
  members, not portal clients — no company/entitlement is created. _RLS enabled, zero policies:
  service-role only._

### Onboarding & preferences
- **onboarding_progress** — per-company step checklist (`step`, `completed`, `data` jsonb).
- **company_preferences** — `profile`, `estimating`, `communication` JSONB (trades, service areas,
  labor rates with provenance, comms channels).

### Projects
- **project_counters** + `next_project_number()` → `MOBI-YYYY-0001` numbering. _No RLS policy by
  design (service-role / SECURITY DEFINER only)._
- **projects** — `company_id, project_number, name, status, project_type, address, bid_due_at,
  requested_completion_at, prevailing_wage`.
- **project_scopes** / **project_constraints** — wide JSONB detail per project.
- **project_files** — metadata for uploaded documents; bytes live in private Storage
  (`storage_path`). Supports `external_url` instead of upload.
- **project_status_history** — pipeline timeline. Has `internal_note` (**never shown to clients**)
  and `client_note`. Clients read the client-safe `client_timeline(project)` RPC.
- **project_assignments** — `estimator_id`, `reviewer_id` per project.

### Forwarded bid intake (migrations 0036, 0037)
- **inbound_intake_messages** — a bid invitation the contractor forwarded to
  `estimates@mobiestimates.com` (or the tagged `estimates+{intake_slug}@…` form):
  `provider`, `provider_email_id` (unique — the webhook's idempotency key),
  `from_email`, `subject`, `body_preview`, `sender_verified`, `attachment_count`,
  `skipped_attachment_count`, `status` (`pending` | `sender_unverified` | `unrouted` |
  `converted` | `dismissed`), `routed_by` (`alias` | `sender`), `unrouted_reason`, `project_id`.
  `company_id` is nullable **only** for `unrouted` — a forward we could not match to a company
  (sender not on any account, sender on several, stale tag). Those are staff-only triage items and
  their attachments are counted but deliberately **not stored**, because the shared intake address
  sits on a public domain that anyone can write to. A check constraint keeps tenant presence and
  status consistent, while still permitting `dismissed` with no tenant so staff can clear spam.
- **inbound_intake_attachments** — the stored documents; bytes live in the existing private
  `project-files` bucket under `{company_id}/inbound/{message_id}/…` so the bucket's
  `foldername[1] = company_id` policy already scopes reads to the tenant. `project_file_id` is set
  once the intake is converted.
- _RLS: **select only** for the tenant and staff. There are deliberately no insert/update/delete
  policies — writes come from the verified webhook (service role) or the two RPCs below. **Capturing
  a forward creates no project and spends no entitlement**: migration 0034's staff-only project
  insert lock stays intact, so a stray or spoofed forward cannot consume a company's one free
  estimate. The contractor converts it through the normal entitlement-checked submission path._

### Communication & delivery
- **project_questions** / **question_responses** — estimator RFIs and answers.
- **deliverables** — completed estimate files; `client_reviewed_at`, `client_approved_at`.
- **revision_requests** — `category`, `description`, `internal_review_required`, `resolved`.
- **support_tickets** — `category, subject, body, status`.
- **notifications** — per-user in-app notifications (`type, title, body, link, read_at`).

### Content & ops
- **training_modules** / **training_completions** — onboarding videos + acknowledgements.
- **faq_entries** — approved knowledge base (also the corpus for a future support assistant).
- **audit_logs** — `actor_id, action, entity, entity_id, metadata`.
- **webhook_events** — Stripe event idempotency (`id` = Stripe `evt_…`). _No RLS policy by design
  (service-role only)._

## RLS helper functions (SECURITY DEFINER)
`current_role()`, `is_staff()`, `is_admin()`, `is_member_of(company)`,
`is_member_of_project(project)`, `next_project_number()`, `client_timeline(project)`,
`handle_new_user()`. The membership helpers are intentionally executable (RLS policies call them).

Forwarded-bid intake adds `generate_intake_slug(name)` and `set_company_intake_slug()` (both
internal — **not** granted to `authenticated`), plus the only two customer-driven transitions:
`dismiss_inbound_intake(message)` and `claim_inbound_intake_for_project(message, project)`. The
latter is single-use and fails closed when the forward and the project belong to different
companies.

## Security notes / advisor findings (2026-06-24)
- ✅ RLS enabled on all 27 tables; default-deny.
- ℹ️ `project_counters`, `webhook_events` have RLS on with **no policy** — intentional (service-role only).
- ⚠️ Several SECURITY DEFINER functions are still callable over PostgREST RPC by anon/authenticated.
  The membership helpers must stay callable; review the rest (Security milestone).
- ⚠️ **Leaked-password protection disabled** in Auth — enable it (Dashboard → Auth → Policies).
- ⚠️ No storage buckets exist yet — `project-files` and `deliverables` (private) must be created
  with member/staff access policies before file upload works.

## What is NOT in the schema yet (future migrations)
- Stripe `customers` convenience view (optional).
- Message threads table if in-app chat goes beyond `project_questions` (optional).
- Email send log (optional; can use Resend dashboard initially).
