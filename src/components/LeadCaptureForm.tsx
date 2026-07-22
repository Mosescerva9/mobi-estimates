"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { captureLead } from "@/app/actions/lead-capture";
import { LEAD_CONSENT_COPY, type LeadSource } from "@/lib/lead-capture";

const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"] as const;

/**
 * Accessible homepage work-email capture. Posts to the captureLead server action
 * which stores the lead only (no email is sent in this packet). The response is
 * always generic — the UI shows the same confirmation regardless of outcome, so
 * it never reveals whether an address is new or already known.
 */
export function LeadCaptureForm({ source = "homepage_hero" as LeadSource }: { source?: LeadSource }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [done, setDone] = useState(false);
  const [pending, startTransition] = useTransition();
  const [utm, setUtm] = useState<Record<string, string>>({});

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const next: Record<string, string> = {};
    for (const key of UTM_KEYS) {
      const value = params.get(key);
      if (value) next[key] = value;
    }
    setUtm(next);
  }, []);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = formRef.current;
    if (!form) return;
    const formData = new FormData(form);
    startTransition(async () => {
      await captureLead({ status: "idle" }, formData);
      setDone(true);
      form.reset();
    });
  }

  if (done) {
    return (
      <div
        role="status"
        className="rounded-2xl border border-green-200 bg-green-50 px-5 py-4 text-sm text-green-900"
      >
        Thanks — you&rsquo;re on the list. We&rsquo;ll be in touch about getting your first
        estimate started.
      </div>
    );
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="w-full" noValidate>
      <input type="hidden" name="source" value={source} />
      {UTM_KEYS.map((key) => (
        <input key={key} type="hidden" name={key} value={utm[key] ?? ""} />
      ))}

      {/* Honeypot: hidden from real users; a bot that fills it is silently ignored. */}
      <div aria-hidden="true" className="absolute left-[-9999px] top-[-9999px] h-0 w-0 overflow-hidden">
        <label htmlFor="company_website">Company website</label>
        <input
          id="company_website"
          name="company_website"
          type="text"
          tabIndex={-1}
          autoComplete="off"
        />
      </div>

      <label htmlFor="lead-email" className="sr-only">
        Work email
      </label>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          id="lead-email"
          name="email"
          type="email"
          required
          maxLength={320}
          autoComplete="email"
          inputMode="email"
          placeholder="you@yourcompany.com"
          className="w-full flex-1 rounded-full border border-slate-300 px-5 py-3 text-base text-navy shadow-sm focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30"
        />
        <button
          type="submit"
          disabled={pending}
          className="shrink-0 rounded-full bg-brand px-6 py-3 text-base font-semibold text-white transition hover:bg-brand-dark disabled:opacity-60 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30"
        >
          {pending ? "Sending…" : "Get updates"}
        </button>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-500">{LEAD_CONSENT_COPY}</p>
    </form>
  );
}
