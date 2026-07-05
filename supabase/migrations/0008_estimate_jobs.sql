-- =============================================================================
-- Mobi Estimates — Phase 1A internal EstimateJob control plane
--
-- Internal-only job/document/evidence register around customer project intake.
-- Client-facing project status remains in public.projects and client_timeline().
-- =============================================================================

create type public.estimate_job_status as enum (
  'intake_received',
  'intake_review_pending',
  'intake_needs_info',
  'ready_for_document_processing',
  'document_processing',
  'document_review_pending',
  'takeoff_ready',
  'takeoff_in_progress',
  'pricing_review_pending',
  'qa_pending',
  'ready_for_owner_approval',
  'blocked',
  'canceled',
  'closed'
);

create table public.estimate_jobs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null unique references public.projects(id) on delete cascade,
  company_id uuid not null references public.companies(id) on delete cascade,
  status public.estimate_job_status not null default 'intake_received',
  priority text not null default 'normal' check (priority in ('low','normal','high','urgent')),
  bid_due_at timestamptz,
  target_delivery_at timestamptz,
  assigned_estimator_id uuid references auth.users(id),
  assigned_reviewer_id uuid references auth.users(id),
  intake_summary jsonb not null default '{}'::jsonb,
  intake_review jsonb not null default '{}'::jsonb,
  automation_state jsonb not null default '{}'::jsonb,
  blocked_reason text,
  kanban_task_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid references auth.users(id),
  closed_at timestamptz
);
create index idx_estimate_jobs_status_due on public.estimate_jobs(status, bid_due_at);
create index idx_estimate_jobs_company on public.estimate_jobs(company_id);
create index idx_estimate_jobs_estimator_status on public.estimate_jobs(assigned_estimator_id, status);
create index idx_estimate_jobs_kanban on public.estimate_jobs(kanban_task_id) where kanban_task_id is not null;
create trigger trg_estimate_jobs_updated before update on public.estimate_jobs
  for each row execute function public.set_updated_at();

create table public.estimate_job_documents (
  id uuid primary key default gen_random_uuid(),
  estimate_job_id uuid not null references public.estimate_jobs(id) on delete cascade,
  project_file_id uuid references public.project_files(id) on delete set null,
  company_id uuid not null references public.companies(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  storage_path text not null,
  file_name text not null,
  category text not null,
  document_type text,
  discipline text,
  revision_label text,
  received_at timestamptz not null default now(),
  sha256 text,
  page_count integer,
  processing_status text not null default 'not_started' check (processing_status in ('not_started','queued','processing','indexed','needs_review','failed','ignored')),
  processing_error text,
  sheet_index jsonb not null default '[]'::jsonb,
  review_status text not null default 'pending' check (review_status in ('pending','accepted','needs_replacement','ignored')),
  review_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (estimate_job_id, project_file_id),
  unique (estimate_job_id, storage_path)
);
create index idx_estimate_job_documents_job_category on public.estimate_job_documents(estimate_job_id, category);
create index idx_estimate_job_documents_project on public.estimate_job_documents(project_id);
create index idx_estimate_job_documents_processing on public.estimate_job_documents(processing_status);
create trigger trg_estimate_job_documents_updated before update on public.estimate_job_documents
  for each row execute function public.set_updated_at();

create table public.estimate_job_events (
  id uuid primary key default gen_random_uuid(),
  estimate_job_id uuid not null references public.estimate_jobs(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  event_type text not null,
  actor_id uuid references auth.users(id),
  actor_type text not null default 'system' check (actor_type in ('system','staff','automation')),
  summary text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index idx_estimate_job_events_job on public.estimate_job_events(estimate_job_id, created_at desc);
create index idx_estimate_job_events_project on public.estimate_job_events(project_id, created_at desc);

alter table public.estimate_jobs enable row level security;
alter table public.estimate_job_documents enable row level security;
alter table public.estimate_job_events enable row level security;

-- Internal control-plane tables are staff-only in Phase 1A. Client pages keep
-- using projects, project_files, deliverables, and client_timeline().
create policy estimate_jobs_staff_select on public.estimate_jobs
  for select using (public.is_staff());
create policy estimate_jobs_staff_insert on public.estimate_jobs
  for insert with check (public.is_staff());
create policy estimate_jobs_staff_update on public.estimate_jobs
  for update using (public.is_staff()) with check (public.is_staff());

create policy estimate_job_documents_staff_select on public.estimate_job_documents
  for select using (public.is_staff());
create policy estimate_job_documents_staff_insert on public.estimate_job_documents
  for insert with check (public.is_staff());
create policy estimate_job_documents_staff_update on public.estimate_job_documents
  for update using (public.is_staff()) with check (public.is_staff());

create policy estimate_job_events_staff_select on public.estimate_job_events
  for select using (public.is_staff());
create policy estimate_job_events_staff_insert on public.estimate_job_events
  for insert with check (public.is_staff());
