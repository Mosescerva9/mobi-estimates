-- =============================================================================
-- Mobi Estimates — Client Portal : Row Level Security (Milestone 1)
--
-- Principles:
--  * Default deny. Every table has explicit policies (RLS enabled in 0001).
--  * Clients only ever see rows belonging to a company they are a member of.
--  * Staff (estimator/reviewer/admin) can see operational data across companies.
--  * The Supabase service-role key BYPASSES RLS and is used ONLY server-side
--    (Stripe webhooks, admin tasks). It is never shipped to the browser.
--  * internal_note on the project timeline is NOT exposed to clients: clients
--    read a client-safe view (or the client_timeline RPC), not the base table.
-- =============================================================================

-- ---- helper functions (security definer to avoid RLS recursion) ------------
create or replace function public.current_role()
returns public.user_role language sql stable security definer set search_path = public as $$
  select role from public.profiles where id = auth.uid();
$$;

create or replace function public.is_staff()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles
                 where id = auth.uid() and role in ('estimator','reviewer','admin'));
$$;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin');
$$;

create or replace function public.is_member_of(cid uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.company_members
                 where user_id = auth.uid() and company_id = cid);
$$;

create or replace function public.is_member_of_project(pid uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.projects pr
    join public.company_members cm on cm.company_id = pr.company_id
    where pr.id = pid and cm.user_id = auth.uid());
$$;

-- ---- profiles --------------------------------------------------------------
create policy profiles_select_self_or_staff on public.profiles
  for select using (id = auth.uid() or public.is_staff());
create policy profiles_update_self on public.profiles
  for update using (id = auth.uid()) with check (id = auth.uid());
create policy profiles_insert_self on public.profiles
  for insert with check (id = auth.uid());

-- ---- companies -------------------------------------------------------------
create policy companies_select on public.companies
  for select using (public.is_staff() or public.is_member_of(id));
create policy companies_insert on public.companies
  for insert with check (auth.uid() is not null);     -- creator linked via company_members
create policy companies_update on public.companies
  for update using (public.is_staff() or public.is_member_of(id));

-- ---- company_members -------------------------------------------------------
create policy members_select on public.company_members
  for select using (public.is_staff() or user_id = auth.uid() or public.is_member_of(company_id));
create policy members_insert on public.company_members
  for insert with check (public.is_admin() or user_id = auth.uid());
create policy members_update_admin on public.company_members
  for update using (public.is_admin());

-- ---- plans / agreements / training / faq : readable, staff-writable --------
create policy plans_read on public.plans for select using (true);
create policy plans_write on public.plans for all using (public.is_admin()) with check (public.is_admin());

create policy agreements_read on public.service_agreements for select using (true);
create policy agreements_write on public.service_agreements for all using (public.is_admin()) with check (public.is_admin());

create policy training_read on public.training_modules for select using (true);
create policy training_write on public.training_modules for all using (public.is_admin()) with check (public.is_admin());

create policy faq_read on public.faq_entries for select using (is_published or public.is_staff());
create policy faq_write on public.faq_entries for all using (public.is_admin()) with check (public.is_admin());

-- ---- agreement acceptances -------------------------------------------------
create policy acceptances_select on public.agreement_acceptances
  for select using (public.is_staff() or public.is_member_of(company_id) or user_id = auth.uid());
create policy acceptances_insert on public.agreement_acceptances
  for insert with check (user_id = auth.uid());

-- ---- onboarding / preferences (company-scoped) -----------------------------
create policy onboarding_rw on public.onboarding_progress
  for all using (public.is_staff() or public.is_member_of(company_id))
  with check (public.is_staff() or public.is_member_of(company_id));

create policy preferences_rw on public.company_preferences
  for all using (public.is_staff() or public.is_member_of(company_id))
  with check (public.is_staff() or public.is_member_of(company_id));

-- ---- subscriptions (clients read; only server/admin writes) ----------------
create policy subscriptions_select on public.subscriptions
  for select using (public.is_staff() or public.is_member_of(company_id));
create policy subscriptions_write_admin on public.subscriptions
  for all using (public.is_admin()) with check (public.is_admin());
-- (Stripe webhook handler writes with the service-role key, bypassing RLS.)

-- ---- projects --------------------------------------------------------------
create policy projects_select on public.projects
  for select using (public.is_staff() or public.is_member_of(company_id));
create policy projects_insert on public.projects
  for insert with check (public.is_member_of(company_id));
create policy projects_update on public.projects
  for update using (public.is_staff() or public.is_member_of(company_id))
  with check (public.is_staff() or public.is_member_of(company_id));

