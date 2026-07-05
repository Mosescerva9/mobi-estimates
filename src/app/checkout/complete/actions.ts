"use server";

import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { activateEntitlement } from "@/lib/entitlement";

export interface ClaimActionResult {
  ok: boolean;
  message: string;
}

/**
 * Pay-first checkout, step 1: turn a confirmed-paid checkout_claims row into a
 * real account and sign the browser in. Company creation happens next via the
 * normal /onboarding flow; finalizeClaim() below completes the entitlement
 * once that company exists.
 */
export async function claimAccount(formData: FormData): Promise<ClaimActionResult> {
  const token = String(formData.get("token") || "");
  const fullName = String(formData.get("fullName") || "").trim();
  const password = String(formData.get("password") || "");

  if (!token) return { ok: false, message: "Missing claim link." };
  if (!fullName) return { ok: false, message: "Please enter your name." };
  if (password.length < 8) return { ok: false, message: "Use at least 8 characters for your password." };

  const admin = createAdminClient();
  const { data: claim } = await admin
    .from("checkout_claims")
    .select("email, paid_at, claimed_at, auth_user_id")
    .eq("claim_token", token)
    .maybeSingle();

  if (!claim) return { ok: false, message: "We couldn't find that purchase. Contact support if this persists." };
  if (!claim.paid_at) return { ok: false, message: "Still confirming your payment — refresh in a few seconds." };
  if (!claim.email) return { ok: false, message: "We couldn't determine the email used at checkout. Contact support." };

  const supabase = await createClient();

  // Already has an auth account linked (e.g. re-submitted the form) — just sign in.
  if (!claim.auth_user_id) {
    const { error: createErr } = await admin.auth.admin.createUser({
      email: claim.email,
      password,
      email_confirm: true,
      user_metadata: { full_name: fullName },
    });
    if (createErr) {
      // If the checkout email already belongs to a Mobi account, treat the
      // password field as "enter your existing password" and let the customer
      // self-service attach the paid claim after sign-in. Other create failures
      // will usually also fail sign-in and return a clear message below.
      const { error: existingSignInErr } = await supabase.auth.signInWithPassword({
        email: claim.email,
        password,
      });
      if (existingSignInErr) {
        return {
          ok: false,
          message: `Could not create or sign in to your account (${createErr.message}). If you already have a Mobi Estimates account, enter that account password here or contact support to link this purchase.`,
        };
      }
    }
  }

  const { error: signInErr } = await supabase.auth.signInWithPassword({
    email: claim.email,
    password,
  });
  if (signInErr) {
    return { ok: false, message: `Account created but sign-in failed: ${signInErr.message}. Try logging in.` };
  }

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user) {
    const { error: linkError } = await admin
      .from("checkout_claims")
      .update({ auth_user_id: user.id })
      .eq("claim_token", token);
    if (linkError) {
      return { ok: false, message: `Signed in, but could not link this purchase: ${linkError.message}. Contact support.` };
    }
  }

  return { ok: true, message: "Account created." };
}

/**
 * Pay-first checkout, step 2: called right after onboarding creates the
 * company. If this user has a paid, unclaimed checkout, activate the real
 * entitlement (subscriptions / pay_per_project_orders) now that a company_id
 * finally exists, using the same shared helper the webhook uses.
 */
export async function finalizeClaim(companyId: string): Promise<{ claimed: boolean }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { claimed: false };

  const admin = createAdminClient();
  const { data: membership, error: membershipError } = await admin
    .from("company_members")
    .select("company_id")
    .eq("company_id", companyId)
    .eq("user_id", user.id)
    .maybeSingle();
  if (membershipError) throw new Error(`Could not verify company membership: ${membershipError.message}`);
  if (!membership) throw new Error("Cannot activate checkout claim for a company this user does not belong to.");

  const { data: claim, error: claimError } = await admin
    .from("checkout_claims")
    .select(
      "id, mode, plan_id, stripe_checkout_session_id, stripe_customer_id, stripe_subscription_id, stripe_payment_intent_id, amount_cents, currency, paid_at, claimed_at",
    )
    .eq("auth_user_id", user.id)
    .is("claimed_at", null)
    .not("paid_at", "is", null)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (claimError) throw new Error(`Could not load checkout claim: ${claimError.message}`);

  if (!claim) return { claimed: false };

  await activateEntitlement(admin, {
    companyId,
    mode: claim.mode as "subscription" | "payment",
    planId: claim.plan_id,
    stripeSessionId: claim.stripe_checkout_session_id,
    stripeCustomerId: claim.stripe_customer_id,
    stripeSubscriptionId: claim.stripe_subscription_id,
    stripePaymentIntentId: claim.stripe_payment_intent_id,
    amountCents: claim.amount_cents,
    currency: claim.currency,
  });

  const { error: claimUpdateError } = await admin
    .from("checkout_claims")
    .update({ claimed_at: new Date().toISOString() })
    .eq("id", claim.id);
  if (claimUpdateError) throw new Error(`Entitlement activated, but claim could not be marked claimed: ${claimUpdateError.message}`);

  return { claimed: true };
}
