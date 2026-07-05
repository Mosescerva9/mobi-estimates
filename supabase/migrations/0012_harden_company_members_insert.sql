-- Harden company membership creation.
--
-- Previous policy allowed any authenticated user to insert themselves into any
-- company_id. Onboarding only needs the creator of a company to add their own
-- first membership row; staff/admin writes still happen via admin role/service
-- role paths.
drop policy if exists members_insert on public.company_members;

create policy members_insert on public.company_members
  for insert
  with check (
    public.is_admin()
    or (
      user_id = auth.uid()
      and exists (
        select 1
          from public.companies c
         where c.id = company_id
           and c.created_by = auth.uid()
      )
    )
  );
