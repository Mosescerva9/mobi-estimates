import Link from "next/link";
import type { Metadata } from "next";
import { DFY_OFFER, dfyCheckoutReady } from "@/lib/dfy-offer";
import { formatUSD } from "@/lib/pricing";

export const metadata: Metadata = {
  title: "Estimator Business Setup (Done-For-You)",
  description:
    "A one-time, done-for-you setup of your freelance construction-estimating business: onboarding call, pricing worksheet, templates, AI prompt library, and client portal workflow. Education and setup only — no income is promised.",
  // Sold via the community/course, not public search — keep it out of the
  // contractor-facing marketing site's indexed surface.
  robots: { index: false, follow: false },
};

export default async function DfyPage({
  searchParams,
}: {
  searchParams: Promise<{ notice?: string }>;
}) {
  const { notice } = await searchParams;
  const noticeText =
    notice === "checkout_soon"
      ? "Checkout is being finalized. You can review what's included now — purchasing goes live shortly."
      : notice === "checkout_error"
        ? "We couldn't start checkout just now. Please try again in a moment."
        : null;
  const ready = dfyCheckoutReady();

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12">
      <div className="mx-auto w-full max-w-3xl">
        <header className="text-center">
          <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            One-time setup · {formatUSD(DFY_OFFER.amountCents)}
          </p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">{DFY_OFFER.name}</h1>
          <p className="mx-auto mt-3 max-w-2xl text-slate-600">
            We set up your freelance construction-estimating business with you — pricing,
            templates, AI workflows, and a client portal — so you start from a working
            system instead of a blank page.
          </p>
        </header>

        {noticeText && (
          <p className="mx-auto mt-6 max-w-2xl rounded-lg border border-slate-300 bg-white px-4 py-3 text-center text-sm text-slate-600">
            {noticeText}
          </p>
        )}

        <section aria-label="What you get" className="mt-10 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">What you get</h2>
          <ul className="mt-4 space-y-2">
            {DFY_OFFER.deliverables.map((item) => (
              <li key={item} className="flex gap-3 text-slate-700">
                <span aria-hidden className="mt-1 text-emerald-600">✓</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="What this is not" className="mt-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">What this is not</h2>
          <ul className="mt-4 space-y-2">
            {DFY_OFFER.boundaries.map((item) => (
              <li key={item} className="flex gap-3 text-slate-700">
                <span aria-hidden className="mt-1 text-slate-400">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-8 text-center">
          {ready ? (
            <Link
              href="/dfy/start"
              prefetch={false}
              className="inline-block rounded-full bg-blue-800 px-8 py-3 text-lg font-semibold text-white hover:bg-blue-900"
            >
              {DFY_OFFER.ctaLabel} — {formatUSD(DFY_OFFER.amountCents)}
            </Link>
          ) : (
            <span className="inline-block cursor-not-allowed rounded-full bg-slate-300 px-8 py-3 text-lg font-semibold text-slate-600">
              Checkout opening soon
            </span>
          )}
          <p className="mx-auto mt-4 max-w-xl text-xs leading-relaxed text-slate-500">
            {DFY_OFFER.disclaimer}
          </p>
        </section>
      </div>
    </main>
  );
}
