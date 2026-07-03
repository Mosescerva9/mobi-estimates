import Link from "next/link";
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getSessionUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { MobiWordmark } from "@/components/PricingCards";

export const metadata: Metadata = {
  title: "Mobi Estimates — Construction estimating for contractors",
  description:
    "Mobi Estimates provides AI-assisted construction estimates and takeoffs — independently audited, deterministically checked, and reconciled before you review and approve them — so contractors can submit more bids. Choose a monthly plan or order one estimate.",
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
};

export default async function Home() {
  const user = await getSessionUser();

  // Signed-in users go where they belong; anonymous visitors see the landing page.
  if (user) {
    if (isStaff(user.role)) redirect("/admin");
    const companyId = await getPrimaryCompanyId();
    redirect(companyId ? "/portal" : "/onboarding");
  }

  return (
    <main className="min-h-screen bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <MobiWordmark />
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/pricing" className="font-medium text-slate-600 hover:text-navy">
            Pricing
          </Link>
          <Link href="/login" className="font-medium text-slate-600 hover:text-navy">
            Sign in
          </Link>
        </nav>
      </header>

      <section className="mx-auto max-w-6xl px-6 py-16 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center rounded-full bg-brand/5 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-brand">
            Construction estimating for contractors
          </span>
          <h1 className="mt-5 text-balance text-4xl font-bold leading-tight text-navy sm:text-5xl">
            Professional construction estimates in as little as 48 hours
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-slate-600">
            Upload your plans online and receive an AI-assisted,
            independently audited, contractor-ready estimate for your review
            and approval — without a sales call or a lengthy onboarding
            process.
          </p>

          {/* One primary call to action — sends visitors to pricing to choose. */}
          <div className="mt-8 flex flex-col items-center gap-3">
            <Link
              href="/pricing"
              className="rounded-full bg-brand px-8 py-3.5 text-base font-semibold text-white transition hover:bg-brand-dark focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30"
            >
              Join Now
            </Link>
            <p className="text-sm text-slate-500">
              View plans and get 50% off your first month.
            </p>
          </div>

          {/* Honest qualification — not an unconditional 48-hour guarantee. */}
          <p className="mx-auto mt-6 max-w-xl text-xs leading-relaxed text-slate-500">
            Most standard-scope estimates are delivered within 48 hours after all
            required plans, documents, and project information are received. Larger
            or unusually complex projects may require a confirmed delivery timeline.
          </p>
        </div>

        <div className="mx-auto mt-16 grid max-w-4xl gap-6 sm:grid-cols-3">
          {[
            ["Monthly estimating support", "Reserve estimating capacity each month so you can keep bidding."],
            ["Pay-per-project estimating", "Need just one? Order a single estimate for a one-time $599 price."],
            ["AI-assisted, independently audited", "Estimates and takeoffs generated with AI, checked with deterministic audits and reconciliation, and yours to review before final approval."],
          ].map(([title, body]) => (
            <div key={title} className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-left">
              <h2 className="text-base font-bold text-navy">{title}</h2>
              <p className="mt-2 text-sm text-slate-600">{body}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
