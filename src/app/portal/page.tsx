import Link from "next/link";
import { requireUser } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { createClient } from "@/lib/supabase/server";
import { statusBadgeClass, statusLabel } from "@/lib/projects";

function Card({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-bold text-navy">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

const CLOSED = new Set(["closed", "canceled"]);

export default async function PortalDashboard() {
  const user = await requireUser();
  const companyId = await getPrimaryCompanyId();
  const supabase = await createClient();

  const [{ data: projects }, { data: sub }, { count: estimateCount }] = await Promise.all([
    supabase
      .from("projects")
      .select("id, project_number, name, status, created_at")
      .is("deleted_at", null)
      .order("created_at", { ascending: false }),
    companyId
      ? supabase
          .from("subscriptions")
          .select("status, plans(name)")
          .eq("company_id", companyId)
          .order("created_at", { ascending: false })
          .limit(1)
          .maybeSingle()
      : Promise.resolve({ data: null }),
    supabase
      .from("deliverables")
      .select("id", { count: "exact", head: true })
      .is("deleted_at", null),
  ]);

  const rows = projects ?? [];
  const activeCount = rows.filter((p) => !CLOSED.has(p.status)).length;
  const subscription = sub as { status?: string; plans?: { name?: string } | null } | null;
  const planName = subscription?.plans?.name ?? "—";
  const subStatus = subscription?.status ?? "—";

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">
            Welcome{user.fullName ? `, ${user.fullName.split(" ")[0]}` : ""}
          </h1>
          <p className="mt-1 text-slate-500">Your estimating workspace.</p>
        </div>
        <Link
          href="/portal/projects/new"
          className="rounded-full bg-brand px-5 py-3 font-semibold text-white hover:bg-brand-dark"
        >
          Submit New Project
        </Link>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label="Current plan" value={planName} hint="Set after checkout" />
        <Card label="Subscription" value={subStatus} hint="pending / active / past_due" />
        <Card label="Active projects" value={String(activeCount)} />
        <Card label="Total submitted" value={String(rows.length)} />
      </div>

      {(estimateCount ?? 0) > 0 && (
        <Link href="/portal/estimates"
          className="mt-6 flex items-center justify-between rounded-2xl border border-green-200 bg-green-50 px-6 py-4 hover:bg-green-100">
          <span className="text-sm font-semibold text-green-800">
            {estimateCount} completed estimate{estimateCount === 1 ? "" : "s"} ready to download
          </span>
          <span className="text-sm font-semibold text-green-700">View estimates →</span>
        </Link>
      )}

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-navy">Recent projects</h2>
          {rows.length > 0 && (
            <Link href="/portal/projects" className="text-sm font-semibold text-slate-500 hover:text-brand">
              View all
            </Link>
          )}
        </div>

        {rows.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            No projects yet.{" "}
            <Link href="/portal/projects/new" className="font-semibold text-brand hover:underline">
              Submit your first project
            </Link>{" "}
            to get an estimate.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100">
            {rows.slice(0, 5).map((p) => (
              <li key={p.id}>
                <Link href={`/portal/projects/${p.id}`}
                  className="flex items-center justify-between gap-3 py-3 hover:opacity-80">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-navy">{p.name}</div>
                    <div className="text-xs text-slate-400">{p.project_number ?? "—"}</div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${statusBadgeClass(p.status)}`}>
                    {statusLabel(p.status)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
