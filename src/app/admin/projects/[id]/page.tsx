import Link from "next/link";
import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import {
  ALL_STATUSES,
  DELIVERABLES_BUCKET,
  PROJECT_FILES_BUCKET,
  PROJECT_TYPES,
  formatBytes,
  statusBadgeClass,
  statusLabel,
} from "@/lib/projects";
import { assignStaff, changeStatus } from "./actions";
import { DeliverableUpload } from "./DeliverableUpload";
import { EstimateJobPanel } from "./EstimateJobPanel";
import { EnginePanel } from "./EnginePanel";
import { AutomationV1Panel } from "./AutomationV1Panel";
import { TakeoffWorkbenchPanel } from "./TakeoffWorkbenchPanel";
import { engineConfigured } from "@/lib/engine";
import {
  canUploadCustomerDeliverable,
  customerDeliverableGateMessage,
  estimateDocumentRegisterHealth,
  estimateJobStatusLabel,
  resolveEstimateJobEventFilter,
  resolveEstimateJobNotice,
} from "@/lib/estimate-jobs";

function fmtDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function fmtDateTime(value: string): string {
  return new Date(value).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}
function typeLabel(value: string | null): string {
  return PROJECT_TYPES.find((t) => t.value === value)?.label ?? "—";
}

export default async function AdminProjectDetail({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ estimateJobNotice?: string | string[]; estimateJobEventFilter?: string | string[] }>;
}) {
  const { id } = await params;
  const { estimateJobNotice: rawEstimateJobNotice, estimateJobEventFilter: rawEstimateJobEventFilter } = await searchParams;
  const estimateJobNoticeCode = Array.isArray(rawEstimateJobNotice) ? rawEstimateJobNotice[0] : rawEstimateJobNotice;
  const estimateJobNotice = resolveEstimateJobNotice(estimateJobNoticeCode);
  const estimateJobEventFilterCode = Array.isArray(rawEstimateJobEventFilter)
    ? rawEstimateJobEventFilter[0]
    : rawEstimateJobEventFilter;
  const estimateJobEventFilter = resolveEstimateJobEventFilter(estimateJobEventFilterCode);
  const supabase = await createClient();

  const { data: project } = await supabase
    .from("projects")
    .select("id, project_number, name, status, project_type, address, bid_due_at, requested_completion_at, prevailing_wage, is_public, created_at, company_id, created_by, engine_project_id, engine_status, engine_page_count, engine_synced_at, companies(legal_name, company_type, website)")
    .eq("id", id)
    .is("deleted_at", null)
    .maybeSingle();

  if (!project) notFound();

  const [
    { data: scope },
    { data: files },
    { data: deliverables },
    { data: history },
    { data: assignment },
    { data: staff },
  ] = await Promise.all([
    supabase.from("project_scopes").select("data").eq("project_id", id).maybeSingle(),
    supabase.from("project_files").select("id, file_name, category, storage_path, size_bytes").eq("project_id", id).is("deleted_at", null).order("created_at"),
    supabase.from("deliverables").select("id, file_name, category, storage_path, size_bytes, created_at").eq("project_id", id).is("deleted_at", null).order("created_at", { ascending: false }),
    supabase.from("project_status_history").select("from_status, to_status, client_note, internal_note, created_at").eq("project_id", id).order("created_at", { ascending: false }),
    supabase.from("project_assignments").select("estimator_id, reviewer_id").eq("project_id", id).maybeSingle(),
    supabase.from("profiles").select("id, full_name, email").in("role", ["estimator", "reviewer", "admin"]),
  ]);

  const fileRows = files ?? [];
  const delRows = deliverables ?? [];
  const staffRows = staff ?? [];

  // Read-only: the admin page must not create/sync EstimateJob rows as a
  // render side effect. Job creation happens explicitly via project
  // submission (src/app/api/projects/route.ts) or the "Generate / refresh
  // intake review" action (regenerateIntakeReview), which calls
  // ensureEstimateJobForProject itself. EstimateJobPanel already renders a
  // "No internal EstimateJob was found" state when this is null.
  const { data: estimateJobRow } = await supabase
    .from("estimate_jobs")
    .select("id, status, priority, blocked_reason, intake_review, automation_state, target_delivery_at, updated_at")
    .eq("project_id", id)
    .maybeSingle();

  const [{ data: estimateDocuments }, { data: estimateEvents }] = estimateJobRow?.id
    ? await Promise.all([
        supabase
          .from("estimate_job_documents")
          .select("id, file_name, category, document_type, page_count, processing_status, review_status, review_notes, sheet_index, project_file_id")
          .eq("estimate_job_id", estimateJobRow.id)
          .order("received_at", { ascending: true }),
        supabase
          .from("estimate_job_events")
          .select("id, event_type, summary, actor_type, created_at, payload")
          .eq("estimate_job_id", estimateJobRow.id)
          .order("created_at", { ascending: false })
          .limit(20),
      ])
    : [{ data: [] }, { data: [] }];

  const fileUrls = new Map<string, string>();
  if (fileRows.length > 0) {
    const { data: signed } = await supabase.storage.from(PROJECT_FILES_BUCKET)
      .createSignedUrls(fileRows.map((f) => f.storage_path), 300);
    for (const s of signed ?? []) if (s.signedUrl && s.path) fileUrls.set(s.path, s.signedUrl);
  }
  const delUrls = new Map<string, string>();
  if (delRows.length > 0) {
    const { data: signed } = await supabase.storage.from(DELIVERABLES_BUCKET)
      .createSignedUrls(delRows.map((d) => d.storage_path), 300);
    for (const s of signed ?? []) if (s.signedUrl && s.path) delUrls.set(s.path, s.signedUrl);
  }

  const company = project.companies as unknown as { legal_name: string; website: string | null } | null;
  const scopeData = (scope?.data ?? {}) as {
    trades?: string | null;
    notes?: string | null;
    estimateType?: string | null;
    alternatesAllowances?: string | null;
    exclusions?: string | null;
    openQuestions?: string | null;
    sharedDocumentLink?: string | null;
  };
  const events = (history ?? []) as { from_status: string | null; to_status: string; client_note: string | null; internal_note: string | null; created_at: string }[];
  const assign = assignment as { estimator_id: string | null; reviewer_id: string | null } | null;

  const registerHealth = estimateDocumentRegisterHealth(
    fileRows.map((f) => f.id),
    (estimateDocuments ?? []).map((d) => (d as { project_file_id: string | null }).project_file_id),
  );

  return (
    <div>
      <Link href="/admin" className="text-sm font-semibold text-slate-500 hover:text-brand">← Queue</Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">{project.name}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {project.project_number ?? "—"} · {company?.legal_name ?? "—"}
          </p>
        </div>
        <span className={`inline-block rounded-full px-3 py-1 text-sm font-semibold ${statusBadgeClass(project.status)}`}>
          {statusLabel(project.status)}
        </span>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          {/* details */}
          <section className="rounded-2xl border border-slate-200 bg-white p-6">
            <h2 className="text-base font-bold text-navy">Details</h2>
            <dl className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <Detail label="Project type" value={typeLabel(project.project_type)} />
              <Detail label="Bid due" value={fmtDate(project.bid_due_at)} />
              <Detail label="Requested completion" value={fmtDate(project.requested_completion_at)} />
              <Detail label="Address" value={project.address || "—"} />
              <Detail label="Prevailing wage" value={project.prevailing_wage ? "Yes" : "No"} />
              <Detail label="Public project" value={project.is_public ? "Yes" : "No"} />
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
            {scopeData.alternatesAllowances && (
              <DetailBlock label="Base bid / alternates / allowances" value={scopeData.alternatesAllowances} />
            )}
            {scopeData.exclusions && <DetailBlock label="Known exclusions" value={scopeData.exclusions} />}
            {scopeData.openQuestions && <DetailBlock label="Open questions" value={scopeData.openQuestions} />}
            {scopeData.sharedDocumentLink && <DetailBlock label="Shared document link" value={scopeData.sharedDocumentLink} />}
          </section>

          <EstimateJobPanel
            projectId={project.id}
            job={estimateJobRow}
            documents={estimateDocuments ?? []}
            events={estimateEvents ?? []}
            notice={estimateJobNotice}
            eventFilter={estimateJobEventFilter}
            registerHealth={registerHealth}
          />

          {/* customer files */}
          <section className="rounded-2xl border border-slate-200 bg-white p-6">
            <h2 className="text-base font-bold text-navy">Customer files</h2>
            {fileRows.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">No files uploaded.</p>
            ) : (
              <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
                {fileRows.map((f) => (
                  <li key={f.id} className="flex items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-navy">{f.file_name}</div>
                      <div className="text-xs text-slate-400">{f.category} · {formatBytes(f.size_bytes)}</div>
                    </div>
                    {fileUrls.get(f.storage_path) ? (
                      <a href={fileUrls.get(f.storage_path)} target="_blank" rel="noopener noreferrer"
                        className="text-sm font-semibold text-brand hover:underline">Download</a>
                    ) : <span className="text-xs text-slate-400">Unavailable</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* estimating engine */}
          <EnginePanel
            projectId={project.id}
            configured={engineConfigured()}
            engineProjectId={project.engine_project_id ?? null}
            engineStatus={project.engine_status ?? null}
            enginePageCount={project.engine_page_count ?? null}
            engineSyncedAt={project.engine_synced_at ?? null}
          />

          <AutomationV1Panel
            projectId={project.id}
            engineProjectId={project.engine_project_id ?? null}
            engineStatus={project.engine_status ?? null}
            estimateJobStatus={estimateJobRow?.status ?? null}
          />

          <TakeoffWorkbenchPanel projectId={project.id} />

          {/* deliverables */}
          <section className="rounded-2xl border border-slate-200 bg-white p-6">
            <h2 className="text-base font-bold text-navy">Deliverables</h2>
            <p className="mt-1 text-sm text-slate-500">
              Customer-visible deliverables must only be uploaded after internal owner (human) approval. Uploading here
              does not send an email or notify the customer automatically — it makes the file immediately downloadable
              in the customer portal.
            </p>
            <div className="mt-4">
              <DeliverableUpload
                projectId={project.id}
                companyId={project.company_id}
                deliveryUnlocked={canUploadCustomerDeliverable(estimateJobRow?.status)}
                statusLabel={estimateJobRow?.status ? estimateJobStatusLabel(estimateJobRow.status) : null}
                gateMessage={customerDeliverableGateMessage(estimateJobRow?.status)}
              />
            </div>
            {delRows.length > 0 && (
              <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
                {delRows.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-navy">{d.file_name}</div>
                      <div className="text-xs text-slate-400">{d.category} · {formatBytes(d.size_bytes)} · {fmtDate(d.created_at)}</div>
                    </div>
                    {delUrls.get(d.storage_path) ? (
                      <a href={delUrls.get(d.storage_path)} target="_blank" rel="noopener noreferrer"
                        className="text-sm font-semibold text-brand hover:underline">Download</a>
                    ) : <span className="text-xs text-slate-400">Unavailable</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* timeline */}
          <section className="rounded-2xl border border-slate-200 bg-white p-6">
            <h2 className="text-base font-bold text-navy">Status timeline</h2>
            {events.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">No status changes recorded yet.</p>
            ) : (
              <ol className="mt-4 space-y-4">
                {events.map((ev, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-brand" />
                    <div>
                      <div className="text-sm font-semibold text-navy">{statusLabel(ev.to_status)}</div>
                      {ev.client_note && <div className="text-sm text-slate-600">Client: {ev.client_note}</div>}
                      {ev.internal_note && (
                        <div className="mt-0.5 rounded bg-amber-50 px-2 py-1 text-sm text-amber-800">
                          Internal: {ev.internal_note}
                        </div>
                      )}
                      <div className="text-xs text-slate-400">{fmtDateTime(ev.created_at)}</div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>

        {/* action sidebar */}
        <div className="space-y-6">
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="text-base font-bold text-navy">Update status</h2>
            <form action={changeStatus} className="mt-3 space-y-3">
              <input type="hidden" name="projectId" value={project.id} />
              <select name="status" defaultValue={project.status}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                {ALL_STATUSES.map((s) => (
                  <option key={s} value={s}>{statusLabel(s)}</option>
                ))}
              </select>
              <textarea name="client_note" rows={2} placeholder="Note visible to the customer (optional)"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              <textarea name="internal_note" rows={2} placeholder="Internal note (never shown to customer)"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              <button className="w-full rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
                Save status
              </button>
            </form>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="text-base font-bold text-navy">Assignment</h2>
            <form action={assignStaff} className="mt-3 space-y-3">
              <input type="hidden" name="projectId" value={project.id} />
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">Estimator</label>
                <select name="estimator_id" defaultValue={assign?.estimator_id ?? ""}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  <option value="">Unassigned</option>
                  {staffRows.map((s) => (
                    <option key={s.id} value={s.id}>{s.full_name || s.email}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">Reviewer</label>
                <select name="reviewer_id" defaultValue={assign?.reviewer_id ?? ""}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  <option value="">Unassigned</option>
                  {staffRows.map((s) => (
                    <option key={s.id} value={s.id}>{s.full_name || s.email}</option>
                  ))}
                </select>
              </div>
              <button className="w-full rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand">
                Save assignment
              </button>
            </form>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 text-sm">
            <h2 className="text-base font-bold text-navy">Company</h2>
            <dl className="mt-3 space-y-2">
              <Detail label="Name" value={company?.legal_name ?? "—"} />
              <Detail label="Website" value={company?.website || "—"} />
            </dl>
          </section>
        </div>
      </div>
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
