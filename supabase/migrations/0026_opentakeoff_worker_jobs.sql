-- OpenTakeoff worker job status persistence for the controlled MCP runtime.
-- This mirrors SQLite migration v39 for deployed Supabase/Postgres environments.
-- It stores status metadata only; raw document text and full provider payloads
-- must stay in bounded artifacts/evidence stores, not general job logs.

CREATE TABLE IF NOT EXISTS public.opentakeoff_worker_jobs (
    job_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    project_id uuid NOT NULL,
    document_id uuid NOT NULL,
    provider text NOT NULL,
    engine_version text NOT NULL,
    operation text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    status text NOT NULL,
    requested_by text,
    started_at timestamptz,
    completed_at timestamptz,
    cancelled_at timestamptz,
    error_category text,
    safe_error_message text,
    artifact_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    attempt_count integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT opentakeoff_worker_jobs_status_check CHECK (status IN (
        'queued',
        'running',
        'awaiting_scale_confirmation',
        'awaiting_geometry_confirmation',
        'completed',
        'failed',
        'cancelled'
    )),
    CONSTRAINT opentakeoff_worker_jobs_artifact_ids_array CHECK (jsonb_typeof(artifact_ids) = 'array'),
    CONSTRAINT opentakeoff_worker_jobs_evidence_ids_array CHECK (jsonb_typeof(evidence_ids) = 'array')
);

CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_project
ON public.opentakeoff_worker_jobs (tenant_id, company_id, project_id);

CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_document
ON public.opentakeoff_worker_jobs (tenant_id, company_id, document_id);

CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_status
ON public.opentakeoff_worker_jobs (status);

CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_tenant_status
ON public.opentakeoff_worker_jobs (tenant_id, company_id, status);

CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_idempotency
ON public.opentakeoff_worker_jobs (idempotency_key);

ALTER TABLE public.opentakeoff_worker_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS opentakeoff_worker_jobs_service_role_all ON public.opentakeoff_worker_jobs;
CREATE POLICY opentakeoff_worker_jobs_service_role_all
ON public.opentakeoff_worker_jobs
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);
