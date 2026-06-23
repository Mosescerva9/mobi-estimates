-- =============================================================================
-- Mobi Estimates — Client Portal : Core Schema (Milestone 1)
-- Target: Supabase / PostgreSQL
--
-- This migration is service-independent and has NOT been executed in the build
-- environment (no database available). Apply it to a Supabase project with the
-- Supabase CLI:  supabase db push   (see mobi-portal/README.md).
--
-- Design notes:
--  * UUID primary keys (gen_random_uuid) everywhere.
--  * created_at / updated_at on every table; updated_at maintained by trigger.
--  * created_by references auth.users for audit.
--  * Soft delete via deleted_at where records should be recoverable.
--  * Very wide preference/scope/constraint sets are stored as JSONB with
--    documented keys (kept maintainable); queryable fields are real columns.
--  * RLS is enabled here but POLICIES live in 0002_policies.sql.
-- =============================================================================

create extension if not exists "pgcrypto";

-- ---- shared updated_at trigger ---------------------------------------------
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---- enums -----------------------------------------------------------------
create type public.user_role           as enum ('client','estimator','reviewer','admin');
create type public.subscription_status as enum ('pending','active','past_due','canceled','suspended');
create type public.company_type        as enum ('general_contractor','subcontractor','developer','owner','supplier','other');
create type public.project_type        as enum ('residential','commercial','industrial','civil','infrastructure','mixed');
create type public.value_provenance    as enum ('client_provided','mobi_assumption_allowed','to_be_confirmed');
create type public.project_status as enum (
  'draft','submitted','needs_information','under_internal_review','accepted','scheduled',
  'document_review','takeoff_in_progress','pricing_in_progress','clarification_required',
  'qa_review','ready_for_delivery','delivered','revision_requested','revised','approved',
  'closed','canceled'
);
create type public.question_status     as enum ('open','answered','resolved','assumption_required','overdue');
create type public.ticket_status       as enum ('open','in_progress','waiting_on_client','resolved','closed');
create type public.revision_category   as enum (
  'mobi_correction','minor_clarification','client_repricing','new_addendum',
  'design_change','scope_change','full_re_estimate'
);

-- ---- profiles (1:1 with auth.users) ----------------------------------------
create table public.profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  full_name    text,
  email        text,
  phone        text,
  -- Global role. Company-level membership is in company_members; this is the
  -- platform role used by RLS helpers (clients default to 'client').
  role         public.user_role not null default 'client',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create trigger trg_profiles_updated before update on public.profiles
  for each row execute function public.set_updated_at();

-- ---- companies -------------------------------------------------------------
create table public.companies (
  id             uuid primary key default gen_random_uuid(),
  legal_name     text not null,
  preferred_name text,
  website        text,
  address        text,
  company_type   public.company_type,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  created_by     uuid references auth.users(id),
  deleted_at     timestamptz
);
create trigger trg_companies_updated before update on public.companies
  for each row execute function public.set_updated_at();