-- ---- project child tables (scope / constraints / assignments) --------------
create policy scopes_rw on public.project_scopes
  for all using (public.is_staff() or public.is_member_of_project(project_id))
  with check (public.is_staff() or public.is_member_of_project(project_id));
create policy constraints_rw on public.project_constraints
  for all using (public.is_staff() or public.is_member_of_project(project_id))
  with check (public.is_staff() or public.is_member_of_project(project_id));
create policy assignments_select on public.project_assignments
  for select using (public.is_staff() or public.is_member_of_project(project_id));
create policy assignments_write_staff on public.project_assignments
  for all using (public.is_staff()) with check (public.is_staff());

-- ---- files / deliverables (metadata; bytes live in private Storage) ---------
create policy files_rw on public.project_files
  for all using (public.is_staff() or public.is_member_of(company_id))
  with check (public.is_staff() or public.is_member_of(company_id));
create policy deliverables_select on public.deliverables
  for select using (public.is_staff() or public.is_member_of(company_id));
create policy deliverables_update_client on public.deliverables
  for update using (public.is_member_of(company_id) or public.is_staff())
  with check (public.is_member_of(company_id) or public.is_staff());  -- mark reviewed/approved
create policy deliverables_write_staff on public.deliverables
  for insert with check (public.is_staff());

-- ---- status history : STAFF read base table only (contains internal_note) ---
create policy status_history_select_staff on public.project_status_history
  for select using (public.is_staff());
create policy status_history_insert_staff on public.project_status_history
  for insert with check (public.is_staff());

-- Client-safe timeline (omits internal_note). Clients call this RPC.
create or replace function public.client_timeline(p_project uuid)
returns table (to_status public.project_status, client_note text, created_at timestamptz)
language sql stable security definer set search_path = public as $$
  select h.to_status, h.client_note, h.created_at
  from public.project_status_history h
  where h.project_id = p_project
    and public.is_member_of_project(p_project)
  order by h.created_at;
$$;

-- ---- questions / responses -------------------------------------------------
create policy questions_select on public.project_questions
  for select using (public.is_staff() or public.is_member_of(company_id));
create policy questions_write_staff on public.project_questions
  for all using (public.is_staff()) with check (public.is_staff());

create policy responses_select on public.question_responses
  for select using (
    public.is_staff() or exists (
      select 1 from public.project_questions q
      where q.id = question_id and public.is_member_of(q.company_id)));
create policy responses_insert on public.question_responses
  for insert with check (
    public.is_staff() or exists (
      select 1 from public.project_questions q
      where q.id = question_id and public.is_member_of(q.company_id)));

-- ---- revision requests -----------------------------------------------------
create policy revisions_select on public.revision_requests
  for select using (public.is_staff() or public.is_member_of(company_id));
create policy revisions_insert on public.revision_requests
  for insert with check (public.is_member_of(company_id) or public.is_staff());
create policy revisions_update_staff on public.revision_requests
  for update using (public.is_staff()) with check (public.is_staff());

-- ---- support tickets / notifications / training completions -----------------
create policy tickets_rw on public.support_tickets
  for all using (public.is_staff() or public.is_member_of(company_id) or user_id = auth.uid())
  with check (public.is_staff() or public.is_member_of(company_id) or user_id = auth.uid());

create policy notifications_select on public.notifications
  for select using (user_id = auth.uid() or public.is_staff());
create policy notifications_update_self on public.notifications
  for update using (user_id = auth.uid()) with check (user_id = auth.uid());

create policy training_completions_rw on public.training_completions
  for all using (public.is_staff() or user_id = auth.uid())
  with check (public.is_staff() or user_id = auth.uid());

-- ---- audit logs : staff read; inserts via server/service role ---------------
create policy audit_select_staff on public.audit_logs
  for select using (public.is_staff());

-- webhook_events : no policies => only the service-role key (which bypasses
-- RLS) can read/write. Intentional.

-- ---- new-user bootstrap: create a profile row on signup --------------------
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'full_name',''))
  on conflict (id) do nothing;
  return new;
end;
$$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- =============================================================================
-- STORAGE (run in Supabase Storage; documented here for reference)
-- Create PRIVATE buckets: 'project-files' and 'deliverables'.
-- Object path convention:  {company_id}/{project_id}/{folder}/{filename}
-- Access via short-lived SIGNED URLs only; never public URLs.
-- Example storage policy (apply via dashboard or storage schema):
--
--   create policy "company members read project files"
--     on storage.objects for select using (
--       bucket_id = 'project-files'
--       and public.is_member_of( (storage.foldername(name))[1]::uuid ) );
--
-- (Mirror insert/delete for members + staff. Deliverables: client read, staff write.)
-- =============================================================================
