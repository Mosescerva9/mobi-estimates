import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getPrimaryCompanyId } from "@/lib/company";
import { createCheckoutSession, stripeConfigured } from "@/lib/stripe";
import {
  FIRST_MONTH_COUPON_ENV,
  getOffer,
  getStripePriceId,
  isApprovedOfferId,
} from "@/lib/pricing";
import { publicBaseUrl } from "@/lib/site-url";

export const runtime = "nodejs";

/**
 * Creates a Stripe Checkout Session for an approved offer and returns its URL.
 * Requires an authenticated user who has completed onboarding (has a company).
 *
 * The plan identifier is validated SERVER-SIDE against the centralized pricing
 * config — a manipulated/unknown/legacy id can never reach Stripe. Prices, mode,
 * and the first-month discount are all derived from config, never from the client.
 */
export async function POST(request: Request) {
  if (!stripeConfigured()) {
    return NextResponse.json(
      { error: "Payments aren't configured yet. Please check back soon." },
      { status: 503 },
    );
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  }

  const companyId = await getPrimaryCompanyId();
  if (!companyId) {
    return NextResponse.json({ error: "Please finish setting up your company first." }, { status: 400 });
  }

  // Accept either { planCode } (legacy) or { plan } — both are the offer id.
  let raw: { plan?: unknown; planCode?: unknown } = {};
  try {
    raw = await request.json();
  } catch {
    /* ignore */
  }
  const planId = raw.plan ?? raw.planCode;
  if (!isApprovedOfferId(planId)) {
    return NextResponse.json({ error: "Unknown or unavailable plan." }, { status: 400 });
  }

  const offer = getOffer(planId);
  const priceId = getStripePriceId(offer);
  if (!priceId) {
    return NextResponse.json(
      { error: "This option isn't available for checkout yet." },
      { status: 400 },
    );
  }

  // Monthly plans must apply the 50%-off-first-month coupon. If it's not
  // configured we fail closed rather than charge full price while advertising
  // the discount.
  let couponId: string | undefined;
  if (offer.firstMonthDiscountApplies) {
    couponId = process.env[FIRST_MONTH_COUPON_ENV] || undefined;
    if (!couponId) {
      return NextResponse.json(
        { error: "The first-month discount isn't configured yet. Please check back soon." },
        { status: 503 },
      );
    }
  }

  // Keep subscriptions.plan_id (uuid FK) populated for the portal's display join.
  let dbPlanId: string | null = null;
  if (offer.recurring) {
    const { data: plan } = await supabase
      .from("plans")
      .select("id")
      .eq("code", offer.id)
      .maybeSingle();
    dbPlanId = plan?.id ?? null;
  }

  // Customer-facing return URLs must point at the canonical public site, not
  // the incoming request origin (which could be a preview/fake host).
  const origin = publicBaseUrl();
  try {
    const { url } = await createCheckoutSession({
      priceId,
      mode: offer.recurring ? "subscription" : "payment",
      companyId,
      planId: dbPlanId,
      planCode: offer.id,
      userId: user.id,
      customerEmail: user.email ?? undefined,
      couponId,
      successUrl: `${origin}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      cancelUrl: `${origin}/pricing`,
    });
    return NextResponse.json({ url });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Could not start checkout.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
