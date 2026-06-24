import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { requireUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { createClient } from "@/lib/supabase/server";
import { stripeConfigured } from "@/lib/stripe";
import { BillingPlans, type PlanCard } from "./BillingPlans";

export const metadata: Metadata = {
  title: "Choose your plan — Mobi Estimates",
  robots: { index: false },
};

export default async function BillingPage() {
  const user = await requireUser();
  if (isStaff(user.role)) redirect("/admin");

  const companyId = await getPrimaryCompanyId();
  if (!companyId) redirect("/onboarding");

  const supabase = await createClient();

  const { data: plans } = await supabase
    .from("plans")
    .select("code, name, description, price_cents, currency, active_capacity, max_active_projects, turnaround_note, stripe_price_id")
    .eq("is_public", true)
    .order("sort_order", { ascending: true });

  const { data: sub } = await supabase
    .from("subscriptions")
    .select("status")
    .eq("company_id", companyId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const cards: PlanCard[] = (plans ?? []).map((p) => ({
    code: p.code,
    name: p.name,
    description: p.description,
    priceCents: p.price_cents,
    currency: p.currency,
    activeCapacity: p.active_capacity,
    maxActiveProjects: p.max_active_projects,
    turnaroundNote: p.turnaround_note,
    available: !!p.stripe_price_id,
  }));

  return (
    <BillingPlans
      plans={cards}
      currentStatus={sub?.status ?? null}
      paymentsLive={stripeConfigured()}
    />
  );
}
