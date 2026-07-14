-- =============================================================================
-- Mobi Estimates — P0 unsupported-scope/test-only evidence owner-ready guard
--
-- Internal QA completion may mark a job "ready_for_owner_approval". That is not
-- customer delivery, but it is the last internal status before future owner
-- approval. Keep it fail-closed for audit P0: unsupported scopes must abstain,
-- and test-only/synthetic quantities must never become real estimate evidence.
-- =============================================================================

create or replace function public.estimate_job_json_delivery_marker_blocker(
  p_value jsonb,
  p_depth integer default 0
)
returns text
language plpgsql
immutable
set search_path = public
as $$
declare
  v_type text := coalesce(jsonb_typeof(p_value), 'null');
  v_key text;
  v_child jsonb;
  v_key_norm text;
  v_key_compact text;
  v_child_text text;
  v_child_norm text;
  v_child_compact text;
  v_nested_blocker text;
  v_count bigint;
begin
  -- Tampered automation_state can hide unsafe markers under arbitrary metadata.
  -- Recursively fail closed for nested unsupported-scope/test-only markers while
  -- preserving explicit false/zero/empty markers as safe compatibility values.
  if p_depth > 12 then
    return 'test_only_evidence_locked';
  end if;

  if v_type = 'string' then
    v_child_norm := regexp_replace(lower(regexp_replace(btrim(p_value #>> '{}'), '([a-z0-9])([A-Z])', '\1_\2', 'g')), '[^a-z0-9]+', '_', 'g');
    v_child_compact := replace(v_child_norm, '_', '');
    if v_child_norm like '%test_only%' or v_child_compact like '%testonly%' or v_child_norm like '%synthetic%' or v_child_norm like '%fixture%' then
      return 'test_only_evidence_locked';
    end if;
    if v_child_compact in ('unsupported', 'unsupportedscope', 'notsupported', 'abstain', 'abstained', 'abstention', 'outofscope', 'outofsupportedscope')
       or v_child_norm like '%scope_not_supported%'
       or v_child_compact like '%scopenotsupported%'
       or v_child_norm like '%unsupported_scope%'
       or v_child_compact like '%unsupportedscope%'
       or v_child_norm like '%should_abstain%' then
      return 'unsupported_scope_locked';
    end if;
    if v_child_compact like '%supportedscopefalse%'
       or v_child_compact like '%supportedscope0%'
       or v_child_compact like '%notsupportedtrue%'
       or v_child_compact like '%containsunsupportedscope%'
       or v_child_compact like '%shouldabstaintrue%' then
      return 'unsupported_scope_locked';
    end if;
    return null;
  end if;

  if v_type = 'array' then
    for v_child in select value from jsonb_array_elements(p_value) loop
      v_nested_blocker := public.estimate_job_json_delivery_marker_blocker(v_child, p_depth + 1);
      if v_nested_blocker is not null then
        return v_nested_blocker;
      end if;
    end loop;
    return null;
  end if;

  if v_type <> 'object' then
    return null;
  end if;

  for v_key, v_child in select key, value from jsonb_each(p_value) loop
    v_key_norm := regexp_replace(lower(regexp_replace(v_key, '([a-z0-9])([A-Z])', '\1_\2', 'g')), '[^a-z0-9]+', '_', 'g');
    v_key_compact := replace(v_key_norm, '_', '');
    v_child_text := btrim(coalesce(v_child #>> '{}', ''));
    v_child_norm := regexp_replace(lower(v_child_text), '[^a-z0-9]+', '_', 'g');
    v_child_compact := replace(v_child_norm, '_', '');

    if (v_key_norm like '%test_only%' or v_key_compact like '%testonly%' or v_key_norm like '%synthetic%' or v_key_norm like '%fixture%')
       and (v_key_norm like '%quantity%' or v_key_norm like '%evidence%' or v_key_norm like '%source%' or v_key_norm like '%metadata%') then
      if v_key_norm like '%count%' then
        begin
          v_count := v_child_text::bigint;
        exception when others then
          return 'test_only_evidence_locked';
        end;
        if v_count <> 0 then
          return 'test_only_evidence_locked';
        end if;
      elsif v_child_text = '' or v_child_norm in ('false', '0', 'no', 'n', 'none', 'null') then
        null;
      else
        return 'test_only_evidence_locked';
      end if;
    end if;

    if v_key_compact in ('unsupportedscopeitemcount', 'unsupportedscopeitemscount', 'unsupportedscopescount', 'unsupportedtradecount', 'unsupportedtradescount', 'abstentioncount') then
      begin
        v_count := v_child_text::bigint;
      exception when others then
        return 'unsupported_scope_locked';
      end;
      if v_count <> 0 then
        return 'unsupported_scope_locked';
      end if;
    elsif v_key_compact in ('unsupportedscopeitems', 'unsupportedscopes', 'unsupportedcustomerdeliveryscopeitems', 'unsupportedtrades', 'abstainedscopes') then
      if (jsonb_typeof(v_child) = 'array' and jsonb_array_length(v_child) <> 0)
         or (jsonb_typeof(v_child) = 'object' and jsonb_object_length(v_child) <> 0)
         or (jsonb_typeof(v_child) = 'string' and v_child_compact not in ('', 'false', '0', 'no', 'n', 'none', 'null')) then
        return 'unsupported_scope_locked';
      end if;
    elsif v_key_compact in ('unsupportedscope', 'unsupported', 'notsupported', 'containsunsupportedscope', 'hasunsupportedscope', 'shouldabstain', 'abstain', 'abstention') then
      if jsonb_typeof(v_child) in ('object', 'array') then
        return 'unsupported_scope_locked';
      elsif v_child_compact not in ('', 'false', '0', 'no', 'n', 'none', 'null', 'supported') then
        return 'unsupported_scope_locked';
      end if;
    elsif v_key_compact in ('supportedscope', 'supportedcustomerdeliveryscope', 'supporteddeliveryscope', 'customerdeliveryscopesupported') then
      if v_child_compact in ('false', '0', 'no', 'n', 'unsupported', 'unsupportedscope', 'abstain', 'abstention', 'notsupported') then
        return 'unsupported_scope_locked';
      end if;
    elsif v_key_compact in ('scopestatus', 'scopeclassification', 'classification', 'status', 'projectstatus', 'deliverystatus', 'releasescopestatus') then
      if v_child_compact in ('unsupported', 'unsupportedscope', 'notsupported', 'abstain', 'abstained', 'abstention', 'outofscope', 'outofsupportedscope') then
        return 'unsupported_scope_locked';
      end if;
    end if;

    v_nested_blocker := public.estimate_job_json_delivery_marker_blocker(v_child, p_depth + 1);
    if v_nested_blocker is not null then
      return v_nested_blocker;
    end if;
  end loop;

  return null;
end;
$$;

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
  v_scope_alias jsonb := coalesce(p_automation_state->'scope', '{}'::jsonb);
  v_evidence jsonb := coalesce(p_automation_state->'evidence_profile', '{}'::jsonb);
  v_unsupported_customer_delivery_scope jsonb := coalesce(p_automation_state->'unsupportedCustomerDeliveryScope', p_automation_state->'unsupported_customer_delivery_scope', '{}'::jsonb);
  v_recursive_blocker text;
begin
  v_recursive_blocker := public.estimate_job_json_delivery_marker_blocker(v_state);
  if v_recursive_blocker is not null then
    return v_recursive_blocker;
  end if;

  -- Several early automation packets used different key names while the P0
  -- registry was being introduced. Treat any explicit unsupported/abstain marker
  -- as blocking owner-ready status until a future canonical scope model replaces
  -- this compatibility guard.
  if lower(btrim(coalesce(v_scope->>'supported', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'supportedScope', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'supported', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'supported_scope', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'supportedScope', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'supported_scope', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'supportedScope', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'supported_scope', ''))) in ('false', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'status', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'status', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'scope_status', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'scope_status', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'scope_status', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'classification', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'classification', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'scope_classification', ''))) in ('unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'unsupported_scope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'unsupportedScope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'containsUnsupportedScope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_state->>'notSupported', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'unsupported_scope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'unsupportedScope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'containsUnsupportedScope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope->>'notSupported', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'unsupported_scope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'unsupportedScope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'containsUnsupportedScope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_scope_alias->>'notSupported', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or coalesce(nullif(v_state->>'unsupported_scope_item_count', ''), '0')::int <> 0
     or coalesce(nullif(v_state->>'unsupportedScopeItemsCount', ''), '0')::int <> 0
     or lower(btrim(coalesce(v_unsupported_customer_delivery_scope->>'unsupported_scope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_unsupported_customer_delivery_scope->>'unsupportedScope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_unsupported_customer_delivery_scope->>'containsUnsupportedScope', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or lower(btrim(coalesce(v_unsupported_customer_delivery_scope->>'notSupported', ''))) in ('true', '1', 'yes', 'unsupported', 'unsupported_scope', 'abstain', 'abstention')
     or (
       coalesce(jsonb_typeof(v_state->'unsupported_scope_items'), 'null') = 'array'
       and jsonb_array_length(v_state->'unsupported_scope_items') <> 0
     )
     or (
       coalesce(jsonb_typeof(v_state->'unsupported_scope_items'), 'null') = 'object'
       and jsonb_object_length(v_state->'unsupported_scope_items') <> 0
     )
     or (
       coalesce(jsonb_typeof(v_state->'unsupportedScopeItems'), 'null') = 'array'
       and jsonb_array_length(v_state->'unsupportedScopeItems') <> 0
     )
     or (
       coalesce(jsonb_typeof(v_state->'unsupportedScopeItems'), 'null') = 'object'
       and jsonb_object_length(v_state->'unsupportedScopeItems') <> 0
     )
     or coalesce(nullif(v_unsupported_customer_delivery_scope->>'unsupported_scope_item_count', ''), '0')::int <> 0
     or coalesce(nullif(v_unsupported_customer_delivery_scope->>'unsupportedScopeItemsCount', ''), '0')::int <> 0
     or (
       coalesce(jsonb_typeof(v_unsupported_customer_delivery_scope->'unsupported_scope_items'), 'null') = 'array'
       and jsonb_array_length(v_unsupported_customer_delivery_scope->'unsupported_scope_items') <> 0
     )
     or (
       coalesce(jsonb_typeof(v_unsupported_customer_delivery_scope->'unsupported_scope_items'), 'null') = 'object'
       and jsonb_object_length(v_unsupported_customer_delivery_scope->'unsupported_scope_items') <> 0
     )
     or (
       coalesce(jsonb_typeof(v_unsupported_customer_delivery_scope->'unsupportedScopeItems'), 'null') = 'array'
       and jsonb_array_length(v_unsupported_customer_delivery_scope->'unsupportedScopeItems') <> 0
     )
     or (
       coalesce(jsonb_typeof(v_unsupported_customer_delivery_scope->'unsupportedScopeItems'), 'null') = 'object'
       and jsonb_object_length(v_unsupported_customer_delivery_scope->'unsupportedScopeItems') <> 0
     ) then
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
     or lower(btrim(coalesce(v_state->>'source', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     or lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     or lower(btrim(coalesce(v_state->>'evidence_source', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     or (
       coalesce(jsonb_typeof(v_state->'evidence_profile'), 'null') <> 'object'
       and lower(btrim(coalesce(v_state->>'evidence_profile', ''))) in ('test_only', 'synthetic', 'synthetic_fixture')
     )
     or lower(btrim(coalesce(v_evidence->>'evidence_type', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_state->>'evidence_type', ''))) like '%test%only%'
     or (
       coalesce(jsonb_typeof(v_state->'evidence_profile'), 'null') <> 'object'
       and lower(btrim(coalesce(v_state->>'evidence_profile', ''))) like '%test%only%'
     )
     or lower(btrim(coalesce(v_evidence->>'source', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_state->>'source', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_state->>'evidence_source', ''))) like '%test%only%'
     or lower(btrim(coalesce(v_evidence->>'evidence_type', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_state->>'evidence_type', ''))) like '%synthetic%'
     or (
       coalesce(jsonb_typeof(v_state->'evidence_profile'), 'null') <> 'object'
       and lower(btrim(coalesce(v_state->>'evidence_profile', ''))) like '%synthetic%'
     )
     or lower(btrim(coalesce(v_evidence->>'source', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_state->>'source', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_state->>'evidence_source', ''))) like '%synthetic%'
     or lower(btrim(coalesce(v_evidence->>'evidence_type', ''))) like '%fixture%'
     or lower(btrim(coalesce(v_state->>'evidence_type', ''))) like '%fixture%'
     or (
       coalesce(jsonb_typeof(v_state->'evidence_profile'), 'null') <> 'object'
       and lower(btrim(coalesce(v_state->>'evidence_profile', ''))) like '%fixture%'
     )
     or lower(btrim(coalesce(v_evidence->>'source', ''))) like '%fixture%'
     or lower(btrim(coalesce(v_state->>'source', ''))) like '%fixture%'
     or lower(btrim(coalesce(v_evidence->>'evidence_source', ''))) like '%fixture%'
     or lower(btrim(coalesce(v_state->>'evidence_source', ''))) like '%fixture%' then
    return 'test_only_evidence_locked';
  end if;

  return null;
exception
  when invalid_text_representation or numeric_value_out_of_range then
    -- Malformed or out-of-range counters are not proof of safe evidence. Fail closed.
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
