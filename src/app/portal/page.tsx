import Link from "next/link";
import { requireUser } from "@/lib/auth";

function Card({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-bold text-navy">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export default async function PortalDashboard() {
  const user = await requireUser();

  // Milestone 1: shell only. Live data (plan, capacity, projects, questions)
  // is wired in later milestones once onboarding + project intake exist.
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
        <Card label="Current plan" value="—" hint="Set after checkout" />
        <Card label="Subscription" value="—" hint="pending / active / past_due" />
        <Card label="Capacity used" value="—" hint="standard bids this month" />
        <Card label="Active projects" value="—" />
      </div>

      <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white p-6 text-slate-500">
        Project intake, questions, and completed estimates appear here as those
        modules are completed (Milestones 3–7).
      </div>
    </div>
  );
}
