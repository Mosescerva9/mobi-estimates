-- =============================================================================
-- Mobi Estimates — Engine multi-document packet: CAS link + manifest save
--
-- ONE staff-only, security-definer, compare-and-swap RPC that atomically:
--   1. locks the estimate job, then the project (established lock order), then
--      reads the exact accepted document register;
--   2. verifies the project's current engine link is null OR equal to the
--      resulting engine project id (never silently replacing an established
--      link — a conflicting existing id returns a conflict result);
--   3. STRICTLY validates the engine-authored packet manifest structurally and
--      against the EXACT accepted document snapshot (a manifest that adds, drops,
--      renames, re-paths, reorders, mis-hashes, mis-pages, or otherwise does not
--      reproduce the accepted registered set is rejected before any write);
--   4. persists the engine link (id + status + page count), the manifest into
--      estimate_jobs.automation_state under 'engine_packet_v1', and AT MOST ONE
--      event for a given (project, packet sha256) — idempotent under retry.
--
-- The manifest is provenance only. It changes no job status and produces no
-- pricing, quantities, takeoff, or customer-facing deliverable. All identity
-- checks use jsonb key existence + jsonb_typeof (not only ->> coercion), require
-- an object body and a schema version, and require lowercase 64-hex SHA-256.
-- =============================================================================

-- Replace the prior 4-arg signature (this migration is un-applied; revise in
-- place rather than adding a second migration). Drop first to change arity.
drop function if exists public.save_engine_packet_manifest(uuid, uuid, uuid, jsonb);

