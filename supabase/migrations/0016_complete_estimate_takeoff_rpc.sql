-- =============================================================================
-- Mobi Estimates — Complete takeoff handoff RPC
--
-- Atomically transitions an EstimateJob from takeoff_in_progress to
-- pricing_review_pending so the status change and audit event cannot diverge.
-- Staff-only; does not create pricing, a final estimate, or any
-- customer-facing deliverable — it only advances the internal job status.
-- =============================================================================

create or replace function public.complete_estimate_takeoff(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_takeoff_notes text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job record;
  v_previous_status text;
  v_notes text;
  v_total int;
  v_accepted int;
  v_counts jsonb;
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

  if v_job.status <> 'takeoff_in_progress' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_job.status::text);
  end if;

  select
    count(*)::int,
    count(*) filter (where review_status = 'accepted')::int
  into v_total, v_accepted
  from public.estimate_job_documents
  where estimate_job_id = p_estimate_job_id;

  v_counts := jsonb_build_object(
    'total', v_total,
    'accepted', v_accepted
  );

  v_notes := nullif(btrim(coalesce(p_takeoff_notes, '')), '');
  v_previous_status := v_job.status::text;

  update public.estimate_jobs
     set status = 'pricing_review_pending',
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
    'takeoff_completed',
    auth.uid(),
    'staff',
    'Takeoff completed; job advanced to pricing review.',
    v_counts || jsonb_build_object(
      'previous_status', v_previous_status,
      'next_status', 'pricing_review_pending',
      'takeoff_notes', v_notes
    )
  );

  return jsonb_build_object(
    'ok', true,
    'previous_status', v_previous_status,
    'next_status', 'pricing_review_pending',
    'takeoff_notes', v_notes,
    'counts', v_counts
  );
end;
$$;

grant execute on function public.complete_estimate_takeoff(uuid, uuid, text) to authenticated;
