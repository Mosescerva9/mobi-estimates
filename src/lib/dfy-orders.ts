import type { SupabaseClient } from "@supabase/supabase-js";
import type { DfyIntake } from "@/lib/dfy-intake";

/**
 * Pure, DB-only state machine for DFY "Estimator Business Setup" orders.
 * Mirrors src/lib/checkout-claims.ts: route handlers own HTTP, redirects, and
 * email; this module owns the row-level invariants that must hold for money to
 * be safely recorded against an intake token.
 *
 * State machine: pending -> paid -> intake_submitted -> fulfilled
 * (refunded is terminal and set by staff directly in the database).
 */

/** /dfy/start: record a pending order before redirecting to Stripe Checkout. */
export async function createPendingOrder(
  admin: SupabaseClient,
  params: {
    orderToken: string;
    stripeCheckoutSessionId: string;
    offerCode: string;
  },
): Promise<void> {
  const { error } = await admin.from("dfy_orders").insert({
    order_token: params.orderToken,
    stripe_checkout_session_id: params.stripeCheckoutSessionId,
    offer_code: params.offerCode,
    status: "pending",
  });
  if (error) throw new Error(`Could not create DFY order: ${error.message}`);
}

export interface DfyStripePayment {
  email: string | null;
  stripeCustomerId: string | null;
  stripePaymentIntentId: string | null;
  amountCents: number | null;
  currency: string | null;
}

/**
 * Webhook `checkout.session.completed` (dfy branch): mark the order paid.
 * Requires BOTH the order token and the Checkout Session id to match the
 * pending row created by createPendingOrder — a webhook event can only ever
 * mark paid the exact order its Stripe session was created for.
 */
export async function markOrderPaid(
  admin: SupabaseClient,
  orderToken: string,
  stripeCheckoutSessionId: string,
  payment: DfyStripePayment,
): Promise<{ id: string; email: string | null }> {
  const { data: updated, error } = await admin
    .from("dfy_orders")
    .update({
      email: payment.email,
      stripe_customer_id: payment.stripeCustomerId,
      stripe_payment_intent_id: payment.stripePaymentIntentId,
      amount_cents: payment.amountCents,
      currency: payment.currency ?? "usd",
      status: "paid",
      paid_at: new Date().toISOString(),
    })
    .eq("order_token", orderToken)
    .eq("stripe_checkout_session_id", stripeCheckoutSessionId)
    .eq("status", "pending")
    .select("id, email")
    .maybeSingle();
  if (error) throw new Error(`Could not mark DFY order paid: ${error.message}`);
  if (!updated) {
    throw new Error("Stripe checkout completed for an unknown or already-processed DFY order.");
  }
  return updated as { id: string; email: string | null };
}

/**
 * Intake form submission: attach the buyer's intake answers to their PAID
 * order. Only a paid order that has not already submitted intake can be
 * written, so a leaked token can never overwrite a completed intake, and an
 * unpaid token can never be used to fabricate an order.
 */
export async function saveOrderIntake(
  admin: SupabaseClient,
  orderToken: string,
  intake: DfyIntake,
): Promise<void> {
  const { data: updated, error } = await admin
    .from("dfy_orders")
    .update({
      intake,
      intake_submitted_at: new Date().toISOString(),
      status: "intake_submitted",
    })
    .eq("order_token", orderToken)
    .eq("status", "paid")
    .not("paid_at", "is", null)
    .select("id")
    .maybeSingle();
  if (error) throw new Error(`Could not save DFY intake: ${error.message}`);
  if (!updated) {
    throw new Error("This intake link is invalid, unpaid, or has already been submitted.");
  }
}
