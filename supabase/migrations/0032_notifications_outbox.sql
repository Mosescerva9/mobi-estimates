-- =============================================================================
-- Mobi Estimates — Notification foundation (in-app rows) + external outbox.
--
-- Scope of THIS packet:
--   • On staff project status changes, tenant-scoped in-app notification rows
--     are created for the customer company's members, with fixed safe status
--     copy and a project link. No internal notes / provider output / plan text /
--     secrets are ever stored in these rows (the app builds them from a fixed
--     template — see src/lib/notifications.ts).
--   • A durable external-notification OUTBOX for future email/sms. Every external
--     row is created HELD: the status check constraint physically forbids any
--     'sent'/'queued'/'sending' state. There is NO sender/worker/provider in
--     this packet and none may run.
--
-- IMPORTANT: public.notifications ALREADY EXISTS from migration 0001 with the
-- shape (id, user_id, company_id, type, title, body, link, read_at, created_at)
-- and the policies notifications_select / notifications_update_self from 0002.
-- This migration EVOLVES that production table in place — it preserves every
-- existing row, column, and policy and only ADDS the nullable event columns,
-- a PARTIAL idempotency index, and a NEW uniquely-named staff insert policy.
-- It never recreates the existing table or the existing policy names.
--
-- Idempotency: the in-app table keys event rows on (status_history_id, channel,
-- user_id); the outbox keys on (status_history_id, channel, recipient). A retried
-- status change can never create duplicate notifications.
-- =============================================================================

-- ---- in-app notifications: evolve the existing public.notifications table -----
-- Add only nullable event/project/status/channel columns. `channel` carries a
-- compatible default so existing rows backfill to 'in_app' automatically; the
-- other columns are null for legacy rows (they predate the status-event model).
alter table public.notifications
  add column if not exists project_id        uuid references public.projects(id) on delete cascade,
  add column if not exists status_history_id uuid references public.project_status_history(id) on delete cascade,
  add column if not exists channel           text not null default 'in_app',
  add column if not exists status_event      text;

-- Bound the channel to the only value this packet emits, without breaking the
-- backfilled legacy rows (all 'in_app'). Guarded so the migration stays idempotent.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'notifications_channel_check') then
    alter table public.notifications
      add constraint notifications_channel_check check (channel in ('in_app'));
  end if;
end $$;

-- Event idempotency: at most one in-app notification per (status-history event,
-- channel, recipient). PARTIAL (only where status_history_id is not null) so the
-- pre-existing rows — whose status_history_id is null — are never touched and can
-- never collide. The app only ever inserts rows WITH a canonical history id.
create unique index if not exists uniq_notifications_status_event_recipient
  on public.notifications (status_history_id, channel, user_id)
  where status_history_id is not null;

create index if not exists idx_notifications_project on public.notifications(project_id);

-- RLS is already enabled (0001) and notifications_select / notifications_update_self
-- already exist (0002) — they are intentionally left as-is. Add ONLY the missing
-- staff insert policy under a NEW, unique name (service-role bypasses RLS, but a
-- staff server session needs an explicit insert grant to create these rows).
drop policy if exists notifications_insert_staff on public.notifications;
create policy notifications_insert_staff on public.notifications
  for insert with check (public.is_staff());

-- ---- external notification outbox (HELD — no sends in this packet) -----------
-- New table. Every row is created held pending explicit approval + a future,
-- separately-approved sender; the status check constraint forbids any sent state.
create table if not exists public.notification_outbox (
  id                 uuid primary key default gen_random_uuid(),
  company_id         uuid not null references public.companies(id) on delete cascade,
  project_id         uuid references public.projects(id) on delete cascade,
  status_history_id  uuid references public.project_status_history(id) on delete cascade,
  channel            text not null check (channel in ('email', 'sms')),
  recipient          text not null,
  recipient_user_id  uuid references auth.users(id) on delete set null,
  subject            text,
  body               text not null,
  -- Deliberately NO 'sent'/'queued'/'sending' value: every external row is held
  -- pending explicit approval and a future, separately-approved sender.
  status             text not null default 'approval_required'
                       check (status in ('approval_required', 'held', 'canceled')),
  created_at         timestamptz not null default now(),
  unique (status_history_id, channel, recipient)
);

create index if not exists idx_notification_outbox_status
  on public.notification_outbox(status) where status = 'approval_required';

alter table public.notification_outbox enable row level security;

-- Outbox rows can carry recipient contact info; customers never read them.
-- Staff (or service-role, which bypasses RLS) only.
drop policy if exists notification_outbox_select_staff on public.notification_outbox;
create policy notification_outbox_select_staff on public.notification_outbox
  for select using (public.is_staff());

drop policy if exists notification_outbox_insert_staff on public.notification_outbox;
create policy notification_outbox_insert_staff on public.notification_outbox
  for insert with check (public.is_staff());
