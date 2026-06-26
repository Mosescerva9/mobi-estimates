import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getSessionUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { createCheckoutSession, stripeConfigured } from "@/lib/stripe";
import {
  FIRST_MONTH_COUPON_ENV,
  getOffer,
  getStripePriceId,
  isApprovedOfferId,
} from "@/lib/pricing";

export const runtime = "nodejs";

/**
 * Selected-plan handoff. A visitor reaches `/start?plan=<id>` from a pricing CTA;
 * we preserve the chosen plan through account creation / sign-in / onboarding and
 * then into the correct Stripe checkout.
 *
 * The plan id is validated SERVER-SIDE against the centralized config, so a
 * manipulated or legacy id can never start a checkout — it is redirected back to
 * pricing instead.
 */
export async function GET(request: Request) {
  const origin = new URL(request.url).origin;
  const url = new URL(request.url);
  const plan = url.searchParams.get("plan");

  const back = (path: string) => NextResponse.redirect(new URL(path, origin));

  if (!isApprovedOfferId(plan)) {
    return back("/pricing");
  }
  const offer = getOffer(plan);

  // Must be signed in to purchase — carry the plan through signup, then back here.
  const user = await getSessionUser();
  if (!user) {
    return back(`/signup?plan=${offer.id}`);
  }
  // Staff don't purchase plans.
  if (isStaff(user.role)) {
    return back("/admin");
  }

  // Must have a company (onboarding) before checkout — carry the plan forward.
  const companyId = await getPrimaryCompanyId();
  if (!companyId) {
    return back(`/onboarding?plan=${offer.id}`);
  }

  // Payments not live yet → let them review plans rather than hit a dead checkout.
  if (!stripeConfigured()) {
    return back("/pricing?notice=checkout_soon");
  }

  const priceId = getStripePriceId(offer);
  if (!priceId) {
    return back("/pricing?notice=checkout_soon");
  }

  let couponId: string | undefined;
  if (offer.firstMonthDiscountApplies) {
    couponId = process.env[FIRST_MONTH_COUPON_ENV] || undefined;
    if (!couponId) {
      return back("/pricing?notice=checkout_soon");
    }
  }

  // Keep subscriptions.plan_id (uuid FK) populated for the portal's display join.
  let dbPlanId: string | null = null;
  if (offer.recurring) {
    const supabase = await createClient();
    const { data: planRow } = await supabase
      .from("plans")
      .select("id")
      .eq("code", offer.id)
      .maybeSingle();
    dbPlanId = planRow?.id ?? null;
  }

  try {
    const { url: checkoutUrl } = await createCheckoutSession({
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
    return NextResponse.redirect(checkoutUrl);
  } catch {
    return back("/pricing?notice=checkout_error");
  }
}
