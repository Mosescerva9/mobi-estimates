-- =============================================================================
-- Mobi Estimates — Customer-acquisition intro offer: one free qualifying
-- estimate per new company.
--
-- Owner-approved offer:
--   • One qualifying estimate free per new company. No card required.
--   • Supported scope and project complexity are reviewed before acceptance.
--   • After the free estimate, regular pay-per-project/monthly pricing applies.
--
-- This migration records a durable, auditable claim per company with:
--   • company ownership + the actor who claimed it,
--   • an optional linked project,
--   • a lifecycle status (requested/accepted/consumed/rejected/released),
--   • a fixed rejection reason class (public copy lives in src/lib/intro-offer.ts),
--   • timestamps for request/decision/consumption/release, and
--   • partial uniqueness so exactly ONE non-rejected/non-released ("occupying")
--     claim can exist per company, while a staff-rejected unsupported request can
--     be retried.
--
-- Claims are NEVER hard-deleted; a failed provisioning attempt is "released"
-- (audit-preserving) so it frees the slot without destroying history.
--
-- All writes go through SECURITY DEFINER RPCs with explicit, fail-closed
-- auth/company-membership checks and a pinned search_path. The base table is
-- RLS default-deny for customers (staff read-only); customers read a
-- client-safe view via intro_offer_status_for_project(), which omits the
-- internal note so private staff notes can never leak.
-- =============================================================================

