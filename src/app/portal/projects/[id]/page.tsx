import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import {
  DELIVERABLES_BUCKET,
  PROJECT_FILES_BUCKET,
  PROJECT_TYPES,
  formatBytes,
  statusBadgeClass,
  statusLabel,
} from "@/lib/projects";
import { approveDeliverable, markReviewed } from "@/app/portal/estimates/actions";
import { canViewCustomerDeliverables, customerDeliverableGateMessage } from "@/lib/estimate-jobs";
import {
  INTRO_OFFER,
  introOfferClaimStatusLabel,
  introOfferRejectionPublicCopy,
} from "@/lib/intro-offer";
import { MilestoneProgress } from "@/components/MilestoneProgress";
import { AddProjectFilesForm } from "./AddProjectFilesForm";
import { getCustomerRevisionHistory, submitCustomerRevision, type CustomerRevisionHistoryResult } from "./actions";
import { CustomerRevisionRequestForm, RevisionNotice } from "./CustomerRevisionRequestForm";

export const metadata: Metadata = {
  title: "Project — Mobi Estimates",
  robots: { index: false },
};

function fmtDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function typeLabel(value: string | null): string {
  return PROJECT_TYPES.find((t) => t.value === value)?.label ?? "—";
}

export default async function ProjectDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ upload?: string; revision?: string }>;
}) {
  await requireUser();
  const { id } = await params;
  const { upload, revision } = await searchParams;
  const supabase = await createClient();
  const customerDeliverablesUnlocked = canViewCustomerDeliverables();

  const { data: project } = await supabase
    .from("projects")
    .select("id, company_id, project_number, name, status, project_type, address, bid_due_at, requested_completion_at, prevailing_wage, created_at")
    .eq("id", id)
    .is("deleted_at", null)
    .maybeSingle();

  if (!project) notFound();

  const [{ data: scope }, { data: files }, { data: timeline }, { data: deliverables }, revisionHistory, { data: introOffer }] = await Promise.all([
    supabase.from("project_scopes").select("data").eq("project_id", id).maybeSingle(),
    supabase
      .from("project_files")
      .select("id, file_name, category, storage_path, size_bytes, created_at")
      .eq("project_id", id)
      .is("deleted_at", null)
      .order("created_at", { ascending: true }),
    supabase.rpc("client_timeline", { p_project: id }),
    customerDeliverablesUnlocked
      ? supabase
          .from("deliverables")
          .select("id, file_name, category, storage_path, size_bytes, created_at, client_reviewed_at, client_approved_at")
          .eq("project_id", id)
          .is("deleted_at", null)
          .order("created_at", { ascending: false })
      : Promise.resolve({ data: [] }),
    getCustomerRevisionHistory(id),
    supabase.rpc("intro_offer_status_for_project", { p_project: id }),
  ]);

  const introOfferClaim = introOffer as {
    ok?: boolean;
    exists?: boolean;
    status?: string | null;
    rejection_reason_class?: string | null;
  } | null;

  // Short-lived signed URLs for private files (5 min).
  const fileRows = files ?? [];
  const signedByPath = new Map<string, string>();
  if (fileRows.length > 0) {
    const { data: signed } = await supabase.storage
      .from(PROJECT_FILES_BUCKET)
      .createSignedUrls(fileRows.map((f) => f.storage_path), 300);
    for (const s of signed ?? []) {
      if (s.signedUrl && s.path) signedByPath.set(s.path, s.signedUrl);
    }
  }

  // Signed URLs for delivered estimates (5 min).
  const delRows = (deliverables ?? []) as Array<{
    id: string; file_name: string; category: string; storage_path: string;
    size_bytes: number | null; created_at: string;
    client_reviewed_at: string | null; client_approved_at: string | null;
  }>;
  const delUrls = new Map<string, string>();
  if (delRows.length > 0) {
    const { data: signed } = await supabase.storage
      .from(DELIVERABLES_BUCKET)
      .createSignedUrls(delRows.map((d) => d.storage_path), 300);
    for (const s of signed ?? []) if (s.signedUrl && s.path) delUrls.set(s.path, s.signedUrl);
  }

  const scopeData = (scope?.data ?? {}) as {
    trades?: string | null;
    notes?: string | null;
    estimateType?: string | null;
    alternatesAllowances?: string | null;
    exclusions?: string | null;
    openQuestions?: string | null;
    sharedDocumentLink?: string | null;
  };
  const events = (timeline ?? []) as { to_status: string; client_note: string | null; created_at: string }[];

  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/portal/projects" className="text-sm font-semibold text-slate-500 hover:text-brand">
        ← My projects
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">{project.name}</h1>
          <p className="mt-1 text-sm text-slate-400">{project.project_number ?? "—"}</p>
        </div>
        <span className={`inline-block rounded-full px-3 py-1 text-sm font-semibold ${statusBadgeClass(project.status)}`}>
          {statusLabel(project.status)}
        </span>
      </div>

      {upload === "partial" && (
        <p className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Your project was created, but some files didn&rsquo;t finish uploading. Please retry the
          missing files in Plans &amp; documents below.
        </p>
      )}

      <RevisionNotice code={revision} />

      {introOfferClaim?.ok && introOfferClaim.exists && introOfferClaim.status && (
        <FreeOfferStatus status={introOfferClaim.status} reasonClass={introOfferClaim.rejection_reason_class ?? null} />
      )}

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-base font-bold text-navy">Progress</h2>
        <div className="mt-4">
          <MilestoneProgress status={project.status} bidDueAt={project.bid_due_at} />
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-base font-bold text-navy">Details</h2>
        <dl className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2">
          <Detail label="Project type" value={typeLabel(project.project_type)} />
          <Detail label="Bid due" value={fmtDate(project.bid_due_at)} />
          <Detail label="Requested completion" value={fmtDate(project.requested_completion_at)} />
          <Detail label="Address" value={project.address || "—"} />
          <Detail label="Prevailing wage" value={project.prevailing_wage ? "Yes" : "No"} />
          <Detail label="Estimate type" value={scopeData.estimateType || "—"} />
          <Detail label="Trades / scopes" value={scopeData.trades || "—"} />
          <Detail label="Submitted" value={fmtDate(project.created_at)} />
        </dl>
        {scopeData.notes && (
          <div className="mt-4">
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Scope notes</dt>
            <dd className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{scopeData.notes}</dd>
          </div>
        )}
        {scopeData.alternatesAllowances && <DetailBlock label="Base bid / alternates / allowances" value={scopeData.alternatesAllowances} />}
        {scopeData.exclusions && <DetailBlock label="Known exclusions" value={scopeData.exclusions} />}
        {scopeData.openQuestions && <DetailBlock label="Open questions" value={scopeData.openQuestions} />}
        {scopeData.sharedDocumentLink && <DetailBlock label="Shared document link" value={scopeData.sharedDocumentLink} />}
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-base font-bold text-navy">Plans & documents</h2>
        {fileRows.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No files were uploaded for this project.</p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {fileRows.map((f) => {
              const url = signedByPath.get(f.storage_path);
              return (
                <li key={f.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-navy">{f.file_name}</div>
                    <div className="text-xs text-slate-400">
                      {f.category} · {formatBytes(f.size_bytes)}
                    </div>
                  </div>
                  {url ? (
                    <a href={url} target="_blank" rel="noopener noreferrer"
                      className="text-sm font-semibold text-brand hover:underline">
                      Download
                    </a>
                  ) : (
                    <span className="text-xs text-slate-400">Unavailable</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        <AddProjectFilesForm
          projectId={id}
          companyId={project.company_id}
          defaultOpen={upload === "partial" || fileRows.length === 0}
          partialUpload={upload === "partial"}
        />
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-base font-bold text-navy">Completed estimates</h2>
        {!customerDeliverablesUnlocked && (
          <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            {customerDeliverableGateMessage(null)}
          </p>
        )}
        {!customerDeliverablesUnlocked || delRows.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            No completed estimates are available for customer access right now.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {delRows.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-navy">{d.file_name}</div>
                  <div className="text-xs text-slate-400">
                    {d.category} · {formatBytes(d.size_bytes)} · {fmtDate(d.created_at)}
                  </div>
                </div>
                {d.client_approved_at ? (
                  <span className="rounded-full bg-green-50 px-2.5 py-1 text-xs font-semibold text-green-700">Approved</span>
                ) : d.client_reviewed_at ? (
                  <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">Reviewed</span>
                ) : null}
                {delUrls.get(d.storage_path) ? (
                  <a href={delUrls.get(d.storage_path)} target="_blank" rel="noopener noreferrer"
                    className="text-sm font-semibold text-brand hover:underline">Download</a>
                ) : <span className="text-xs text-slate-400">Unavailable</span>}
                {!d.client_reviewed_at && (
                  <form action={markReviewed}>
                    <input type="hidden" name="deliverableId" value={d.id} />
                    <input type="hidden" name="projectId" value={id} />
                    <button className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-navy hover:border-brand hover:text-brand">
                      Mark reviewed
                    </button>
                  </form>
                )}
                {!d.client_approved_at && (
                  <form action={approveDeliverable}>
                    <input type="hidden" name="deliverableId" value={d.id} />
                    <input type="hidden" name="projectId" value={id} />
                    <button className="rounded-full bg-navy px-3 py-1 text-xs font-semibold text-white hover:opacity-90">
                      Approve
                    </button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-base font-bold text-navy">Request a revision</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          If something needs to be added, removed, revised, or clarified, submit it here so Mobi can review it against the project documents.
        </p>
        <CustomerRevisionRequestForm action={submitCustomerRevision} projectId={id} />
      </section>

      <RevisionHistoryPanel history={revisionHistory} />

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-base font-bold text-navy">Status timeline</h2>
        <ol className="mt-4 space-y-4">
          {events.length === 0 ? (
            <TimelineItem
              label={statusLabel(project.status)}
              note="Project received. We'll confirm scope and a delivery date shortly."
              at={project.created_at}
            />
          ) : (
            events.map((ev, i) => (
              <TimelineItem key={i} label={statusLabel(ev.to_status)} note={ev.client_note} at={ev.created_at} />
            ))
          )}
        </ol>
      </section>
    </div>
  );
}

/**
 * Customer-facing free-offer status. Shows requested/accepted/rejected using
 * only fixed safe public copy — never internal notes. On rejection the customer
 * sees the public reason class copy and that they may retry a supported request.
 */
function FreeOfferStatus({ status, reasonClass }: { status: string; reasonClass: string | null }) {
  const tone =
    status === "accepted" || status === "consumed"
      ? "border-green-200 bg-green-50 text-green-900"
      : status === "rejected"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : "border-blue-200 bg-blue-50 text-blue-900";
  return (
    <section className={`mt-4 rounded-2xl border px-5 py-4 ${tone}`} aria-label="Free estimate status">
      <p className="text-sm font-bold">{introOfferClaimStatusLabel(status)}</p>
      {status === "requested" && (
        <p className="mt-1 text-sm">{INTRO_OFFER.reviewNote}</p>
      )}
      {(status === "accepted" || status === "consumed") && (
        <p className="mt-1 text-sm">
          Your free qualifying estimate was accepted and moves through our normal review and approval steps.
        </p>
      )}
      {status === "rejected" && (
        <p className="mt-1 text-sm">
          {introOfferRejectionPublicCopy(reasonClass)} You&rsquo;re welcome to submit a supported request.
        </p>
      )}
    </section>
  );
}

function RevisionHistoryPanel({ history }: { history: CustomerRevisionHistoryResult }) {
  if (!history.available) {
    const copy =
      history.reason === "engine_unavailable"
        ? "Revision history is temporarily unavailable. Mobi can still review changes through the request form above."
        : history.reason === "project_unlinked"
          ? "Revision history will appear here after this project is linked to the estimating workspace."
          : "Revision history could not be loaded right now. Please try again later or contact Mobi directly.";
    return (
      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-base font-bold text-navy">Revision history</h2>
        <p className="mt-3 text-sm text-slate-500">{copy}</p>
      </section>
    );
  }

  return (
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-base font-bold text-navy">Revision history</h2>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">
        Track requested changes and clarifications here. This is read-only; use the request form above for new changes.
      </p>
      {history.items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No revision requests have been recorded for this project yet.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {history.items.map((item) => (
            <li key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-navy">{item.requested_action_label}</p>
                  <p className="mt-1 text-sm leading-relaxed text-slate-700">{item.summary}</p>
                </div>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-600">
                  {item.status_label}
                </span>
              </div>
              <dl className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                {item.trade_label && <HistoryMeta label="Scope" value={item.trade_label} />}
                {item.sheet_ref && <HistoryMeta label="Sheet" value={item.sheet_ref} />}
                {item.follow_up_label && <HistoryMeta label="Next step" value={item.follow_up_label} />}
                <HistoryMeta label="Versions" value={String(item.version_count ?? 0)} />
                {item.created_at && <HistoryMeta label="Requested" value={fmtDateTime(item.created_at)} />}
                {item.latest_version_created_at && <HistoryMeta label="Latest update" value={fmtDateTime(item.latest_version_created_at)} />}
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function HistoryMeta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-600">{value}</dd>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-700">{value}</dd>
    </div>
  );
}

function DetailBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-4">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{value}</dd>
    </div>
  );
}

function TimelineItem({ label, note, at }: { label: string; note: string | null; at: string }) {
  return (
    <li className="flex gap-3">
      <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-brand" />
      <div>
        <div className="text-sm font-semibold text-navy">{label}</div>
        {note && <div className="text-sm text-slate-600">{note}</div>}
        <div className="text-xs text-slate-400">{fmtDateTime(at)}</div>
      </div>
    </li>
  );
}
