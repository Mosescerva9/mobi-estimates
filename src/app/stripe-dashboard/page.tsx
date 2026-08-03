import type { Metadata } from "next";
import StripeDashboard from "@/components/stripe-dashboard/StripeDashboard";

// Static, indexing-suppressed VISUAL DEMONSTRATION. This route renders SAMPLE
// DATA only — it is not a live Stripe account and never connects to Stripe.
// Note: Next's structured `robots.nocache` emits the wrong directive string,
// so the exact robots value is set via `other`.
export const metadata: Metadata = {
  title: "Stripe Dashboard Demo | Mobi Estimates",
  description:
    "A visual demonstration of a Stripe-style dashboard using synthetic sample data. Not a live Stripe account.",
  // Unset the layout's structured robots so only the exact string below renders.
  robots: null,
  other: { robots: "noindex, nofollow, noarchive" },
};

export const dynamic = "force-static";

export default function StripeDashboardPage() {
  return <StripeDashboard />;
}
