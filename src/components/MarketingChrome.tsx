import Link from "next/link";
import { INTRO_OFFER } from "@/lib/intro-offer";

const freeEstimateHref = `/signup?offer=${INTRO_OFFER.code}`;

export function MarketingHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-[76px] max-w-7xl items-center justify-between gap-4 px-5 sm:px-7 lg:px-10">
        <Link href="/" aria-label="Mobi Estimates home" className="shrink-0">
          {/* Existing Mobi-owned brand asset. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/assets/img/mobi-logo.png" alt="Mobi Estimates" width="170" height="68" className="h-9 w-auto" />
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-7 text-sm font-medium text-slate-600 lg:flex">
          <a href="#how-it-works" className="transition hover:text-navy focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">How it works</a>
          <a href="#capabilities" className="transition hover:text-navy focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">Capabilities</a>
          <Link href="/pricing" className="transition hover:text-navy focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">Pricing</Link>
          <Link href="/login" className="transition hover:text-navy focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">Sign in</Link>
        </nav>

        <div className="flex items-center gap-2">
          <Link
            href={freeEstimateHref}
            className="hidden rounded-full bg-brand px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-brand/20 transition hover:-translate-y-0.5 hover:bg-brand-dark active:translate-y-0 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30 sm:inline-flex"
          >
            Book a Free Estimate
          </Link>
          <details className="group relative lg:hidden">
            <summary className="flex h-11 w-11 cursor-pointer list-none items-center justify-center rounded-xl border border-slate-200 text-navy transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/20" aria-label="Open navigation menu">
              <span aria-hidden="true" className="text-2xl leading-none">☰</span>
            </summary>
            <nav aria-label="Mobile" className="absolute right-0 mt-3 w-[min(86vw,22rem)] rounded-2xl border border-slate-200 bg-white p-3 shadow-2xl">
              <a href="#how-it-works" className="block rounded-xl px-4 py-3 font-medium text-navy hover:bg-slate-50">How it works</a>
              <a href="#capabilities" className="block rounded-xl px-4 py-3 font-medium text-navy hover:bg-slate-50">Capabilities</a>
              <Link href="/pricing" className="block rounded-xl px-4 py-3 font-medium text-navy hover:bg-slate-50">Pricing</Link>
              <Link href="/login" className="block rounded-xl px-4 py-3 font-medium text-navy hover:bg-slate-50">Sign in</Link>
              <Link href={freeEstimateHref} className="mt-2 flex min-h-12 items-center justify-center rounded-full bg-brand px-5 py-3 text-center font-semibold text-white hover:bg-brand-dark">Book a Free Estimate</Link>
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="bg-navy-deep text-slate-300">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-7 md:grid-cols-2 lg:grid-cols-4 lg:px-10">
        <div className="md:col-span-2 lg:col-span-1">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/assets/img/mobi-logo-white.png" alt="Mobi Estimates" width="170" height="68" className="h-9 w-auto" />
          <p className="mt-5 max-w-xs text-sm leading-7 text-slate-400">Construction estimating capacity, human review, contractor-controlled revisions, and professional deliverables in one organized workflow.</p>
        </div>
        <div><h2 className="text-sm font-semibold text-white">Explore</h2><div className="mt-4 grid gap-3 text-sm"><a href="#how-it-works" className="hover:text-white">How it works</a><a href="#capabilities" className="hover:text-white">Capabilities</a><Link href="/pricing" className="hover:text-white">Pricing</Link></div></div>
        <div><h2 className="text-sm font-semibold text-white">Account</h2><div className="mt-4 grid gap-3 text-sm"><Link href="/signup" className="hover:text-white">Create account</Link><Link href="/login" className="hover:text-white">Sign in</Link><Link href="/reset" className="hover:text-white">Reset password</Link></div></div>
        <div><h2 className="text-sm font-semibold text-white">Get started</h2><Link href={freeEstimateHref} className="mt-4 inline-flex rounded-full bg-brand px-5 py-3 text-sm font-semibold text-white hover:bg-brand-dark">Book a Free Estimate</Link><p className="mt-4 text-xs leading-5 text-slate-400">One qualifying estimate per new company. No card required. Scope and complexity reviewed before acceptance.</p></div>
      </div>
      <div className="border-t border-white/10"><div className="mx-auto flex max-w-7xl flex-col gap-2 px-5 py-6 text-xs text-slate-500 sm:px-7 md:flex-row md:items-center md:justify-between lg:px-10"><span>© 2026 Mobi Estimates. All rights reserved.</span><span>Final estimates remain subject to contractor review and Mobi approval gates.</span></div></div>
    </footer>
  );
}
