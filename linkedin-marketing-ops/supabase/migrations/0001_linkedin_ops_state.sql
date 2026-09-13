-- LinkedIn Ops durable state.
--
-- The whole control-panel queue (settings, posts, engage, DMs) is stored as a
-- single JSONB row. This is a single-owner internal tool, so one row is enough
-- and keeps reads/writes atomic at the row level.
--
-- Access is server-only through the Supabase service-role key. Row Level
-- Security is enabled with NO policies, so the anon/public key cannot read or
-- write this table from the browser. The service role bypasses RLS.

create table if not exists public.linkedin_ops_state (
  id         text primary key default 'singleton',
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.linkedin_ops_state enable row level security;

-- Seed the singleton row if it is not there yet. Safe to run repeatedly.
insert into public.linkedin_ops_state (id, data)
values ('singleton', '{}'::jsonb)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Compare-and-swap write.
--
-- The app reads (data, updated_at) and, when it writes back, passes the
-- updated_at it read. The update only lands when that expected version still
-- matches the row's current updated_at, so two concurrent requests cannot
-- silently overwrite each other — the loser gets a NULL back (conflict).
--
--   p_expected_updated_at = NULL  → caller expected no row yet (allow insert).
--   returns the new updated_at on success, or NULL on a CAS conflict.
--
-- security definer + a locked search_path so it runs with table access while
-- still being callable only by the service role (see grants below). The row is
-- locked FOR UPDATE to serialize concurrent CAS attempts.
-- ---------------------------------------------------------------------------
create or replace function public.linkedin_ops_state_cas(
  p_expected_updated_at timestamptz,
  p_data jsonb
) returns timestamptz
language plpgsql
security definer
set search_path = public
as $$
declare
  v_current timestamptz;
  v_new     timestamptz := now();
begin
  select updated_at into v_current
    from public.linkedin_ops_state
    where id = 'singleton'
    for update;

  if not found then
    -- Row missing: only initialize when the caller also expected no row.
    if p_expected_updated_at is not null then
      return null;
    end if;
    insert into public.linkedin_ops_state (id, data, updated_at)
      values ('singleton', p_data, v_new);
    return v_new;
  end if;

  -- Row present: the caller's expected version must match exactly.
  if p_expected_updated_at is null or p_expected_updated_at <> v_current then
    return null;
  end if;

  update public.linkedin_ops_state
    set data = p_data, updated_at = v_new
    where id = 'singleton';
  return v_new;
end;
$$;

-- Lock the function down: server-only via the service role. Revoke the implicit
-- execute grant to PUBLIC and deny anon/authenticated. RLS stays default-deny.
revoke all on function public.linkedin_ops_state_cas(timestamptz, jsonb) from public;
revoke all on function public.linkedin_ops_state_cas(timestamptz, jsonb) from anon;
revoke all on function public.linkedin_ops_state_cas(timestamptz, jsonb) from authenticated;
grant execute on function public.linkedin_ops_state_cas(timestamptz, jsonb) to service_role;
