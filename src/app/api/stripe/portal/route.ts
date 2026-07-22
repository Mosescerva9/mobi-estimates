import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getPrimaryCompanyId } from "@/lib/company";
import { createBillingPortalSession, stripeConfigured } from "@/lib/stripe";
import { portalBaseUrl } from "@/lib/site-url";

export const runtime = "nodejs";

/**
 * Creates a Stripe Billing Portal session for the caller's company and returns
 * its URL. Requires an authenticated user whose company has a Stripe customer
 * id (set by the checkout webhook).
 */
export async function POST() {
  if (!stripeConfigured()) {
    return NextResponse.json({ error: "Billing isn't configured yet." }, { status: 503 });
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
    return NextResponse.json({ error: "No company found." }, { status: 400 });
  }

  // Find the most recent subscription with a Stripe customer id (RLS: members read their own).
  const { data: sub } = await supabase
    .from("subscriptions")
    .select("stripe_customer_id")
    .eq("company_id", companyId)
    .not("stripe_customer_id", "is", null)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (!sub?.stripe_customer_id) {
    return NextResponse.json(
      { error: "No billing account yet. Choose a plan first.", redirect: "/billing" },
      { status: 400 },
    );
  }

  // Return the customer to the canonical portal, not the request origin.
  const origin = portalBaseUrl();
  try {
    const { url } = await createBillingPortalSession({
      customerId: sub.stripe_customer_id,
      returnUrl: `${origin}/portal/subscription`,
    });
    return NextResponse.json({ url });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Could not open billing portal.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
