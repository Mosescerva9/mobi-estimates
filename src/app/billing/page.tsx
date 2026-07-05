import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { requireUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { createClient } from "@/lib/supabase/server";
import { checkoutReadiness } from "@/lib/pricing";
import { BillingPlans } from "./BillingPlans";

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
  const { data: sub } = await supabase
    .from("subscriptions")
    .select("status")
    .eq("company_id", companyId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  // Plans, prices, and CTAs come from the centralized pricing config — never
  // hard-coded here — so this page always matches the public pricing page.
  return (
    <BillingPlans currentStatus={sub?.status ?? null} paymentsLive={checkoutReadiness()} />
  );
}
