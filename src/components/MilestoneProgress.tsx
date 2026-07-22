import {
  CUSTOMER_MILESTONES,
  customerProgressForStatus,
} from "@/lib/milestones";

function fmtDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? null
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/**
 * Accessible, reusable customer progress tracker. Renders the fail-closed
 * milestone mapping (src/lib/milestones.ts) as an ordered list with a clear
 * current step, an honest next-step explanation, and the bid due date where
 * present. Never shows a "delivered/complete" state — final delivery stays
 * behind the existing approval gate.
 *
 * `compact` hides the next-step paragraph (used in dense dashboard lists).
 */
export function MilestoneProgress({
  status,
  bidDueAt,
  compact = false,
}: {
  status: string | null | undefined;
  bidDueAt?: string | null;
  compact?: boolean;
}) {
  const progress = customerProgressForStatus(status);
  const bidDue = fmtDate(bidDueAt);

  if (progress.isClosed) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
        <p className="text-sm font-semibold text-slate-700">{progress.closedLabel}</p>
        {!compact && <p className="mt-1 text-sm text-slate-500">{progress.nextStep}</p>}
      </div>
    );
  }

  const currentLabel = `${progress.label} (step ${progress.index + 1} of ${CUSTOMER_MILESTONES.length})`;

  return (
    <div>
      <ol
        className="flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-2"
        aria-label={`Progress: ${currentLabel}`}
      >
        {CUSTOMER_MILESTONES.map((m, i) => {
          const done = i < progress.index;
          const current = i === progress.index;
          const state = current ? "current" : done ? "done" : "upcoming";
          const dot = done
            ? "border-brand bg-brand text-white"
            : current
              ? "border-brand bg-white text-brand"
              : "border-slate-300 bg-white text-slate-400";
          const text = current ? "text-navy font-semibold" : done ? "text-slate-600" : "text-slate-400";
          return (
            <li
              key={m.key}
              className="flex items-start gap-2 sm:flex-1 sm:flex-col sm:items-center sm:text-center"
              aria-current={current ? "step" : undefined}
            >
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${dot}`}
                aria-hidden="true"
              >
                {done ? "✓" : i + 1}
              </span>
              <span className={`text-xs leading-tight ${text}`}>
                {m.label}
                <span className="sr-only">
                  {" "}— {state === "current" ? "current step" : state === "done" ? "completed" : "upcoming"}
                </span>
              </span>
            </li>
          );
        })}
      </ol>

      {!compact && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-sm text-slate-700">
            <span className="font-semibold text-navy">Next step: </span>
            {progress.nextStep}
          </p>
          {bidDue && (
            <p className="mt-1 text-xs text-slate-500">
              Bid due <span className="font-semibold text-slate-700">{bidDue}</span>.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
