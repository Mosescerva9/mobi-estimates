import {
  INTRO_OFFER_REJECTION_REASON_CLASSES,
  introOfferClaimStatusLabel,
  introOfferRejectionPublicCopy,
} from "@/lib/intro-offer";
import { decideIntroOfferClaim } from "./actions";

export interface IntroOfferClaimRow {
  status: string;
  rejection_reason_class: string | null;
  internal_note: string | null;
  requested_at: string | null;
  decided_at: string | null;
}

function fmt(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

const REASON_LABELS: Record<string, string> = {
  unsupported_scope: "Unsupported scope",
  incomplete_documents: "Incomplete documents",
  complexity_out_of_range: "Complexity out of range",
  duplicate_request: "Duplicate request",
  other: "Other",
};

/**
 * Staff review of the free-offer (intro offer) qualification. Accept or reject
 * with a fixed public reason class. Internal notes stay internal; the customer
 * only sees the safe public copy for the chosen reason class.
 */
export function IntroOfferPanel({
  projectId,
  claim,
}: {
  projectId: string;
  claim: IntroOfferClaimRow | null;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-base font-bold text-navy">Free-offer qualification</h2>
      <p className="mt-1 text-sm text-slate-500">
        One qualifying estimate is free per new company. Review supported scope and
        project complexity before accepting. Rejection uses a fixed public reason
        class; internal notes are never shown to the customer.
      </p>

      {!claim ? (
        <p className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
          This project was not submitted through the free-offer flow (paid entitlement or no claim).
        </p>
      ) : (
        <>
          <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Status</dt>
              <dd className="mt-0.5 text-sm font-semibold text-navy">{introOfferClaimStatusLabel(claim.status)}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Requested</dt>
              <dd className="mt-0.5 text-sm text-slate-700">{fmt(claim.requested_at)}</dd>
            </div>
            {claim.decided_at && (
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Decided</dt>
                <dd className="mt-0.5 text-sm text-slate-700">{fmt(claim.decided_at)}</dd>
              </div>
            )}
            {claim.rejection_reason_class && (
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Reason (public)</dt>
                <dd className="mt-0.5 text-sm text-slate-700">
                  {introOfferRejectionPublicCopy(claim.rejection_reason_class)}
                </dd>
              </div>
            )}
          </dl>

          {claim.internal_note && (
            <div className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Internal note (never shown to customer): {claim.internal_note}
            </div>
          )}

          {claim.status === "requested" && (
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <form action={decideIntroOfferClaim} className="rounded-xl border border-green-200 bg-green-50 p-4">
                <input type="hidden" name="projectId" value={projectId} />
                <input type="hidden" name="decision" value="accept" />
                <p className="text-sm font-semibold text-green-800">Accept qualification</p>
                <p className="mt-1 text-xs text-green-700">
                  The free estimate proceeds through the normal review and approval gates.
                </p>
                <textarea
                  name="internalNote"
                  rows={2}
                  placeholder="Internal note (optional, never shown to customer)"
                  className="mt-2 w-full rounded-lg border border-green-300 bg-white px-3 py-2 text-sm"
                />
                <button className="mt-3 w-full rounded-full bg-green-700 px-4 py-2 text-sm font-semibold text-white hover:bg-green-800">
                  Accept free estimate
                </button>
              </form>

              <form action={decideIntroOfferClaim} className="rounded-xl border border-red-200 bg-red-50 p-4">
                <input type="hidden" name="projectId" value={projectId} />
                <input type="hidden" name="decision" value="reject" />
                <p className="text-sm font-semibold text-red-800">Reject as not qualifying</p>
                <p className="mt-1 text-xs text-red-700">
                  The company may retry a supported request afterward.
                </p>
                <select
                  name="reasonClass"
                  defaultValue="unsupported_scope"
                  className="mt-2 w-full rounded-lg border border-red-300 bg-white px-3 py-2 text-sm"
                >
                  {INTRO_OFFER_REJECTION_REASON_CLASSES.map((rc) => (
                    <option key={rc} value={rc}>{REASON_LABELS[rc] ?? rc}</option>
                  ))}
                </select>
                <textarea
                  name="internalNote"
                  rows={2}
                  placeholder="Internal note (optional, never shown to customer)"
                  className="mt-2 w-full rounded-lg border border-red-300 bg-white px-3 py-2 text-sm"
                />
                <button className="mt-3 w-full rounded-full bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800">
                  Reject free estimate
                </button>
              </form>
            </div>
          )}
        </>
      )}
    </section>
  );
}
