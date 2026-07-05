import type { SupabaseClient } from "@supabase/supabase-js";
import { FakeSupabaseAdmin } from "./checkout-flow-fakes";
import {
  createPendingClaim,
  finalizeCheckoutClaim,
  isDuplicateWebhookEvent,
  linkClaimToAuthUser,
  markClaimPaid,
} from "../src/lib/checkout-claims";
import { activateEntitlement } from "../src/lib/entitlement";

/**
 * Automated, fully offline validation of the pay-first checkout flow:
 * pricing selection -> pending claim -> webhook paid -> claim-account ->
 * onboarding/finalize -> entitlement. See docs/checkout-flow-harness.md.
 *
 * Run with: npm run test:checkout-flow
 */

function guardAgainstLiveUsage(): () => void {
  const stripeKey = process.env.STRIPE_SECRET_KEY;
  const supabaseServiceRole = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (stripeKey?.startsWith("sk_live_") || supabaseServiceRole) {
    console.warn(
      "[checkout-flow harness] Live-looking credentials found in the environment " +
        "(STRIPE_SECRET_KEY starting with sk_live_ and/or SUPABASE_SERVICE_ROLE_KEY). " +
        "This harness never calls Stripe or Supabase over the network -- it only " +
        "exercises in-memory fakes. Continuing safely with fakes only.",
    );
  } else {
    console.log("[checkout-flow harness] No live credentials detected. Using in-memory fakes only.");
  }

  // Belt-and-braces: fail loudly (rather than silently succeed) if any code
  // path under test ever attempts a real network call.
  const realFetch = globalThis.fetch;
  globalThis.fetch = (() => {
    throw new Error(
      "[checkout-flow harness] fetch() was called -- this harness must run fully offline with no network access.",
    );
  }) as typeof fetch;
  return () => {
    globalThis.fetch = realFetch;
  };
}

