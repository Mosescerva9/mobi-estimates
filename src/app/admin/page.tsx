import { requireStaff } from "@/lib/auth";

export default async function AdminDashboard() {
  const user = await requireStaff();

  return (
    <main className="min-h-screen p-6">
      <div className="flex items-center justify-between border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-navy">Production dashboard</h1>
          <p className="mt-1 text-slate-500">
            Signed in as {user.email} ({user.role})
          </p>
        </div>
        <form action="/auth/signout" method="post">
          <button className="rounded-full border border-slate-300 px-4 py-1.5 text-sm font-semibold text-navy hover:border-brand hover:text-brand">
            Sign out
          </button>
        </form>
      </div>

      <p className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white p-6 text-slate-500">
        Estimator / reviewer / admin tools (submissions queue, assignments,
        status changes, capacity) are built in Milestone 5. This route is already
        role-protected (staff only) via <code>requireStaff()</code> and RLS.
      </p>
    </main>
  );
}
