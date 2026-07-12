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
