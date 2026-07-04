"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { sendToEngine } from "./actions";

function fmtDateTime(value: string): string {
  return new Date(value).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export function EnginePanel({
  projectId,
  configured,
  engineProjectId,
  engineStatus,
  enginePageCount,
  engineSyncedAt,
}: {
  projectId: string;
  configured: boolean;
  engineProjectId: string | null;
  engineStatus: string | null;
  enginePageCount: number | null;
  engineSyncedAt: string | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  function onSend() {
    setResult(null);
    startTransition(async () => {
      const res = await sendToEngine(projectId);
      setResult(res);
      if (res.ok) router.refresh();
    });
  }

  const synced = Boolean(engineProjectId);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-base font-bold text-navy">Estimating engine</h2>
      <p className="mt-1 text-sm text-slate-500">
        Ingest the customer&apos;s PDF plan set into the estimating engine to start the
        automated pipeline. Takeoff and pricing are added once a cost book is seeded.
      </p>

      {!configured ? (
        <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          The engine is not configured on this deployment (missing MOBI_ENGINE_BASE_URL /
          MOBI_ENGINE_API_KEY).
        </p>
      ) : (
        <>
          {synced && (
            <dl className="mt-4 grid gap-x-6 gap-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Engine status</dt>
                <dd className="mt-0.5 text-slate-700">{engineStatus ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Pages</dt>
                <dd className="mt-0.5 text-slate-700">{enginePageCount ?? "—"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Engine project id</dt>
                <dd className="mt-0.5 break-all font-mono text-xs text-slate-500">{engineProjectId}</dd>
              </div>
              {engineSyncedAt && (
                <div className="sm:col-span-2">
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Last synced</dt>
                  <dd className="mt-0.5 text-slate-700">{fmtDateTime(engineSyncedAt)}</dd>
                </div>
              )}
            </dl>
          )}

          <div className="mt-4">
            <button
              type="button"
              onClick={onSend}
              disabled={pending}
              className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
            >
              {pending ? "Sending…" : synced ? "Re-send to engine" : "Send to estimating engine"}
            </button>
          </div>

          {result && (
            <p className={`mt-3 text-sm ${result.ok ? "text-green-700" : "text-red-600"}`}>
              {result.message}
            </p>
          )}
        </>
      )}
    </section>
  );
}
