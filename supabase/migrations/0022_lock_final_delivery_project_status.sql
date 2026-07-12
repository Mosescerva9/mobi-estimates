-- P0 final-delivery project status lock.
--
-- The app-layer admin action already fails closed for legacy project statuses
-- that imply customer final delivery (delivered/revised). This RLS policy closes
-- the direct Supabase client path too: authenticated staff/company members may
-- continue normal project edits/status movement, but cannot set status to a
-- final-delivery value until a future explicit owner-approval/evidence workflow
-- replaces this lock.

drop policy if exists projects_update on public.projects;

create policy projects_update on public.projects
  for update using (public.is_staff() or public.is_member_of(company_id))
  with check (
    (public.is_staff() or public.is_member_of(company_id))
    and status not in ('delivered', 'revised')
  );
