-- =============================================================================
-- Mobi Estimates — Harden project_files project/company scope
--
-- The original broad project_files policy allowed any company member to write a
-- metadata row for their company_id, without also proving project_id belongs to
-- that same company. Browser-direct uploads pass project_id/company_id from the
-- client, so enforce the project/company relationship at RLS as well.
-- =============================================================================

drop policy if exists files_rw on public.project_files;

create policy project_files_select_scoped on public.project_files
  for select using (
    public.is_staff()
    or exists (
      select 1
      from public.projects p
      where p.id = project_files.project_id
        and p.company_id = project_files.company_id
        and p.deleted_at is null
        and public.is_member_of(p.company_id)
    )
  );

create policy project_files_insert_scoped on public.project_files
  for insert with check (
    public.is_staff()
    or exists (
      select 1
      from public.projects p
      where p.id = project_files.project_id
        and p.company_id = project_files.company_id
        and p.deleted_at is null
        and public.is_member_of(p.company_id)
    )
  );

create policy project_files_update_scoped on public.project_files
  for update using (
    public.is_staff()
    or exists (
      select 1
      from public.projects p
      where p.id = project_files.project_id
        and p.company_id = project_files.company_id
        and p.deleted_at is null
        and public.is_member_of(p.company_id)
    )
  ) with check (
    public.is_staff()
    or exists (
      select 1
      from public.projects p
      where p.id = project_files.project_id
        and p.company_id = project_files.company_id
        and p.deleted_at is null
        and public.is_member_of(p.company_id)
    )
  );

create policy project_files_delete_scoped on public.project_files
  for delete using (
    public.is_staff()
    or exists (
      select 1
      from public.projects p
      where p.id = project_files.project_id
        and p.company_id = project_files.company_id
        and p.deleted_at is null
        and public.is_member_of(p.company_id)
    )
  );
