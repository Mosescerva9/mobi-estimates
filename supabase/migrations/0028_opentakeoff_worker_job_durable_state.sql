-- Durable worker-job create parameters, confirmed scale, and retry lineage.
-- Mirrors SQLite migration v41 for deployed Supabase/Postgres environments.
-- The deployable worker API previously held trade/scope/condition, the confirmed
-- scale, and artifact records in process-local memory, so a job could not be
-- measured/read by a fresh instance or after a restart. These columns make that
-- state durable and tenant-scoped on the job row. Every column is additive and
-- nullable (or defaulted) so the migration is non-destructive. Create parameters
-- are immutable once written; scale columns are written once at confirm-scale;
-- the lineage columns support real retry (a new attempt linked to a failed job).

ALTER TABLE public.opentakeoff_worker_jobs
    ADD COLUMN IF NOT EXISTS trade text,
    ADD COLUMN IF NOT EXISTS scope_category text,
    ADD COLUMN IF NOT EXISTS default_description text,
    ADD COLUMN IF NOT EXISTS create_condition text,
    ADD COLUMN IF NOT EXISTS scale_sheet_id uuid,
    ADD COLUMN IF NOT EXISTS scale_sheet_key text,
    ADD COLUMN IF NOT EXISTS scale_page_number integer,
    ADD COLUMN IF NOT EXISTS scale_source text,
    ADD COLUMN IF NOT EXISTS scale_label text,
    ADD COLUMN IF NOT EXISTS scale_units_per_px double precision,
    ADD COLUMN IF NOT EXISTS scale_confirmed_by text,
    ADD COLUMN IF NOT EXISTS scale_confirmed_at timestamptz,
    ADD COLUMN IF NOT EXISTS attempt_number integer NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS parent_job_id uuid,
    ADD COLUMN IF NOT EXISTS root_job_id uuid;

UPDATE public.opentakeoff_worker_jobs
SET root_job_id = job_id
WHERE root_job_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_parent
ON public.opentakeoff_worker_jobs (parent_job_id);

CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_root
ON public.opentakeoff_worker_jobs (root_job_id);
