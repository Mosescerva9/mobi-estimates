-- =============================================================================
-- Mobi Estimates — Storage: project-files bucket + RLS (Milestone 2)
--
-- Private bucket holding customer-uploaded plans/documents. Bytes are NEVER
-- public — access is via short-lived signed URLs only. Row isolation is enforced
-- on storage.objects using the documented path convention:
--
--     {company_id}/{project_id}/{filename}
--
-- so (storage.foldername(name))[1] is the company_id. A user may read/write an
-- object only if they are a member of that company (public.is_member_of), and
-- staff (public.is_staff) may read/write across companies.
--
-- Idempotent: safe to re-run.
-- =============================================================================

-- ---- bucket ----------------------------------------------------------------
-- 25 MB per object. allowed_mime_types is intentionally left null: CAD formats
-- (.dwg/.dwf) have inconsistent MIME types across browsers, so the file-type
-- allowlist is enforced in the app layer; the private bucket + size cap + RLS
-- are the security boundary here.
insert into storage.buckets (id, name, public, file_size_limit)
values ('project-files', 'project-files', false, 26214400)
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit;

-- ---- policies on storage.objects (scoped to this bucket) -------------------
drop policy if exists "project_files_select" on storage.objects;
create policy "project_files_select" on storage.objects
  for select to authenticated
  using (
    bucket_id = 'project-files'
    and (
      public.is_staff()
      or public.is_member_of((storage.foldername(name))[1]::uuid)
    )
  );

drop policy if exists "project_files_insert" on storage.objects;
create policy "project_files_insert" on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'project-files'
    and (
      public.is_staff()
      or public.is_member_of((storage.foldername(name))[1]::uuid)
    )
  );

drop policy if exists "project_files_update" on storage.objects;
create policy "project_files_update" on storage.objects
  for update to authenticated
  using (
    bucket_id = 'project-files'
    and (
      public.is_staff()
      or public.is_member_of((storage.foldername(name))[1]::uuid)
    )
  )
  with check (
    bucket_id = 'project-files'
    and (
      public.is_staff()
      or public.is_member_of((storage.foldername(name))[1]::uuid)
    )
  );

drop policy if exists "project_files_delete" on storage.objects;
create policy "project_files_delete" on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'project-files'
    and (
      public.is_staff()
      or public.is_member_of((storage.foldername(name))[1]::uuid)
    )
  );
