-- Fixes a hard onboarding blocker: OnboardingForm.tsx creates the company row
-- with `.insert(...).select("id").single()`, which requires the new row to
-- satisfy companies_select's RETURNING check. At that point the creator isn't
-- a company_members row yet (that's the next step), so is_member_of(id) is
-- false and is_staff() is false too -> every real signup failed with
-- "new row violates row-level security policy for table companies".
-- Fix: let the creator see their own just-created company immediately.
drop policy if exists companies_select on public.companies;
create policy companies_select on public.companies
  for select using (public.is_staff() or public.is_member_of(id) or created_by = auth.uid());
