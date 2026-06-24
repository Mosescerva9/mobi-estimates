import { createClient } from "@/lib/supabase/server";

export interface ActiveSubscription {
  id: string;
  status: string;
  plan_id: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

/**
 * Returns the company's current active subscription, or null. RLS lets a member
 * read their own company's subscription (subscriptions_select policy).
 */
export async function getActiveSubscription(
  companyId: string,
): Promise<ActiveSubscription | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("subscriptions")
    .select("id, status, plan_id, current_period_end, cancel_at_period_end")
    .eq("company_id", companyId)
    .eq("status", "active")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return (data as ActiveSubscription) ?? null;
}

export async function hasActiveSubscription(companyId: string): Promise<boolean> {
  return (await getActiveSubscription(companyId)) !== null;
}

/**
 * Whether the subscription paywall should be enforced. It activates
 * automatically once Stripe is configured, so the portal stays usable in the
 * pre-Stripe state and locks down the moment real billing is live.
 */
export function billingEnforced(): boolean {
  return !!process.env.STRIPE_SECRET_KEY;
}
