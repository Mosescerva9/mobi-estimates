import Link from "next/link";
import type { Metadata } from "next";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { DELIVERABLES_BUCKET, formatBytes } from "@/lib/projects";
import { approveDeliverable, markReviewed } from "./actions";

export const metadata: Metadata = {
  title: "Completed estimates — Mobi Estimates",
  robots: { index: false },
};

function fmtDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

interface Row {
  id: string;
  project_id: string;
  category: string;
  file_name: string;
  storage_path: string;
  size_bytes: number | null;
  created_at: string;
  client_reviewed_at: string | null;
  client_approved_at: string | null;
  projects: { name: string; project_number: string | null } | null;
}

export default async function EstimatesPage() {
  await requireUser();
  const supabase = await createClient();

  const { data } = await supabase
    .from("deliverables")
    .select("id, project_id, category, file_name, storage_path, size_bytes, created_at, client_reviewed_at, client_approved_at, projects(name, project_number)")
    .is("deleted_at", null)
    .order("created_at", { ascending: false });

  const rows = (data ?? []) as unknown as Row[];

  const urls = new Map<string, string>();
  if (rows.length > 0) {
    const { data: signed } = await supabase.storage
      .from(DELIVERABLES_BUCKET)
      .createSignedUrls(rows.map((r) => r.storage_path), 300);
    for (const s of signed ?? []) if (s.signedUrl && s.path) urls.set(s.path, s.signedUrl);
  }

  // Group by project, preserving newest-first order.
  const groups = new Map<string, { name: string; number: string | null; items: Row[] }>();
  for (const r of rows) {
    if (!groups.has(r.project_id)) {
      groups.set(r.project_id, {
        name: r.projects?.name ?? "Project",
        number: r.projects?.project_number ?? null,
        items: [],
      });
    }
    groups.get(r.project_id)!.items.push(r);
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-navy">Completed estimates</h1>
      <p className="mt-1 text-slate-500">Download your finished estimates and mark them reviewed or approved.</p>

      {rows.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
          No completed estimates yet. You&rsquo;ll see them here once our team delivers them.
        </div>
      ) : (
        <div className="mt-6 space-y-6">
          {[...groups.entries()].map(([projectId, g]) => (
            <section key={projectId} className="rounded-2xl border border-slate-200 bg-white p-6">
              <div className="flex items-center justify-between">
                <div>
                  <Link href={`/portal/projects/${projectId}`} className="font-semibold text-navy hover:text-brand">
                    {g.name}
                  </Link>
                  <div className="text-xs text-slate-400">{g.number ?? "—"}</div>
                </div>
              </div>
              <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
                {g.items.map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-navy">{d.file_name}</div>
                      <div className="text-xs text-slate-400">
                        {d.category} · {formatBytes(d.size_bytes)} · {fmtDate(d.created_at)}
                      </div>
                    </div>
                    {d.client_approved_at ? (
                      <span className="rounded-full bg-green-50 px-2.5 py-1 text-xs font-semibold text-green-700">Approved</span>
                    ) : d.client_reviewed_at ? (
                      <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">Reviewed</span>
                    ) : null}
                    {urls.get(d.storage_path) ? (
                      <a href={urls.get(d.storage_path)} target="_blank" rel="noopener noreferrer"
                        className="text-sm font-semibold text-brand hover:underline">Download</a>
                    ) : <span className="text-xs text-slate-400">Unavailable</span>}
                    {!d.client_reviewed_at && (
                      <form action={markReviewed}>
                        <input type="hidden" name="deliverableId" value={d.id} />
                        <input type="hidden" name="projectId" value={d.project_id} />
                        <button className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-navy hover:border-brand hover:text-brand">
                          Mark reviewed
                        </button>
                      </form>
                    )}
                    {!d.client_approved_at && (
                      <form action={approveDeliverable}>
                        <input type="hidden" name="deliverableId" value={d.id} />
                        <input type="hidden" name="projectId" value={d.project_id} />
                        <button className="rounded-full bg-navy px-3 py-1 text-xs font-semibold text-white hover:opacity-90">
                          Approve
                        </button>
                      </form>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
