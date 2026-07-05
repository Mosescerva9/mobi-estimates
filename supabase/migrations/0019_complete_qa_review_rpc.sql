-- =============================================================================
-- Mobi Estimates — Complete QA review handoff RPC
--
-- Atomically transitions an EstimateJob from qa_pending to
-- ready_for_owner_approval so the status change and audit event cannot
-- diverge. Staff-only; marks the job ready for internal owner (Moses) review
-- only — it does not send, publish, or deliver a final estimate to the
-- customer, and does not create line items, a final estimate, an approval
-- package, or any customer-facing deliverable.
-- =============================================================================

create or replace function public.complete_qa_review(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_qa_notes text default null
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
  v_plan_context jsonb;
  v_plan_context_summary jsonb;
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

  if v_job.status <> 'qa_pending' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_job.status::text);
  end if;

  v_notes := nullif(btrim(coalesce(p_qa_notes, '')), '');
  v_previous_status := v_job.status::text;

  v_plan_context := v_job.automation_state->'plan_context_v1';
  if v_plan_context is not null then
    v_plan_context_summary := jsonb_build_object(
      'document_summary', v_plan_context->'document_summary',
      'source_gaps', v_plan_context->'source_gaps'
    );
  end if;

  update public.estimate_jobs
     set status = 'ready_for_owner_approval',
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
    'qa_review_completed',
    auth.uid(),
    'staff',
    'QA review completed; job marked ready for internal owner approval.',
    jsonb_build_object(
      'previous_status', v_previous_status,
      'next_status', 'ready_for_owner_approval',
      'qa_notes', v_notes,
      'plan_context', v_plan_context_summary
    )
  );

  return jsonb_build_object(
    'ok', true,
    'previous_status', v_previous_status,
    'next_status', 'ready_for_owner_approval',
    'qa_notes', v_notes
  );
end;
$$;

grant execute on function public.complete_qa_review(uuid, uuid, text) to authenticated;
