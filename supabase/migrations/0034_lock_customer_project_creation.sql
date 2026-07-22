-- =============================================================================
-- Customer project creation entitlement lock.
--
-- Direct authenticated inserts into projects bypass the application offer,
-- subscription, and paid-credit checks. After this migration:
--   * staff may still insert operational projects under RLS;
--   * customers must use create_entitled_project or create_free_offer_project;
--   * paid-credit consumption and project creation commit atomically.
-- =============================================================================

-- Replace the legacy customer-member insert policy with a staff-only policy.
drop policy if exists projects_insert on public.projects;
drop policy if exists projects_insert_staff on public.projects;
create policy projects_insert_staff on public.projects
  for insert with check (
    public.is_staff()
    and status not in ('delivered', 'revised', 'approved')
  );

create or replace function public.create_entitled_project(
  p_company uuid,
  p_name text,
  p_project_type text,
  p_address text,
  p_bid_due_at timestamptz,
  p_requested_completion_at timestamptz,
  p_prevailing_wage boolean,
  p_is_public boolean
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_company uuid;
  v_paid_order uuid;
  v_project uuid;
  v_project_number text;
  v_project_type public.project_type;
  v_has_subscription boolean := false;
  v_entitlement text;
begin
  if auth.uid() is null then
    return jsonb_build_object('ok', false, 'reason', 'not_authenticated');
  end if;
  if p_company is null or not public.is_member_of(p_company) then
    return jsonb_build_object('ok', false, 'reason', 'not_authorized');
  end if;
  if p_name is null or char_length(btrim(p_name)) < 2 or char_length(btrim(p_name)) > 200 then
    return jsonb_build_object('ok', false, 'reason', 'invalid_name');
  end if;
  if p_address is not null and char_length(p_address) > 5000 then
    return jsonb_build_object('ok', false, 'reason', 'invalid_address');
  end if;

  if p_project_type is not null then
    begin
      v_project_type := p_project_type::public.project_type;
    exception when invalid_text_representation then
      return jsonb_build_object('ok', false, 'reason', 'invalid_project_type');
    end;
  end if;

  -- Serialize every customer creation decision for this company. This prevents
  -- concurrent requests from racing entitlement state or consuming one credit
  -- for more than one project.
  select id into v_company
    from public.companies
   where id = p_company and deleted_at is null
   for update;
  if v_company is null then
    return jsonb_build_object('ok', false, 'reason', 'company_not_found');
  end if;

  select exists (
    select 1
      from public.subscriptions
     where company_id = p_company
       and status = 'active'
  ) into v_has_subscription;

  if v_has_subscription then
    v_entitlement := 'subscription';
  else
    select id into v_paid_order
      from public.pay_per_project_orders
     where company_id = p_company
       and status = 'paid'
       and consumed_project_id is null
     order by created_at
     for update
     limit 1;

    if v_paid_order is null then
      return jsonb_build_object('ok', false, 'reason', 'no_paid_entitlement');
    end if;
    v_entitlement := 'pay_per_project';
  end if;

  v_project_number := public.next_project_number();

  insert into public.projects (
    company_id,
    project_number,
    name,
    status,
    project_type,
    address,
    bid_due_at,
    requested_completion_at,
    prevailing_wage,
    is_public,
    created_by
  ) values (
    p_company,
    v_project_number,
    btrim(p_name),
    'submitted',
    v_project_type,
    nullif(btrim(coalesce(p_address, '')), ''),
    p_bid_due_at,
    p_requested_completion_at,
    coalesce(p_prevailing_wage, false),
    coalesce(p_is_public, false),
    auth.uid()
  ) returning id into v_project;

  if v_paid_order is not null then
    update public.pay_per_project_orders
       set consumed_project_id = v_project
     where id = v_paid_order
       and consumed_project_id is null;
    if not found then
      raise exception 'paid project credit was not consumed';
    end if;
  end if;

  return jsonb_build_object(
    'ok', true,
    'project_id', v_project,
    'project_number', v_project_number,
    'entitlement', v_entitlement
  );
end;
$$;

revoke all on function public.create_entitled_project(
  uuid, text, text, text, timestamptz, timestamptz, boolean, boolean
) from public;
grant execute on function public.create_entitled_project(
  uuid, text, text, text, timestamptz, timestamptz, boolean, boolean
) to authenticated;
