-- =============================================================================
-- Mobi Estimates — least-privilege table grants for API roles
--
-- A clean local stack applied every migration but left `authenticated` with no
-- SELECT/INSERT/UPDATE/DELETE on core customer-flow tables (profiles, companies,
-- company_members, company_preferences, onboarding_progress, projects,
-- project_files) while unexpectedly retaining REFERENCES/TRIGGER/TRUNCATE. A real
-- signup then failed at getPrimaryCompanyId() with "permission denied for table
-- company_members" even though RLS would have allowed the self row.
--
-- This migration establishes EXPLICIT least-privilege table grants:
--   * strip TRUNCATE / TRIGGER / REFERENCES (never needed by API roles) from
--     anon, authenticated, and service_role on every table;
--   * grant SELECT/INSERT/UPDATE/DELETE to `authenticated` ONLY on the
--     customer-flow tables whose existing RLS policies + triggers already govern
--     which rows a customer may touch (table grants do NOT replace RLS);
--   * keep pure service-role infrastructure (notification_outbox, webhook_events)
--     closed to browser roles while restoring ordinary DML to service_role;
--   * leave every other table's existing grants untouched, so staff-only data
--     (estimate_jobs/documents/events, deliverables, audit_logs, internal notes)
--     stays governed by its current RLS contract and locked surfaces stay locked.
--
-- Anon keeps only whatever SELECT the existing public-read contract already
-- granted it; nothing is broadened here. No `grant all` is used.
-- =============================================================================

-- 1) Remove privileges the API roles must never hold, across all current tables.
revoke truncate, references, trigger on all tables in schema public from anon;
revoke truncate, references, trigger on all tables in schema public from authenticated;
revoke truncate, references, trigger on all tables in schema public from service_role;

-- 2) Customer-flow CRUD for authenticated, governed by existing RLS/triggers.
--    These are the onboarding/self-service tables a signed-in user reads/writes
--    directly (not via a security-definer RPC). RLS restricts every operation to
--    the caller's own profile / company / membership / project rows.
grant select, insert, update, delete on public.profiles            to authenticated;
grant select, insert, update, delete on public.companies           to authenticated;
grant select, insert, update, delete on public.company_members     to authenticated;
grant select, insert, update, delete on public.company_preferences to authenticated;
grant select, insert, update, delete on public.onboarding_progress to authenticated;
grant select, insert, update, delete on public.projects            to authenticated;
grant select, insert, update, delete on public.project_files       to authenticated;

-- 3) Defense-in-depth: pure service-role infrastructure stays closed to both API
--    roles (RLS already denies these; the explicit revoke removes any stray
--    table privilege so a customer can never read the notification/webhook lanes).
revoke all on public.notification_outbox from anon, authenticated;
revoke all on public.webhook_events      from anon, authenticated;

-- 4) Server-side administration and webhook processing need ordinary DML across
--    current public tables, but never table-definition/destructive privileges.
--    service_role bypasses RLS by design; this grant is not exposed to browsers.
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select, update on all sequences in schema public to service_role;
