-- =============================================================================
-- Mobi Estimates — Intro-offer acceptance/rejection atomicity + EstimateJob gate
--
-- Prior behavior (bug): the free-offer project submission path provisioned an
-- EstimateJob immediately, before staff ever reviewed the intro_offer_claims
-- row created alongside it. An unreviewed (or later-rejected) free request
-- could enter internal processing. Staff accept/reject also only flipped the
-- claim status — it never provisioned the job on acceptance, and rejection
-- never canceled/soft-deleted the project.
--
-- This migration:
--   1) Replaces decide_intro_offer_claim so that:
--        accept: requested -> accepted AND provisions the EstimateJob, in one
--                transaction. Idempotent — repeating an already-accepted/
--                consumed decision just ensures the job exists.
--        reject: requested -> rejected AND cancels + soft-deletes the linked
--                project AND appends an audit timeline event, in one
--                transaction. Idempotent — repeating an already-rejected +
--                already-deleted decision is a safe no-op success. Never
--                hard-deletes the project.
--   2) Adds a trigger-level guard on estimate_jobs so NO EstimateJob can be
--      inserted, nor have its status advanced, for a project whose linked
--      intro_offer_claims row is not 'accepted'/'consumed' — including
--      pre-existing requested/rejected/released free projects, and
--      regardless of RLS/service-role bypass (triggers fire unconditionally).
--      Paid/non-intro projects (no claim row) are unaffected. The guard does
--      not block decide_intro_offer_claim itself: acceptance flips the claim
--      to 'accepted' before inserting the job, in the same transaction, so
--      the trigger's own read sees the update.
-- =============================================================================

create or replace function public.decide_intro_offer_claim(
  p_project uuid,
  p_decision text,
  p_reason_class text default null,
  p_internal_note text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_claim record;
  v_project record;
  v_note text;
  v_job_id uuid;
  v_intake_summary jsonb;
  v_job_created boolean := false;
begin
  if not public.is_staff() then
    raise exception 'Not authorized';
  end if;

  if p_decision not in ('accept', 'reject') then
    return jsonb_build_object('ok', false, 'reason', 'invalid_decision');
  end if;

  select c.id, c.status
    into v_claim
    from public.intro_offer_claims c
   where c.project_id = p_project
   order by c.requested_at desc
   for update
   limit 1;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'claim_not_found');
  end if;

  select p.id, p.company_id, p.status, p.deleted_at, p.bid_due_at, p.requested_completion_at, p.created_by
    into v_project
    from public.projects p
   where p.id = p_project
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'project_not_found');
  end if;

  v_note := nullif(btrim(coalesce(p_internal_note, '')), '');

  -- -------------------------------------------------------------------------
  -- Accept: requested -> accepted, then provision the EstimateJob atomically.
  -- -------------------------------------------------------------------------
  if p_decision = 'accept' then
    if v_claim.status in ('accepted', 'consumed') then
      -- Idempotent repeat: the decision already landed. Only ensure the job
      -- exists (covers a retry after a partial prior application) — never
      -- re-decide, re-note, or duplicate the job_created event.
      select id into v_job_id from public.estimate_jobs where project_id = p_project;
      if v_job_id is null and v_project.deleted_at is null then
        v_intake_summary := jsonb_build_object('source', 'intro_offer_accepted');
        insert into public.estimate_jobs (
          project_id, company_id, bid_due_at, target_delivery_at, created_by, intake_summary
        ) values (
          p_project, v_project.company_id, v_project.bid_due_at, v_project.requested_completion_at,
          v_project.created_by, v_intake_summary
        )
        on conflict (project_id) do nothing
        returning id into v_job_id;

        if v_job_id is not null then
          insert into public.estimate_job_events (
            estimate_job_id, project_id, event_type, actor_id, actor_type, summary, payload
          ) values (
            v_job_id, p_project, 'job_created', auth.uid(), 'staff',
            'Internal estimate job created after free-offer acceptance.', v_intake_summary
          );
        else
          select id into v_job_id from public.estimate_jobs where project_id = p_project;
        end if;
      end if;

      return jsonb_build_object(
        'ok', true, 'status', v_claim.status, 'already_decided', true, 'estimate_job_id', v_job_id
      );
    end if;

    if v_claim.status <> 'requested' then
      return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_claim.status);
    end if;

    if v_project.deleted_at is not null then
      return jsonb_build_object('ok', false, 'reason', 'project_not_found');
    end if;

    -- Flip the claim to accepted FIRST: the estimate_jobs insert guard trigger
    -- (below) reads the claim status for this project within the same
    -- transaction, so it must already see 'accepted' before the job insert.
    update public.intro_offer_claims
       set status = 'accepted',
           rejection_reason_class = null,
           internal_note = v_note,
           decided_at = now(),
           decided_by = auth.uid()
     where id = v_claim.id;

    v_intake_summary := jsonb_build_object('source', 'intro_offer_accepted');
    insert into public.estimate_jobs (
      project_id, company_id, bid_due_at, target_delivery_at, created_by, intake_summary
    ) values (
      p_project, v_project.company_id, v_project.bid_due_at, v_project.requested_completion_at,
      v_project.created_by, v_intake_summary
    )
    on conflict (project_id) do nothing
    returning id into v_job_id;

    if v_job_id is null then
      select id into v_job_id from public.estimate_jobs where project_id = p_project;
    else
      v_job_created := true;
    end if;

    if v_job_created then
      insert into public.estimate_job_events (
        estimate_job_id, project_id, event_type, actor_id, actor_type, summary, payload
      ) values (
        v_job_id, p_project, 'job_created', auth.uid(), 'staff',
        'Internal estimate job created after free-offer acceptance.', v_intake_summary
      );
    end if;

    return jsonb_build_object('ok', true, 'status', 'accepted', 'estimate_job_id', v_job_id);
  end if;

  -- -------------------------------------------------------------------------
  -- Reject: requested -> rejected, then cancel + soft-delete the project and
  -- append an audit timeline event, atomically. Never hard-deletes.
  -- -------------------------------------------------------------------------
  if v_claim.status = 'rejected' and v_project.deleted_at is not null then
    return jsonb_build_object('ok', true, 'status', 'already_rejected');
  end if;

  if v_claim.status <> 'requested' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_status', 'current_status', v_claim.status);
  end if;

  if p_reason_class is null or p_reason_class not in (
    'unsupported_scope', 'incomplete_documents', 'complexity_out_of_range', 'duplicate_request', 'other'
  ) then
    return jsonb_build_object('ok', false, 'reason', 'invalid_reason_class');
  end if;

  update public.intro_offer_claims
     set status = 'rejected',
         rejection_reason_class = p_reason_class,
         internal_note = v_note,
         decided_at = now(),
         decided_by = auth.uid()
   where id = v_claim.id;

  update public.projects
     set status = 'canceled', deleted_at = now()
   where id = p_project
     and deleted_at is null;
  if not found then
    raise exception 'intro offer rejection project cancellation did not update a row';
  end if;

  insert into public.project_status_history (
    project_id, from_status, to_status, changed_by, internal_note, client_note
  ) values (
    p_project,
    v_project.status,
    'canceled',
    auth.uid(),
    'Free-offer request not accepted (' || p_reason_class || ').',
    'This request was not accepted for the free qualifying estimate.'
  );

  return jsonb_build_object('ok', true, 'status', 'rejected', 'reason_class', p_reason_class);
