import Link from "next/link";
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { ExplainerVideo } from "@/components/ExplainerVideo";
import { LeadCaptureForm } from "@/components/LeadCaptureForm";
import { MarketingFooter, MarketingHeader } from "@/components/MarketingChrome";
import { MilestoneProgress } from "@/components/MilestoneProgress";
import { getSessionUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { INTRO_OFFER } from "@/lib/intro-offer";

export const metadata: Metadata = {
  title: "Mobi Estimates — An estimating department in your pocket",
  description:
    "Mobi combines construction estimating automation, human review, contractor-controlled revisions, and professional deliverables without another full-time estimating hire.",
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
};

const freeEstimateHref = `/signup?offer=${INTRO_OFFER.code}`;

const workflow = [
  ["1", "Upload the project", "Send drawings, specifications, addenda, scope notes, and the bid due date without scheduling an onboarding call."],
  ["2", "Scope, takeoff, and price", "Mobi organizes the documents, develops the supported takeoff and pricing, and routes the work through human review."],
  ["3", "Correct and review", "Comment on scope, quantities, rates, assumptions, and revisions before you use the final deliverables."],
] as const;

const benefits = [
  ["Capacity on demand", "Handle more supported estimates without recruiting another full-time estimator first."],
  ["AI speed, human review", "Automation helps organize the work; people review supported scope, pricing, and quality before final delivery."],
  ["No-call intake", "Start with your project documents and written scope. Clarification can stay attached to the project."],
  ["Professional outputs", "Receive organized takeoff, labor, material, equipment, assumptions, exclusions, Excel, and PDF deliverables as applicable."],
] as const;

const trades = ["Sitework and civil", "Concrete and masonry", "Metals and carpentry", "Building envelope", "Interiors and finishes", "Mechanical, electrical, and plumbing"] as const;

const faqs = [
  ["Is the first estimate really free?", `${INTRO_OFFER.qualifyingRule} ${INTRO_OFFER.afterOffer}`],
  ["Is Mobi just takeoff software?", "No. Mobi combines project intake, scope organization, takeoff, pricing, quality review, contractor revisions, deliverables, and customer-safe progress tracking."],
  ["Do I have to sit through a sales or onboarding call?", "No required sales or onboarding call is part of the standard intake. Mobi may request written clarification when plans or scope need it."],
  ["Can I correct the estimate?", "Yes. Supported comments and revisions stay connected to the project. Contractors remain responsible for reviewing scope, quantities, rates, assumptions, exclusions, and the final bid."],
  ["Do you guarantee turnaround or a winning bid?", "No. Mobi helps you track bid progress and follow-up steps, but we do not promise a turnaround time or a guaranteed win. Schedule is confirmed after complete documents, scope, and complexity are reviewed."],
] as const;

export default async function Home() {
  const user = await getSessionUser();
  if (user) {
    if (isStaff(user.role)) redirect("/admin");
    const companyId = await getPrimaryCompanyId();
    redirect(companyId ? "/portal" : "/onboarding");
  }

  return (
    <main className="min-h-screen overflow-x-clip bg-white text-slate-900">
      <MarketingHeader />

      <section
        className="relative isolate overflow-hidden bg-navy-deep bg-cover bg-center text-white"
        style={{ backgroundImage: "linear-gradient(90deg, rgba(12,24,48,.96), rgba(12,24,48,.76)), url('/assets/img/hero-structure.jpg')" }}
      >
        <div aria-hidden="true" className="absolute inset-0 -z-10 opacity-20 [background-image:linear-gradient(rgba(255,255,255,.13)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.13)_1px,transparent_1px)] [background-size:48px_48px]" />
        <div className="mx-auto grid max-w-7xl items-center gap-10 px-5 py-14 sm:px-7 sm:py-20 lg:grid-cols-[1.02fr_.98fr] lg:px-10 lg:py-24">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.17em] text-blue-200">AI-powered construction estimating</p>
            <h1 className="mt-5 max-w-3xl text-balance text-[clamp(2.7rem,6.8vw,5.6rem)] font-extrabold leading-[1.02] tracking-[-0.045em] text-white">Estimating Department in Your Pocket</h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-blue-50 sm:text-lg sm:leading-8">Mobi gives contractors an estimating service and workflow for supported scopes without the overhead of another full-time hire. Upload plans, collaborate inside the platform, and receive a detailed, human-reviewed estimate built around your approved scope, pricing inputs, and preferences—without unnecessary calls.</p>
            <div className="mt-8 flex max-w-xl flex-col gap-4 sm:flex-row sm:items-center">
              <Link href={freeEstimateHref} className="inline-flex min-h-14 w-full items-center justify-center rounded-full bg-brand px-7 py-4 text-base font-semibold text-white shadow-xl shadow-black/20 transition hover:-translate-y-0.5 hover:bg-brand-dark active:translate-y-0 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-300/60 sm:w-auto">Book a Free Estimate</Link>
              <a href="#explainer-video" className="inline-flex min-h-12 items-center justify-center font-semibold text-blue-100 underline-offset-4 hover:text-white hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-200">See How Mobi Works →</a>
            </div>
            <p className="mt-5 max-w-2xl text-xs leading-5 text-blue-200">One qualifying estimate per new company. No card required. Supported scope and complexity are reviewed before acceptance. Schedule is confirmed after complete documents are reviewed.</p>
          </div>

          <div className="rounded-[1.75rem] border border-white/20 bg-white/10 p-3 shadow-2xl backdrop-blur-sm sm:p-5">
            <div className="rounded-2xl bg-white p-5 text-slate-900 shadow-xl sm:p-7">
              <div className="flex items-center justify-between gap-4 border-b border-slate-200 pb-4"><div><p className="text-sm font-semibold text-navy">Riverside Medical Office</p><p className="text-xs text-slate-500">Example customer-safe project view</p></div><span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">Pricing & QA</span></div>
              <div className="mt-5"><MilestoneProgress status="pricing_in_progress" bidDueAt="2026-08-14T00:00:00.000Z" /></div>
              <div className="mt-6 grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Documents</p><p className="mt-1 font-semibold text-navy">Plans + addenda</p></div><div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Review</p><p className="mt-1 font-semibold text-navy">Human gated</p></div></div>
            </div>
          </div>
        </div>
      </section>

      <ExplainerVideo />

      <section aria-label="Mobi credibility" className="border-y border-slate-200 bg-white py-8">
        <div className="mx-auto flex max-w-7xl flex-wrap justify-center gap-x-9 gap-y-4 px-5 text-sm font-semibold text-slate-600 sm:px-7 lg:px-10">
          {['Nationwide remote service', 'Broad multi-trade support', 'Human-reviewed estimates', 'Confidential project workflow', 'Per-project or monthly'].map((item) => <span key={item} className="inline-flex items-center gap-2"><span className="text-brand">✓</span>{item}</span>)}
        </div>
      </section>

      <section id="how-it-works" className="scroll-mt-24 py-16 sm:py-20 lg:py-24">
        <div className="mx-auto max-w-7xl px-5 sm:px-7 lg:px-10"><div className="mx-auto max-w-3xl text-center"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">How Mobi works</p><h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl lg:text-5xl">From project documents to a usable estimate</h2><p className="mt-5 text-lg leading-8 text-slate-600">A streamlined workflow for contractors who need capacity—not another software implementation project.</p></div><ol className="mt-12 grid gap-6 md:grid-cols-3">{workflow.map(([number,title,body]) => <li key={number} className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-xl"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-navy text-sm font-bold text-white">{number}</span><h3 className="mt-5 text-xl font-semibold text-navy">{title}</h3><p className="mt-3 leading-7 text-slate-600">{body}</p></li>)}</ol></div>
      </section>

      <section id="capabilities" className="scroll-mt-24 bg-slate-50 py-16 sm:py-20 lg:py-24"><div className="mx-auto max-w-7xl px-5 sm:px-7 lg:px-10"><div className="grid gap-10 lg:grid-cols-[.85fr_1.15fr] lg:items-start"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">Key benefits</p><h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl">More estimating capacity, without more department overhead</h2><p className="mt-5 max-w-xl text-lg leading-8 text-slate-600">Mobi is not a self-serve takeoff tool. It combines service, workflow, automation, and review around the contractor’s actual project.</p></div><div className="grid gap-5 sm:grid-cols-2">{benefits.map(([title,body]) => <article key={title} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"><h3 className="text-lg font-semibold text-navy">{title}</h3><p className="mt-3 text-sm leading-7 text-slate-600">{body}</p></article>)}</div></div></div></section>

      <section className="py-16 sm:py-20 lg:py-24"><div className="mx-auto grid max-w-7xl gap-10 px-5 sm:px-7 lg:grid-cols-2 lg:items-center lg:px-10"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">Contractor-controlled collaboration</p><h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl">Corrections stay connected to the estimate</h2><p className="mt-5 text-lg leading-8 text-slate-600">Clarify inclusions, flag missing information, and request supported revisions without losing the project history. Approved company rates, markups, and preferences can stay visible to the review workflow.</p><p className="mt-4 text-sm leading-6 text-slate-500">Contractors remain responsible for confirming scope, quantities, assumptions, rates, exclusions, and the final bid.</p></div><div className="rounded-[1.75rem] border border-slate-200 bg-navy-deep p-6 text-white shadow-2xl sm:p-8"><div className="rounded-2xl bg-white p-5 text-slate-900"><p className="text-xs font-semibold uppercase tracking-wide text-brand">Revision request</p><h3 className="mt-2 font-semibold text-navy">Update concrete labor rate and add Addendum 02</h3><div className="mt-5 space-y-3 text-sm text-slate-600"><p className="rounded-xl bg-slate-50 p-3">Contractor note and supporting document stay attached to this project.</p><p className="rounded-xl bg-blue-50 p-3 text-blue-900">Estimator review required before the revised deliverable is released.</p></div></div></div></div></section>

      <section className="bg-navy-deep py-16 text-white sm:py-20 lg:py-24"><div className="mx-auto grid max-w-7xl gap-10 px-5 sm:px-7 lg:grid-cols-2 lg:items-center lg:px-10"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-200">Multi-trade estimating</p><h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl">One organized estimate across the trades in your project</h2><p className="mt-5 text-lg leading-8 text-blue-100">Mobi can organize quantities, labor, material, equipment, assumptions, and exclusions across common construction divisions. Supported scope and complexity are confirmed during review.</p></div><div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{trades.map((trade) => <div key={trade} className="flex min-h-24 items-center rounded-2xl border border-white/15 bg-white/10 p-4 text-sm font-semibold">{trade}</div>)}</div></div></section>

      <section className="py-16 sm:py-20 lg:py-24"><div className="mx-auto max-w-7xl px-5 sm:px-7 lg:px-10"><div className="mx-auto max-w-3xl text-center"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">Professional deliverables</p><h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl">Estimate information your team can actually use</h2><p className="mt-5 text-lg leading-8 text-slate-600">Deliverables can include supported takeoff quantities, labor, material, equipment, trade and CSI breakdowns, assumptions, exclusions, and contractor-ready Excel and PDF files.</p></div><div className="mx-auto mt-10 max-w-5xl overflow-hidden rounded-[1.75rem] border border-slate-200 bg-white shadow-2xl"><div className="border-b border-slate-200 bg-slate-50 px-6 py-4"><p className="font-semibold text-navy">Example estimate summary</p><p className="text-xs text-slate-500">Illustrative interface — not a customer project or final estimate</p></div><div className="grid gap-4 p-6 md:grid-cols-3">{[['Division 03','Concrete quantities + pricing'],['Division 09','Interior finish breakdown'],['Assumptions','Scope notes and exclusions']].map(([title,body]) => <div key={title} className="rounded-2xl border border-slate-200 p-5"><p className="text-xs font-semibold uppercase tracking-wide text-brand">{title}</p><p className="mt-2 font-semibold text-navy">{body}</p></div>)}</div></div></div></section>

      <section className="bg-slate-50 py-16 sm:py-20 lg:py-24"><div className="mx-auto max-w-7xl px-5 sm:px-7 lg:px-10"><div className="mx-auto max-w-3xl text-center"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">Compared with another internal hire</p><h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl">Add capacity before adding another department</h2><p className="mt-5 text-lg leading-8 text-slate-600">Mobi supports defined estimating work; it does not claim to replace every responsibility or judgment of an experienced employee.</p></div><div className="mt-10 grid gap-6 md:grid-cols-2"><article className="rounded-3xl border border-slate-200 bg-white p-7"><h3 className="text-xl font-semibold text-navy">Another full-time hire</h3><ul className="mt-5 space-y-3 text-slate-600">{['Recruiting and onboarding','Ongoing payroll and employee overhead','Software, training, and management','Fixed capacity during slower bid periods'].map((item) => <li key={item}>• {item}</li>)}</ul></article><article className="rounded-3xl border-2 border-brand bg-white p-7 shadow-xl"><h3 className="text-xl font-semibold text-navy">Mobi estimating capacity</h3><ul className="mt-5 space-y-3 text-slate-600">{['Per-project or monthly options','Plans, scope, pricing, and QA in one workflow','Contractor-controlled corrections and preferences','Human review before final delivery'].map((item) => <li key={item}><span className="text-brand">✓</span> {item}</li>)}</ul></article></div></div></section>

      {/* No testimonial section is rendered because the repository contains no verified customer quotes or approved customer logos. */}
      <section className="py-16 sm:py-20 lg:py-24"><div className="mx-auto max-w-7xl px-5 sm:px-7 lg:px-10"><div className="mx-auto max-w-3xl text-center"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">Pricing preview</p><h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl">Start free, then choose the capacity you need</h2><p className="mt-5 text-lg leading-8 text-slate-600">One qualifying estimate is free for each new company. After that, regular one-time or monthly pricing applies.</p></div><div className="mt-10 grid gap-5 md:grid-cols-4">{[['One Project','$599','one-time'],['Starter','$995','per month'],['Growth','$1,995','per month'],['Estimating Department','$2,995','per month']].map(([name,price,period]) => <Link href="/pricing" key={name} className="rounded-3xl border border-slate-200 bg-white p-6 text-center shadow-sm transition hover:-translate-y-1 hover:border-brand hover:shadow-xl"><h3 className="font-semibold text-navy">{name}</h3><p className="mt-4 text-3xl font-bold text-navy">{price}</p><p className="mt-1 text-sm text-slate-500">{period}</p></Link>)}</div><div className="mt-8 text-center"><Link href="/pricing" className="inline-flex min-h-12 items-center justify-center rounded-full border border-slate-300 px-6 py-3 font-semibold text-navy transition hover:border-brand hover:text-brand">View full pricing and capacity</Link></div></div></section>

      <section className="bg-slate-50 py-16 sm:py-20 lg:py-24"><div className="mx-auto max-w-4xl px-5 sm:px-7 lg:px-10"><div className="text-center"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">FAQ</p><h2 className="mt-3 text-balance text-3xl font-bold tracking-tight text-navy sm:text-4xl">What contractors should know</h2></div><div className="mt-10 space-y-3">{faqs.map(([question,answer]) => <details key={question} className="group rounded-2xl border border-slate-200 bg-white p-5"><summary className="cursor-pointer list-none pr-8 font-semibold text-navy marker:hidden">{question}<span aria-hidden="true" className="float-right text-brand group-open:rotate-45">+</span></summary><p className="mt-4 pr-6 text-sm leading-7 text-slate-600">{answer}</p></details>)}</div></div></section>

      <section className="py-16 sm:py-20"><div className="mx-auto max-w-7xl px-5 sm:px-7 lg:px-10"><div className="overflow-hidden rounded-[2rem] bg-navy-deep px-6 py-12 text-center text-white shadow-2xl sm:px-10 sm:py-16"><h2 className="mx-auto max-w-3xl text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-5xl">Put your next estimate into a clearer workflow</h2><p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-blue-100">Start with one qualifying estimate free. Upload the project, confirm the supported scope, and keep every revision organized.</p><Link href={freeEstimateHref} className="mt-8 inline-flex min-h-14 w-full items-center justify-center rounded-full bg-brand px-8 py-4 text-base font-semibold text-white transition hover:-translate-y-0.5 hover:bg-brand-dark focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-300/60 sm:w-auto">Book a Free Estimate</Link><p className="mx-auto mt-4 max-w-xl text-xs leading-5 text-blue-200">No card required. Supported scope and complexity are reviewed before acceptance.</p></div><div className="mx-auto mt-10 max-w-xl rounded-3xl border border-slate-200 bg-slate-50 p-6"><h2 className="text-center text-base font-semibold text-navy">Prefer email? Get Mobi updates.</h2><div className="mt-4"><LeadCaptureForm source="homepage_hero" /></div></div></div></section>

      <MarketingFooter />
    </main>
  );
}
