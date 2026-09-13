import { NextResponse } from "next/server";
import crypto from "crypto";
import { createAdminClient } from "@/lib/supabase/admin";
import { createCheckoutSession } from "@/lib/stripe";
import { DFY_OFFER, dfyCheckoutReady, getDfyStripePriceId } from "@/lib/dfy-offer";
import { createPendingOrder } from "@/lib/dfy-orders";
import { portalBaseUrl } from "@/lib/site-url";

export const runtime = "nodejs";

/**
 * DFY "Estimator Business Setup" checkout handoff. Linked from /dfy (and from
 * the community/course). Always an anonymous pay-first checkout: buyers are
 * course members, not portal users, so no account or company is involved.
 *
 * The pending dfy_orders row is created BEFORE redirecting to Stripe so the
 * webhook (the source of truth) can match token + session id exactly.
 */
export async function GET(request: Request) {
  const origin = new URL(request.url).origin;
  const back = (path: string) => NextResponse.redirect(new URL(path, origin));

  if (!dfyCheckoutReady()) {
    return back("/dfy?notice=checkout_soon");
  }

  const priceId = getDfyStripePriceId();
  if (!priceId) {
    return back("/dfy?notice=checkout_soon");
  }

  const baseUrl = portalBaseUrl();
  const orderToken = crypto.randomBytes(32).toString("base64url");

  try {
    const { url: checkoutUrl, id: sessionId } = await createCheckoutSession({
      priceId,
      mode: "payment",
      planId: null,
      planCode: DFY_OFFER.code,
      // Reuses the claim_token metadata slot; the webhook routes on plan_code
      // to the dfy handler before the generic claim branch.
      claimToken: orderToken,
      successUrl: `${baseUrl}/dfy/success`,
      cancelUrl: `${baseUrl}/dfy`,
    });

    const admin = createAdminClient();
    await createPendingOrder(admin, {
      orderToken,
      stripeCheckoutSessionId: sessionId,
      offerCode: DFY_OFFER.code,
    });

    return NextResponse.redirect(checkoutUrl);
  } catch {
    return back("/dfy?notice=checkout_error");
  }
}
