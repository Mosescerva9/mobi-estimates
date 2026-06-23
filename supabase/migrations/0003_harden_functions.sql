-- =============================================================================
-- Mobi Estimates — Client Portal : function hardening (Milestone 1)
--
-- Addresses Supabase security advisors raised after applying 0001/0002:
--  * function_search_path_mutable on set_updated_at
--  * anon/authenticated_security_definer_function_executable on internal-only
--    functions that should not be reachable over the public PostgREST API.
--
-- The RLS helper functions (is_staff, is_admin, is_member_of,
-- is_member_of_project) are intentionally LEFT executable: RLS policy
-- expressions run with the caller's privileges and must be able to call them.
-- =============================================================================

-- Pin search_path on the trigger helper.
alter function public.set_updated_at() set search_path = public;

-- handle_new_user: fired by the on_auth_user_created trigger only. Revoking
-- EXECUTE from PUBLIC does not affect trigger firing.
revoke execute on function public.handle_new_user() from public;

-- current_role: defined but unused; nothing should call it over RPC.
revoke execute on function public.current_role() from public;

-- next_project_number: server-side project-number assignment only.
revoke execute on function public.next_project_number() from public;
grant execute on function public.next_project_number() to service_role;

-- client_timeline: client-safe timeline RPC — signed-in users only, never anon.
revoke execute on function public.client_timeline(uuid) from public;
grant execute on function public.client_timeline(uuid) to authenticated;