end;
$$;

revoke all on function public.decide_intro_offer_claim(uuid, text, text, text) from public;
grant execute on function public.decide_intro_offer_claim(uuid, text, text, text) to authenticated;

-- ---------------------------------------------------------------------------
-- Trigger-level guard: no EstimateJob may be inserted, nor have its status
-- advanced, for a project whose linked intro_offer_claims row is not
-- 'accepted'/'consumed'. A project with no claim row at all (paid/non-intro)
-- is unaffected — the check only fires when a claim exists.
--
-- This is necessary (not just RLS) because internal EstimateJob writes go
-- through the service role, which bypasses RLS entirely. A BEFORE trigger
-- fires regardless of role, so it is the only reliable enforcement point.
-- ---------------------------------------------------------------------------
create or replace function public.prevent_intro_offer_estimate_job_before_accepted()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_claim_status text;
begin
  select status into v_claim_status
    from public.intro_offer_claims
   where project_id = new.project_id
   order by requested_at desc
   limit 1;

  if v_claim_status is not null and v_claim_status not in ('accepted', 'consumed') then
    raise exception 'intro_offer_not_accepted: estimate job blocked until the linked free-offer claim is accepted (current status: %)', v_claim_status
      using errcode = 'P0001';
  end if;

  return new;
end;
$$;

revoke all on function public.prevent_intro_offer_estimate_job_before_accepted() from public;

drop trigger if exists trg_prevent_intro_offer_estimate_job_before_accepted on public.estimate_jobs;
create trigger trg_prevent_intro_offer_estimate_job_before_accepted
  before insert or update of status on public.estimate_jobs
  for each row execute function public.prevent_intro_offer_estimate_job_before_accepted();
