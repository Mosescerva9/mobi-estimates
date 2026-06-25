import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { statusBadgeClass, statusLabel } from "@/lib/projects";

const QUICK_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "All" },
  { value: "submitted", label: "New" },
  { value: "needs_information", label: "Needs info" },
  { value: "ready_for_delivery", label: "Ready" },
  { value: "delivered", label: "Delivered" },
];

function fmtDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default async function AdminQueue({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; q?: string }>;
}) {
  const { status = "all", q = "" } = await searchParams;
  const supabase = await createClient();

  let query = supabase
    .from("projects")
    .select("id, project_number, name, status, bid_due_at, created_at, companies(legal_name), project_assignments(estimator_id)")
    .is("deleted_at", null)
    .order("created_at", { ascending: false });

  if (status && status !== "all") query = query.eq("status", status);
  if (q.trim()) query = query.or(`name.ilike.%${q.trim()}%,project_number.ilike.%${q.trim()}%`);

  const [{ data: projects }, { data: staff }] = await Promise.all([
    query,
    supabase.from("profiles").select("id, full_name, email").in("role", ["estimator", "reviewer", "admin"]),
  ]);

  const rows = (projects ?? []) as unknown as Array<{
    id: string; project_number: string | null; name: string; status: string;
    bid_due_at: string | null; created_at: string;
    companies: { legal_name: string } | null;
    project_assignments: { estimator_id: string | null } | null;
  }>;

  const staffName = new Map((staff ?? []).map((s) => [s.id, s.full_name || s.email || "—"]));

  return (
    <div>
      <h1 className="text-2xl font-bold text-navy">Submissions queue</h1>
      <p className="mt-1 text-slate-500">All client projects across companies, newest first.</p>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {QUICK_FILTERS.map((f) => {
            const active = status === f.value;
            const params = new URLSearchParams();
            if (f.value !== "all") params.set("status", f.value);
            if (q) params.set("q", q);
            const href = params.toString() ? `/admin?${params}` : "/admin";
            return (
              <Link key={f.value} href={href}
                className={`rounded-full px-3 py-1.5 text-sm font-semibold ${active ? "bg-brand text-white" : "border border-slate-300 text-slate-600 hover:border-brand hover:text-brand"}`}>
                {f.label}
              </Link>
            );
          })}
        </div>
        <form action="/admin" method="get" className="flex gap-2">
          {status !== "all" && <input type="hidden" name="status" value={status} />}
          <input type="search" name="q" defaultValue={q} placeholder="Search name or number"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-brand" />
          <button className="rounded-lg bg-navy px-3 py-1.5 text-sm font-semibold text-white">Search</button>
        </form>
      </div>

      {rows.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
          No projects match this view.
        </div>
      ) : (
        <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Project</th>
                <th className="px-4 py-3 font-semibold">Company</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="hidden px-4 py-3 font-semibold md:table-cell">Estimator</th>
                <th className="hidden px-4 py-3 font-semibold md:table-cell">Bid due</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((p) => {
                const estId = p.project_assignments?.estimator_id ?? null;
                return (
                  <tr key={p.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <Link href={`/admin/projects/${p.id}`} className="block">
                        <span className="font-semibold text-navy hover:text-brand">{p.name}</span>
                        <span className="block text-xs text-slate-400">{p.project_number ?? "—"}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{p.companies?.legal_name ?? "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${statusBadgeClass(p.status)}`}>
                        {statusLabel(p.status)}
                      </span>
                    </td>
                    <td className="hidden px-4 py-3 text-slate-600 md:table-cell">
                      {estId ? staffName.get(estId) ?? "Assigned" : <span className="text-slate-400">Unassigned</span>}
                    </td>
                    <td className="hidden px-4 py-3 text-slate-600 md:table-cell">{fmtDate(p.bid_due_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
