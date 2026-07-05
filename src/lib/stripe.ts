import crypto from "crypto";

/**
 * Minimal dependency-free Stripe client (REST + webhook signature verification).
 * We talk to the Stripe API directly with fetch so the app needs no extra npm
 * dependency. SERVER-ONLY: requires STRIPE_SECRET_KEY in the environment.
 */

const STRIPE_API = "https://api.stripe.com/v1";

export function stripeConfigured(): boolean {
  return !!process.env.STRIPE_SECRET_KEY;
}

/** Flatten a nested object into Stripe's form-encoded bracket notation. */
function encodeForm(obj: Record<string, unknown>, prefix = ""): string[] {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    if (value === undefined || value === null) continue;
    const k = prefix ? `${prefix}[${key}]` : key;
    if (Array.isArray(value)) {
      value.forEach((v, i) => {
        if (v && typeof v === "object") {
          parts.push(...encodeForm(v as Record<string, unknown>, `${k}[${i}]`));
        } else {
          parts.push(`${encodeURIComponent(`${k}[${i}]`)}=${encodeURIComponent(String(v))}`);
        }
      });
    } else if (typeof value === "object") {
      parts.push(...encodeForm(value as Record<string, unknown>, k));
    } else {
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(value))}`);
    }
  }
  return parts;
}

async function stripeRequest(
  method: "GET" | "POST",
  path: string,
  body?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) throw new Error("STRIPE_SECRET_KEY is not configured (server-only).");
  const res = await fetch(`${STRIPE_API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body ? encodeForm(body).join("&") : undefined,
  });
  const json = (await res.json()) as Record<string, unknown>;
  if (!res.ok) {
    const err = json?.error as { message?: string } | undefined;
    throw new Error(err?.message || `Stripe ${method} ${path} failed (${res.status}).`);
  }
  return json;
}

/**
 * Create a Stripe Checkout Session for a Mobi Estimates offer.
 *
 * Two shapes:
 *  • mode: "subscription" — the three monthly plans. When `couponId` is given it
 *    is a one-time-duration 50% coupon that discounts ONLY the first invoice; the
 *    customer is charged the discounted first month immediately and the regular
 *    price from month two onward. There is NO trial — no `trial_period_days`, no
 *    `trial_end`, no delayed billing. Payment is collected at checkout.
 *  • mode: "payment" — Pay Per Project. A single one-time $599 charge. No
 *    subscription is created, nothing renews, and no discount is applied.
 *
 * The first-month coupon is attached explicitly via `discounts`. Generic Stripe
 * promotion-code entry stays disabled so Pay Per Project can never receive a
 * discount and monthly discounts cannot drift from the approved offer.
 */
export async function createCheckoutSession(params: {
  priceId: string;
  mode: "subscription" | "payment";
  /** Omitted for a pay-first anonymous checkout — no account exists yet. */
  companyId?: string;
  planId: string | null;
  planCode: string;
  userId?: string;
  customerEmail?: string;
  /** One-time-duration 50% coupon id for the first month (subscription only). */
  couponId?: string;
  successUrl: string;
  cancelUrl: string;
  /** Pay-first checkout only: lets the webhook find the checkout_claims row
   *  once Stripe confirms payment. */
  claimToken?: string;
}): Promise<{ url: string; id: string }> {
  const metadata: Record<string, string> = {
    plan_code: params.planCode,
    plan_id: params.planId ?? "",
  };
  if (params.companyId) metadata.company_id = params.companyId;
  if (params.userId) metadata.user_id = params.userId;
  if (params.claimToken) metadata.claim_token = params.claimToken;

  const body: Record<string, unknown> = {
    mode: params.mode,
    line_items: [{ price: params.priceId, quantity: 1 }],
    success_url: params.successUrl,
    cancel_url: params.cancelUrl,
    customer_email: params.customerEmail,
    client_reference_id: params.companyId,
    metadata,
  };

  if (params.couponId) {
    // First-month 50% off, applied exactly once (coupon duration must be "once").
    body.discounts = [{ coupon: params.couponId }];
  }

  if (params.mode === "subscription") {
    // Carry identity onto the subscription. Deliberately NO trial settings.
    body.subscription_data = { metadata };
  } else {
    // One-time payment (Pay Per Project): carry identity onto the PaymentIntent.
    body.payment_intent_data = { metadata };
  }

  const session = await stripeRequest("POST", "/checkout/sessions", body);
  return { url: String(session.url), id: String(session.id) };
}

/**
 * Create a Stripe Billing Portal session so a customer can manage their
 * subscription (update card, cancel, view invoices). Requires the company's
 * stored stripe_customer_id.
 */
export async function createBillingPortalSession(params: {
  customerId: string;
  returnUrl: string;
}): Promise<{ url: string }> {
  const session = await stripeRequest("POST", "/billing_portal/sessions", {
    customer: params.customerId,
    return_url: params.returnUrl,
  });
  return { url: String(session.url) };
}

/**
 * Verify a Stripe webhook signature (HMAC-SHA256 of `${t}.${rawBody}`) and
 * return the parsed event. Throws on any mismatch. Equivalent to the Stripe
 * SDK's webhooks.constructEvent, implemented with Node crypto.
 */
export function verifyStripeSignature(
  rawBody: string,
  sigHeader: string | null,
  secret: string,
): Record<string, unknown> {
  if (!sigHeader) throw new Error("Missing Stripe-Signature header.");
  const fields: Record<string, string> = {};
  for (const part of sigHeader.split(",")) {
    const [k, v] = part.split("=");
    if (k && v) fields[k.trim()] = v.trim();
  }
  const timestamp = fields["t"];
  const v1 = fields["v1"];
  if (!timestamp || !v1) throw new Error("Malformed Stripe-Signature header.");

  const expected = crypto
    .createHmac("sha256", secret)
    .update(`${timestamp}.${rawBody}`, "utf8")
    .digest("hex");
  const a = Buffer.from(expected);
  const b = Buffer.from(v1);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    throw new Error("Signature verification failed.");
  }
  // Reject events older than 5 minutes (replay protection).
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - Number(timestamp)) > 300) {
    throw new Error("Timestamp outside tolerance.");
  }
  return JSON.parse(rawBody) as Record<string, unknown>;
}
