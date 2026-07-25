-- =============================================================================
-- Mobi Estimates — least-privilege table grants for API roles
--
-- Why this migration exists
-- -------------------------
-- A clean local stack applied every migration but left `authenticated` with no
-- SELECT/INSERT/UPDATE/DELETE on core customer-flow tables (profiles, companies,
-- company_members, company_preferences, onboarding_progress, projects,
-- project_files) while unexpectedly retaining REFERENCES/TRIGGER/TRUNCATE. A real
-- signup then failed at getPrimaryCompanyId() with "permission denied for table
-- company_members" even though RLS would have allowed the self row.
--
-- The PRODUCTION baseline is the opposite failure: a read-only inspection of the
-- live project found EVERY public table still carrying Supabase's default
-- `grant all` to anon, authenticated, AND service_role. An earlier revision of
-- this migration only stripped TRUNCATE/TRIGGER/REFERENCES and then ADDED grants,
-- so applying it to production would have left anon and authenticated holding
-- direct SELECT/INSERT/UPDATE/DELETE on all 35 tables — including the staff and
-- service-role lanes. Least privilege must not depend on which baseline the
-- migration lands on.
--
-- Therefore this migration is written REVOKE-FIRST: it first strips every table
-- privilege from the two browser-reachable roles, then re-grants an explicit,
-- enumerated set. The end state is identical whether it runs against a clean
-- local stack (where the roles hold nothing) or production (where they hold
-- everything), and it stays correct if it is ever re-run.
--
-- What is (and is not) touched
-- ----------------------------
--   * `revoke ... on all tables in schema public` affects tables/views only. It
--     does NOT touch FUNCTION privileges, so every security-definer RPC keeps the
--     execute grants its own migration set (e.g. 0036's authenticated-only grant
--     on save_engine_packet_manifest), and it does NOT touch sequences.
--   * Table grants are NOT a substitute for RLS. Every table granted below has
--     RLS enabled with policies that scope rows to the caller's tenant or to
--     public.is_staff()/is_admin(); the grants merely stop Postgres from refusing
--     the statement before RLS is ever consulted.
--   * `grant all` is never used, in either direction of this file.
--   * Step 6 closes the FUTURE-object hole: without it, the very next migration
--     that creates a table hands anon and authenticated full DML again through
--     Supabase's default ACLs, silently undoing steps 1-4 for that table.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1) Fail-safe: strip EVERY table privilege from the browser-reachable roles.
--    This is the step that makes the outcome deterministic from the production
--    baseline. It must precede every grant below.
-- ---------------------------------------------------------------------------
revoke all privileges on all tables in schema public from anon;
revoke all privileges on all tables in schema public from authenticated;

-- Explicit, and independent of the blanket revoke above: the three privileges no
-- API role may ever hold. service_role is included because it keeps its ordinary
-- DML in step 5 and would otherwise retain the default TRUNCATE/TRIGGER/REFERENCES.
revoke truncate, references, trigger on all tables in schema public from anon;
revoke truncate, references, trigger on all tables in schema public from authenticated;
revoke truncate, references, trigger on all tables in schema public from service_role;

-- ---------------------------------------------------------------------------
-- 2) anon: exactly one narrowly named grant, for one existing customer flow.
--    /start (src/app/start/route.ts) resolves plans.id by offer code BEFORE the
--    session lookup, so a signed-out visitor arriving from the public pricing
--    page reads this row as `anon`. plans is a public catalog table whose RLS
--    read policy is already `using (true)` (0002_policies.sql). Without this
--    grant, anonymous checkout silently stops populating subscriptions.plan_id.
--    anon receives NO other table privilege anywhere in this schema.
-- ---------------------------------------------------------------------------
grant select on public.plans to anon;

-- ---------------------------------------------------------------------------
-- 3) authenticated — customer-flow tables the browser reads/writes directly
--    (not through a security-definer RPC). RLS restricts every operation to the
--    caller's own profile / company / membership / project rows.
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on public.profiles            to authenticated;
grant select, insert, update, delete on public.companies           to authenticated;
grant select, insert, update, delete on public.company_members     to authenticated;
grant select, insert, update, delete on public.company_preferences to authenticated;
grant select, insert, update, delete on public.onboarding_progress to authenticated;
grant select, insert, update, delete on public.projects            to authenticated;
grant select, insert, update, delete on public.project_files       to authenticated;

-- ---------------------------------------------------------------------------
-- 4) authenticated — the remaining tables that existing signed-in surfaces reach
--    with the cookie/anon-key client. Staff run the admin console as
--    `authenticated` too (only webhooks and server-only helpers use the
--    service-role key), so revoking these would break the staff queue, not just
--    harden it. Each line grants ONLY the operations that a call site actually
--    performs, and each table's RLS policy is named so the row-level contract
--    that governs the grant is auditable from here.
-- ---------------------------------------------------------------------------
-- Billing/catalog reads (subscriptions_select, ppp_orders_select, plans_read).
-- plans is also read through the `plans(...)` embed on subscriptions.
grant select on public.plans                 to authenticated;
grant select on public.subscriptions         to authenticated;
grant select on public.pay_per_project_orders to authenticated;

-- Customer deliverables: portal list/detail read + the client acknowledgement
-- update, plus the staff upload insert (deliverables_select / _update_client /
-- _write_staff). The 0022 final-delivery trigger still blocks every write; these
-- grants keep that trigger the single point of enforcement rather than adding a
-- second, silent ACL failure in front of it.
grant select, insert, update on public.deliverables to authenticated;

-- In-app notifications: customer read (notifications_select) and the staff
-- status-change insert (notifications_insert_staff).
grant select, insert on public.notifications to authenticated;

