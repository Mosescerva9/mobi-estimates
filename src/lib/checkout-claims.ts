import type { SupabaseClient } from "@supabase/supabase-js";
import { activateEntitlement } from "@/lib/entitlement";

/**
 * Pure, DB-only state machine for the pay-first `checkout_claims` flow. Pulled
 * out of the route/action handlers (webhook, /start, /checkout/complete) so it
 * can be exercised without Next.js request/cookie plumbing — those callers own
 * auth, redirects, and email; this module owns the row-level invariants that
 * must hold for money to be safely attached to an account.
 */

export interface CreatePendingClaimParams {
  claimToken: string;
  stripeCheckoutSessionId: string;
  mode: "subscription" | "payment";
  planCode: string;
  planId: string | null;
}

/** /start: record a pending claim before redirecting to Stripe Checkout. */
export async function createPendingClaim(
  admin: SupabaseClient,
  params: CreatePendingClaimParams,
): Promise<void> {
  const { error } = await admin.from("checkout_claims").insert({
    claim_token: params.claimToken,
    stripe_checkout_session_id: params.stripeCheckoutSessionId,
    mode: params.mode,
    plan_code: params.planCode,
    plan_id: params.planId,
  });
  if (error) throw new Error(`Could not create checkout claim: ${error.message}`);
}

export interface StripeCheckoutCompletedPayment {
  email: string | null;
  stripeCustomerId: string | null;
  stripeSubscriptionId: string | null;
  stripePaymentIntentId: string | null;
  amountCents: number | null;
  currency: string | null;
}

/**
 * Webhook `checkout.session.completed` (pay-first branch): mark the claim paid.
 *
 * Requires both the claim token and the Stripe Checkout Session id to match
 * the pending row created by `createPendingClaim`. The claim token alone is
 * not sufficient proof of payment for *this* session — matching the session
 * id too ensures a webhook event can only ever mark paid the exact claim its
 * Stripe Checkout Session was created for.
 */
export async function markClaimPaid(
  admin: SupabaseClient,
  claimToken: string,
  stripeCheckoutSessionId: string,
  payment: StripeCheckoutCompletedPayment,
): Promise<{ id: string }> {
  const { data: claim, error: claimError } = await admin
    .from("checkout_claims")
    .select("id")
    .eq("claim_token", claimToken)
    .eq("stripe_checkout_session_id", stripeCheckoutSessionId)
    .maybeSingle();
  if (claimError) throw new Error(`Could not load checkout claim: ${claimError.message}`);
  if (!claim) throw new Error("Stripe checkout completed with an unknown claim token or session id.");

  const { data: updatedClaim, error: updateError } = await admin
    .from("checkout_claims")
    .update({
      email: payment.email,
      stripe_customer_id: payment.stripeCustomerId,
      stripe_subscription_id: payment.stripeSubscriptionId,
      stripe_payment_intent_id: payment.stripePaymentIntentId,
      amount_cents: payment.amountCents,
      currency: payment.currency ?? "usd",
      paid_at: new Date().toISOString(),
    })
    .eq("claim_token", claimToken)
    .eq("stripe_checkout_session_id", stripeCheckoutSessionId)
    .select("id")
    .maybeSingle();
  if (updateError) throw new Error(`Could not mark checkout claim paid: ${updateError.message}`);
  if (!updatedClaim) throw new Error("Checkout claim disappeared before it could be marked paid.");
  return updatedClaim as { id: string };
}

/**
 * claim-account step: attach the newly-created/signed-in auth user to the
 * claim. Single-assignment: only a paid, unclaimed claim with no
 * `auth_user_id` yet can be linked, so a leaked/reused claim token can never
 * reassign an already-linked claim to a second auth account.
 */
