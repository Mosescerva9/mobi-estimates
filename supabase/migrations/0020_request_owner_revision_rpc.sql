-- =============================================================================
-- Mobi Estimates — Request internal owner revision RPC
--
-- Atomically transitions an EstimateJob from ready_for_owner_approval back to
-- either qa_pending or pricing_review_pending so the status change and audit
-- event cannot diverge. Staff-only; this is an internal revision-request loop
-- only — it does not approve, send, publish, or deliver a final estimate to
-- the customer, and does not create line items, a final estimate, an approval
-- package, or any customer-facing deliverable.
-- =============================================================================

create or replace function public.request_owner_revision(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_revision_target text,
  p_revision_notes text default null
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
  v_summary text;
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

  if v_job.status <> 'ready_for_owner_approval' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_job.status::text);
  end if;

  if p_revision_target is null or p_revision_target not in ('qa_pending', 'pricing_review_pending') then
    return jsonb_build_object('ok', false, 'reason', 'invalid_revision_target');
  end if;

  v_notes := nullif(btrim(coalesce(p_revision_notes, '')), '');
  v_previous_status := v_job.status::text;

  v_summary := case p_revision_target
    when 'qa_pending' then 'Internal owner requested revisions; job returned to QA.'
    else 'Internal owner requested revisions; job returned to pricing review.'
  end;

  update public.estimate_jobs
     set status = p_revision_target::public.estimate_job_status,
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
    'owner_revision_requested',
    auth.uid(),
    'staff',
    v_summary,
    jsonb_build_object(
      'previous_status', v_previous_status,
      'next_status', p_revision_target,
      'revision_target', p_revision_target,
      'revision_notes', v_notes
    )
  );

  return jsonb_build_object(
    'ok', true,
    'previous_status', v_previous_status,
    'next_status', p_revision_target,
    'revision_notes', v_notes
  );
end;
$$;

grant execute on function public.request_owner_revision(uuid, uuid, text, text) to authenticated;


-- Replace downstream repeated-status handoff RPCs with freshness-token guards.
-- Once owner revisions can return a job to pricing_review_pending or qa_pending,
-- exact status alone is no longer enough: a stale pre-revision form could skip
-- the requested correction. The admin UI passes the job.updated_at value rendered
-- with the form; stale or missing tokens are rejected.

drop function if exists public.complete_pricing_review(uuid, uuid, text);

create or replace function public.complete_pricing_review(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_pricing_notes text default null,
  p_expected_updated_at timestamptz default null
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

  select id, project_id, status, automation_state, updated_at
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

  if v_job.status <> 'pricing_review_pending' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_job.status::text);
  end if;

  if p_expected_updated_at is null or v_job.updated_at <> p_expected_updated_at then
    return jsonb_build_object(
      'ok', false,
      'reason', 'stale_job_form',
      'current_status', v_job.status::text,
      'current_updated_at', v_job.updated_at
    );
  end if;

  v_notes := nullif(btrim(coalesce(p_pricing_notes, '')), '');
  v_previous_status := v_job.status::text;

  v_plan_context := v_job.automation_state->'plan_context_v1';
  if v_plan_context is not null then
    v_plan_context_summary := jsonb_build_object(
      'document_summary', v_plan_context->'document_summary',
      'source_gaps', v_plan_context->'source_gaps'
    );
  end if;

  update public.estimate_jobs
     set status = 'qa_pending',
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
    'pricing_review_completed',
    auth.uid(),
    'staff',
    'Pricing review completed; job advanced to QA.',
    jsonb_build_object(
      'previous_status', v_previous_status,
      'next_status', 'qa_pending',
      'pricing_notes', v_notes,
      'plan_context', v_plan_context_summary
    )
  );

  return jsonb_build_object(
    'ok', true,
    'previous_status', v_previous_status,
    'next_status', 'qa_pending',
    'pricing_notes', v_notes
  );
end;
$$;

grant execute on function public.complete_pricing_review(uuid, uuid, text, timestamptz) to authenticated;

drop function if exists public.complete_qa_review(uuid, uuid, text);

create or replace function public.complete_qa_review(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_qa_notes text default null,
  p_expected_updated_at timestamptz default null
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

  select id, project_id, status, automation_state, updated_at
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

  if p_expected_updated_at is null or v_job.updated_at <> p_expected_updated_at then
    return jsonb_build_object(
      'ok', false,
      'reason', 'stale_job_form',
      'current_status', v_job.status::text,
      'current_updated_at', v_job.updated_at
    );
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

grant execute on function public.complete_qa_review(uuid, uuid, text, timestamptz) to authenticated;
