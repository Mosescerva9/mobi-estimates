import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import {
  intakeStatusBadgeClass,
  intakeStatusLabel,
  unroutedReasonCopy,
} from "@/lib/inbound-intake";
import { sharedIntakeAddress } from "@/lib/intake-email";
import { dismissIntakeAsStaff } from "./actions";
import { adminInboxNoticeCopy } from "./notices";

const VIEWS: { value: string; label: string }[] = [
  { value: "unrouted", label: "Needs routing" },
  { value: "waiting", label: "Waiting on client" },
  { value: "converted", label: "Submitted" },
  { value: "all", label: "All" },
];

interface Row {
  id: string;
  company_id: string | null;
  subject: string | null;
  from_email: string;
  from_name: string | null;
  intake_address: string;
  status: string;
  routed_by: string | null;
  unrouted_reason: string | null;
  sender_verified: boolean;
  attachment_count: number;
  skipped_attachment_count: number;
  project_id: string | null;
  received_at: string;
  companies: { legal_name: string } | null;
}

function fmtDateTime(value: string): string {
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Staff view of every forwarded bid across tenants, including the ones we could
 * not place.
 *
 * The unrouted queue is the one that needs watching: a contractor who forwarded
 * from an address that isn't on their account is sitting on a real bid deadline
 * and has no idea we couldn't match them.
 */
export default async function AdminForwardedBids({
  searchParams,
}: {
  searchParams: Promise<{ view?: string; notice?: string }>;
}) {
  const { view = "unrouted", notice } = await searchParams;
  const supabase = await createClient();

  let query = supabase
    .from("inbound_intake_messages")
    .select(
      "id, company_id, subject, from_email, from_name, intake_address, status, routed_by, unrouted_reason, sender_verified, attachment_count, skipped_attachment_count, project_id, received_at, companies(legal_name)",
    )
    .order("received_at", { ascending: false })
    .limit(100);

  if (view === "unrouted") query = query.eq("status", "unrouted");
  else if (view === "waiting") query = query.in("status", ["pending", "sender_unverified"]);
  else if (view === "converted") query = query.eq("status", "converted");

  const [{ data: messages }, { count: unroutedCount }] = await Promise.all([
    query,
    supabase
      .from("inbound_intake_messages")
      .select("id", { count: "exact", head: true })
      .eq("status", "unrouted"),
  ]);

  const rows = (messages ?? []) as unknown as Row[];
  const noticeCopy = adminInboxNoticeCopy(notice);

  return (
    <div>
      <h1 className="text-2xl font-bold text-navy">Forwarded bids</h1>
      <p className="mt-1 text-slate-500">
        Invitations to bid forwarded to <code className="font-mono">{sharedIntakeAddress()}</code>{" "}
        across all companies, newest first.
      </p>

      {noticeCopy && (
        <p
          className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
            noticeCopy.tone === "success"
              ? "border-green-200 bg-green-50 text-green-800"
              : noticeCopy.tone === "warning"
                ? "border-amber-200 bg-amber-50 text-amber-800"
                : "border-red-200 bg-red-50 text-red-800"
          }`}
        >
          {noticeCopy.message}
        </p>
      )}

      {(unroutedCount ?? 0) > 0 && view !== "unrouted" && (
        <Link
          href="/admin/inbox?view=unrouted"
          className="mt-4 flex items-center justify-between rounded-2xl border border-amber-200 bg-amber-50 px-6 py-4 hover:bg-amber-100"
        >
          <span className="text-sm font-semibold text-amber-900">
            {unroutedCount} forwarded bid{unroutedCount === 1 ? "" : "s"} could not be matched to a
            company
          </span>
          <span className="text-sm font-semibold text-amber-800">Triage →</span>
        </Link>
      )}

      <div className="mt-5 flex flex-wrap gap-2">
        {VIEWS.map((v) => {
          const active = view === v.value;
          const href = v.value === "unrouted" ? "/admin/inbox" : `/admin/inbox?view=${v.value}`;
          return (
            <Link
              key={v.value}
              href={href}
              className={`rounded-full px-3 py-1.5 text-sm font-semibold ${
                active
                  ? "bg-brand text-white"
                  : "border border-slate-300 text-slate-600 hover:border-brand hover:text-brand"
              }`}
            >
              {v.label}
              {v.value === "unrouted" && (unroutedCount ?? 0) > 0 ? ` (${unroutedCount})` : ""}
            </Link>
          );
        })}
      </div>

      {rows.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
          Nothing in this view.
        </div>
      ) : (
        <ul className="mt-6 space-y-4">
          {rows.map((row) => {
            const unrouted = row.status === "unrouted";
            const reason = unrouted ? unroutedReasonCopy(row.unrouted_reason) : null;
            return (
              <li key={row.id} className="rounded-2xl border border-slate-200 bg-white p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate font-semibold text-navy">
                      {row.subject || "(no subject)"}
                    </h2>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {row.from_name ? `${row.from_name} · ` : ""}
                      {row.from_email} → {row.intake_address} · {fmtDateTime(row.received_at)}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${intakeStatusBadgeClass(row.status)}`}
                  >
                    {intakeStatusLabel(row.status)}
                  </span>
                </div>

                <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                  <div className="flex gap-2">
                    <dt className="text-slate-400">Company</dt>
                    <dd className="text-slate-700">
                      {row.companies?.legal_name ?? (
                        <span className="text-amber-700">unmatched</span>
                      )}
                    </dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-slate-400">Routed by</dt>
                    <dd className="text-slate-700">{row.routed_by ?? "—"}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-slate-400">Documents saved</dt>
                    <dd className="text-slate-700">{row.attachment_count}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-slate-400">Not saved</dt>
                    <dd className="text-slate-700">{row.skipped_attachment_count}</dd>
                  </div>
                </dl>

                {reason && (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    <p className="font-semibold">{reason.label}</p>
                    <p className="mt-1">{reason.nextStep}</p>
                    {row.skipped_attachment_count > 0 && (
                      <p className="mt-2 text-xs">
                        {row.skipped_attachment_count} attachment(s) were counted but not stored —
                        documents are only saved once a forward is matched to a company.
                      </p>
                    )}
                  </div>
                )}

                <div className="mt-4 flex flex-wrap items-center gap-4">
                  {row.project_id && (
                    <Link
                      href={`/admin/projects/${row.project_id}`}
                      className="text-sm font-semibold text-brand hover:underline"
                    >
                      Open project →
                    </Link>
                  )}
                  {row.status !== "converted" && row.status !== "dismissed" && (
                    <form action={dismissIntakeAsStaff}>
                      <input type="hidden" name="messageId" value={row.id} />
                      <button
                        type="submit"
                        className="text-sm font-semibold text-slate-400 hover:text-red-600"
                      >
                        Dismiss
                      </button>
                    </form>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
