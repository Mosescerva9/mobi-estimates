import Link from "next/link";
import type { Metadata } from "next";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { statusBadgeClass, statusLabel } from "@/lib/projects";

export const metadata: Metadata = {
  title: "My projects — Mobi Estimates",
  robots: { index: false },
};

function fmtDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default async function ProjectsPage() {
  await requireUser();
  const supabase = await createClient();

  // RLS restricts this to the caller's company (or all, for staff).
  const { data: projects } = await supabase
    .from("projects")
    .select("id, project_number, name, status, project_type, bid_due_at, created_at")
    .is("deleted_at", null)
    .order("created_at", { ascending: false });

  const rows = projects ?? [];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">My projects</h1>
          <p className="mt-1 text-slate-500">Everything you&rsquo;ve submitted, newest first.</p>
        </div>
        <Link href="/portal/projects/new"
          className="rounded-full bg-brand px-5 py-3 font-semibold text-white hover:bg-brand-dark">
          Submit New Project
        </Link>
      </div>

      {rows.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <p className="text-slate-500">You haven&rsquo;t submitted any projects yet.</p>
          <Link href="/portal/projects/new"
            className="mt-4 inline-block rounded-full bg-brand px-5 py-2.5 font-semibold text-white hover:bg-brand-dark">
            Submit your first project
          </Link>
        </div>
      ) : (
        <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Project</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="hidden px-4 py-3 font-semibold sm:table-cell">Bid due</th>
                <th className="hidden px-4 py-3 font-semibold sm:table-cell">Submitted</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/portal/projects/${p.id}`} className="block">
                      <span className="font-semibold text-navy hover:text-brand">{p.name}</span>
                      <span className="block text-xs text-slate-400">{p.project_number ?? "—"}</span>
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${statusBadgeClass(p.status)}`}>
                      {statusLabel(p.status)}
                    </span>
                  </td>
                  <td className="hidden px-4 py-3 text-slate-600 sm:table-cell">{fmtDate(p.bid_due_at)}</td>
                  <td className="hidden px-4 py-3 text-slate-600 sm:table-cell">{fmtDate(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
