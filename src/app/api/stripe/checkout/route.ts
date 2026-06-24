import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getPrimaryCompanyId } from "@/lib/company";
import { createCheckoutSession, stripeConfigured } from "@/lib/stripe";

export const runtime = "nodejs";

/**
 * Creates a Stripe Checkout Session for the given plan and returns its URL.
 * Requires an authenticated user who has completed onboarding (has a company).
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

  let planCode: string | undefined;
  try {
    ({ planCode } = await request.json());
  } catch {
    /* ignore */
  }
  if (!planCode) {
    return NextResponse.json({ error: "Missing plan." }, { status: 400 });
  }

  const { data: plan } = await supabase
    .from("plans")
    .select("id, name, stripe_price_id")
    .eq("code", planCode)
    .maybeSingle();

  if (!plan) {
    return NextResponse.json({ error: "Unknown plan." }, { status: 400 });
  }
  if (!plan.stripe_price_id) {
    return NextResponse.json(
      { error: "This plan isn't available for checkout yet." },
      { status: 400 },
    );
  }

  const origin = new URL(request.url).origin;
  try {
    const { url } = await createCheckoutSession({
      priceId: plan.stripe_price_id,
      companyId,
      planId: plan.id,
      userId: user.id,
      customerEmail: user.email ?? undefined,
      successUrl: `${origin}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      cancelUrl: `${origin}/billing`,
    });
    return NextResponse.json({ url });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Could not start checkout.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
