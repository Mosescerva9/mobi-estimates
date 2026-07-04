-- Pay-first checkout: an anonymous visitor pays via Stripe Checkout before any
-- account exists. This table bridges that gap between "Stripe confirmed
-- payment" and "we know who they are and have a company to attach it to."
--
-- Service-role only: RLS is enabled with zero policies, so anon/authenticated
-- roles get default-deny. Only the webhook and the claim/finalize routes
-- (service-role client) ever touch this table.
create table public.checkout_claims (
  id                       uuid primary key default gen_random_uuid(),
  claim_token              text not null unique,
  stripe_checkout_session_id text not null unique,
  mode                     text not null check (mode in ('subscription', 'payment')),
  plan_code                text not null,
  plan_id                  uuid references public.plans(id),
  email                    text,
  stripe_customer_id       text,
  stripe_subscription_id   text,
  stripe_payment_intent_id text,
  amount_cents             integer,
  currency                 text,
  paid_at                  timestamptz,
  auth_user_id             uuid references auth.users(id) on delete set null,
  claimed_at               timestamptz,
  created_at               timestamptz not null default now()
);

create index idx_checkout_claims_auth_user on public.checkout_claims(auth_user_id);

alter table public.checkout_claims enable row level security;
