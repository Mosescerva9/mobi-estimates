-- =============================================================================
-- Mobi Estimates — Pay Per Project entitlement (Milestone 2.2)
--
-- A Pay Per Project purchase ($599 one-time) grants limited authenticated portal
-- access for exactly ONE estimate. This migration tracks credit consumption and
-- provides an atomic claim so a customer can submit exactly one project per paid
-- order — never an unlimited number of unpaid projects, and never a subscription.
-- =============================================================================

-- One paid order = one estimate credit. When the customer submits a project we
-- record which project consumed the credit; an order with a NULL value is unused.
alter table public.pay_per_project_orders
  add column if not exists consumed_project_id uuid references public.projects(id) on delete set null;

create index if not exists idx_ppp_orders_unconsumed
  on public.pay_per_project_orders(company_id)
  where status = 'paid' and consumed_project_id is null;

-- Atomically claim one unused paid credit for a company and bind it to a project.
-- Returns true if a credit was consumed, false if none was available. Uses
-- FOR UPDATE SKIP LOCKED so concurrent submissions can't double-spend one credit.
create or replace function public.consume_ppp_credit(p_company uuid, p_project uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
begin
  -- Only a member of the company (or staff) may consume that company's credit.
  if not (public.is_member_of(p_company) or public.is_staff()) then
    raise exception 'not authorized to consume credit for this company';
  end if;

  select id into v_id
    from public.pay_per_project_orders
   where company_id = p_company
     and status = 'paid'
     and consumed_project_id is null
   order by created_at
   for update skip locked
   limit 1;

  if v_id is null then
    return false;
  end if;

  update public.pay_per_project_orders
     set consumed_project_id = p_project
   where id = v_id;

  return true;
end;
$$;

revoke all on function public.consume_ppp_credit(uuid, uuid) from public;
grant execute on function public.consume_ppp_credit(uuid, uuid) to authenticated;