export async function linkClaimToAuthUser(
  admin: SupabaseClient,
  claimToken: string,
  userId: string,
): Promise<void> {
  const { data: linkedClaim, error } = await admin
    .from("checkout_claims")
    .update({ auth_user_id: userId })
    .eq("claim_token", claimToken)
    .not("paid_at", "is", null)
    .is("claimed_at", null)
    .is("auth_user_id", null)
    .select("id")
    .maybeSingle();
  if (error) throw new Error(`Signed in, but could not link this purchase: ${error.message}. Contact support.`);
  if (!linkedClaim) {
    throw new Error("Signed in, but this purchase could not be linked. It may still be confirming payment, already claimed, or no longer available. Contact support.");
  }
}

async function verifyCompanyMembership(
  admin: SupabaseClient,
  companyId: string,
  userId: string,
): Promise<boolean> {
  const { data, error } = await admin
    .from("company_members")
    .select("company_id")
    .eq("company_id", companyId)
    .eq("user_id", userId)
    .maybeSingle();
  if (error) throw new Error(`Could not verify company membership: ${error.message}`);
  return !!data;
}

export interface FinalizeClaimParams {
  companyId: string;
  userId: string;
}

/**
 * onboarding/finalize step: activate the real entitlement now that a company
 * exists. Returns `{ claimed: false }` when there is no paid, unclaimed claim
 * for this user (nothing to do) rather than treating that as an error.
 */
export async function finalizeCheckoutClaim(
  admin: SupabaseClient,
  params: FinalizeClaimParams,
): Promise<{ claimed: boolean }> {
  const isMember = await verifyCompanyMembership(admin, params.companyId, params.userId);
  if (!isMember) {
    throw new Error("Cannot activate checkout claim for a company this user does not belong to.");
  }

  const { data: claim, error: claimError } = await admin
    .from("checkout_claims")
    .select(
      "id, mode, plan_id, stripe_checkout_session_id, stripe_customer_id, stripe_subscription_id, stripe_payment_intent_id, amount_cents, currency, paid_at, claimed_at",
    )
    .eq("auth_user_id", params.userId)
    .is("claimed_at", null)
    .not("paid_at", "is", null)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (claimError) throw new Error(`Could not load checkout claim: ${claimError.message}`);
  if (!claim) return { claimed: false };

  await activateEntitlement(admin, {
    companyId: params.companyId,
    mode: claim.mode as "subscription" | "payment",
    planId: claim.plan_id,
    stripeSessionId: claim.stripe_checkout_session_id,
    stripeCustomerId: claim.stripe_customer_id,
    stripeSubscriptionId: claim.stripe_subscription_id,
    stripePaymentIntentId: claim.stripe_payment_intent_id,
    amountCents: claim.amount_cents,
    currency: claim.currency,
  });

  const { error: claimUpdateError } = await admin
    .from("checkout_claims")
    .update({ claimed_at: new Date().toISOString() })
    .eq("id", claim.id);
  if (claimUpdateError) {
    throw new Error(`Entitlement activated, but claim could not be marked claimed: ${claimUpdateError.message}`);
  }

  return { claimed: true };
}

/**
 * Webhook idempotency guard: first writer wins on the `webhook_events` unique
 * id. Returns true when this event id has already been recorded (duplicate
 * delivery) so the caller can skip reprocessing.
 */
export async function isDuplicateWebhookEvent(
  admin: SupabaseClient,
  event: { id: string; type: string; payload: unknown },
): Promise<boolean> {
  const { error } = await admin
    .from("webhook_events")
    .insert({ id: event.id, type: event.type, payload: event.payload });
  if (!error) return false;

  // Preserve idempotent duplicate handling, but do not accidentally swallow
  // unrelated database failures (permission issue, connectivity, schema drift).
  if (/duplicate key|unique constraint/i.test(error.message)) return true;
  throw new Error(`Could not record Stripe webhook event: ${error.message}`);
}

/** On processing failure, remove the idempotency marker so Stripe's retry reprocesses. */
export async function rollbackWebhookEvent(admin: SupabaseClient, eventId: string): Promise<void> {
  await admin.from("webhook_events").delete().eq("id", eventId);
}
