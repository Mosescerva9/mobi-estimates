import { NextResponse } from "next/server";
import { verifyStripeSignature } from "@/lib/stripe";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Map Stripe subscription status → our subscription_status enum.
 * Mobi Estimates does not offer trials, so no `trialing` status is expected or
 * handled — any unexpected status falls through to the safe default ("pending").
 */
function mapStatus(stripeStatus: string): string {
  switch (stripeStatus) {
    case "active":
      return "active";
    case "past_due":
    case "unpaid":
      return "past_due";
    case "canceled":
      return "canceled";
    case "incomplete_expired":
      return "canceled";
    case "paused":
      return "suspended";
    case "incomplete":
    default:
      return "pending";
  }
}

function isoFromUnix(seconds: unknown): string | null {
  return typeof seconds === "number" ? new Date(seconds * 1000).toISOString() : null;
}

/**
 * Verified, idempotent Stripe webhook. Writes subscription state with the
 * service-role client (bypasses RLS). Never trusts the success redirect as
 * proof of payment — this endpoint is the source of truth.
 */
export async function POST(request: Request) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "Webhook not configured." }, { status: 503 });
  }

  const raw = await request.text();
  let event: Record<string, unknown>;
  try {
    event = verifyStripeSignature(raw, request.headers.get("stripe-signature"), secret);
  } catch (e) {
    const message = e instanceof Error ? e.message : "Invalid signature.";
    return NextResponse.json({ error: message }, { status: 400 });
  }

  const admin = createAdminClient();
  const eventId = String(event.id);
  const eventType = String(event.type);

  // Idempotency: first writer wins. A duplicate delivery hits the unique PK and
  // is acknowledged without reprocessing.
  const { error: dupErr } = await admin
    .from("webhook_events")
    .insert({ id: eventId, type: eventType, payload: event });
  if (dupErr) {
    return NextResponse.json({ received: true, duplicate: true });
  }

  const dataObject = (event.data as { object?: Record<string, unknown> })?.object ?? {};

  try {
    switch (eventType) {
      case "checkout.session.completed": {
        const meta = (dataObject.metadata as Record<string, string>) ?? {};
        const companyId = meta.company_id;
        const mode = String(dataObject.mode ?? "");
        if (!companyId) break;

        if (mode === "payment") {
          // Pay Per Project: a one-time purchase. Record it as a single order —
          // it does NOT create a subscription and nothing renews.
          await admin.from("pay_per_project_orders").upsert(
            {
              company_id: companyId,
              stripe_session_id: String(dataObject.id),
              stripe_payment_intent_id: (dataObject.payment_intent as string) ?? null,
              stripe_customer_id: (dataObject.customer as string) ?? null,
              amount_cents:
                typeof dataObject.amount_total === "number" ? dataObject.amount_total : null,
              currency: (dataObject.currency as string) ?? "usd",
              status: "paid",
            },
            { onConflict: "stripe_session_id" },
          );
        } else {
          // Monthly subscription: activate after verified payment.
          await admin.from("subscriptions").upsert(
            {
              company_id: companyId,
              plan_id: meta.plan_id || null,
              status: "active",
              stripe_customer_id: (dataObject.customer as string) ?? null,
              stripe_subscription_id: (dataObject.subscription as string) ?? null,
            },
            { onConflict: "stripe_subscription_id" },
          );
        }
        break;
      }
      case "customer.subscription.created":
      case "customer.subscription.updated":
      case "customer.subscription.deleted": {
        const subId = String(dataObject.id);
        const companyId = (dataObject.metadata as Record<string, string>)?.company_id;
        const status =
          eventType === "customer.subscription.deleted"
            ? "canceled"
            : mapStatus(String(dataObject.status));
        const patch = {
          status,
          stripe_customer_id: (dataObject.customer as string) ?? null,
          current_period_start: isoFromUnix(dataObject.current_period_start),
          current_period_end: isoFromUnix(dataObject.current_period_end),
          cancel_at_period_end: !!dataObject.cancel_at_period_end,
        };
        const { data: existing } = await admin
          .from("subscriptions")
          .select("id")
          .eq("stripe_subscription_id", subId)
          .maybeSingle();
        if (existing) {
          await admin.from("subscriptions").update(patch).eq("stripe_subscription_id", subId);
        } else if (companyId) {
          await admin
            .from("subscriptions")
            .upsert(
              { company_id: companyId, stripe_subscription_id: subId, ...patch },
              { onConflict: "stripe_subscription_id" },
            );
        }
        break;
      }
      case "invoice.payment_failed": {
        const subId = dataObject.subscription as string | undefined;
        if (subId) {
          await admin
            .from("subscriptions")
            .update({ status: "past_due" })
            .eq("stripe_subscription_id", subId);
        }
        break;
      }
      default:
        break;
    }
  } catch (e) {
    // Allow Stripe to retry: remove the idempotency marker so the retry reprocesses.
    await admin.from("webhook_events").delete().eq("id", eventId);
    const message = e instanceof Error ? e.message : "Processing error.";
    return NextResponse.json({ error: message }, { status: 500 });
  }

  return NextResponse.json({ received: true });
}
