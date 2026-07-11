-- =============================================================================
-- Mobi Estimates — P0 final-delivery lock: lock customer-visible deliverable writes
--
-- Staff uploads to the `deliverables` bucket/table are immediately visible to
-- company members through the customer portal. Until a full final-delivery
-- approval workflow exists (complete evidence + supported scope + required
-- reviews + explicit owner approval), the real database/storage boundary must
-- stay tighter than the browser UI gate.
--
-- This migration removes direct-SDK bypasses by locking customer-visible
-- deliverable reads/inserts/replacements/deletes for authenticated users entirely.
-- Admin/owner users may still need a future service workflow, but that workflow
-- must prove the P0 prerequisites before a customer-visible artifact is created.
-- =============================================================================

-- Metadata rows for customer-visible deliverables: authenticated users cannot
-- read, create, or mutate rows that make a deliverable visible in the portal
-- until the full final-delivery approval workflow exists.
drop policy if exists deliverables_select on public.deliverables;
drop policy if exists deliverables_update_client on public.deliverables;
drop policy if exists deliverables_write_staff on public.deliverables;
drop policy if exists deliverables_update_admin on public.deliverables;
drop policy if exists deliverables_insert_admin on public.deliverables;

create policy deliverables_select_locked on public.deliverables
  for select using (false);

create policy deliverables_update_locked on public.deliverables
  for update using (false)
  with check (false);

create policy deliverables_insert_locked on public.deliverables
  for insert with check (false);

-- Storage objects in the customer-visible deliverables bucket. Block direct SDK
-- download/list/upload/replacement/deletion for authenticated users until a
-- final-delivery approval workflow can enforce evidence/scope/review/owner gates.
drop policy if exists "deliverables_select" on storage.objects;
create policy "deliverables_select" on storage.objects
  for select to authenticated
  using (bucket_id = 'deliverables' and false);

drop policy if exists "deliverables_insert" on storage.objects;
create policy "deliverables_insert" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'deliverables' and false);

drop policy if exists "deliverables_update" on storage.objects;
create policy "deliverables_update" on storage.objects
  for update to authenticated
  using (bucket_id = 'deliverables' and false)
  with check (bucket_id = 'deliverables' and false);

drop policy if exists "deliverables_delete" on storage.objects;
create policy "deliverables_delete" on storage.objects
  for delete to authenticated
  using (bucket_id = 'deliverables' and false);
