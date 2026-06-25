import Link from "next/link";
import { requireStaff } from "@/lib/auth";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = await requireStaff();

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-6">
            <Link href="/admin" className="text-lg font-extrabold tracking-tight text-navy">
              MOBI <span className="font-semibold text-brand">Estimates</span>
              <span className="ml-2 align-middle text-xs font-semibold uppercase tracking-wide text-slate-400">
                Admin
              </span>
            </Link>
            <nav className="hidden gap-4 sm:flex" aria-label="Admin">
              <Link href="/admin" className="text-sm font-medium text-slate-600 hover:text-navy">
                Queue
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-500 sm:inline">
              {user.email} ({user.role})
            </span>
            <form action="/auth/signout" method="post">
              <button className="rounded-full border border-slate-300 px-4 py-1.5 text-sm font-semibold text-navy hover:border-brand hover:text-brand">
                Sign out
              </button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  );
}
