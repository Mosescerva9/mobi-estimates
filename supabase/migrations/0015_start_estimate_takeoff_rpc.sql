-- =============================================================================
-- Mobi Estimates — Start takeoff handoff RPC
--
-- Atomically transitions an EstimateJob from takeoff_ready to
-- takeoff_in_progress so the status change and audit event cannot diverge.
-- Staff-only; client-facing pages do not call this function.
-- =============================================================================

create or replace function public.start_estimate_takeoff(
  p_project_id uuid,
  p_estimate_job_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job record;
  v_counts jsonb;
  v_total int;
  v_accepted int;
  v_pending int;
  v_needs_replacement int;
  v_ignored int;
  v_project_file_count int;
  v_missing_registered_file_count int;
  v_previous_status text;
begin
  if not public.is_staff() then
    raise exception 'Not authorized';
  end if;

  select id, project_id, status
    into v_job
    from public.estimate_jobs
   where id = p_estimate_job_id
     and project_id = p_project_id
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'job_not_found');
  end if;

  perform 1
    from public.projects
   where id = p_project_id
     and deleted_at is null
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'project_not_found');
  end if;

  if v_job.status <> 'takeoff_ready' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_job.status::text);
  end if;

  select count(*)::int
    into v_project_file_count
    from public.project_files
   where project_id = p_project_id
     and deleted_at is null;

  select count(*)::int
    into v_missing_registered_file_count
    from public.project_files pf
   where pf.project_id = p_project_id
     and pf.deleted_at is null
     and not exists (
       select 1
         from public.estimate_job_documents ejd
        where ejd.estimate_job_id = p_estimate_job_id
          and ejd.project_file_id = pf.id
     );

  -- Serialize takeoff start with per-document review edits. The review-update
  -- RPC locks the job first and then the target document; takeoff start follows
  -- the same order and locks all documents before counting them.
  perform 1
    from public.estimate_job_documents
   where estimate_job_id = p_estimate_job_id
   for update;

  select
    count(*)::int,
    count(*) filter (where review_status = 'accepted')::int,
    count(*) filter (where review_status = 'pending')::int,
    count(*) filter (where review_status = 'needs_replacement')::int,
    count(*) filter (where review_status = 'ignored')::int
  into v_total, v_accepted, v_pending, v_needs_replacement, v_ignored
  from public.estimate_job_documents
  where estimate_job_id = p_estimate_job_id;

  v_counts := jsonb_build_object(
    'total', v_total,
    'accepted', v_accepted,
    'pending', v_pending,
    'needs_replacement', v_needs_replacement,
    'ignored', v_ignored,
    'project_files', v_project_file_count,
    'missing_registered_project_files', v_missing_registered_file_count
  );

  if v_missing_registered_file_count > 0 then
    return jsonb_build_object('ok', false, 'reason', 'document_register_stale', 'counts', v_counts);
  end if;

  if v_pending > 0 then
    return jsonb_build_object('ok', false, 'reason', 'pending_documents', 'counts', v_counts);
  end if;

  if v_needs_replacement > 0 then
    return jsonb_build_object('ok', false, 'reason', 'replacement_documents_required', 'counts', v_counts);
  end if;

  if v_accepted = 0 then
    return jsonb_build_object('ok', false, 'reason', 'no_accepted_documents', 'counts', v_counts);
  end if;

  v_previous_status := v_job.status::text;

  update public.estimate_jobs
     set status = 'takeoff_in_progress',
         blocked_reason = null
   where id = p_estimate_job_id
     and project_id = p_project_id;

  insert into public.estimate_job_events (
    estimate_job_id,
    project_id,
    event_type,
    actor_id,
    actor_type,
    summary,
    payload
  ) values (
    p_estimate_job_id,
    p_project_id,
    'takeoff_started',
    auth.uid(),
    'staff',
    'Takeoff started.',
    v_counts || jsonb_build_object(
      'previous_status', v_previous_status,
      'next_status', 'takeoff_in_progress'
    )
  );

  return jsonb_build_object(
    'ok', true,
    'previous_status', v_previous_status,
    'next_status', 'takeoff_in_progress',
    'counts', v_counts
  );
end;
$$;

grant execute on function public.start_estimate_takeoff(uuid, uuid) to authenticated;

create or replace function public.update_estimate_job_document_review(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_document_id uuid,
  p_review_status text,
  p_review_notes text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job record;
  v_document record;
begin
  if not public.is_staff() then
    raise exception 'Not authorized';
  end if;

  if p_review_status not in ('pending', 'accepted', 'needs_replacement', 'ignored') then
    return jsonb_build_object('ok', false, 'reason', 'invalid_review_status');
  end if;

  select id, project_id, status
    into v_job
    from public.estimate_jobs
   where id = p_estimate_job_id
     and project_id = p_project_id
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'job_not_found');
  end if;

  if v_job.status in ('takeoff_in_progress', 'pricing_review_pending', 'qa_pending', 'ready_for_owner_approval', 'closed', 'canceled') then
    return jsonb_build_object('ok', false, 'reason', 'document_review_locked', 'current_status', v_job.status::text);
  end if;

  select id, project_id, review_status
    into v_document
    from public.estimate_job_documents
   where id = p_document_id
     and estimate_job_id = p_estimate_job_id
     and project_id = p_project_id
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'document_not_found');
  end if;

  update public.estimate_job_documents
     set review_status = p_review_status,
         review_notes = nullif(btrim(coalesce(p_review_notes, '')), '')
   where id = p_document_id
     and estimate_job_id = p_estimate_job_id
     and project_id = p_project_id;

  insert into public.estimate_job_events (
    estimate_job_id,
    project_id,
    event_type,
    actor_id,
    actor_type,
    summary,
    payload
  ) values (
    p_estimate_job_id,
    p_project_id,
    'document_review_updated',
    auth.uid(),
    'staff',
    format('Document review marked %s.', p_review_status),
    jsonb_build_object(
      'document_id', p_document_id,
      'previous_review_status', v_document.review_status,
      'review_status', p_review_status,
      'review_notes', nullif(btrim(coalesce(p_review_notes, '')), '')
    )
  );

  return jsonb_build_object(
    'ok', true,
    'document_id', p_document_id,
    'previous_review_status', v_document.review_status,
    'review_status', p_review_status
  );
