import type { Metadata } from "next";
import { StarterKitLeadForm } from "@/components/StarterKitLeadForm";

export const metadata: Metadata = {
  title: "Free Construction Estimating Business Starter Kit | Mobi Estimates",
  description:
    "Get the free 19-page Construction Estimating Business Starter Kit with offer design, pricing, contractor outreach scripts, QA checklists, a lead tracker, and a first-10-clients action plan.",
  alternates: { canonical: "/starter-kit" },
  robots: { index: true, follow: true },
};

const included = [
  "Offer design and pricing framework",
  "Contractor outreach scripts",
  "Free-estimate conversion funnel",
  "Client intake and estimator QA checklists",
  "Simple lead tracker",
  "First 10 clients action plan",
  "Unit economics worksheet",
  "7-day launch challenge",
] as const;

export default function StarterKitPage() {
  return (
    <main className="min-h-screen bg-white text-slate-900">
      <section className="relative isolate overflow-hidden bg-navy-deep text-white">
        <div aria-hidden="true" className="absolute inset-0 -z-10 opacity-20 [background-image:linear-gradient(rgba(255,255,255,.12)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.12)_1px,transparent_1px)] [background-size:48px_48px]" />
        <div className="mx-auto max-w-7xl px-5 py-6 sm:px-7 lg:px-10">
          <a href="/" className="inline-flex items-center text-lg font-extrabold tracking-tight text-white">MOBI ESTIMATES</a>
        </div>

        <div className="mx-auto grid max-w-7xl gap-10 px-5 pb-16 pt-8 sm:px-7 sm:pb-20 lg:grid-cols-[1.08fr_.92fr] lg:items-center lg:px-10 lg:pb-24 lg:pt-14">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-200">Free construction estimating business resource</p>
            <h1 className="mt-5 max-w-4xl text-balance text-[clamp(2.6rem,6.5vw,5.3rem)] font-extrabold leading-[1.02] tracking-[-0.045em] text-white">
              Build Your First Construction Estimating Business.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-blue-50 sm:text-xl">
              Get the practical 19-page blueprint for going from zero to your first 10 estimating clients — without wasting weeks building complicated software before anyone pays you.
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {included.map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-2xl border border-white/15 bg-white/10 p-4 text-sm leading-6 text-blue-50 backdrop-blur-sm">
                  <span className="mt-0.5 font-bold text-blue-200">✓</span>
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>

          <StarterKitLeadForm />
        </div>
      </section>

      <section className="py-16 sm:py-20">
        <div className="mx-auto max-w-5xl px-5 sm:px-7 lg:px-10">
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">What is inside</p>
            <h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl">Not another generic “start a business” PDF.</h2>
            <p className="mt-5 text-lg leading-8 text-slate-600">
              This kit is specifically built around selling construction estimating as a service: finding contractors with a bid bottleneck, reducing the trust barrier with a free first estimate, delivering quality work, and converting the right customers into recurring relationships.
            </p>
          </div>

          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {[
              ["Get sellable", "Define the customer, free-trial scope, paid offer, and pricing before you obsess over branding."],
              ["Get contractors", "Use the included cold email, LinkedIn/DM, phone opener, follow-up, and lead tracker to start real conversations."],
              ["Deliver correctly", "Use the intake, human-review, QA, project SOP, and unit-economics checklists to build a repeatable service."],
            ].map(([title, body]) => (
              <article key={title} className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
                <h3 className="text-xl font-semibold text-navy">{title}</h3>
                <p className="mt-3 text-sm leading-7 text-slate-600">{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-slate-50 py-16 sm:py-20">
        <div className="mx-auto max-w-4xl px-5 text-center sm:px-7 lg:px-10">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">The goal</p>
          <h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl">Get to the first real contractor conversation as fast as possible.</h2>
          <p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-slate-600">Real feedback beats another week of planning. Download the kit, complete the offer worksheet, build your first contractor list, and start outreach.</p>
          <a href="#top" className="mt-7 inline-flex min-h-12 items-center justify-center rounded-full bg-navy px-6 py-3 font-semibold text-white hover:bg-navy-deep">Get the free kit ↑</a>
        </div>
      </section>

      <footer className="border-t border-slate-200 bg-white py-8">
        <div className="mx-auto max-w-7xl px-5 text-center text-xs leading-5 text-slate-500 sm:px-7 lg:px-10">
          © 2026 Mobi Estimates. This resource is a business-development framework, not a guarantee of income. Construction bids carry real financial risk; use qualified estimators and verify client-facing work.
        </div>
      </footer>
    </main>
  );
}
