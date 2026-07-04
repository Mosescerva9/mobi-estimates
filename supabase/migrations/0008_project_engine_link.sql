-- 0008_project_engine_link.sql
-- Link a portal project to its counterpart in the estimating engine.
--
-- When staff push a project's PDF plan set to the engine, we record the
-- engine-side project id and last-known status so the admin UI can show the
-- sync state and drive later pipeline steps. These columns are written only by
-- trusted server code (service role); no client RLS policy grants write access.

alter table public.projects
  add column if not exists engine_project_id uuid,
  add column if not exists engine_status text,
  add column if not exists engine_page_count integer,
  add column if not exists engine_synced_at timestamptz;

comment on column public.projects.engine_project_id is
  'Project id in the estimating engine (FastAPI service), set when a plan set is ingested.';
comment on column public.projects.engine_status is
  'Last-known engine-side project status.';
comment on column public.projects.engine_page_count is
  'Page count the engine reported for the ingested PDF plan set.';
comment on column public.projects.engine_synced_at is
  'When the project was last pushed to / synced with the engine.';
