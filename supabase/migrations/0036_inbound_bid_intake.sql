-- =============================================================================
-- Mobi Estimates — Forwarded bid-invitation intake (email → portal)
--
-- Contractors already forward invitations to bid inside their own offices, so
-- the lowest-friction way for a new company to try the free qualifying estimate
-- is to forward the ITB (plans, specs, addenda attached) to a per-company
-- address instead of logging in to upload. This migration adds:
--
--   1. companies.intake_slug — the unguessable local part of that company's
--      forwarding address ({intake_slug}@{INTAKE_EMAIL_DOMAIN}). A BEFORE INSERT
--      trigger guarantees every company has one, no matter which code path
--      created it (onboarding form, staff, seed).
--   2. inbound_intake_messages / inbound_intake_attachments — the captured
--      forward and its stored documents, held as a REVIEWABLE INTAKE ITEM.
--   3. Two security-definer RPCs for the only two state transitions a customer
--      may perform: dismiss, and convert-into-a-project.
--
-- IMPORTANT — this does NOT create projects.
-- Migration 0034 deliberately restricted project insertion to staff so that the
-- intro-offer / subscription / paid-credit boundary can only be crossed through
-- create_free_offer_project or create_entitled_project. A forwarded email is
-- unauthenticated input and must never widen that boundary: capturing a forward
-- costs nothing and burns no entitlement. The company member converts the
-- captured intake through the normal, entitlement-checked submission path, and
-- claim_inbound_intake_for_project only binds the already-created project to the
-- intake row. A stray or spoofed forward therefore cannot consume a company's
-- one free estimate.
--
-- Idempotent: safe to re-run.
-- =============================================================================

-- ---- 1. per-company forwarding alias ---------------------------------------

alter table public.companies
  add column if not exists intake_slug text;

create unique index if not exists uniq_companies_intake_slug
  on public.companies (intake_slug)
  where intake_slug is not null;

-- Slug = readable company stem + a random suffix. The suffix is what keeps the
-- address from being guessable from the company name alone, which matters
-- because anyone who knows the address can drop documents into the company's
-- intake queue. md5(gen_random_uuid()) avoids a pgcrypto dependency.
create or replace function public.generate_intake_slug(p_name text)
returns text
language plpgsql
volatile
set search_path = public
as $$
declare
  v_base text;
  v_slug text;
  v_attempt integer := 0;
begin
  v_base := lower(coalesce(nullif(btrim(p_name), ''), 'company'));
  -- Fold common accented Latin-1 letters to ASCII first. Without this the
  -- stripping below would delete them outright, turning "Ácme Plumbing" into
  -- "cme-plumbing" — and this stem is printed to the customer as part of their
  -- own email address. Done with translate() rather than unaccent so the
  -- migration needs no extension.
  v_base := translate(
    v_base,
    'àáâãäåāăąèéêëēĕėęěìíîïĩīĭįıòóôõöøōŏőùúûüũūŭůűųçćĉċčñńņňýÿŷžźżšśŝşğĝďđťţłŀĺļľŕŗřß',
    'aaaaaaaaaeeeeeeeeeiiiiiiiiiooooooooouuuuuuuuuucccccnnnnyyyzzzsssssgggddttllllrrrs'
  );
  v_base := regexp_replace(v_base, '[^a-z0-9]+', '-', 'g');
  v_base := btrim(v_base, '-');
  v_base := btrim(left(v_base, 24), '-');
  if v_base = '' then
    v_base := 'company';
  end if;

  loop
    v_slug := v_base || '-' || substr(md5(gen_random_uuid()::text), 1, 6);
    exit when not exists (
      select 1 from public.companies where intake_slug = v_slug
    );
    v_attempt := v_attempt + 1;
    if v_attempt > 20 then
      -- Degenerate case only (pathological collisions): drop the readable stem
      -- rather than loop forever or hand back a duplicate.
      v_slug := 'co-' || replace(gen_random_uuid()::text, '-', '');
      exit;
    end if;
  end loop;

  return v_slug;
end;
$$;

revoke all on function public.generate_intake_slug(text) from public;

create or replace function public.set_company_intake_slug()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.intake_slug is null then
    new.intake_slug := public.generate_intake_slug(
      coalesce(new.preferred_name, new.legal_name)
    );
  end if;
  return new;
end;
$$;

drop trigger if exists companies_set_intake_slug on public.companies;
create trigger companies_set_intake_slug
  before insert on public.companies
  for each row execute function public.set_company_intake_slug();

-- Backfill companies that predate the trigger.
do $$
declare
  r record;
begin
  for r in
    select id, coalesce(preferred_name, legal_name) as nm
      from public.companies
     where intake_slug is null
  loop
    update public.companies
       set intake_slug = public.generate_intake_slug(r.nm)
     where id = r.id;
  end loop;
end $$;

-- ---- 2. captured forwards ---------------------------------------------------

create table if not exists public.inbound_intake_messages (
  id                       uuid primary key default gen_random_uuid(),
  company_id               uuid not null references public.companies(id) on delete cascade,
  provider                 text not null default 'resend',
  -- Provider-side id for the received email. The unique constraint below is the
  -- webhook's idempotency key: a redelivered email.received event is a no-op.
  provider_email_id        text not null,
  intake_address           text not null,
  from_email               text not null,
  from_name                text,
  subject                  text,
  -- Truncated plain-text body. This is the customer's own forwarded ITB text
  -- (GC, deadline, submission instructions) and is readable by the tenant.
  body_preview             text,
  -- True only when the sender matches a profile email of a member of this
  -- company. False means "arrived at the right address from someone we can't
  -- place" — surfaced to the tenant with a warning, never silently trusted.
  sender_verified          boolean not null default false,
  status                   text not null default 'pending'
                             check (status in ('pending', 'sender_unverified', 'converted', 'dismissed')),
  attachment_count         integer not null default 0,
  -- Attachments rejected by the app-layer type/size allowlist, so the customer
  -- can see that something was dropped rather than silently losing a document.
  skipped_attachment_count integer not null default 0,
  project_id               uuid references public.projects(id) on delete set null,
  received_at              timestamptz not null default now(),
  converted_at             timestamptz,
  dismissed_at             timestamptz,
  created_at               timestamptz not null default now(),
  unique (provider, provider_email_id)
);

