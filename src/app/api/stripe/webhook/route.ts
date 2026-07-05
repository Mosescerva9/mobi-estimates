import { NextResponse } from "next/server";
import { verifyStripeSignature } from "@/lib/stripe";
import { createAdminClient } from "@/lib/supabase/admin";
import { activateEntitlement } from "@/lib/entitlement";
import { emailConfigured, sendEmail, claimAccountEmailHtml, SITE_URL } from "@/lib/email";
import type { SupabaseClient } from "@supabase/supabase-js";

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
 * Pay-first checkout: no company_id exists yet. Records the confirmed payment
 * against its checkout_claims row and emails the customer a link to finish
 * account setup. /checkout/complete + finalizeClaim() do the rest once they
 * create an account and a company.
 */
async function recordPendingClaim(
  admin: SupabaseClient,
  claimToken: string,
  dataObject: Record<string, unknown>,
): Promise<void> {
  const { data: claim, error: claimError } = await admin
    .from("checkout_claims")
    .select("id")
    .eq("claim_token", claimToken)
    .maybeSingle();
  if (claimError) throw new Error(`Could not load checkout claim: ${claimError.message}`);
  if (!claim) throw new Error("Stripe checkout completed with an unknown claim token.");

  const customerDetails = dataObject.customer_details as { email?: string } | undefined;
  const email = customerDetails?.email ?? (dataObject.customer_email as string | undefined) ?? null;

  const { data: updatedClaim, error: updateError } = await admin
    .from("checkout_claims")
    .update({
      email,
      stripe_customer_id: (dataObject.customer as string) ?? null,
      stripe_subscription_id: (dataObject.subscription as string) ?? null,
      stripe_payment_intent_id: (dataObject.payment_intent as string) ?? null,
      amount_cents: typeof dataObject.amount_total === "number" ? dataObject.amount_total : null,
      currency: (dataObject.currency as string) ?? "usd",
      paid_at: new Date().toISOString(),
    })
    .eq("claim_token", claimToken)
    .select("id")
    .maybeSingle();
  if (updateError) throw new Error(`Could not mark checkout claim paid: ${updateError.message}`);
  if (!updatedClaim) throw new Error("Checkout claim disappeared before it could be marked paid.");

  if (email && emailConfigured()) {
    try {
      await sendEmail({
        to: email,
        subject: "Payment received — finish setting up your Mobi Estimates account",
        html: claimAccountEmailHtml(`${SITE_URL}/checkout/complete?token=${claimToken}`),
      });
    } catch (e) {
      // Best-effort: the paid row is already saved, so nothing is lost — the
      // browser redirect (same success_url) is the primary path anyway.
      console.error("Failed to send checkout claim email:", e);
    }
  }
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
        const mode = String(dataObject.mode ?? "") === "payment" ? "payment" : "subscription";

        if (!companyId) {
          // Pay-first checkout: no account exists yet. Stash the confirmed
          // payment against its claim instead of an entitlement row.
          if (meta.claim_token) {
            await recordPendingClaim(admin, meta.claim_token, dataObject);
          }
          break;
        }

        await activateEntitlement(admin, {
          companyId,
          mode,
          planId: meta.plan_id || null,
          stripeSessionId: String(dataObject.id),
          stripeCustomerId: (dataObject.customer as string) ?? null,
          stripeSubscriptionId: (dataObject.subscription as string) ?? null,
          stripePaymentIntentId: (dataObject.payment_intent as string) ?? null,
          amountCents: typeof dataObject.amount_total === "number" ? dataObject.amount_total : null,
          currency: (dataObject.currency as string) ?? "usd",
        });
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