create table if not exists public.intro_offer_claims (
  id                     uuid primary key default gen_random_uuid(),
  company_id             uuid not null references public.companies(id) on delete cascade,
  -- The member (or staff) who reserved the free estimate for the company.
  claimed_by             uuid references auth.users(id) on delete set null,
  -- Optional project the free estimate is attached to.
  project_id             uuid references public.projects(id) on delete set null,
  offer_code             text not null default 'first_estimate_free',
  status                 text not null default 'requested'
                           check (status in ('requested', 'accepted', 'consumed', 'rejected', 'released')),
  -- Fixed public reason class (set only on rejection). Keep in sync with
  -- INTRO_OFFER_REJECTION_REASONS in src/lib/intro-offer.ts.
  rejection_reason_class text
                           check (
                             rejection_reason_class is null
                             or rejection_reason_class in (
                               'unsupported_scope',
                               'incomplete_documents',
                               'complexity_out_of_range',
                               'duplicate_request',
                               'other'
                             )
                           ),
  -- Internal-only staff note. NEVER exposed to customers.
  internal_note          text,
  requested_at           timestamptz not null default now(),
  decided_at             timestamptz,
  decided_by             uuid references auth.users(id) on delete set null,
  consumed_at            timestamptz,
  released_at            timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create index if not exists idx_intro_offer_claims_company on public.intro_offer_claims(company_id);
create index if not exists idx_intro_offer_claims_project on public.intro_offer_claims(project_id);

-- One "occupying" (non-rejected, non-released) claim per company. A rejected or
-- released request frees the slot so a supported request can be retried.
create unique index if not exists uniq_intro_offer_active_per_company
  on public.intro_offer_claims (company_id)
  where status in ('requested', 'accepted', 'consumed');

drop trigger if exists trg_intro_offer_claims_updated on public.intro_offer_claims;
create trigger trg_intro_offer_claims_updated
  before update on public.intro_offer_claims
  for each row execute function public.set_updated_at();

-- ---- RLS: default-deny for customers; staff read-only -----------------------
alter table public.intro_offer_claims enable row level security;

-- Staff may read claims (admin project UI). Customers get NO direct base-table
-- access (which would expose internal_note); they use the client-safe RPCs
-- below. All writes flow through SECURITY DEFINER RPCs, so no write policy is
-- granted here.
drop policy if exists intro_offer_claims_select_staff on public.intro_offer_claims;
create policy intro_offer_claims_select_staff on public.intro_offer_claims
  for select using (public.is_staff());

-- ---------------------------------------------------------------------------
-- intro_offer_company_eligible: authoritative "genuinely unused acquisition
-- offer" predicate. A company qualifies for the one free qualifying estimate
-- ONLY when it has never used the product through any other door. Eligibility
-- means ALL of:
--   • no occupying (requested/accepted/consumed) intro claim;
--   • no prior paid subscription history (any status past the initial 'pending');
--   • no prior paid pay-per-project order;
--   • no prior NON-intro project. A project counts as "intro" only when it is
--     linked to an intro_offer_claim (any status, INCLUDING rejected/released),
--     so a company retrying after a rejected/released attempt is not disqualified
--     by the project that attempt left behind. Any project with no claim link
--     (a paid submission, a legacy project) means the offer is already spent.
-- This is a pure predicate (no membership/auth check): callers verify membership
-- first, then use this so a stale client-side preflight can never widen it. It is
-- consumed by intro_offer_company_state (client-safe read), attach_intro_offer_claim,
-- and create_free_offer_project (server-side reservation), and is intentionally
-- NOT granted to end users — only the security-definer RPCs call it.
--
-- p_ignore_project lets a caller that has ALREADY inserted the project it is
-- about to attach (the legacy attach flow) exclude that row from the "prior
-- non-intro project" test, so the project being claimed does not disqualify its
-- own claim. The claim-first create_free_offer_project path passes null.
-- ---------------------------------------------------------------------------
create or replace function public.intro_offer_company_eligible(
  p_company uuid,
  p_ignore_project uuid default null
)
returns boolean
language plpgsql
stable
security definer
set search_path = public
as $$
begin
  if p_company is null then
    return false;
  end if;

  -- 1) No occupying intro claim already holding the one-per-company slot.
  if exists (
    select 1 from public.intro_offer_claims
     where company_id = p_company
       and status in ('requested', 'accepted', 'consumed')
  ) then
    return false;
  end if;

  -- 2) No prior paid subscription history. 'pending' is a never-activated stub;
  --    anything beyond it means the company has already been a paying customer.
  if exists (
    select 1 from public.subscriptions
     where company_id = p_company
       and status in ('active', 'past_due', 'canceled', 'suspended')
  ) then
    return false;
  end if;

  -- 3) No prior paid pay-per-project order.
  if exists (
    select 1 from public.pay_per_project_orders
     where company_id = p_company
       and status = 'paid'
  ) then
    return false;
  end if;

  -- 4) No prior NON-intro project (a project not linked to any intro claim).
  --    Projects tied only to rejected/released claims stay "intro" and do not
  --    disqualify a retry.
  if exists (
    select 1 from public.projects p
     where p.company_id = p_company
       and p.deleted_at is null
       and (p_ignore_project is null or p.id <> p_ignore_project)
       and not exists (
         select 1 from public.intro_offer_claims c
          where c.project_id = p.id
       )
  ) then
    return false;
  end if;

  return true;
end;
$$;

revoke all on function public.intro_offer_company_eligible(uuid, uuid) from public;

-- ---------------------------------------------------------------------------
-- attach_intro_offer_claim: atomically reserve the company's one free claim and
-- bind it to a project. Fail-closed on membership. Concurrent submissions can
-- never create two occupying claims — the partial unique index makes the second
-- insert fail, which we translate to { ok:false, reason:'already_claimed' } so a
-- failed project can be rolled back rather than double-spending the free offer.
-- ---------------------------------------------------------------------------
create or replace function public.attach_intro_offer_claim(p_company uuid, p_project uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
begin
  if p_company is null or p_project is null then
    return jsonb_build_object('ok', false, 'reason', 'invalid_input');
  end if;

  -- Only a member of the company (or staff) may reserve that company's claim.
  if not (public.is_member_of(p_company) or public.is_staff()) then
    raise exception 'not authorized to claim the intro offer for this company';
  end if;

  -- The project must belong to the same company (fail closed on tenant mismatch).
  perform 1 from public.projects
    where id = p_project and company_id = p_company and deleted_at is null;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'project_not_found');
  end if;

  -- Re-check genuine new-company eligibility server-side so a stale client-side
  -- preflight (old company, paid history, prior non-intro project) can never
  -- widen the offer. The partial unique index still guards concurrency below.
  if not public.intro_offer_company_eligible(p_company, p_project) then
    return jsonb_build_object('ok', false, 'reason', 'not_eligible');
  end if;

  begin
    insert into public.intro_offer_claims (company_id, claimed_by, project_id, status)
    values (p_company, auth.uid(), p_project, 'requested')
    returning id into v_id;
  exception when unique_violation then
    return jsonb_build_object('ok', false, 'reason', 'already_claimed');
  end;

  return jsonb_build_object('ok', true, 'claim_id', v_id, 'status', 'requested');
