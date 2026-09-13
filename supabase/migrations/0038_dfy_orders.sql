-- Done-For-You "Estimator Business Setup" ($997 one-time) orders.
--
-- This product belongs to the education/community business (YouTube -> Skool
-- -> DFY upsell), NOT to the Mobi Estimates client offers — buyers are course
-- members, so no account, company, or portal entitlement is created. The flow
-- mirrors the pay-first checkout_claims pattern: an anonymous visitor pays via
-- Stripe Checkout, the webhook marks the order paid, and the buyer completes
-- an intake form (stored in `intake`) that drives the onboarding call.
--
-- Service-role only: RLS is enabled with zero policies, so anon/authenticated
-- roles get default-deny. Only the dfy start route, the Stripe webhook, and
-- the intake endpoint (all service-role) ever touch this table.
create table public.dfy_orders (
  id                        uuid primary key default gen_random_uuid(),
  order_token               text not null unique,
  stripe_checkout_session_id text not null unique,
  offer_code                text not null check (offer_code in ('dfy_setup')),
  email                     text,
  stripe_customer_id        text,
  stripe_payment_intent_id  text,
  amount_cents              integer,
  currency                  text,
  status                    text not null default 'pending'
                            check (status in ('pending', 'paid', 'intake_submitted', 'fulfilled', 'refunded')),
  intake                    jsonb,
  intake_submitted_at       timestamptz,
  paid_at                   timestamptz,
  created_at                timestamptz not null default now()
);

create index idx_dfy_orders_status on public.dfy_orders(status);

alter table public.dfy_orders enable row level security;
