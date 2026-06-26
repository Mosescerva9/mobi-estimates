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
 * Whether the company has at least one paid Pay Per Project order. This grants
 * limited authenticated portal access (view/submit the purchased estimate and
 * read prior orders) — it is NOT a subscription and confers no monthly status.
 */
export async function hasPayPerProjectAccess(companyId: string): Promise<boolean> {
  const supabase = await createClient();
  const { count } = await supabase
    .from("pay_per_project_orders")
    .select("id", { count: "exact", head: true })
    .eq("company_id", companyId)
    .eq("status", "paid");
  return (count ?? 0) > 0;
}

/**
 * Number of paid Pay Per Project credits not yet spent on a project. Each paid
 * $599 order is exactly one estimate; once consumed the customer must buy
 * another estimate or subscribe to submit again.
 */
export async function availablePayPerProjectCredits(companyId: string): Promise<number> {
  const supabase = await createClient();
  const { count } = await supabase
    .from("pay_per_project_orders")
    .select("id", { count: "exact", head: true })
    .eq("company_id", companyId)
    .eq("status", "paid")
    .is("consumed_project_id", null);
  return count ?? 0;
}

/**
 * Whether the company may access the portal at all: an active subscription OR at
 * least one paid Pay Per Project order.
 */
export async function hasPortalEntitlement(companyId: string): Promise<boolean> {
  if (await hasActiveSubscription(companyId)) return true;
  return hasPayPerProjectAccess(companyId);
}

/**
 * Whether the subscription paywall should be enforced. It activates
 * automatically once Stripe is configured, so the portal stays usable in the
 * pre-Stripe state and locks down the moment real billing is live.
 */
export function billingEnforced(): boolean {
  return !!process.env.STRIPE_SECRET_KEY;
}
