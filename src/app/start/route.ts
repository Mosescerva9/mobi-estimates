import { NextResponse } from "next/server";
import crypto from "crypto";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getSessionUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { createCheckoutSession, stripeConfigured } from "@/lib/stripe";
import {
  getOffer,
  getStripePriceId,
  isApprovedOfferId,
} from "@/lib/pricing";
import { createPendingClaim } from "@/lib/checkout-claims";
import { portalBaseUrl } from "@/lib/site-url";

export const runtime = "nodejs";

/**
 * Selected-plan handoff. A visitor reaches `/start?plan=<id>` from a pricing CTA.
 *
 * The plan id is validated SERVER-SIDE against the centralized config, so a
 * manipulated or legacy id can never start a checkout — it is redirected back to
 * pricing instead.
 *
 * Two paths:
 *  • Anonymous visitor (the normal case from the public pricing page): pay
 *    first. Stripe collects the email; a `checkout_claims` row lets
 *    /checkout/complete finish account creation once the webhook confirms
 *    payment.
 *  • Signed-in client (e.g. adding/changing a plan from inside the portal):
 *    unchanged — must have a company before checkout.
 */
export async function GET(request: Request) {
  const origin = new URL(request.url).origin;
  const url = new URL(request.url);
  const plan = url.searchParams.get("plan");

  // Internal same-app redirects follow the request origin; Stripe return URLs
  // (success/cancel) must resolve to the canonical portal instead.
  const baseUrl = portalBaseUrl();
  const back = (path: string) => NextResponse.redirect(new URL(path, origin));

  if (!isApprovedOfferId(plan)) {
    return back("/pricing");
  }
  const offer = getOffer(plan);

  // Payments not live yet → let them review plans rather than hit a dead checkout.
  if (!stripeConfigured()) {
    return back("/pricing?notice=checkout_soon");
  }

  const priceId = getStripePriceId(offer);
  if (!priceId) {
    return back("/pricing?notice=checkout_soon");
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

  const user = await getSessionUser();

  if (!user) {
    // Anonymous visitor from the public pricing page: pay first. Stripe
    // collects the email during checkout; the claim token lets
    // /checkout/complete finish account creation once the webhook confirms
    // payment.
    const claimToken = crypto.randomBytes(32).toString("base64url");
    try {
      const { url: checkoutUrl, id: sessionId } = await createCheckoutSession({
        priceId,
        mode: offer.recurring ? "subscription" : "payment",
        planId: dbPlanId,
        planCode: offer.id,
        claimToken,
        successUrl: `${baseUrl}/checkout/complete?token=${claimToken}`,
        cancelUrl: `${baseUrl}/pricing`,
      });

      const admin = createAdminClient();
      await createPendingClaim(admin, {
        claimToken,
        stripeCheckoutSessionId: sessionId,
        mode: offer.recurring ? "subscription" : "payment",
        planCode: offer.id,
        planId: dbPlanId,
      });

      return NextResponse.redirect(checkoutUrl);
    } catch {
      return back("/pricing?notice=checkout_error");
    }
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

  try {
    const { url: checkoutUrl } = await createCheckoutSession({
      priceId,
      mode: offer.recurring ? "subscription" : "payment",
      companyId,
      planId: dbPlanId,
      planCode: offer.id,
      userId: user.id,
      customerEmail: user.email ?? undefined,
      successUrl: `${baseUrl}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      cancelUrl: `${baseUrl}/pricing`,
    });
    return NextResponse.redirect(checkoutUrl);
  } catch {
    return back("/pricing?notice=checkout_error");
  }
}
