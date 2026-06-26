import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { requireUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { isApprovedOfferId } from "@/lib/pricing";
import { OnboardingForm } from "./OnboardingForm";

export const metadata: Metadata = {
  title: "Get started — Mobi Estimates",
  robots: { index: false },
};

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ plan?: string }>;
}) {
  const user = await requireUser();

  // Staff don't onboard a company; send them to the production dashboard.
  if (isStaff(user.role)) redirect("/admin");

  // Preserve a plan selected before onboarding so checkout resumes afterward.
  const { plan } = await searchParams;
  const selectedPlan = isApprovedOfferId(plan) ? plan : null;

  // Already onboarded → continue to checkout for the selected plan, else portal.
  const companyId = await getPrimaryCompanyId();
  if (companyId) redirect(selectedPlan ? `/start?plan=${selectedPlan}` : "/portal");

  return (
    <OnboardingForm
      defaultContactName={user.fullName ?? ""}
      defaultEmail={user.email ?? ""}
      selectedPlan={selectedPlan}
    />
  );
}