end;
$$;

revoke all on function public.attach_intro_offer_claim(uuid, uuid) from public;
grant execute on function public.attach_intro_offer_claim(uuid, uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- release_intro_offer_claim: audit-preserving auto-release used when project
-- provisioning fails after a claim was reserved. Only a still-'requested' claim
-- bound to this project is released; the row is kept (status='released') so the
-- slot is freed without stranding an unusable claim and without losing history.
-- ---------------------------------------------------------------------------
create or replace function public.release_intro_offer_claim(p_company uuid, p_project uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
begin
  if not (public.is_member_of(p_company) or public.is_staff()) then
    raise exception 'not authorized to release the intro offer for this company';
  end if;

  update public.intro_offer_claims
     set status = 'released', released_at = now()
   where company_id = p_company
     and project_id = p_project
     and status = 'requested'
  returning id into v_id;

  return v_id is not null;
end;
$$;

revoke all on function public.release_intro_offer_claim(uuid, uuid) from public;
revoke all on function public.release_intro_offer_claim(uuid, uuid) from authenticated;
-- Legacy helper is intentionally not executable by customers. All customer-path
-- cleanup must use fail_free_offer_project_provisioning so the project and audit
-- trail change atomically with the claim.

-- ---------------------------------------------------------------------------
-- fail_free_offer_project_provisioning: atomic, audit-preserving cleanup when
-- downstream scope/job provisioning fails after create_free_offer_project.
-- Claim release, project cancellation/soft-delete, and the timeline event commit
-- together or not at all. Repeating a completed cleanup is a safe success.
-- ---------------------------------------------------------------------------
create or replace function public.fail_free_offer_project_provisioning(
  p_company uuid,
  p_project uuid
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_claim uuid;
  v_claim_status text;
  v_from_status public.project_status;
  v_deleted_at timestamptz;
begin
  if p_company is null or p_project is null then
    return jsonb_build_object('ok', false, 'reason', 'invalid_input');
  end if;

  if not (public.is_member_of(p_company) or public.is_staff()) then
    raise exception 'not authorized to fail free-offer provisioning for this company';
  end if;

  select c.id, c.status, p.status, p.deleted_at
    into v_claim, v_claim_status, v_from_status, v_deleted_at
    from public.intro_offer_claims c
    join public.projects p on p.id = c.project_id
   where c.company_id = p_company
     and c.project_id = p_project
     and p.company_id = p_company
   order by c.requested_at desc
   for update of c, p
   limit 1;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'claim_or_project_not_found');
  end if;

  if v_claim_status = 'released' and v_deleted_at is not null then
    return jsonb_build_object('ok', true, 'status', 'already_released');
  end if;

  if v_claim_status <> 'requested' or v_deleted_at is not null then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status');
  end if;

  update public.intro_offer_claims
     set status = 'released', released_at = now()
   where id = v_claim and status = 'requested';
  if not found then
    raise exception 'intro offer release did not update a row';
  end if;

  update public.projects
     set status = 'canceled', deleted_at = now()
   where id = p_project
     and company_id = p_company
     and deleted_at is null;
  if not found then
    raise exception 'free-offer project cancellation did not update a row';
  end if;

  insert into public.project_status_history (
    project_id, from_status, to_status, changed_by, internal_note, client_note
  ) values (
    p_project,
    v_from_status,
    'canceled',
    auth.uid(),
    'Automatic audit-preserving cancellation after project provisioning failed.',
    'Project setup did not complete. Your free estimate request was reset so you can try again.'
  );

  return jsonb_build_object('ok', true, 'status', 'released_and_canceled');
end;
$$;

revoke all on function public.fail_free_offer_project_provisioning(uuid, uuid) from public;
grant execute on function public.fail_free_offer_project_provisioning(uuid, uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- decide_intro_offer_claim: staff accept/reject of the free-offer qualification
-- from the admin project UI. Rejection requires a fixed reason class; the
-- optional internal note is stored but never surfaced to customers.
-- ---------------------------------------------------------------------------
create or replace function public.decide_intro_offer_claim(
  p_project uuid,
  p_decision text,
  p_reason_class text default null,
  p_internal_note text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_claim record;
  v_note text;
begin
  if not public.is_staff() then
    raise exception 'Not authorized';
  end if;

  if p_decision not in ('accept', 'reject') then
    return jsonb_build_object('ok', false, 'reason', 'invalid_decision');
  end if;

  select id, status into v_claim
    from public.intro_offer_claims
   where project_id = p_project
     and status in ('requested', 'accepted', 'consumed')
   order by requested_at desc
   for update
   limit 1;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'claim_not_found');
  end if;

  if v_claim.status <> 'requested' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_claim.status);
  end if;

  v_note := nullif(btrim(coalesce(p_internal_note, '')), '');

  if p_decision = 'reject' then
    if p_reason_class is null or p_reason_class not in (
      'unsupported_scope', 'incomplete_documents', 'complexity_out_of_range', 'duplicate_request', 'other'
    ) then
      return jsonb_build_object('ok', false, 'reason', 'invalid_reason_class');
    end if;

    update public.intro_offer_claims
       set status = 'rejected',
           rejection_reason_class = p_reason_class,
           internal_note = v_note,
           decided_at = now(),
           decided_by = auth.uid()
     where id = v_claim.id;

    return jsonb_build_object('ok', true, 'status', 'rejected', 'reason_class', p_reason_class);
  end if;

  update public.intro_offer_claims
     set status = 'accepted',
         rejection_reason_class = null,
         internal_note = v_note,
         decided_at = now(),
         decided_by = auth.uid()
   where id = v_claim.id;

  return jsonb_build_object('ok', true, 'status', 'accepted');
end;
$$;

revoke all on function public.decide_intro_offer_claim(uuid, text, text, text) from public;
grant execute on function public.decide_intro_offer_claim(uuid, text, text, text) to authenticated;

-- ---------------------------------------------------------------------------
-- Client-safe reads. These never return internal_note. Customers may only read
-- claims for a company/project they belong to (or staff).
-- ---------------------------------------------------------------------------
create or replace function public.intro_offer_company_state(p_company uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_active record;
begin
  if not (public.is_member_of(p_company) or public.is_staff()) then
    return jsonb_build_object('ok', false, 'reason', 'not_authorized');
  end if;

  select status, project_id into v_active
    from public.intro_offer_claims
   where company_id = p_company
     and status in ('requested', 'accepted', 'consumed')
   order by requested_at desc
   limit 1;

  return jsonb_build_object(
    'ok', true,
    'has_active_claim', v_active.status is not null,
    -- Eligibility is the authoritative "genuinely unused acquisition offer"
    -- predicate: no occupying claim AND no paid subscription/order history AND
    -- no prior non-intro project. This is only a client-safe PREFLIGHT; the same
    -- predicate is re-run inside the reservation RPC so a stale read can't bypass it.
    'eligible', public.intro_offer_company_eligible(p_company),
    'active_status', v_active.status,
    'active_project_id', v_active.project_id
  );
end;
$$;

revoke all on function public.intro_offer_company_state(uuid) from public;
grant execute on function public.intro_offer_company_state(uuid) to authenticated;

create or replace function public.intro_offer_status_for_project(p_project uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_claim record;
begin
  if not (public.is_member_of_project(p_project) or public.is_staff()) then
    return jsonb_build_object('ok', false, 'reason', 'not_authorized');
  end if;

  select status, rejection_reason_class, requested_at, decided_at
    into v_claim
    from public.intro_offer_claims
   where project_id = p_project
   order by requested_at desc
   limit 1;

  if not found then
    return jsonb_build_object('ok', true, 'exists', false);
  end if;

  -- The private staff note is intentionally omitted from this client-safe surface.
  return jsonb_build_object(
    'ok', true,
    'exists', true,
    'status', v_claim.status,
    'rejection_reason_class', v_claim.rejection_reason_class,
    'requested_at', v_claim.requested_at,
    'decided_at', v_claim.decided_at
  );
end;
$$;

revoke all on function public.intro_offer_status_for_project(uuid) from public;
grant execute on function public.intro_offer_status_for_project(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- create_free_offer_project: transaction-safe provisioning of the ONE free
-- qualifying-estimate project. In a single DB transaction this:
--   1) fails closed unless the caller is a member of (or staff for) the company;
--   2) re-checks genuine new-company eligibility (authoritative, not the client
--      preflight) — old companies, paid history, or a prior non-intro project are
--      rejected here even if a stale client thought otherwise;
--   3) inserts the occupying claim FIRST (claim-first), so the partial unique
--      index rejects a concurrent second first-submission with 'already_claimed'
--      and NO project is ever created for the loser;
--   4) assigns the sequential project number and inserts the submitted project;
--   5) binds the claim to the new project.
-- Because everything runs in one transaction, any failure after the claim insert
-- rolls the whole unit back — there is no orphaned project and no hard-delete
-- rollback path. next_project_number()'s semantics are unchanged (it is called,
-- not modified); this function is SECURITY DEFINER so it may invoke it.
-- Returns { ok, reason?, project_id?, project_number?, claim_id? }.
-- ---------------------------------------------------------------------------
create or replace function public.create_free_offer_project(
  p_company uuid,
  p_name text,
  p_project_type text default null,
  p_address text default null,
  p_bid_due_at timestamptz default null,
  p_requested_completion_at timestamptz default null,
  p_prevailing_wage boolean default false,
  p_is_public boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_claim uuid;
  v_project uuid;
  v_number text;
begin
  if p_company is null or coalesce(btrim(p_name), '') = '' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_input');
  end if;

  if not (public.is_member_of(p_company) or public.is_staff()) then
    raise exception 'not authorized to create a free-offer project for this company';
  end if;

  -- Authoritative eligibility (no project exists yet, so nothing to ignore).
  if not public.intro_offer_company_eligible(p_company) then
    return jsonb_build_object('ok', false, 'reason', 'not_eligible');
  end if;

  -- Claim-first: reserve the one-per-company slot before any project row exists.
  -- A concurrent first submission trips the partial unique index; that loser gets
  -- 'already_claimed' with zero side effects (no project created).
  begin
    insert into public.intro_offer_claims (company_id, claimed_by, status)
    values (p_company, auth.uid(), 'requested')
    returning id into v_claim;
  exception when unique_violation then
    return jsonb_build_object('ok', false, 'reason', 'already_claimed');
  end;

  v_number := public.next_project_number();

  insert into public.projects (
    company_id, project_number, name, status, project_type, address,
    bid_due_at, requested_completion_at, prevailing_wage, is_public, created_by
  )
  values (
    p_company, v_number, btrim(p_name), 'submitted',
    p_project_type::public.project_type, p_address,
    p_bid_due_at, p_requested_completion_at, coalesce(p_prevailing_wage, false),
    coalesce(p_is_public, false), auth.uid()
  )
  returning id into v_project;

  update public.intro_offer_claims
     set project_id = v_project
   where id = v_claim;

  return jsonb_build_object(
    'ok', true,
    'project_id', v_project,
    'project_number', v_number,
    'claim_id', v_claim
  );
end;
$$;

revoke all on function public.create_free_offer_project(
  uuid, text, text, text, timestamptz, timestamptz, boolean, boolean
) from public;
grant execute on function public.create_free_offer_project(
  uuid, text, text, text, timestamptz, timestamptz, boolean, boolean
) to authenticated;
