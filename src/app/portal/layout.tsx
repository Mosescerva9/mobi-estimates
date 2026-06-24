import Link from "next/link";
import { redirect } from "next/navigation";
import { requireUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";
import { billingEnforced, hasActiveSubscription } from "@/lib/subscription";

const NAV = [
  ["/portal", "Dashboard"],
  ["/portal/projects/new", "Submit a Project"],
  ["/portal/projects", "My Projects"],
  ["/portal/questions", "Questions"],
  ["/portal/estimates", "Completed Estimates"],
  ["/portal/subscription", "Subscription"],
  ["/portal/training", "Training"],
  ["/portal/support", "Support"],
  ["/portal/account", "Account Settings"],
] as const;

export default async function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireUser();

  // A client with no company hasn't onboarded — RLS would block all their data.
  if (!isStaff(user.role)) {
    const companyId = await getPrimaryCompanyId();
    if (!companyId) redirect("/onboarding");
    // Paywall: once Stripe is configured, an inactive company must subscribe.
    if (billingEnforced() && !(await hasActiveSubscription(companyId))) {
      redirect("/billing");
    }
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[260px_1fr]">
      <aside className="border-r border-slate-200 bg-white md:min-h-screen">
        <div className="flex items-center justify-between p-5">
          <span className="text-lg font-extrabold tracking-tight text-navy">
            MOBI <span className="font-semibold text-brand">Estimates</span>
          </span>
        </div>
        <nav className="px-3 pb-4" aria-label="Portal">
          {NAV.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className="block rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-navy"
            >
              {label}
            </Link>
          ))}
          {isStaff(user.role) && (
            <Link
              href="/admin"
              className="mt-2 block rounded-lg px-3 py-2.5 text-sm font-semibold text-brand hover:bg-slate-100"
            >
              Admin dashboard →
            </Link>
          )}
        </nav>
      </aside>

      <div className="flex min-h-screen flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <span className="text-sm text-slate-500">
            {user.fullName || user.email}
          </span>
          <form action="/auth/signout" method="post">
            <button className="rounded-full border border-slate-300 px-4 py-1.5 text-sm font-semibold text-navy hover:border-brand hover:text-brand">
              Sign out
            </button>
          </form>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
