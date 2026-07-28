"use client";

import { useState } from "react";
import { DFY_EXPERIENCE_RANGES } from "@/lib/dfy-intake";

type SubmitState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "done" }
  | { kind: "error"; message: string };

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-blue-700 focus:outline-none";

export function DfyIntakeForm({ token }: { token: string }) {
  const [state, setState] = useState<SubmitState>({ kind: "idle" });

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ kind: "submitting" });
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    try {
      const res = await fetch("/api/dfy/intake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, ...payload }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error || "Could not submit the form. Please try again.");
      }
      setState({ kind: "done" });
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : "Could not submit the form. Please try again.",
      });
    }
  }

  if (state.kind === "done") {
    return (
      <div className="mt-8 rounded-xl border border-emerald-300 bg-emerald-50 px-5 py-4 text-emerald-900">
        <p className="font-semibold">Intake received.</p>
        <p className="mt-1 text-sm">
          We&apos;ll review your answers and reach out to schedule your onboarding call.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-8 space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      {/* Honeypot: invisible to humans, catches bots. Screen-reader hidden too. */}
      <div className="hidden" aria-hidden="true">
        <label>
          Leave this field empty
          <input name="honeypot" type="text" tabIndex={-1} autoComplete="off" />
        </label>
      </div>

      <div>
        <label htmlFor="name" className="text-sm font-medium text-slate-800">Full name</label>
        <input id="name" name="name" required maxLength={120} className={inputClass} />
      </div>

      <div>
        <label htmlFor="email" className="text-sm font-medium text-slate-800">Email</label>
        <input id="email" name="email" type="email" required className={inputClass} />
      </div>

      <div>
        <label htmlFor="trade_niche" className="text-sm font-medium text-slate-800">
          Trade / niche you estimate (or want to)
        </label>
        <input id="trade_niche" name="trade_niche" required maxLength={120}
               placeholder="e.g. concrete, electrical, multi-trade GC" className={inputClass} />
      </div>

      <div>
        <label htmlFor="years_experience" className="text-sm font-medium text-slate-800">
          Years of estimating experience
        </label>
        <select id="years_experience" name="years_experience" required className={inputClass} defaultValue="">
          <option value="" disabled>Select one</option>
          {DFY_EXPERIENCE_RANGES.map((range) => (
            <option key={range} value={range}>{range} years</option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="current_situation" className="text-sm font-medium text-slate-800">
          Where are you today?
        </label>
        <textarea id="current_situation" name="current_situation" required rows={3} maxLength={1000}
                  placeholder="Employed estimator? Side hustle? Already freelancing?"
                  className={inputClass} />
      </div>

      <div>
        <label htmlFor="goals" className="text-sm font-medium text-slate-800">
          What do you want this business to look like in 6–12 months?
        </label>
        <textarea id="goals" name="goals" required rows={3} maxLength={1000} className={inputClass} />
      </div>

      <div>
        <label htmlFor="call_availability" className="text-sm font-medium text-slate-800">
          Availability for your 45-minute onboarding call
        </label>
        <input id="call_availability" name="call_availability" required maxLength={200}
               placeholder="e.g. weekday evenings CT, or Sat mornings" className={inputClass} />
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" name="community_member" value="yes" className="h-4 w-4" />
        I&apos;m already a member of the paid community
      </label>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
          {state.message}
        </p>
      )}

      <button
        type="submit"
        disabled={state.kind === "submitting"}
        className="w-full rounded-full bg-blue-800 px-6 py-3 font-semibold text-white hover:bg-blue-900 disabled:opacity-60"
      >
        {state.kind === "submitting" ? "Submitting…" : "Submit intake"}
      </button>
    </form>
  );
}
