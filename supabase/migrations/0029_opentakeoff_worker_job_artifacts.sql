-- Durable, tenant-scoped worker-job artifact records.
-- Mirrors SQLite migration v42 for deployed Supabase/Postgres environments.
-- Artifact metadata (export/canonical-evidence/marked-region/worker-metadata)
-- was held in process-local memory, so a fresh instance could not return a
-- job's artifacts. This table persists the server-only storage key plus opaque
-- id/type/hash/size so artifacts remain retrievable across restarts and
-- instances. The storage key is never returned by the API; reads strip it.

CREATE TABLE IF NOT EXISTS public.opentakeoff_worker_job_artifacts (
    artifact_id text PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES public.opentakeoff_worker_jobs (job_id),
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    project_id uuid NOT NULL,
    artifact_type text NOT NULL,
    sha256 text NOT NULL,
    bytes integer NOT NULL,
    storage_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_opentakeoff_artifacts_job
ON public.opentakeoff_worker_job_artifacts (job_id);

CREATE INDEX IF NOT EXISTS idx_opentakeoff_artifacts_tenant_job
ON public.opentakeoff_worker_job_artifacts (tenant_id, company_id, job_id);

ALTER TABLE public.opentakeoff_worker_job_artifacts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS opentakeoff_worker_job_artifacts_service_role_all ON public.opentakeoff_worker_job_artifacts;
CREATE POLICY opentakeoff_worker_job_artifacts_service_role_all
ON public.opentakeoff_worker_job_artifacts
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);