function admin(): SupabaseClient {
  return new FakeSupabaseAdmin() as unknown as SupabaseClient;
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function assertEqual<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message} (expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)})`);
  }
}

async function assertThrows(fn: () => Promise<unknown>, messageIncludes: string): Promise<void> {
  try {
    await fn();
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    assert(message.includes(messageIncludes), `expected error to include "${messageIncludes}", got: ${message}`);
    return;
  }
  throw new Error(`expected an error including "${messageIncludes}" but none was thrown`);
}

async function fetchClaimByToken(a: SupabaseClient, token: string) {
  const { data } = await a.from("checkout_claims").select("*").eq("claim_token", token).maybeSingle();
  return data as Record<string, unknown> | null;
}

async function seedMembership(a: SupabaseClient, companyId: string, userId: string) {
  await a.from("company_members").insert({ company_id: companyId, user_id: userId });
}

type Test = { name: string; fn: () => Promise<void> };
const tests: Test[] = [];
function test(name: string, fn: () => Promise<void>) {
  tests.push({ name, fn });
}

// 1. Pricing selection creates a pending checkout claim with mode/plan metadata.
test("pricing selection creates a pending checkout claim", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_pending",
    stripeCheckoutSessionId: "cs_pending",
    mode: "subscription",
    planCode: "starter",
    planId: "plan-starter-uuid",
  });

  const claim = await fetchClaimByToken(a, "tok_pending");
  assert(claim, "pending claim row should exist");
  assertEqual(claim!.mode, "subscription", "claim mode");
  assertEqual(claim!.plan_code, "starter", "claim plan_code");
  assertEqual(claim!.plan_id, "plan-starter-uuid", "claim plan_id");
  assertEqual(claim!.paid_at, undefined, "pending claim must not be paid yet");
});

// 2. Webhook checkout.session.completed marks the claim paid with Stripe IDs/email/amount/currency.
test("webhook marks the claim paid with Stripe IDs/email/amount/currency", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_paid",
    stripeCheckoutSessionId: "cs_paid",
    mode: "subscription",
    planCode: "growth",
    planId: "plan-growth-uuid",
  });

  await markClaimPaid(a, "tok_paid", "cs_paid", {
    email: "buyer@example.com",
    stripeCustomerId: "cus_123",
    stripeSubscriptionId: "sub_123",
    stripePaymentIntentId: null,
    amountCents: 99_750,
    currency: "usd",
  });

  const claim = await fetchClaimByToken(a, "tok_paid");
  assert(claim, "claim should still exist after webhook");
  assert(typeof claim!.paid_at === "string", "paid_at should be set");
  assertEqual(claim!.email, "buyer@example.com", "claim email");
  assertEqual(claim!.stripe_customer_id, "cus_123", "stripe customer id");
  assertEqual(claim!.stripe_subscription_id, "sub_123", "stripe subscription id");
  assertEqual(claim!.amount_cents, 99_750, "amount cents");
  assertEqual(claim!.currency, "usd", "currency");
});

// 2b. Mismatched claim token + session id cannot mark a claim paid.
test("mismatched claim token and session id cannot mark a claim paid", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_mismatch",
    stripeCheckoutSessionId: "cs_mismatch",
    mode: "subscription",
    planCode: "growth",
    planId: "plan-growth-uuid",
  });

  await assertThrows(
    () =>
      markClaimPaid(a, "tok_other", "cs_other", {
        email: "attacker@example.com",
        stripeCustomerId: "cus_evil",
        stripeSubscriptionId: "sub_evil",
        stripePaymentIntentId: null,
        amountCents: 1,
        currency: "usd",
      }),
    "unknown claim token or session id",
  );

  const claim = await fetchClaimByToken(a, "tok_mismatch");
  assertEqual(claim!.paid_at, undefined, "paid_at must not be set on mismatch");
  assertEqual(claim!.email, undefined, "email must not be set on mismatch");
  assertEqual(claim!.stripe_customer_id, undefined, "stripe_customer_id must not be set on mismatch");
});

// 2c. Correct claim token but wrong session id cannot mark a claim paid.
test("correct claim token but wrong session id cannot mark a claim paid", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_right_wrong_session",
    stripeCheckoutSessionId: "cs_right",
    mode: "subscription",
    planCode: "growth",
    planId: "plan-growth-uuid",
  });

  await assertThrows(
    () =>
      markClaimPaid(a, "tok_right_wrong_session", "cs_wrong_session", {
        email: "attacker@example.com",
        stripeCustomerId: "cus_evil",
        stripeSubscriptionId: "sub_evil",
        stripePaymentIntentId: null,
        amountCents: 1,
        currency: "usd",
      }),
    "unknown claim token or session id",
  );

  const claim = await fetchClaimByToken(a, "tok_right_wrong_session");
  assertEqual(claim!.paid_at, undefined, "paid_at must not be set on session id mismatch");
  assertEqual(claim!.email, undefined, "email must not be set on session id mismatch");
  assertEqual(claim!.stripe_payment_intent_id, undefined, "stripe_payment_intent_id must not be set on session id mismatch");
});

// 3. Claim-account step links an auth user.
test("claim-account step links an auth user to the claim", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_link",
    stripeCheckoutSessionId: "cs_link",
    mode: "payment",
    planCode: "pay_per_project",
    planId: null,
  });
  await markClaimPaid(a, "tok_link", "cs_link", {
    email: "linkme@example.com",
    stripeCustomerId: "cus_link",
    stripeSubscriptionId: null,
    stripePaymentIntentId: "pi_link",
    amountCents: 59_900,
    currency: "usd",
  });

  await linkClaimToAuthUser(a, "tok_link", "user-link-uuid");

  const claim = await fetchClaimByToken(a, "tok_link");
  assertEqual(claim!.auth_user_id, "user-link-uuid", "auth_user_id should be linked");
});

// 4a. Finalize activates a subscription-style entitlement for a monthly plan.
test("finalize activates a subscription entitlement for a monthly plan", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_sub",
    stripeCheckoutSessionId: "cs_sub",
    mode: "subscription",
    planCode: "starter",
    planId: "plan-starter-uuid",
  });
  await markClaimPaid(a, "tok_sub", "cs_sub", {
    email: "subscriber@example.com",
    stripeCustomerId: "cus_sub",
    stripeSubscriptionId: "sub_sub",
    stripePaymentIntentId: null,
    amountCents: 49_750,
    currency: "usd",
  });
  await linkClaimToAuthUser(a, "tok_sub", "user-sub-uuid");
  await seedMembership(a, "company-sub", "user-sub-uuid");

  const result = await finalizeCheckoutClaim(a, { companyId: "company-sub", userId: "user-sub-uuid" });
  assertEqual(result.claimed, true, "finalize should report claimed");

  const { data: subs } = await a.from("subscriptions").select("*").eq("stripe_subscription_id", "sub_sub").maybeSingle();
  assert(subs, "subscription row should be created");
  const subRow = subs as Record<string, unknown>;
  assertEqual(subRow.company_id, "company-sub", "subscription company_id");
  assertEqual(subRow.status, "active", "subscription status");
  assertEqual(subRow.plan_id, "plan-starter-uuid", "subscription plan_id");

  const claim = await fetchClaimByToken(a, "tok_sub");
  assert(typeof claim!.claimed_at === "string", "claim should be marked claimed");
});

// 4b. Finalize activates a pay_per_project_order-style entitlement for pay-per-project.
test("finalize activates a pay_per_project_order entitlement for pay-per-project", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_ppp",
    stripeCheckoutSessionId: "cs_ppp",
    mode: "payment",
    planCode: "pay_per_project",
    planId: null,
  });
  await markClaimPaid(a, "tok_ppp", "cs_ppp", {
    email: "oneoff@example.com",
    stripeCustomerId: "cus_ppp",
    stripeSubscriptionId: null,
    stripePaymentIntentId: "pi_ppp",
    amountCents: 59_900,
    currency: "usd",
  });
  await linkClaimToAuthUser(a, "tok_ppp", "user-ppp-uuid");
  await seedMembership(a, "company-ppp", "user-ppp-uuid");

  const result = await finalizeCheckoutClaim(a, { companyId: "company-ppp", userId: "user-ppp-uuid" });
  assertEqual(result.claimed, true, "finalize should report claimed");

  const { data: order } = await a
    .from("pay_per_project_orders")
    .select("*")
    .eq("stripe_session_id", "cs_ppp")
    .maybeSingle();
  assert(order, "pay_per_project_orders row should be created");
  const orderRow = order as Record<string, unknown>;
  assertEqual(orderRow.company_id, "company-ppp", "order company_id");
  assertEqual(orderRow.status, "paid", "order status");
  assertEqual(orderRow.amount_cents, 59_900, "order amount_cents");
});

// 5. Duplicate webhook delivery is idempotent.
test("duplicate webhook delivery is idempotent", async () => {
  const a = admin();
  const event = { id: "evt_dup", type: "checkout.session.completed", payload: { any: "thing" } };

  const firstDelivery = await isDuplicateWebhookEvent(a, event);
  assertEqual(firstDelivery, false, "first delivery should not be flagged as duplicate");

  const secondDelivery = await isDuplicateWebhookEvent(a, event);
  assertEqual(secondDelivery, true, "second delivery of the same event id should be flagged as duplicate");

  // Depth check: even if reprocessing slipped past the webhook_events guard,
  // activateEntitlement's upsert-by-Stripe-id is itself idempotent.
  await activateEntitlement(a, {
    companyId: "company-idem",
    mode: "subscription",
    planId: "plan-idem",
    stripeSessionId: "cs_idem",
    stripeCustomerId: "cus_idem",
    stripeSubscriptionId: "sub_idem",
    amountCents: 99_500,
    currency: "usd",
  });
  await activateEntitlement(a, {
    companyId: "company-idem",
    mode: "subscription",
    planId: "plan-idem",
    stripeSessionId: "cs_idem",
    stripeCustomerId: "cus_idem",
    stripeSubscriptionId: "sub_idem",
    amountCents: 99_500,
    currency: "usd",
  });
  const { data: allSubs } = await a.from("subscriptions").select("*").eq("stripe_subscription_id", "sub_idem");
  assertEqual((allSubs as unknown[]).length, 1, "duplicate entitlement activation must not create a second row");
});

// 6. Unpaid claim cannot be linked or finalized.
test("an unpaid claim cannot be linked or finalized", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_unpaid",
    stripeCheckoutSessionId: "cs_unpaid",
    mode: "subscription",
    planCode: "starter",
    planId: "plan-starter-uuid",
  });

  await assertThrows(
    () => linkClaimToAuthUser(a, "tok_unpaid", "user-unpaid-uuid"),
    "could not be linked",
  );

  // Defensive depth check: even if a bad row somehow has auth_user_id set
  // without paid_at, finalize must still refuse to activate an entitlement.
  await a.from("checkout_claims").update({ auth_user_id: "user-unpaid-uuid" }).eq("claim_token", "tok_unpaid");
  await seedMembership(a, "company-unpaid", "user-unpaid-uuid");

  const result = await finalizeCheckoutClaim(a, { companyId: "company-unpaid", userId: "user-unpaid-uuid" });
  assertEqual(result.claimed, false, "unpaid claim must not be finalized");

  const { data: subs } = await a.from("subscriptions").select("*").eq("company_id", "company-unpaid");
  assertEqual((subs as unknown[]).length, 0, "no entitlement should be written for an unpaid claim");
});

// 7. Claim cannot finalize for a company the user does not belong to.
test("a claim cannot finalize for a company the user does not belong to", async () => {
  const a = admin();
  await createPendingClaim(a, {
    claimToken: "tok_wrong_company",
    stripeCheckoutSessionId: "cs_wrong_company",
    mode: "payment",
    planCode: "pay_per_project",
    planId: null,
  });
  await markClaimPaid(a, "tok_wrong_company", "cs_wrong_company", {
    email: "outsider@example.com",
    stripeCustomerId: "cus_wrong",
    stripeSubscriptionId: null,
    stripePaymentIntentId: "pi_wrong",
    amountCents: 59_900,
    currency: "usd",
  });
  await linkClaimToAuthUser(a, "tok_wrong_company", "user-outsider-uuid");
  // Deliberately do NOT seed company_members for "company-not-mine".

  await assertThrows(
    () => finalizeCheckoutClaim(a, { companyId: "company-not-mine", userId: "user-outsider-uuid" }),
    "does not belong to",
  );

  const { data: orders } = await a.from("pay_per_project_orders").select("*").eq("company_id", "company-not-mine");
  assertEqual((orders as unknown[]).length, 0, "no entitlement should be written for a foreign company");
});

async function main() {
  const restoreFetch = guardAgainstLiveUsage();
  let failures = 0;
  for (const t of tests) {
    try {
      await t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      const message = e instanceof Error ? e.message : String(e);
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${message}`);
    }
  }
  restoreFetch();

  console.log("");
  console.log(`${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) {
    process.exit(1);
  }
}

main();
