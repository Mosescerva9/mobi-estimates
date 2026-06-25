import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import {
  PROJECT_FILES_BUCKET,
  PROJECT_TYPES,
  formatBytes,
  statusBadgeClass,
  statusLabel,
} from "@/lib/projects";

export const metadata: Metadata = {
  title: "Project — Mobi Estimates",
  robots: { index: false },
};

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

export default async function ProjectDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ upload?: string }>;
}) {
  await requireUser();
  const { id } = await params;
  const { upload } = await searchParams;
  const supabase = await createClient();

  const { data: project } = await supabase
    .from("projects")
    .select("id, project_number, name, status, project_type, address, bid_due_at, requested_completion_at, prevailing_wage, created_at")
    .eq("id", id)
    .is("deleted_at", null)
    .maybeSingle();

  if (!project) notFound();

  const [{ data: scope }, { data: files }, { data: timeline }] = await Promise.all([
    supabase.from("project_scopes").select("data").eq("project_id", id).maybeSingle(),
    supabase
      .from("project_files")
      .select("id, file_name, category, storage_path, size_bytes, created_at")
      .eq("project_id", id)
      .is("deleted_at", null)
      .order("created_at", { ascending: true }),
    supabase.rpc("client_timeline", { p_project: id }),
  ]);

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

  const scopeData = (scope?.data ?? {}) as { trades?: string | null; notes?: string | null };
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
          Your project was created, but some files didn&rsquo;t finish uploading. Please contact
          support or re-submit the missing files.
        </p>
      )}

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-base font-bold text-navy">Details</h2>
        <dl className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2">
          <Detail label="Project type" value={typeLabel(project.project_type)} />
          <Detail label="Bid due" value={fmtDate(project.bid_due_at)} />
          <Detail label="Address" value={project.address || "—"} />
          <Detail label="Prevailing wage" value={project.prevailing_wage ? "Yes" : "No"} />
          <Detail label="Trades / scopes" value={scopeData.trades || "—"} />
          <Detail label="Submitted" value={fmtDate(project.created_at)} />
        </dl>
        {scopeData.notes && (
          <div className="mt-4">
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Scope notes</dt>
            <dd className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{scopeData.notes}</dd>
          </div>
        )}
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
      </section>

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

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-700">{value}</dd>
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
