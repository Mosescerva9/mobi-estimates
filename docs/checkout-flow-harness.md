# Checkout flow validation harness

Automated, offline test of the pay-first checkout state machine: pricing
selection -> pending `checkout_claims` row -> Stripe webhook marks it paid ->
claim-account links an auth user -> onboarding/finalize activates the real
entitlement.

## Run it

```
npm run test:checkout-flow
```

Exits non-zero if any scenario fails.

## What it does and does not do

- **No network calls.** It never talks to Stripe or Supabase. `src/lib/checkout-claims.ts`
  and `src/lib/entitlement.ts` (the real production modules, unmodified logic)
  are exercised against `scripts/checkout-flow-fakes.ts`, an in-memory
  stand-in for the handful of Supabase query-builder chains those modules use.
  The harness also monkey-patches `fetch` to throw, so any accidental network
  call fails loudly instead of silently succeeding or hanging.
- **Guardrail:** if `STRIPE_SECRET_KEY` starts with `sk_live_` or
  `SUPABASE_SERVICE_ROLE_KEY` is set in the environment, the harness prints a
  warning and proceeds using fakes only — it is structurally incapable of
  making a real Stripe or Supabase call, regardless of what's in the
  environment.
- **Does not** exercise Supabase Auth (`createUser` / `signInWithPassword`) or
  outbound email — those are framework/vendor concerns, not business logic.
  The harness covers the DB-level invariants: claim creation, payment
  recording, auth-user linking (the `checkout_claims.auth_user_id` column
  write), and entitlement activation.

## Scenarios covered

1. Pricing selection creates a pending claim with mode/plan metadata.
2. Webhook `checkout.session.completed` marks the claim paid with Stripe
   IDs/email/amount/currency, requiring both the claim token and the Stripe
   Checkout Session id to match the pending row:
   - a mismatched claim token + session id pair cannot mark a claim paid
   - the correct claim token with the wrong session id cannot mark a claim
     paid
   - in both cases, no `paid_at`/email/Stripe ids are written
3. Claim-account step links an auth user to the claim.
4. Finalize activates the correct entitlement shape for both offer types:
   - monthly subscription -> `subscriptions` row (`status: active`)
   - pay-per-project -> `pay_per_project_orders` row (`status: paid`)
5. Duplicate webhook delivery is idempotent (both the `webhook_events`
   dedup guard and the entitlement upsert-by-Stripe-id are checked).
6. An unpaid claim cannot be linked or finalized.
7. A claim cannot be finalized for a company the user does not belong to.

## Files

- `scripts/test-checkout-flow.ts` — test runner and scenarios.
- `scripts/checkout-flow-fakes.ts` — in-memory Supabase query-builder fake.
- `src/lib/checkout-claims.ts` — the pure, DB-only checkout-claims state
  machine extracted from the webhook route, `/start`, and
  `/checkout/complete` actions so it can be exercised without Next.js
  request/cookie plumbing. The routes call these same functions in
  production.

`scripts/**` is excluded from the app's `tsconfig.json` (it runs via `tsx`,
not the Next.js build) and is not part of the production bundle.
