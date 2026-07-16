-- =============================================================================
-- Mobi Estimates — Milestone 2: canonical takeoff evidence store
--
-- Additive, provider-neutral persistence for the single canonical takeoff
-- evidence contract (`app.takeoff.evidence.CanonicalEvidence`). Every takeoff
-- source normalizes into this one shape before anything downstream (routing,
-- quantity engine, pricing, delivery) is allowed to read it. Only *validated*
-- canonical evidence is ever written here: unknown/unmapped provider payloads
-- are quarantined upstream and never become a row in this table.
--
-- This migration is service-independent and has NOT been executed in the build
-- environment. Apply it with the Supabase CLI (`supabase db push`). It only
-- creates a new table + policies + indexes; nothing existing is modified.
--
-- First slice: staff-only select/insert/update under RLS. Company-member read
-- access and an update workflow are intentionally deferred until the evidence
-- review/approval surface exists.
-- =============================================================================

create table if not exists public.canonical_takeoff_evidence (
  evidence_id        uuid primary key default gen_random_uuid(),
  schema_version     text not null default 'takeoff_evidence_v1',

  -- Tenancy / document coordinates (server-owned; never from provider payloads).
  tenant_id          uuid not null,
  company_id         uuid not null references public.companies(id) on delete cascade,
  project_id         uuid not null references public.projects(id) on delete cascade,
  document_id        uuid not null,
  sheet_id           uuid not null,
  page_number        integer not null check (page_number >= 1),
  region_coordinates jsonb,

  -- Provenance (controlled vocabularies mirroring the Pydantic enums).
  takeoff_provider   text not null,
  provider_record_id text not null,
  evidence_class     text not null,
  measurement_method text not null,

  -- Scope / measurement.
  trade              text not null,
  scope_category     text not null,
  description        text not null,
  quantity           numeric,
  unit               text,
  confidence         numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  condition          text,
  scale              text,

  -- Review.
  review_status      text not null default 'pending',
  reviewed_by        text,

  -- Lineage / normalized payload / timestamps.
  extractor_version  text not null,
  raw_payload        jsonb not null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),

  constraint canonical_takeoff_evidence_class_check check (
    evidence_class in (
      'measured', 'formula_derived', 'schedule_extracted',
      'specification_extracted', 'customer_supplied', 'human_verified',
      'vendor_quote', 'cost_book', 'allowance', 'model_candidate',
      'test_fixture', 'unsupported'
    )
  ),
  constraint canonical_takeoff_evidence_provider_check check (
    takeoff_provider in (
      'mobi_native', 'open_takeoff', 'manual_import', 'human_verified',
      'customer_supplied', 'authorized_third_party', 'future_cad_bim',
      'future_third_party', 'unknown'
    )
  ),
  constraint canonical_takeoff_evidence_review_status_check check (
    review_status in ('pending', 'approved', 'corrected', 'rejected', 'blocked')
  ),
  constraint canonical_takeoff_evidence_raw_identity_check check (
    jsonb_typeof(raw_payload) = 'object'
    and raw_payload ? 'evidence_id'
    and jsonb_typeof(raw_payload->'evidence_id') = 'string'
    and raw_payload ? 'schema_version'
    and jsonb_typeof(raw_payload->'schema_version') = 'string'
    and raw_payload ? 'tenant_id'
    and jsonb_typeof(raw_payload->'tenant_id') = 'string'
    and raw_payload ? 'company_id'
    and jsonb_typeof(raw_payload->'company_id') = 'string'
    and raw_payload ? 'project_id'
    and jsonb_typeof(raw_payload->'project_id') = 'string'
    and raw_payload ? 'document_id'
    and jsonb_typeof(raw_payload->'document_id') = 'string'
    and raw_payload ? 'sheet_id'
    and jsonb_typeof(raw_payload->'sheet_id') = 'string'
    and raw_payload->>'evidence_id' = evidence_id::text
    and raw_payload->>'schema_version' = schema_version
    and raw_payload->>'tenant_id' = tenant_id::text
    and raw_payload->>'company_id' = company_id::text
    and raw_payload->>'project_id' = project_id::text
    and raw_payload->>'document_id' = document_id::text
    and raw_payload->>'sheet_id' = sheet_id::text
  )
);

-- Tenant/company/project + document/sheet indexes for later integration reads.
create index if not exists idx_canonical_evidence_tenant_company_project
  on public.canonical_takeoff_evidence (tenant_id, company_id, project_id, evidence_id);
create index if not exists idx_canonical_evidence_project
  on public.canonical_takeoff_evidence (project_id);
create index if not exists idx_canonical_evidence_document
  on public.canonical_takeoff_evidence (document_id);
create index if not exists idx_canonical_evidence_sheet
  on public.canonical_takeoff_evidence (sheet_id);

create trigger trg_canonical_takeoff_evidence_updated
  before update on public.canonical_takeoff_evidence
  for each row execute function public.set_updated_at();

-- RLS: default deny. Staff-only access for this first slice.
alter table public.canonical_takeoff_evidence enable row level security;

create policy canonical_takeoff_evidence_select_staff
  on public.canonical_takeoff_evidence
  for select using (public.is_staff());

create policy canonical_takeoff_evidence_insert_staff
  on public.canonical_takeoff_evidence
  for insert with check (public.is_staff());

create policy canonical_takeoff_evidence_update_staff
  on public.canonical_takeoff_evidence
  for update using (public.is_staff()) with check (public.is_staff());
