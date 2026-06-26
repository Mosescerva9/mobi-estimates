-- =============================================================================
-- Mobi Estimates — Pricing & offer correction (Milestone 2.1)
--
-- Aligns the database with the approved, authoritative offer:
--   • Three monthly plans: Starter, Growth, Estimating Department.
--   • One Pay Per Project one-time option ($599) — tracked as orders, NOT a plan.
--   • No free trial. The 50%-off-first-month promotion is handled in Stripe
--     (one-time-duration coupon), not in the database.
-- The centralized pricing config (src/lib/pricing.ts) is the source of truth for
-- public prices; this table keeps the portal's subscription display consistent.
-- =============================================================================

-- ---- 1. Align monthly plan codes & public names ----------------------------
-- The third plan previously used code 'department'; standardize on
-- 'estimating_department' to match the offer id used across the app.
update public.plans
   set code = 'estimating_department'
 where code = 'department';

update public.plans set name = 'Starter',
       description = 'Add estimating capacity without hiring another full-time estimator.',
       price_cents = 99500,  sort_order = 1 where code = 'starter';
update public.plans set name = 'Growth',
       description = 'More monthly estimating capacity so you can submit more bids.',
       price_cents = 199500, sort_order = 2 where code = 'growth';
update public.plans set name = 'Estimating Department',
       description = 'Your outsourced estimating department for steady monthly bid volume.',
       price_cents = 299500, sort_order = 3 where code = 'estimating_department';

-- ---- 2. Pay Per Project orders (one-time purchases) ------------------------
-- One row per completed one-time $599 estimate purchase. Written only by the
-- verified Stripe webhook (service-role key, bypasses RLS).
create table if not exists public.pay_per_project_orders (
  id                       uuid primary key default gen_random_uuid(),
  company_id               uuid not null references public.companies(id) on delete cascade,
  stripe_session_id        text unique not null,
  stripe_payment_intent_id text,
  stripe_customer_id       text,
  amount_cents             integer,
  currency                 text not null default 'usd',
  status                   text not null default 'paid',
  created_at               timestamptz not null default now()
);
create index if not exists idx_ppp_orders_company on public.pay_per_project_orders(company_id);

alter table public.pay_per_project_orders enable row level security;

-- Company members (and staff) may read their own orders. Writes happen only via
-- the service-role key in the webhook, so no insert/update policy is granted.
drop policy if exists ppp_orders_select on public.pay_per_project_orders;
create policy ppp_orders_select on public.pay_per_project_orders
  for select using (public.is_staff() or public.is_member_of(company_id));

-- ---- 3. Approved FAQ entries (mirrors the public pricing page) --------------
insert into public.faq_entries (category, question, answer, sort_order) values
  ('Plans and billing','Do you offer a free trial?','No. Mobi Estimates does not offer a free trial. New monthly subscribers receive 50% off their first month, and regular monthly pricing begins with the second month.',10),
  ('Plans and billing','Is the 50% discount recurring?','No. The 50% discount applies only to the first month of a new monthly subscription. Regular pricing begins with the second month.',11),
  ('Plans and billing','Can I purchase only one estimate?','Yes. The Pay Per Project option is a one-time payment of $599 for one estimate. It does not create a monthly subscription.',12),
  ('Plans and billing','Where does the Join Now button take me?','The Join Now button takes you to the pricing page, where you can compare the available options and choose the plan that fits your business.',13)
on conflict do nothing;
