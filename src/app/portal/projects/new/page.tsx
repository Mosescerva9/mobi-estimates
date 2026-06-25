import type { Metadata } from "next";
import { NewProjectForm } from "./NewProjectForm";

export const metadata: Metadata = {
  title: "Submit a project — Mobi Estimates",
  robots: { index: false },
};

// Auth, company, and subscription gating are handled by the portal layout
// (requireUser + onboarding/paywall redirects), so this route just renders the form.
export default function NewProjectPage() {
  return <NewProjectForm />;
}
