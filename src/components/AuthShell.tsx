export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <main className="min-h-screen grid place-items-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <span className="inline-block text-2xl font-extrabold tracking-tight text-navy">
            MOBI <span className="font-semibold text-brand">Estimates</span>
          </span>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="text-xl font-bold text-navy">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
        {footer && <div className="mt-5 text-center text-sm text-slate-500">{footer}</div>}
      </div>
    </main>
  );
}

export const fieldClass =
  "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-[15px] outline-none focus:border-brand focus:ring-4 focus:ring-brand/15";
export const btnClass =
  "w-full rounded-full bg-brand px-5 py-3 font-semibold text-white transition hover:bg-brand-dark disabled:opacity-60";
export const labelClass = "mb-1.5 block text-sm font-semibold text-navy";
