-- P0 final-delivery project status lock.
--
-- The app-layer admin action already fails closed for legacy project statuses
-- that imply customer final delivery (delivered/revised). These RLS policies
-- close the direct Supabase client paths too: authenticated staff/company
-- members may continue normal project edits/status movement, but cannot set a
-- customer-visible project or timeline status to a final-delivery value until a
-- future explicit owner-approval/evidence workflow replaces this lock.

drop policy if exists projects_insert on public.projects;
drop policy if exists projects_update on public.projects;
drop policy if exists status_history_insert_staff on public.project_status_history;

create policy projects_insert on public.projects
  for insert with check (
    public.is_member_of(company_id)
    and status not in ('delivered', 'revised')
  );

create policy projects_update on public.projects
  for update using (public.is_staff() or public.is_member_of(company_id))
  with check (
    (public.is_staff() or public.is_member_of(company_id))
    and status not in ('delivered', 'revised')
  );

create policy status_history_insert_staff on public.project_status_history
  for insert with check (
    public.is_staff()
    and to_status not in ('delivered', 'revised')
  );

-- RLS is necessary but not sufficient for this audit gate because privileged
-- server/service-role paths can bypass RLS. Keep a database-level tripwire in
-- front of every project-status write path until a future explicit
-- owner-approval/evidence workflow replaces the lock.
create or replace function public.prevent_final_delivery_project_status()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.status in ('delivered', 'revised') then
    raise exception 'P0 final-delivery gate locked: project status % requires complete evidence, supported scope, required reviews, and explicit owner approval', new.status;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_prevent_final_delivery_project_status on public.projects;
create trigger trg_prevent_final_delivery_project_status
  before insert or update of status on public.projects
  for each row execute function public.prevent_final_delivery_project_status();

create or replace function public.prevent_final_delivery_timeline_status()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.to_status in ('delivered', 'revised') then
    raise exception 'P0 final-delivery gate locked: timeline status % requires complete evidence, supported scope, required reviews, and explicit owner approval', new.to_status;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_prevent_final_delivery_timeline_status on public.project_status_history;
create trigger trg_prevent_final_delivery_timeline_status
  before insert or update of to_status on public.project_status_history
  for each row execute function public.prevent_final_delivery_timeline_status();
