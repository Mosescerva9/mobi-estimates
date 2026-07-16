-- Relax the OpenTakeoff worker-job status CHECK for the deployable worker API.
-- Mirrors SQLite migration v40. Migration 0026 shipped a status CHECK covering
-- only the in-process values; the deployable worker API adds the richer
-- lifecycle statuses (starting, document_loaded, awaiting_geometry,
-- running_measurement, awaiting_review) while keeping the older values as a
-- backward-compatible superset. Status metadata only — raw document text and
-- full provider payloads stay in bounded artifact/evidence stores.

ALTER TABLE public.opentakeoff_worker_jobs
    DROP CONSTRAINT IF EXISTS opentakeoff_worker_jobs_status_check;

ALTER TABLE public.opentakeoff_worker_jobs
    ADD CONSTRAINT opentakeoff_worker_jobs_status_check CHECK (status IN (
        'queued',
        'starting',
        'document_loaded',
        'running',
        'awaiting_scale_confirmation',
        'awaiting_geometry',
        'awaiting_geometry_confirmation',
        'running_measurement',
        'awaiting_review',
        'completed',
        'failed',
        'cancelled'
    ));