create or replace function public.save_engine_packet_manifest(
  p_project_id uuid,
  p_estimate_job_id uuid,
  p_engine_project_id uuid,
  p_engine_status text,
  p_engine_page_count integer,
  p_packet_manifest jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job record;
  v_project record;
  v_packet jsonb;
  v_sources jsonb;
  v_schema text;
  v_packet_sha text;
  v_source_count int;
  v_page_count int;
  v_generated_at jsonb;
  v_stats record;
  v_accepted_count int;
  v_match_count int;
begin
  if not public.is_staff() then
    raise exception 'Not authorized';
  end if;

  if p_engine_project_id is null then
    return jsonb_build_object('ok', false, 'reason', 'missing_engine_project_id');
  end if;

  -- ---- Established lock order: estimate_jobs, then projects ------------------
  select id, project_id, company_id, status, automation_state
    into v_job
    from public.estimate_jobs
   where id = p_estimate_job_id
     and project_id = p_project_id
   for update;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'job_not_found');
  end if;

  select id, company_id, engine_project_id
    into v_project
    from public.projects
   where id = p_project_id
     and deleted_at is null
   for update;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'project_not_found');
  end if;

  if v_job.status::text in ('closed', 'canceled') then
    return jsonb_build_object('ok', false, 'reason', 'job_closed_or_canceled',
                              'current_status', v_job.status::text);
  end if;

  if v_project.company_id is distinct from v_job.company_id then
    return jsonb_build_object('ok', false, 'reason', 'company_mismatch');
  end if;

  -- CAS: the engine link must be null or already equal to the resulting id.
  if v_project.engine_project_id is not null
     and v_project.engine_project_id is distinct from p_engine_project_id then
    return jsonb_build_object('ok', false, 'reason', 'engine_project_conflict',
                              'linked_engine_project_id', v_project.engine_project_id);
  end if;

  -- ---- Strict manifest structure -------------------------------------------
  if p_packet_manifest is null or jsonb_typeof(p_packet_manifest) is distinct from 'object' then
    return jsonb_build_object('ok', false, 'reason', 'manifest_not_object');
  end if;
  if not (p_packet_manifest ? 'schema_version')
     or jsonb_typeof(p_packet_manifest->'schema_version') is distinct from 'string' then
    return jsonb_build_object('ok', false, 'reason', 'missing_schema_version');
  end if;
  v_schema := p_packet_manifest->>'schema_version';
  if v_schema <> 'engine_packet_v1' then
    return jsonb_build_object('ok', false, 'reason', 'unsupported_schema_version',
                              'schema_version', v_schema);
  end if;

  if not (p_packet_manifest ? 'packet') or jsonb_typeof(p_packet_manifest->'packet') is distinct from 'object' then
    return jsonb_build_object('ok', false, 'reason', 'packet_not_object');
  end if;
  v_packet := p_packet_manifest->'packet';
  if not (v_packet ? 'sha256') or jsonb_typeof(v_packet->'sha256') is distinct from 'string'
     or (v_packet->>'sha256') !~ '^[0-9a-f]{64}$' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_packet_sha256');
  end if;
  -- NOTE ON NULL SEMANTICS: a missing jsonb key yields SQL NULL, and `NULL <>
  -- 'number'` is NULL, not TRUE -- an `if` over an all-NULL OR-chain does NOT
  -- fire. Validating with bare `<>` would therefore let a manifest that simply
  -- OMITS page_count/source_count slip past every downstream comparison (all of
  -- which would also be NULL) and be persisted. Every scalar check below is
  -- therefore key-existence + `is distinct from`, which is NULL-safe.
  if not (v_packet ? 'page_count') or jsonb_typeof(v_packet->'page_count') is distinct from 'number'
     or not (v_packet ? 'source_count') or jsonb_typeof(v_packet->'source_count') is distinct from 'number'
     or not (v_packet ? 'bytes') or jsonb_typeof(v_packet->'bytes') is distinct from 'number' then
    return jsonb_build_object('ok', false, 'reason', 'invalid_packet_scalar');
  end if;
  v_packet_sha := v_packet->>'sha256';
  v_page_count := (v_packet->>'page_count')::int;
  v_source_count := (v_packet->>'source_count')::int;
  if v_packet_sha is null or v_page_count is null or v_source_count is null
     or v_page_count <= 0 or v_source_count <= 0 then
    return jsonb_build_object('ok', false, 'reason', 'nonpositive_packet_counts');
  end if;

  -- Engine link must agree with the manifest's declared page count. A NULL
  -- p_engine_page_count is rejected outright rather than compared, so a caller
  -- cannot pair a null argument with a null manifest value to satisfy this.
  if p_engine_page_count is null then
    return jsonb_build_object('ok', false, 'reason', 'missing_engine_page_count');
  end if;
  if p_engine_page_count is distinct from v_page_count then
    return jsonb_build_object('ok', false, 'reason', 'engine_page_count_mismatch');
  end if;

  if not (p_packet_manifest ? 'sources') or jsonb_typeof(p_packet_manifest->'sources') is distinct from 'array' then
    return jsonb_build_object('ok', false, 'reason', 'sources_not_array');
  end if;
  v_sources := p_packet_manifest->'sources';
  if jsonb_array_length(v_sources) <> v_source_count then
    return jsonb_build_object('ok', false, 'reason', 'source_count_mismatch');
  end if;

  -- Per-source scalar types + lowercase hashes + required identity strings.
  -- Same NULL-safety rule as above: `is distinct from` (never bare `<>`) so an
  -- absent key is a rejection, not an unevaluated NULL. Numeric fields must also
  -- be whole numbers -- a fractional value would otherwise blow up the ::int
  -- casts further down instead of returning a clean validation reason.
  if exists (
    select 1 from jsonb_array_elements(v_sources) e
    where jsonb_typeof(e) is distinct from 'object'
       or jsonb_typeof(e->'order') is distinct from 'number'
       or jsonb_typeof(e->'source_bytes') is distinct from 'number'
       or jsonb_typeof(e->'source_page_count') is distinct from 'number'
       or jsonb_typeof(e->'combined_page_start') is distinct from 'number'
       or jsonb_typeof(e->'combined_page_end') is distinct from 'number'
       or jsonb_typeof(e->'project_file_id') is distinct from 'string'
       or jsonb_typeof(e->'storage_path') is distinct from 'string'
       or jsonb_typeof(e->'original_filename') is distinct from 'string'
       or jsonb_typeof(e->'source_sha256') is distinct from 'string'
       or coalesce(e->>'order', '') !~ '^[0-9]+$'
       or coalesce(e->>'source_bytes', '') !~ '^[0-9]+$'
       or coalesce(e->>'source_page_count', '') !~ '^[0-9]+$'
       or coalesce(e->>'combined_page_start', '') !~ '^[0-9]+$'
       or coalesce(e->>'combined_page_end', '') !~ '^[0-9]+$'
       or coalesce(e->>'source_sha256', '') !~ '^[0-9a-f]{64}$'
       or coalesce(e->>'original_filename', '') = ''
       or coalesce(e->>'project_file_id', '') = ''
       or coalesce(e->>'storage_path', '') = ''
  ) then
    return jsonb_build_object('ok', false, 'reason', 'invalid_source_scalar');
  end if;

  -- Aggregate structural checks: unique 0..n-1 orders, unique ids/paths, pages.
  select count(*) n,
         count(distinct (e->>'order')::int) dord,
         min((e->>'order')::int) mino,
         max((e->>'order')::int) maxo,
         count(distinct e->>'project_file_id') dpf,
         count(distinct e->>'storage_path') dsp,
         sum((e->>'source_page_count')::int) sump
    into v_stats
    from jsonb_array_elements(v_sources) e;
  if v_stats.n is distinct from v_source_count
     or v_stats.dord is distinct from v_source_count
     or v_stats.mino is distinct from 0
     or v_stats.maxo is distinct from v_source_count - 1
     or v_stats.dpf is distinct from v_source_count
     or v_stats.dsp is distinct from v_source_count then
    return jsonb_build_object('ok', false, 'reason', 'invalid_source_orders_or_duplicates');
  end if;
  if v_stats.sump is distinct from v_page_count then
    return jsonb_build_object('ok', false, 'reason', 'page_sum_mismatch');
  end if;

  -- Contiguous, gap-free page coverage starting at page 1.
  if exists (
    select 1 from (
      select (e->>'order')::int ord,
             (e->>'combined_page_start')::int cstart,
             (e->>'combined_page_end')::int cend,
             (e->>'source_page_count')::int spages,
             sum((e->>'source_page_count')::int)
               over (order by (e->>'order')::int
                     rows between unbounded preceding and 1 preceding) prior
        from jsonb_array_elements(v_sources) e
    ) x
    where cend - cstart + 1 <> spages
       or cstart <> coalesce(prior, 0) + 1
  ) then
    return jsonb_build_object('ok', false, 'reason', 'noncontiguous_pages');
  end if;

  -- ---- Exact accepted-document snapshot match ------------------------------
  -- The manifest's (project_file_id, storage_path, original_filename) set must
  -- equal the estimate job's ACCEPTED registered document set exactly. This
  -- rejects a stale accepted set, a wrong/renamed/re-pathed doc, and any doc
  -- the portal did not accept.
  select count(*) into v_accepted_count
    from public.estimate_job_documents
   where estimate_job_id = p_estimate_job_id
     and review_status = 'accepted';

  select count(*) into v_match_count
    from jsonb_array_elements(v_sources) e
    join public.estimate_job_documents d
      on d.estimate_job_id = p_estimate_job_id
     and d.review_status = 'accepted'
     and d.project_file_id::text = e->>'project_file_id'
     and d.storage_path = e->>'storage_path'
     and d.file_name = e->>'original_filename';

  if v_accepted_count is distinct from v_source_count
     or v_match_count is distinct from v_source_count then
    return jsonb_build_object('ok', false, 'reason', 'accepted_set_mismatch',
                              'accepted_count', v_accepted_count,
                              'manifest_source_count', v_source_count,
                              'matched', v_match_count);
  end if;

  -- ---- Persist link + manifest (atomic) ------------------------------------
  v_generated_at := to_jsonb(now());

  update public.projects
     set engine_project_id = p_engine_project_id,
         engine_status = p_engine_status,
         engine_page_count = p_engine_page_count,
         engine_synced_at = now()
   where id = p_project_id
     and (engine_project_id is null or engine_project_id = p_engine_project_id);
  if not found then
    -- Lost the CAS race to a conflicting link between the read and the write.
    return jsonb_build_object('ok', false, 'reason', 'engine_project_conflict');
  end if;

  update public.estimate_jobs
     set automation_state = coalesce(v_job.automation_state, '{}'::jsonb)
       || jsonb_build_object(
            'engine_packet_v1', jsonb_build_object(
              'project_id', p_project_id,
              'company_id', v_job.company_id,
              'engine_project_id', p_engine_project_id,
              'manifest', p_packet_manifest,
              'recorded_at', v_generated_at
            )
          )
   where id = p_estimate_job_id
     and project_id = p_project_id;

  -- Idempotent event: at most one for a given (project, packet sha256).
  if not exists (
    select 1 from public.estimate_job_events
     where estimate_job_id = p_estimate_job_id
       and project_id = p_project_id
       and event_type = 'engine_packet_assembled'
       and payload #>> '{packet,sha256}' = v_packet_sha
  ) then
    insert into public.estimate_job_events (
      estimate_job_id, project_id, event_type, actor_id, actor_type, summary, payload
    ) values (
      p_estimate_job_id, p_project_id, 'engine_packet_assembled', auth.uid(), 'staff',
      'Engine multi-document packet manifest recorded.',
      jsonb_build_object(
        'engine_project_id', p_engine_project_id,
        'packet', v_packet,
        'source_count', v_source_count,
        'recorded_at', v_generated_at
      )
    );
  end if;

  return jsonb_build_object(
    'ok', true,
    'engine_project_id', p_engine_project_id,
    'recorded_at', v_generated_at,
    'source_count', v_source_count,
    'packet_sha256', v_packet_sha
  );
end;
$$;

-- Least privilege on a SECURITY DEFINER function: Postgres grants EXECUTE to
-- PUBLIC by default, which would leave this definer-rights function reachable by
-- anon (and every future role). Strip that default first, then grant EXECUTE to
-- `authenticated` only -- the is_staff() gate inside is the authorization check,
-- not the entry gate. Mirrors 0003_harden_functions.sql.
revoke execute on function
  public.save_engine_packet_manifest(uuid, uuid, uuid, text, integer, jsonb)
  from public;
revoke execute on function
  public.save_engine_packet_manifest(uuid, uuid, uuid, text, integer, jsonb)
  from anon;
grant execute on function
  public.save_engine_packet_manifest(uuid, uuid, uuid, text, integer, jsonb)
  to authenticated;