-- External notification outbox: staff-only INSERT (notification_outbox_insert_staff).
-- createStatusChangeNotifications() enqueues held rows with the caller's
-- authenticated staff client, so a blanket revoke here would silently drop every
-- customer status notification. No SELECT is granted: nothing reads the outbox
-- outside service-role paths today. Customers reach neither operation — the RLS
-- policy requires public.is_staff() — and anon holds nothing on this table.
grant insert on public.notification_outbox to authenticated;

-- Project working data behind the portal/admin screens.
grant select, insert, update on public.project_scopes         to authenticated; -- scopes_rw
grant select, insert         on public.project_status_history to authenticated; -- status_history_select_staff/_insert_staff
grant select, insert, update on public.project_assignments    to authenticated; -- assignments_select/_write_staff
grant select                 on public.intro_offer_claims     to authenticated; -- intro_offer_claims_select_staff

-- Estimate-job spine, read and advanced by the staff console under staff-only
-- RLS. Document review/status transitions run through security-definer RPCs, so
-- estimate_job_documents needs read access only.
grant select, insert, update on public.estimate_jobs          to authenticated; -- estimate_jobs_staff_*
grant select                 on public.estimate_job_documents to authenticated; -- estimate_job_documents_staff_select
grant select, insert         on public.estimate_job_events    to authenticated; -- estimate_job_events_staff_*

-- Every other public table — audit_logs, webhook_events, checkout_claims,
-- lead_captures, canonical_takeoff_evidence, the opentakeoff worker tables, and
-- the rest — is intentionally absent above: it has no browser call site and is
-- reached only by service-role code or security-definer RPCs. Step 1 already
-- left those tables closed to anon and authenticated.

-- ---------------------------------------------------------------------------
-- 5) service_role: ordinary DML for server flows and webhook processing, never
--    table-definition/destructive privileges (already revoked in step 1).
--    service_role bypasses RLS by design and is never exposed to browsers.
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select, update on all sequences in schema public to service_role;

-- ---------------------------------------------------------------------------
-- 6) FUTURE objects: strip the broad default ACLs.
--
--    Steps 1-5 only touch the 35 tables that exist when this migration runs. A
--    read-only inspection of the live catalog showed pg_default_acl in schema
--    public still grants EVERY future postgres-owned table ALL table privileges
--    (insert/select/update/delete/truncate/references/trigger, plus MAINTAIN on
--    PG17) and every future sequence usage/select/update to anon, authenticated,
--    service_role and postgres. So the next migration that runs
--    `create table public.<x>` would hand both browser roles full DML on it the
--    moment it is created, and no reviewer of that migration would see a grant.
--
--    The same inspection established what this file may authoritatively change:
--      * migrations execute with current_user = session_user = postgres;
--      * all 35 existing public tables are owned by postgres, and there are no
--        public sequences or views yet, so postgres owns everything this repo
--        creates going forward;
--      * postgres may alter its own defaults (FOR ROLE postgres).
--
--    KNOWN, UNFIXABLE-FROM-HERE LIMITATION: pg_default_acl also carries an
--    equally broad default-ACL entry owned by supabase_admin. postgres is NOT a
--    member of supabase_admin, so `alter default privileges for role
--    supabase_admin ...` would fail outright ("permission denied") and abort this
--    migration -- it is deliberately absent below and must not be added. That
--    entry only governs objects CREATED BY supabase_admin (Supabase's own managed
--    objects), never the tables this repo's migrations create as postgres, and it
--    can only be narrowed by supabase_admin/a superuser, i.e. by Supabase
--    support. It is an accepted platform limitation, not a gap in the control
--    below, and it does not weaken it.
--
--    Effect of the four statements: future postgres-owned tables and sequences
--    grant NOTHING to anon or authenticated, and service_role keeps ordinary DML
--    (select/insert/update/delete) plus sequence usage/select -- exactly the
--    shape steps 4-5 settled on for existing objects. Explicit grants therefore
--    remain REQUIRED in every future migration that adds a browser-reachable
--    table; that is the intended outcome, since such a grant is now visible in
--    the migration that needs it. (A future serial/identity column also needs an
--    explicit `grant usage, select on sequence ...` for whichever role inserts —
--    there are no public sequences today, so nothing regresses now.)
--
--    Re-runnable: `alter default privileges ... revoke` is a no-op once the
--    privilege is already absent.
--
--    POST-APPLY PRODUCTION VERIFICATION (read-only; run after this migration
--    lands, since no runtime Postgres is available to this repo's test harness):
--      select d.defaclrole::regrole as owner, d.defaclobjtype, d.defaclacl
--        from pg_default_acl d
--        join pg_namespace n on n.oid = d.defaclnamespace
--       where n.nspname = 'public';
--    Required result for the owner = postgres rows:
--      defaclobjtype 'r' (tables):    no anon= or authenticated= entry at all,
--                                     and service_role=arwd/postgres exactly
--                                     (no D, x, t or m).
--      defaclobjtype 'S' (sequences): no anon= or authenticated= entry at all,
--                                     and service_role=rU/postgres exactly (no w).
--    The postgres=... self entry stays; the supabase_admin-owned rows are
--    expected to remain broad per the limitation above.
-- ---------------------------------------------------------------------------
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke truncate, trigger, references on tables from service_role;
alter default privileges for role postgres in schema public revoke update on sequences from service_role;

-- MAINTAIN is the PG17 addition to the default table ACL. Production is PG17, so
-- it must be revoked there; the keyword does not parse on PG15/16, where the
-- privilege does not exist and the revoke would be meaningless anyway. Guarding
-- it keeps this migration applyable on every stack the repo may be reset against.
do $$
begin
  if current_setting('server_version_num')::int >= 170000 then
    execute 'alter default privileges for role postgres in schema public revoke maintain on tables from service_role';
  end if;
end
$$;
