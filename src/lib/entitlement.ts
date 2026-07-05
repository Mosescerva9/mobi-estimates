import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Activates a company's entitlement from confirmed Stripe payment data. Shared
 * by the webhook (normal signed-in-first checkout) and the pay-first claim
 * finalize route, so there is exactly one place that writes these rows.
 */
export async function activateEntitlement(
  admin: SupabaseClient,
  params: {
    companyId: string;
    mode: "subscription" | "payment";
    planId: string | null;
    stripeSessionId: string | null;
    stripeCustomerId: string | null;
    stripeSubscriptionId?: string | null;
    stripePaymentIntentId?: string | null;
    amountCents?: number | null;
    currency?: string | null;
  },
): Promise<void> {
  if (params.mode === "payment") {
    if (!params.stripeSessionId) {
      throw new Error("Cannot activate Pay Per Project entitlement without a Stripe Checkout Session id.");
    }

    const { error } = await admin.from("pay_per_project_orders").upsert(
      {
        company_id: params.companyId,
        stripe_session_id: params.stripeSessionId,
        stripe_payment_intent_id: params.stripePaymentIntentId ?? null,
        stripe_customer_id: params.stripeCustomerId,
        amount_cents: params.amountCents ?? null,
        currency: params.currency ?? "usd",
        status: "paid",
      },
      { onConflict: "stripe_session_id" },
    );
    if (error) throw new Error(`Could not activate Pay Per Project entitlement: ${error.message}`);
    return;
  }

  if (!params.stripeSubscriptionId) {
    throw new Error("Cannot activate subscription entitlement without a Stripe Subscription id.");
  }

  const { error } = await admin.from("subscriptions").upsert(
    {
      company_id: params.companyId,
      plan_id: params.planId,
      status: "active",
      stripe_customer_id: params.stripeCustomerId,
      stripe_subscription_id: params.stripeSubscriptionId,
    },
    { onConflict: "stripe_subscription_id" },
  );
  if (error) throw new Error(`Could not activate subscription entitlement: ${error.message}`);
}