-- ---- company_members (users <-> companies, with company-scoped role) --------
create table public.company_members (
  id          uuid primary key default gen_random_uuid(),
  company_id  uuid not null references public.companies(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role        public.user_role not null default 'client',
  is_primary  boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (company_id, user_id)
);
create index idx_company_members_user on public.company_members(user_id);
create index idx_company_members_company on public.company_members(company_id);
create trigger trg_company_members_updated before update on public.company_members
  for each row execute function public.set_updated_at();

-- ---- plans (configurable; real values live in OWNER_DECISIONS.md/seed) ------
create table public.plans (
  id                 uuid primary key default gen_random_uuid(),
  code               text unique not null,             -- e.g. 'starter'
  name               text not null,                    -- placeholder until owner confirms
  description        text,
  price_cents        integer,                          -- monthly price in cents (nullable = custom)
  currency           text not null default 'usd',
  active_capacity    integer,                          -- standard bids/month (capacity, not hours)
  max_active_projects integer,
  turnaround_note    text,
  revision_note      text,
  stripe_price_id    text,                             -- set after Stripe config
  is_public          boolean not null default true,
  sort_order         integer not null default 0,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create trigger trg_plans_updated before update on public.plans
  for each row execute function public.set_updated_at();

-- ---- subscriptions ---------------------------------------------------------
create table public.subscriptions (
  id                     uuid primary key default gen_random_uuid(),
  company_id             uuid not null references public.companies(id) on delete cascade,
  plan_id                uuid references public.plans(id),
  status                 public.subscription_status not null default 'pending',
  stripe_customer_id     text,
  stripe_subscription_id text unique,
  current_period_start   timestamptz,
  current_period_end     timestamptz,
  cancel_at_period_end   boolean not null default false,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create index idx_subscriptions_company on public.subscriptions(company_id);
create trigger trg_subscriptions_updated before update on public.subscriptions
  for each row execute function public.set_updated_at();

-- ---- service agreements + acceptances --------------------------------------
create table public.service_agreements (
  id            uuid primary key default gen_random_uuid(),
  version       text not null unique,                  -- e.g. 'v1-2026-06'
  title         text not null,
  body          text not null,                         -- DRAFT; owner/attorney to finalize
  effective_at  timestamptz not null default now(),
  is_current    boolean not null default false,
  created_at    timestamptz not null default now()
);

create table public.agreement_acceptances (
  id            uuid primary key default gen_random_uuid(),
  agreement_id  uuid not null references public.service_agreements(id),
  version       text not null,
  company_id    uuid references public.companies(id) on delete cascade,
  user_id       uuid not null references auth.users(id) on delete cascade,
  accepted_at   timestamptz not null default now(),
  ip_address    text,
  user_agent    text
);
create index idx_agreement_acceptances_company on public.agreement_acceptances(company_id);

-- ---- onboarding progress ---------------------------------------------------
create table public.onboarding_progress (
  id          uuid primary key default gen_random_uuid(),
  company_id  uuid not null references public.companies(id) on delete cascade,
  step        text not null,                           -- 'welcome','company_profile',...
  completed   boolean not null default false,
  data        jsonb not null default '{}'::jsonb,      -- saved partial answers
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (company_id, step)
);
create trigger trg_onboarding_updated before update on public.onboarding_progress
  for each row execute function public.set_updated_at();

-- ---- company preferences (estimating/communication) ------------------------
-- Wide, evolving set -> JSONB with documented keys. Each numeric estimating
-- value should carry a provenance flag (client_provided / mobi_assumption_allowed
-- / to_be_confirmed) inside its JSON entry. Never silently invent values.
create table public.company_preferences (
  company_id   uuid primary key references public.companies(id) on delete cascade,
  profile      jsonb not null default '{}'::jsonb,   -- contacts, service areas, trades, formats
  estimating   jsonb not null default '{}'::jsonb,   -- labor rates, OH&P, waste, CSI, etc. (+provenance)
  communication jsonb not null default '{}'::jsonb,  -- channels, milestone/daily, contacts
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create trigger trg_company_preferences_updated before update on public.company_preferences
  for each row execute function public.set_updated_at();

-- ---- project numbering (MOBI-YYYY-0001, unique, no duplicates) --------------
create table public.project_counters (
  year      integer primary key,
  last_seq  integer not null default 0
);
create or replace function public.next_project_number()
returns text language plpgsql security definer set search_path = public as $$
declare
  y int := extract(year from now())::int;
  n int;
begin
  insert into public.project_counters(year, last_seq) values (y, 1)
    on conflict (year) do update set last_seq = public.project_counters.last_seq + 1
    returning last_seq into n;
  return 'MOBI-' || y::text || '-' || lpad(n::text, 4, '0');
end;
$$;

-- ---- projects --------------------------------------------------------------
create table public.projects (
  id              uuid primary key default gen_random_uuid(),
  company_id      uuid not null references public.companies(id) on delete cascade,
  project_number  text unique,                          -- assigned on submit
  name            text not null,
  status          public.project_status not null default 'draft',
  project_type    public.project_type,
  -- key queryable identification fields (full set in project_scopes/constraints)
  address         text,
  bid_due_at      timestamptz,
  requested_completion_at timestamptz,
  is_public       boolean,
  prevailing_wage boolean,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  created_by      uuid references auth.users(id),
  deleted_at      timestamptz
);
create index idx_projects_company on public.projects(company_id);
create index idx_projects_status  on public.projects(status);
create index idx_projects_bid_due on public.projects(bid_due_at);
create trigger trg_projects_updated before update on public.projects
  for each row execute function public.set_updated_at();

create table public.project_scopes (
  project_id  uuid primary key references public.projects(id) on delete cascade,
  data        jsonb not null default '{}'::jsonb,   -- trades/CSI, estimate type, base/alts/allowances...
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create trigger trg_project_scopes_updated before update on public.project_scopes
  for each row execute function public.set_updated_at();

create table public.project_constraints (
  project_id  uuid primary key references public.projects(id) on delete cascade,
  data        jsonb not null default '{}'::jsonb,   -- working hours, access, staging, milestones...
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create trigger trg_project_constraints_updated before update on public.project_constraints
  for each row execute function public.set_updated_at();

-- ---- project files (private Supabase Storage; signed URLs only) -------------
create table public.project_files (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects(id) on delete cascade,
  company_id    uuid not null references public.companies(id) on delete cascade,
  category      text not null,                         -- '02 Drawings', '03 Specifications', ...
  storage_path  text not null,                         -- path in private bucket
  external_url  text,                                  -- optional link instead of upload
  file_name     text not null,
  mime_type     text,
  size_bytes    bigint,
  uploaded_by   uuid references auth.users(id),
  created_at    timestamptz not null default now(),
  deleted_at    timestamptz
);
create index idx_project_files_project on public.project_files(project_id);

-- ---- status history (timeline) ---------------------------------------------
create table public.project_status_history (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects(id) on delete cascade,
  from_status   public.project_status,
  to_status     public.project_status not null,
  changed_by    uuid references auth.users(id),
  internal_note text,                                   -- NEVER shown to clients
  client_note   text,                                   -- client-visible
  created_at    timestamptz not null default now()
);
create index idx_status_history_project on public.project_status_history(project_id);

-- ---- assignments -----------------------------------------------------------
create table public.project_assignments (
  project_id   uuid primary key references public.projects(id) on delete cascade,
  estimator_id uuid references auth.users(id),
  reviewer_id  uuid references auth.users(id),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create trigger trg_project_assignments_updated before update on public.project_assignments
  for each row execute function public.set_updated_at();

-- ---- estimator questions + responses ---------------------------------------
create table public.project_questions (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects(id) on delete cascade,
  company_id    uuid not null references public.companies(id) on delete cascade,
  title         text not null,
  body          text not null,
  drawing_ref   text,
  spec_ref      text,
  csi_division  text,
  priority      text,                                   -- low/normal/high/urgent
  response_due_at timestamptz,
  attachment_path text,
  asked_by      uuid references auth.users(id),
  status        public.question_status not null default 'open',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index idx_questions_project on public.project_questions(project_id);
create trigger trg_questions_updated before update on public.project_questions
  for each row execute function public.set_updated_at();

create table public.question_responses (
  id              uuid primary key default gen_random_uuid(),
  question_id     uuid not null references public.project_questions(id) on delete cascade,
  body            text not null,
  attachment_path text,
  responded_by    uuid references auth.users(id),
  created_at      timestamptz not null default now()
);
create index idx_question_responses_q on public.question_responses(question_id);

-- ---- deliverables ----------------------------------------------------------
create table public.deliverables (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects(id) on delete cascade,
  company_id    uuid not null references public.companies(id) on delete cascade,
  category      text not null,                          -- 'estimate_summary', 'takeoff', ...
  storage_path  text not null,
  file_name     text not null,
  mime_type     text,
  size_bytes    bigint,
  uploaded_by   uuid references auth.users(id),
  client_reviewed_at timestamptz,
  client_approved_at timestamptz,
  created_at    timestamptz not null default now(),
  deleted_at    timestamptz
);
create index idx_deliverables_project on public.deliverables(project_id);

-- ---- revision requests -----------------------------------------------------
create table public.revision_requests (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects(id) on delete cascade,
  company_id    uuid not null references public.companies(id) on delete cascade,
  category      public.revision_category,               -- NOT auto-classified as free
  reason        text,
  description   text not null,
  drawing_ref   text,
  spec_ref      text,
  new_bid_due_at timestamptz,
  internal_review_required boolean not null default true,
  resolved      boolean not null default false,
  requested_by  uuid references auth.users(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index idx_revisions_project on public.revision_requests(project_id);
create trigger trg_revisions_updated before update on public.revision_requests
  for each row execute function public.set_updated_at();

-- ---- support tickets -------------------------------------------------------
create table public.support_tickets (
  id           uuid primary key default gen_random_uuid(),
  company_id   uuid references public.companies(id) on delete cascade,
  user_id      uuid references auth.users(id),
  category     text not null,                           -- 'billing','account_access',...
  subject      text not null,
  body         text not null,
  status       public.ticket_status not null default 'open',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index idx_tickets_company on public.support_tickets(company_id);
create trigger trg_tickets_updated before update on public.support_tickets
  for each row execute function public.set_updated_at();

-- ---- notifications ---------------------------------------------------------
create table public.notifications (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  company_id  uuid references public.companies(id) on delete cascade,
  type        text not null,
  title       text not null,
  body        text,
  link        text,
  read_at     timestamptz,
  created_at  timestamptz not null default now()
);
create index idx_notifications_user on public.notifications(user_id);

-- ---- training --------------------------------------------------------------
create table public.training_modules (
  id          uuid primary key default gen_random_uuid(),
  code        text unique not null,
  title       text not null,
  summary     text,
  video_url   text,                                     -- placeholder until owner supplies
  sort_order  integer not null default 0,
  requires_ack boolean not null default true,
  created_at  timestamptz not null default now()
);

create table public.training_completions (
  id            uuid primary key default gen_random_uuid(),
  module_id     uuid not null references public.training_modules(id) on delete cascade,
  company_id    uuid references public.companies(id) on delete cascade,
  user_id       uuid not null references auth.users(id) on delete cascade,
  acknowledged_at timestamptz not null default now(),
  agreement_version text,
  unique (module_id, user_id)
);

-- ---- FAQ (curated knowledge base for the assistant) ------------------------
create table public.faq_entries (
  id          uuid primary key default gen_random_uuid(),
  category    text not null,
  question    text not null,
  answer      text not null,                            -- approved content only
  is_published boolean not null default true,
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create trigger trg_faq_updated before update on public.faq_entries
  for each row execute function public.set_updated_at();

-- ---- audit log -------------------------------------------------------------
create table public.audit_logs (
  id          uuid primary key default gen_random_uuid(),
  actor_id    uuid references auth.users(id),
  company_id  uuid references public.companies(id),
  action      text not null,
  entity      text,
  entity_id   uuid,
  metadata    jsonb,
  created_at  timestamptz not null default now()
);
create index idx_audit_company on public.audit_logs(company_id);

-- ---- Stripe webhook idempotency -------------------------------------------
create table public.webhook_events (
  id            text primary key,                       -- Stripe event id (evt_...)
  type          text not null,
  processed_at  timestamptz not null default now(),
  payload       jsonb
);

-- ---- enable RLS on all app tables (policies in 0002_policies.sql) -----------
alter table public.profiles               enable row level security;
alter table public.companies              enable row level security;
alter table public.company_members        enable row level security;
alter table public.plans                  enable row level security;
alter table public.subscriptions          enable row level security;
alter table public.service_agreements     enable row level security;
alter table public.agreement_acceptances  enable row level security;
alter table public.onboarding_progress    enable row level security;
alter table public.company_preferences    enable row level security;
alter table public.projects               enable row level security;
alter table public.project_scopes         enable row level security;
alter table public.project_constraints    enable row level security;
alter table public.project_files          enable row level security;
alter table public.project_status_history enable row level security;
alter table public.project_assignments    enable row level security;
alter table public.project_questions      enable row level security;
alter table public.question_responses     enable row level security;
alter table public.deliverables           enable row level security;
alter table public.revision_requests      enable row level security;
alter table public.support_tickets        enable row level security;
alter table public.notifications          enable row level security;
alter table public.training_modules       enable row level security;
alter table public.training_completions   enable row level security;
alter table public.faq_entries            enable row level security;
alter table public.audit_logs             enable row level security;
alter table public.webhook_events         enable row level security;
alter table public.project_counters       enable row level security;
-- project_counters has no policies on purpose: only next_project_number()
-- (security definer) and the service-role key may touch it.
