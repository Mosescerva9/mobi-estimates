-- =============================================================================
-- Mobi Estimates — Plan context intake packet RPC
--
-- Staff-only atomic save of a deterministically-built plan context packet
-- (src/lib/plan-context.ts) into estimate_jobs.automation_state. Does not
-- change job status; only persists the packet plus a generated_at marker
-- and appends an audit event. No pricing, quantities, takeoff, or
-- customer-facing deliverable is produced here.
-- =============================================================================

create or replace function public.save_plan_context_intake(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_plan_context jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job record;
  v_generated_at jsonb;
  v_source_gaps_count int;
begin
  if not public.is_staff() then
    raise exception 'Not authorized';
  end if;

  select id, project_id, status, automation_state
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

  if v_job.status in ('closed', 'canceled') then
    return jsonb_build_object('ok', false, 'reason', 'job_closed_or_canceled', 'current_status', v_job.status::text);
  end if;

  -- Plan-context intake is read/summarize-only and does not change status, so
  -- staff may regenerate it at any active workflow state. Closed/canceled jobs
  -- are blocked above to preserve completed/canceled history.

  v_generated_at := to_jsonb(now());

  update public.estimate_jobs
     set automation_state = coalesce(v_job.automation_state, '{}'::jsonb)
       || jsonb_build_object(
            'plan_context_v1', p_plan_context,
            'plan_context_generated_at', v_generated_at
          )
   where id = p_estimate_job_id
     and project_id = p_project_id;

  v_source_gaps_count := coalesce(jsonb_array_length(p_plan_context->'source_gaps'), 0);

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
    'plan_context_generated',
    auth.uid(),
    'staff',
    'Plan context intake packet generated.',
    jsonb_build_object(
      'document_summary', p_plan_context->'document_summary',
      'source_gaps', p_plan_context->'source_gaps',
      'generated_at', v_generated_at
    )
  );

  return jsonb_build_object(
    'ok', true,
    'generated_at', v_generated_at,
    'source_gaps_count', v_source_gaps_count
  );
end;
$$;

grant execute on function public.save_plan_context_intake(uuid, uuid, jsonb) to authenticated;
