-- =============================================================================
-- Mobi Estimates — Forwarded bid intake: shared mailbox routing + staff triage
--
-- Migration 0036 assumed every forward arrived at a per-company address, so the
-- company was always known and company_id could be NOT NULL. The advertised
-- intake address is the shared `estimates@mobiestimates.com` mailbox, which
-- means a forward can arrive that we cannot place:
--
--   * the contractor forwarded from an address that isn't on their account
--     (an assistant, a phone's personal account, a shared estimating inbox);
--   * the sender's address belongs to members of more than one company;
--   * it isn't a client at all — a shared address on a public domain receives
--     spam and misdirected mail.
--
-- Silently dropping those would lose a real bid on the contractor's deadline, so
-- they are recorded as 'unrouted' for staff triage. Deliberately WITHOUT their
-- attachments: a shared address anyone can write to must not be a way to fill
-- our storage with arbitrary files. The attachment count is still recorded so
-- staff can tell a contractor exactly what didn't make it through.
--
-- Idempotent: safe to re-run.
-- =============================================================================

-- An unrouted forward has no tenant yet.
alter table public.inbound_intake_messages
  alter column company_id drop not null;

-- Extend the status set. The constraint was created inline in 0036, so it
-- carries Postgres's generated name.
alter table public.inbound_intake_messages
  drop constraint if exists inbound_intake_messages_status_check;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'inbound_intake_messages_status_allowed'
  ) then
    alter table public.inbound_intake_messages
      add constraint inbound_intake_messages_status_allowed
      check (status in ('pending', 'sender_unverified', 'unrouted', 'converted', 'dismissed'));
  end if;
end $$;

-- Keep tenant presence and status consistent:
--   * 'unrouted' always means no tenant, so an unroutable forward can never sit
--     in a company's queue — which would inflate the portal's "waiting for your
--     review" count with something the customer cannot open;
--   * every LIVE customer-facing status must have a tenant, so a routed forward
--     can never end up in nobody's queue;
--   * 'dismissed' is allowed either way, because staff dismiss untenanted spam
--     out of the triage queue and that transition must not be blocked.
alter table public.inbound_intake_messages
  drop constraint if exists inbound_intake_messages_company_matches_status;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'inbound_intake_messages_company_status_consistent'
  ) then
    alter table public.inbound_intake_messages
      add constraint inbound_intake_messages_company_status_consistent
      check (
        (status = 'unrouted' and company_id is null)
        or status = 'dismissed'
        or (status in ('pending', 'sender_unverified', 'converted') and company_id is not null)
      );
  end if;
end $$;

alter table public.inbound_intake_messages
  -- How the tenant was resolved, so staff can see why a forward landed where it
  -- did: 'alias' (the unguessable +tag) or 'sender' (matched a member's email).
  add column if not exists routed_by text,
  add column if not exists unrouted_reason text;

alter table public.inbound_intake_messages
  drop constraint if exists inbound_intake_messages_routed_by_check;
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'inbound_intake_messages_routed_by_allowed'
  ) then
    alter table public.inbound_intake_messages
      add constraint inbound_intake_messages_routed_by_allowed
      check (routed_by is null or routed_by in ('alias', 'sender'));
  end if;
end $$;

-- Staff triage queue.
create index if not exists idx_inbound_intake_unrouted
  on public.inbound_intake_messages (received_at desc)
  where status = 'unrouted';

-- The 0036 select policies already fail closed for these rows: a customer's
-- branch is public.is_member_of(company_id), and is_member_of(null) is false, so
-- only public.is_staff() can read an unrouted forward. Nothing to change.
