-- =============================================================================
-- Mobi Estimates — canonical takeoff evidence: provider fields + provenance
--
-- Forward migration over the already-applied `0024_canonical_takeoff_evidence`
-- table. `0024` shipped with a fixed provider vocabulary and no takeoff
-- measurement provenance columns; this migration evolves it in place without
-- rewriting history and preserving every existing row:
--
--   * adds optional `condition` and `scale` columns (digital-takeoff measurement
--     provenance; omitted by providers that cannot express them);
--   * expands the named `takeoff_provider` CHECK to admit the `open_takeoff`,
--     `customer_supplied` and `future_third_party` lanes;
--   * adds fail-closed, null-safe raw-vs-flattened CHECKs so a stored
--     `condition`/`scale` column can never diverge from the value inside the
--     canonical `raw_payload` (mirrors the existing identity CHECKs and the
--     `deserialize_canonical_evidence` guard).
--
-- Apply with the Supabase CLI (`supabase db push`). Existing rows carry no
-- `condition`/`scale` (NULL) and their `raw_payload` predates those keys, so
-- `raw_payload->>'condition' is not distinct from condition` holds (NULL vs
-- NULL) and the constraints validate against the existing data — no NOT VALID
-- escape hatch is required.
-- =============================================================================

alter table public.canonical_takeoff_evidence
  add column if not exists condition text,
  add column if not exists scale text;

-- Expand the provider vocabulary: drop and recreate the named CHECK so the
-- constraint name stays stable and mirrors the Pydantic enum.
alter table public.canonical_takeoff_evidence
  drop constraint if exists canonical_takeoff_evidence_provider_check;
alter table public.canonical_takeoff_evidence
  add constraint canonical_takeoff_evidence_provider_check check (
    takeoff_provider in (
      'mobi_native', 'open_takeoff', 'manual_import', 'human_verified',
      'customer_supplied', 'authorized_third_party', 'future_cad_bim',
      'future_third_party', 'unknown'
    )
  );

-- Fail-closed, null-safe raw-vs-flattened provenance checks. `is not distinct
-- from` treats NULL as a comparable value, so both "both absent" and "both set
-- and equal" pass while any divergence (set-vs-null or set-vs-different) fails.
alter table public.canonical_takeoff_evidence
  add constraint canonical_takeoff_evidence_condition_flat_check check (
    raw_payload->>'condition' is not distinct from condition
  );
alter table public.canonical_takeoff_evidence
  add constraint canonical_takeoff_evidence_scale_flat_check check (
    raw_payload->>'scale' is not distinct from scale
  );