end;
$$;

grant execute on function public.update_estimate_job_document_review(uuid, uuid, uuid, text, text) to authenticated;

-- Replace the 0014 document-review completion RPC with the same job-first lock
-- order used by takeoff/review-edit RPCs, and prevent stale forms from moving
-- jobs backward after document review is already complete.
create or replace function public.complete_estimate_document_review(
  p_project_id uuid,
  p_estimate_job_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job record;
  v_counts jsonb;
  v_total int;
  v_accepted int;
  v_pending int;
  v_needs_replacement int;
  v_ignored int;
  v_project_file_count int;
  v_registered_file_count int;
  v_missing_registered_file_count int;
  v_next_status public.estimate_job_status;
  v_blocked_reason text;
  v_previous_status text;
  v_summary text;
begin
  if not public.is_staff() then
    raise exception 'Not authorized';
  end if;

  select id, project_id, status
    into v_job
    from public.estimate_jobs
   where id = p_estimate_job_id
     and project_id = p_project_id
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'job_not_found');
  end if;

  perform 1
    from public.projects
   where id = p_project_id
     and deleted_at is null
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'project_not_found');
  end if;

  if v_job.status in ('takeoff_ready', 'takeoff_in_progress', 'pricing_review_pending', 'qa_pending', 'ready_for_owner_approval', 'closed', 'canceled') then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_job.status::text);
  end if;

  perform 1
    from public.estimate_job_documents
   where estimate_job_id = p_estimate_job_id
   for update;

  select
    count(*)::int,
    count(*) filter (where review_status = 'accepted')::int,
    count(*) filter (where review_status = 'pending')::int,
    count(*) filter (where review_status = 'needs_replacement')::int,
    count(*) filter (where review_status = 'ignored')::int
  into v_total, v_accepted, v_pending, v_needs_replacement, v_ignored
  from public.estimate_job_documents
  where estimate_job_id = p_estimate_job_id;

  select count(*)::int
    into v_project_file_count
    from public.project_files
   where project_id = p_project_id
     and deleted_at is null;

  select count(distinct project_file_id)::int
    into v_registered_file_count
    from public.estimate_job_documents
   where estimate_job_id = p_estimate_job_id
     and project_file_id is not null;

  select count(*)::int
    into v_missing_registered_file_count
    from public.project_files pf
   where pf.project_id = p_project_id
     and pf.deleted_at is null
     and not exists (
       select 1
         from public.estimate_job_documents ejd
        where ejd.estimate_job_id = p_estimate_job_id
          and ejd.project_file_id = pf.id
     );

  v_counts := jsonb_build_object(
    'total', v_total,
    'accepted', v_accepted,
    'pending', v_pending,
    'needs_replacement', v_needs_replacement,
    'ignored', v_ignored,
    'project_files', v_project_file_count,
    'registered_project_files', v_registered_file_count,
    'missing_registered_project_files', v_missing_registered_file_count
  );

  if v_total = 0 then
    return jsonb_build_object('ok', false, 'reason', 'no_documents', 'counts', v_counts);
  end if;

  if v_missing_registered_file_count > 0 then
    return jsonb_build_object('ok', false, 'reason', 'document_register_stale', 'counts', v_counts);
  end if;

  if v_pending > 0 then
    return jsonb_build_object('ok', false, 'reason', 'pending_documents', 'counts', v_counts);
  end if;

  if v_accepted = 0 then
    return jsonb_build_object('ok', false, 'reason', 'no_accepted_documents', 'counts', v_counts);
  end if;

  if v_needs_replacement > 0 then
    v_next_status := 'intake_needs_info';
    v_blocked_reason := v_needs_replacement || ' document(s) need replacement before takeoff.';
    v_summary := 'Document review completed with ' || v_needs_replacement || ' replacement(s) needed; job returned to intake.';
  else
    v_next_status := 'takeoff_ready';
    v_blocked_reason := null;
    v_summary := 'Document review completed; job advanced to takeoff ready.';
  end if;

  v_previous_status := v_job.status::text;

  update public.estimate_jobs
     set status = v_next_status,
         blocked_reason = v_blocked_reason
   where id = p_estimate_job_id
     and project_id = p_project_id;

  insert into public.estimate_job_events (
    estimate_job_id,
    project_id,
    event_type,
    actor_id,
    actor_type,
    summary,
    payload
  ) values (
    p_estimate_job_id,
    p_project_id,
    'document_review_completed',
    auth.uid(),
    'staff',
    v_summary,
    v_counts || jsonb_build_object(
      'previous_status', v_previous_status,
      'next_status', v_next_status::text,
      'blocked_reason', v_blocked_reason
    )
  );

  return jsonb_build_object(
    'ok', true,
    'previous_status', v_previous_status,
    'next_status', v_next_status::text,
    'blocked_reason', v_blocked_reason,
    'counts', v_counts
  );
end;
$$;

grant execute on function public.complete_estimate_document_review(uuid, uuid) to authenticated;
