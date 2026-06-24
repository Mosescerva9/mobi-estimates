import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { requireUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { OnboardingForm } from "./OnboardingForm";

export const metadata: Metadata = {
  title: "Get started — Mobi Estimates",
  robots: { index: false },
};

export default async function OnboardingPage() {
  const user = await requireUser();

  // Staff don't onboard a company; send them to the production dashboard.
  if (isStaff(user.role)) redirect("/admin");

  // Already onboarded → straight to the portal.
  const companyId = await getPrimaryCompanyId();
  if (companyId) redirect("/portal");

  return (
    <OnboardingForm
      defaultContactName={user.fullName ?? ""}
      defaultEmail={user.email ?? ""}
    />
  );
}
