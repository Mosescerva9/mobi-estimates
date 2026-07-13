-- =============================================================================
-- Mobi Estimates — P0 unsupported-scope/test-only evidence owner-ready guard
--
-- Internal QA completion may mark a job "ready_for_owner_approval". That is not
-- customer delivery, but it is the last internal status before future owner
-- approval. Keep it fail-closed for audit P0: unsupported scopes must abstain,
-- and test-only/synthetic quantities must never become real estimate evidence.
-- =============================================================================

create or replace function public.estimate_job_delivery_safety_blocker(
  p_automation_state jsonb
)
returns text
language plpgsql
immutable
set search_path = public
as $$
declare
  v_state jsonb := coalesce(p_automation_state, '{}'::jsonb);
  v_scope jsonb := coalesce(p_automation_state->'scope_classification', '{}'::jsonb);
  v_evidence jsonb := coalesce(p_automation_state->'evidence_profile', '{}'::jsonb);
begin
  -- Several early automation packets used different key names while the P0
  -- registry was being introduced. Treat any explicit unsupported/abstain marker
  -- as blocking owner-ready status until a future canonical scope model replaces
  -- this compatibility guard.
  if lower(btrim(coalesce(v_scope->>'supported', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'supported_scope', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'supported_scope', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'status', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'scope_status', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'scope_status', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'classification', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'scope_classification', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention') then
    return 'unsupported_scope_locked';
  end if;

  -- Block explicit test-only/synthetic evidence counters and booleans. This is a
  -- conservative compatibility guard over automation_state until first-class
  -- evidence tables exist. Check every known marker independently so a safe
  -- nested marker cannot mask an unsafe root-level compatibility marker.
  if coalesce(nullif(v_evidence->>'test_only_quantity_count', ''), '0')::int <> 0
     or coalesce(nullif(v_state->>'test_only_quantity_count', ''), '0')::int <> 0
     or coalesce(nullif(v_evidence->>'testOnlyQuantityCount', ''), '0')::int <> 0
     or coalesce(nullif(v_state->>'testOnlyQuantityCount', ''), '0')::int <> 0
     or lower(btrim(coalesce(v_evidence->>'contains_test_only_quantities', ''))) = 'true'
     or lower(btrim(coalesce(v_state->>'contains_test_only_quantities', ''))) = 'true'
     or lower(btrim(coalesce(v_evidence->>'containsTestOnlyQuantities', ''))) = 'true'
     or lower(btrim(coalesce(v_state->>'containsTestOnlyQuantities', ''))) = 'true'
     or lower(btrim(coalesce(v_evidence->>'evidence_type', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     or lower(btrim(coalesce(v_state->>'evidence_type', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     or lower(btrim(coalesce(v_evidence->>'source', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     or lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     or lower(btrim(coalesce(v_state->>'evidence_source', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     or lower(btrim(coalesce(v_evidence->>'evidence_type', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_state->>'evidence_type', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_evidence->>'source', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_state->>'evidence_source', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_evidence->>'evidence_type', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_state->>'evidence_type', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_evidence->>'source', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_state->>'evidence_source', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_evidence->>'evidence_type', ''))) like '%fixture%'
     or lower(btrim(coalesce(v_state->>'evidence_type', ''))) like '%fixture%'
     or lower(btrim(coalesce(v_evidence->>'source', ''))) like '%fixture%'
     or lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) like '%fixture%'
     or lower(btrim(coalesce(v_state->>'evidence_source', ''))) like '%fixture%' then
    return 'test_only_evidence_locked';
  end if;

  return null;
exception
  when invalid_text_representation then
    -- Malformed counters are not proof of safe evidence. Fail closed.
    return 'test_only_evidence_locked';
end;
$$;

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
  v_safety_blocker text;
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
    return jsonb_build_object('ok', false, 'reason', 'stale_job_form', 'current_status', v_job.status::text);
  end if;

  v_safety_blocker := public.estimate_job_delivery_safety_blocker(v_job.automation_state);
  if v_safety_blocker is not null then
    update public.estimate_jobs
       set status = 'blocked',
           blocked_reason = case v_safety_blocker
             when 'unsupported_scope_locked' then 'Unsupported scope abstention: this job cannot advance to internal owner-ready status until supported scope evidence is recorded.'
             else 'Test-only evidence blocker: synthetic/test-only quantities cannot advance to internal owner-ready status.'
           end
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
      'owner_ready_safety_blocked',
      auth.uid(),
      'staff',
      'QA completion blocked by P0 supported-scope/test-only evidence guard.',
      jsonb_build_object(
        'previous_status', v_job.status::text,
        'next_status', 'blocked',
        'reason', v_safety_blocker
      )
    );

    return jsonb_build_object('ok', false, 'reason', v_safety_blocker, 'current_status', 'blocked');
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

create or replace function public.change_estimate_job_status(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_status public.estimate_job_status,
  p_blocked_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job record;
  v_blocked_reason text;
  v_safety_blocker text;
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

  if p_status = 'ready_for_owner_approval' then
    v_safety_blocker := public.estimate_job_delivery_safety_blocker(v_job.automation_state);
    if v_safety_blocker is not null then
      update public.estimate_jobs
         set status = 'blocked',
             blocked_reason = case v_safety_blocker
               when 'unsupported_scope_locked' then 'Unsupported scope abstention: this job cannot advance to internal owner-ready status until supported scope evidence is recorded.'
               else 'Test-only evidence blocker: synthetic/test-only quantities cannot advance to internal owner-ready status.'
             end
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
        'owner_ready_safety_blocked',
        auth.uid(),
        'staff',
        'Manual owner-ready status change blocked by P0 supported-scope/test-only evidence guard.',
        jsonb_build_object(
          'previous_status', v_job.status::text,
          'requested_status', p_status::text,
          'next_status', 'blocked',
          'reason', v_safety_blocker
        )
      );

      return jsonb_build_object('ok', false, 'reason', v_safety_blocker, 'current_status', 'blocked');
    end if;
  end if;

  v_blocked_reason := case when p_status = 'blocked' then nullif(trim(p_blocked_reason), '') else null end;

  update public.estimate_jobs
     set status = p_status,
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
    'status_changed',
    auth.uid(),
    'staff',
    'Estimate job status changed to ' || p_status::text || '.',
    jsonb_build_object(
      'previous_status', v_job.status::text,
      'status', p_status::text,
      'blocked_reason', v_blocked_reason
    )
  );

  return jsonb_build_object(
    'ok', true,
    'previous_status', v_job.status::text,
    'status', p_status::text,
    'blocked_reason', v_blocked_reason
  );
end;
$$;

create or replace function public.prevent_unsafe_owner_ready_estimate_job_write()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_safety_blocker text;
begin
  if new.status = 'ready_for_owner_approval' then
    v_safety_blocker := public.estimate_job_delivery_safety_blocker(new.automation_state);
    if v_safety_blocker is not null then
      raise exception 'unsafe_owner_ready_status: %', v_safety_blocker using errcode = 'P0001';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists trg_prevent_unsafe_owner_ready_estimate_job_write on public.estimate_jobs;
create trigger trg_prevent_unsafe_owner_ready_estimate_job_write
  before insert or update of status, automation_state on public.estimate_jobs
  for each row execute function public.prevent_unsafe_owner_ready_estimate_job_write();

grant execute on function public.estimate_job_delivery_safety_blocker(jsonb) to authenticated;
grant execute on function public.complete_qa_review(uuid, uuid, text, timestamptz) to authenticated;
grant execute on function public.change_estimate_job_status(uuid, uuid, public.estimate_job_status, text) to authenticated;
