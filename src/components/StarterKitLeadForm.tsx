"use client";

import { FormEvent, useMemo, useState } from "react";

const GUIDE_PATH = "/starter-kit/guide";

function allowedUtm(value: string | null, fallback: string) {
  return value && value.length <= 120 ? value : fallback;
}

export function StarterKitLeadForm() {
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const attribution = useMemo(() => {
    if (typeof window === "undefined") {
      return { source: "youtube", medium: "social", campaign: "estimating-starter-kit" };
    }
    const params = new URLSearchParams(window.location.search);
    return {
      source: allowedUtm(params.get("utm_source"), "youtube"),
      medium: allowedUtm(params.get("utm_medium"), "social"),
      campaign: allowedUtm(params.get("utm_campaign"), "estimating-starter-kit"),
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await fetch("/api/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          source: "unknown",
          utm_source: attribution.source,
          utm_medium: attribution.medium,
          utm_campaign: attribution.campaign,
          company_website: website,
        }),
      });

      if (!response.ok) throw new Error("Lead capture failed");
      setSubmitted(true);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    return (
      <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-6 text-center shadow-sm sm:p-8">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-600 text-xl font-bold text-white">✓</div>
        <h2 className="mt-4 text-2xl font-bold tracking-tight text-navy">Your Starter Kit is unlocked.</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600">Tap below to open the complete Construction Estimating Business Starter Kit.</p>
        <a
          href={GUIDE_PATH}
          className="mt-6 inline-flex min-h-14 w-full items-center justify-center rounded-full bg-brand px-7 py-4 text-base font-semibold text-white shadow-lg transition hover:bg-brand-dark focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-300/60"
        >
          Open the Free Starter Kit →
        </a>
        <p className="mt-4 text-xs leading-5 text-slate-500">Bookmark the guide on your phone so you can work through the worksheets while you build.</p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl sm:p-8">
      <div className="rounded-2xl bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-900">Free starter kit • No credit card</div>
      <label htmlFor="starter-kit-email" className="mt-6 block text-sm font-semibold text-navy">Enter your email to unlock the kit</label>
      <input
        id="starter-kit-email"
        type="email"
        required
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder="you@example.com"
        className="mt-2 min-h-14 w-full rounded-2xl border border-slate-300 bg-white px-4 text-base text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-brand focus:ring-4 focus:ring-blue-100"
      />
      <div className="absolute -left-[10000px] top-auto h-px w-px overflow-hidden" aria-hidden="true">
        <label htmlFor="starter-kit-website">Website</label>
        <input id="starter-kit-website" tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="mt-4 inline-flex min-h-14 w-full items-center justify-center rounded-full bg-brand px-7 py-4 text-base font-semibold text-white shadow-lg transition hover:bg-brand-dark disabled:cursor-wait disabled:opacity-70 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-300/60"
      >
        {loading ? "Unlocking…" : "Get the Free Starter Kit →"}
      </button>
      {error ? <p role="alert" className="mt-3 text-sm font-medium text-red-600">{error}</p> : null}
      <p className="mt-4 text-xs leading-5 text-slate-500">By submitting, you agree Mobi may send you the starter kit and related estimating-business training. You can unsubscribe at any time.</p>
    </form>
  );
}
