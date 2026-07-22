import Link from "next/link";
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getSessionUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { MobiWordmark } from "@/components/PricingCards";
import { LeadCaptureForm } from "@/components/LeadCaptureForm";
import { MilestoneProgress } from "@/components/MilestoneProgress";
import { INTRO_OFFER } from "@/lib/intro-offer";

export const metadata: Metadata = {
  title: "Mobi Estimates — Construction estimating support for contractors",
  description:
    "New companies get one qualifying estimate free — no card required, supported scope reviewed before acceptance. Submit your plans, track bid progress and follow-up steps, and get review-assisted estimating support. Final estimate delivery stays behind human review and approval.",
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
};

const STEPS: { title: string; body: string }[] = [
  {
    title: "Submit your plans",
    body: "Upload your drawings, specs, and addenda in one place. Tell us the trades, scope, and bid due date.",
  },
  {
    title: "Track progress",
    body: "Watch your project move through document review, takeoff, and pricing/QA — with a clear next step at each stage.",
  },
  {
    title: "Review the estimate",
    body: "Your estimate is released only after our human review and approval gates. Nothing final is exposed before it's ready.",
  },
];

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

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 pb-8 pt-10 sm:pt-16">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center rounded-full bg-brand/5 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-brand">
            {INTRO_OFFER.eyebrow}
          </span>
          <h1 className="mt-5 text-balance text-4xl font-bold leading-tight text-navy sm:text-5xl">
            Keep bidding without falling behind on estimates
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-slate-600">
            Mobi gives contractors review-assisted estimating support — so plans
            get organized, scope gets reviewed, and you can keep more bids moving.
          </p>

          <div className="mt-8 flex flex-col items-center gap-3">
            <Link
              href="/signup"
              className="rounded-full bg-brand px-8 py-3.5 text-base font-semibold text-white transition hover:bg-brand-dark focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30"
            >
              {INTRO_OFFER.cta}
            </Link>
            <p className="max-w-md text-sm text-slate-500">{INTRO_OFFER.qualifyingRule}</p>
          </div>
        </div>

        {/* Email capture */}
        <div className="mx-auto mt-10 max-w-xl rounded-3xl border border-slate-200 bg-slate-50 p-6 sm:p-7">
          <h2 className="text-center text-base font-bold text-navy">
            Prefer email? Get updates and start when you&rsquo;re ready.
          </h2>
          <div className="mt-4">
            <LeadCaptureForm source="homepage_hero" />
          </div>
        </div>
      </section>

      {/* Pain / outcome */}
      <section className="mx-auto max-w-6xl px-6 py-12">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-balance text-3xl font-bold text-navy">
            More bid invitations than estimating hours?
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            When plans pile up, good bids get skipped. Mobi adds estimating
            capacity and a clear place to track every project — without hiring
            another full-time estimator first.
          </p>
        </div>
        <div className="mx-auto mt-10 grid max-w-4xl gap-6 sm:grid-cols-3">
          {[
            ["Stop skipping bids", "Move more projects forward instead of passing on work you don't have hours to estimate."],
            ["One organized workspace", "Drawings, specs, addenda, scope, and bid dates for each project live in one place."],
            ["Review-assisted support", "Real people review your documents and supported scope — no unsupported automation claims."],
          ].map(([title, body]) => (
            <div key={title} className="rounded-2xl border border-slate-200 bg-white p-6 text-left">
              <h3 className="text-base font-bold text-navy">{title}</h3>
              <p className="mt-2 text-sm text-slate-600">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 3-step flow */}
      <section className="bg-slate-50 py-14">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-3xl font-bold text-navy">How it works</h2>
          <ol className="mx-auto mt-10 grid max-w-4xl gap-6 sm:grid-cols-3">
            {STEPS.map((step, i) => (
              <li key={step.title} className="rounded-2xl border border-slate-200 bg-white p-6">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand text-sm font-bold text-white">
                  {i + 1}
                </span>
                <h3 className="mt-4 text-base font-bold text-navy">{step.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Honest dashboard / progress preview */}
      <section className="mx-auto max-w-6xl px-6 py-14">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-balance text-3xl font-bold text-navy">
            See exactly where each project stands
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            Your dashboard shows the same honest milestones our team works from —
            Submitted, Qualification &amp; document review, Scope &amp; takeoff,
            Pricing &amp; QA, and Ready after approval.
          </p>
        </div>
        <div className="mx-auto mt-8 max-w-2xl rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-navy">Riverside Medical Office — Fit-out</p>
              <p className="text-xs text-slate-400">MOBI-2026-0142</p>
            </div>
            <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
              Pricing in progress
            </span>
          </div>
          <div className="mt-5">
            <MilestoneProgress status="pricing_in_progress" bidDueAt="2026-08-14T00:00:00.000Z" />
          </div>
          <p className="mt-4 text-xs text-slate-400">
            Example preview. Final estimate delivery stays locked until our review
            and approval gates are met.
          </p>
        </div>
      </section>

      {/* Bid progress / follow-up (no win promises) */}
      <section className="bg-slate-50 py-14">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h2 className="text-balance text-3xl font-bold text-navy">
            Stay on top of bid dates and follow-ups
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            After your estimate is prepared, Mobi helps you keep track of bid due
            dates and the next follow-up steps so nothing slips. {INTRO_OFFER.noGuarantee}
          </p>
        </div>
      </section>

      {/* Trust / safety (grounded in implemented capabilities) */}
      <section className="mx-auto max-w-6xl px-6 py-14">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-3xl font-bold text-navy">Built to be truthful</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-3">
            {[
              ["Reviewed by people", "Supported scope and project complexity are reviewed by a person before your free estimate is accepted."],
              ["Nothing final leaks early", "Final customer estimate delivery stays behind complete evidence, supported scope, required reviews, and owner approval."],
              ["No overpromises", "We don't promise a turnaround time, a guaranteed win, or automation we haven't shipped."],
            ].map(([title, body]) => (
              <div key={title} className="rounded-2xl border border-slate-200 bg-white p-6">
                <h3 className="text-base font-bold text-navy">{title}</h3>
                <p className="mt-2 text-sm text-slate-600">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ + secondary pricing link */}
      <section className="bg-slate-50 py-14">
        <div className="mx-auto max-w-3xl px-6">
          <h2 className="text-center text-3xl font-bold text-navy">Common questions</h2>
          <dl className="mt-8 space-y-4">
            {[
              ["Is the free estimate really free?", `Yes. ${INTRO_OFFER.qualifyingRule} ${INTRO_OFFER.afterOffer}`],
              ["Do you guarantee I'll win the bid?", INTRO_OFFER.noGuarantee],
              ["What does it cost after the free estimate?", "Regular pricing: $599 per project one-time, or a monthly plan billed at the regular price from month one. No promotional first-month rate and no free trial."],
            ].map(([q, a]) => (
              <div key={q} className="rounded-xl border border-slate-200 bg-white p-5">
                <dt className="font-semibold text-navy">{q}</dt>
                <dd className="mt-1 text-sm text-slate-600">{a}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-8 text-center">
            <Link
              href="/signup"
              className="inline-flex rounded-full bg-brand px-8 py-3.5 text-base font-semibold text-white transition hover:bg-brand-dark focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30"
            >
              {INTRO_OFFER.cta}
            </Link>
            <p className="mt-3 text-sm text-slate-500">
              Or{" "}
              <Link href="/pricing" className="font-semibold text-brand hover:underline">
                see full pricing
              </Link>
              .
            </p>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 px-6 text-center">
          <MobiWordmark />
          <p className="text-xs text-slate-400">
            Review-assisted construction estimating support for contractors.
          </p>
        </div>
      </footer>
    </main>
  );
}
