-- =============================================================================
-- Mobi Estimates — Storage: deliverables bucket + RLS (Milestone 4)
--
-- Private bucket holding STAFF-produced deliverables (completed estimates,
-- takeoffs, marked-up plans). Same path convention as project-files:
--
--     {company_id}/{project_id}/{filename}
--
-- Access model differs from project-files: clients (company members) may READ
-- their own deliverables, but only STAFF may write/replace/delete them. Mirrors
-- the deliverables table policies in 0002 (deliverables_select for members/staff,
-- deliverables_write_staff for insert).
--
-- Idempotent: safe to re-run.
-- =============================================================================

insert into storage.buckets (id, name, public, file_size_limit)
values ('deliverables', 'deliverables', false, 104857600) -- 100 MB
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit;

-- Company members (and staff) may read their company's deliverables.
drop policy if exists "deliverables_select" on storage.objects;
create policy "deliverables_select" on storage.objects
  for select to authenticated
  using (
    bucket_id = 'deliverables'
    and (
      public.is_staff()
      or public.is_member_of((storage.foldername(name))[1]::uuid)
    )
  );

-- Only staff may upload / replace / delete deliverables.
drop policy if exists "deliverables_insert" on storage.objects;
create policy "deliverables_insert" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'deliverables' and public.is_staff());

drop policy if exists "deliverables_update" on storage.objects;
create policy "deliverables_update" on storage.objects
  for update to authenticated
  using (bucket_id = 'deliverables' and public.is_staff())
  with check (bucket_id = 'deliverables' and public.is_staff());

drop policy if exists "deliverables_delete" on storage.objects;
create policy "deliverables_delete" on storage.objects
  for delete to authenticated
  using (bucket_id = 'deliverables' and public.is_staff());