create index if not exists idx_inbound_intake_company_status
  on public.inbound_intake_messages (company_id, status, received_at desc);

create table if not exists public.inbound_intake_attachments (
  id              uuid primary key default gen_random_uuid(),
  message_id      uuid not null references public.inbound_intake_messages(id) on delete cascade,
  company_id      uuid not null references public.companies(id) on delete cascade,
  file_name       text not null,
  content_type    text,
  size_bytes      bigint,
  -- Object key in the private 'project-files' bucket. Written under
  -- {company_id}/inbound/{message_id}/... so the existing storage RLS policy
  -- (foldername[1] = company_id) already scopes reads to the tenant.
  storage_path    text not null,
  -- Set once the intake is converted and the file is registered as a real
  -- project document.
  project_file_id uuid references public.project_files(id) on delete set null,
  created_at      timestamptz not null default now()
);

create index if not exists idx_inbound_intake_attachments_message
  on public.inbound_intake_attachments (message_id);

alter table public.inbound_intake_messages enable row level security;
alter table public.inbound_intake_attachments enable row level security;

-- Read-only for the tenant and staff. There are deliberately NO insert/update/
-- delete policies: writes come from the verified webhook (service role, which
-- bypasses RLS) or the two RPCs below, so a customer can never fabricate an
-- intake row or move one into 'converted' without going through the RPC.
drop policy if exists inbound_intake_messages_select on public.inbound_intake_messages;
create policy inbound_intake_messages_select on public.inbound_intake_messages
  for select using (
    public.is_staff() or public.is_member_of(company_id)
  );

drop policy if exists inbound_intake_attachments_select on public.inbound_intake_attachments;
create policy inbound_intake_attachments_select on public.inbound_intake_attachments
  for select using (
    public.is_staff() or public.is_member_of(company_id)
  );

-- ---- 3. the only two customer-driven transitions ----------------------------

-- dismiss_inbound_intake: the customer says "not a bid I want estimated".
-- Repeating a completed dismiss is a safe success so a double-click can't error.
create or replace function public.dismiss_inbound_intake(p_message uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_company uuid;
  v_status text;
begin
  if p_message is null then
    return jsonb_build_object('ok', false, 'reason', 'invalid_input');
  end if;

  select company_id, status
    into v_company, v_status
    from public.inbound_intake_messages
   where id = p_message
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'not_found');
  end if;
  if not (public.is_member_of(v_company) or public.is_staff()) then
    return jsonb_build_object('ok', false, 'reason', 'not_authorized');
  end if;
  if v_status = 'dismissed' then
    return jsonb_build_object('ok', true, 'status', 'dismissed');
  end if;
  if v_status = 'converted' then
    return jsonb_build_object('ok', false, 'reason', 'already_converted');
  end if;

  update public.inbound_intake_messages
     set status = 'dismissed', dismissed_at = now()
   where id = p_message;

  return jsonb_build_object('ok', true, 'status', 'dismissed');
end;
$$;

revoke all on function public.dismiss_inbound_intake(uuid) from public;
grant execute on function public.dismiss_inbound_intake(uuid) to authenticated;

-- claim_inbound_intake_for_project: bind a captured forward to a project the
-- caller has ALREADY created through the entitlement-checked path. Fail-closed
-- on tenant mismatch, and single-use — the status guard means two concurrent
-- conversions can never attach the same forward to two projects.
create or replace function public.claim_inbound_intake_for_project(
  p_message uuid,
  p_project uuid
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_company uuid;
  v_status text;
  v_project_company uuid;
begin
  if p_message is null or p_project is null then
    return jsonb_build_object('ok', false, 'reason', 'invalid_input');
  end if;

  select company_id, status
    into v_company, v_status
    from public.inbound_intake_messages
   where id = p_message
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'not_found');
  end if;
  if not (public.is_member_of(v_company) or public.is_staff()) then
    return jsonb_build_object('ok', false, 'reason', 'not_authorized');
  end if;
  if v_status not in ('pending', 'sender_unverified') then
    return jsonb_build_object('ok', false, 'reason', 'not_convertible');
  end if;

  select company_id into v_project_company
    from public.projects
   where id = p_project and deleted_at is null;

  if v_project_company is null then
    return jsonb_build_object('ok', false, 'reason', 'project_not_found');
  end if;
  -- The forward and the project must belong to the same tenant. Without this a
  -- member of two companies could pull another tenant's documents into a
  -- project. Fail closed.
  if v_project_company <> v_company then
    return jsonb_build_object('ok', false, 'reason', 'tenant_mismatch');
  end if;

  update public.inbound_intake_messages
     set status = 'converted', converted_at = now(), project_id = p_project
   where id = p_message
     and status in ('pending', 'sender_unverified');

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'not_convertible');
  end if;

  return jsonb_build_object('ok', true, 'company_id', v_company, 'project_id', p_project);
end;
$$;

revoke all on function public.claim_inbound_intake_for_project(uuid, uuid) from public;
grant execute on function public.claim_inbound_intake_for_project(uuid, uuid) to authenticated;
