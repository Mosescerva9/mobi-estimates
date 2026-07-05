"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { fieldClass, labelClass } from "@/components/AuthShell";
import {
  ACCEPT_ATTR,
  DEFAULT_FILE_CATEGORY,
  FILE_CATEGORIES,
  MAX_FILES,
  MAX_FILE_BYTES,
  PROJECT_FILES_BUCKET,
  PROJECT_TYPES,
  buildStoragePath,
  formatBytes,
  mergePickedFiles,
  validateProjectFile,
} from "@/lib/projects";

interface PickedFile {
  file: File;
  category: string;
  error?: string;
}

export function NewProjectForm() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState("");
  const [projectType, setProjectType] = useState("");
  const [address, setAddress] = useState("");
  const [bidDueAt, setBidDueAt] = useState("");
  const [requestedCompletionAt, setRequestedCompletionAt] = useState("");
  const [estimateType, setEstimateType] = useState("");
  const [trades, setTrades] = useState("");
  const [scopeNotes, setScopeNotes] = useState("");
  const [alternatesAllowances, setAlternatesAllowances] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [openQuestions, setOpenQuestions] = useState("");
  const [sharedDocumentLink, setSharedDocumentLink] = useState("");
  const [prevailingWage, setPrevailingWage] = useState(false);
  const [isPublicProject, setIsPublicProject] = useState(false);
  const [files, setFiles] = useState<PickedFile[]>([]);

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);

  function addFiles(list: FileList | null) {
    if (!list) return;
    setError(null);
    const next: PickedFile[] = Array.from(list).map((file) => ({
      file,
      category: DEFAULT_FILE_CATEGORY,
      error: validateProjectFile(file),
    }));
    setFiles((prev) => {
      const { combined, overflow } = mergePickedFiles(prev, next);
      if (overflow > 0) {
        setError(
          `Only ${MAX_FILES} files are allowed per upload. ${overflow} file(s) were not added — remove some files or upload the rest separately.`,
        );
      }
      return combined;
    });
    if (inputRef.current) inputRef.current.value = "";
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  function setCategory(idx: number, category: string) {
    setFiles((prev) => prev.map((f, i) => (i === idx ? { ...f, category } : f)));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (name.trim().length < 2) {
      setError("Please enter a project name.");
      return;
    }
    if (files.some((f) => f.error)) {
      setError("Please remove the files flagged below before submitting.");
      return;
    }

    setSubmitting(true);
    try {
      // 1) Create the project record (server-validated).
      setProgress("Creating project…");
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          projectType: projectType || undefined,
          address: address.trim() || undefined,
          bidDueAt: bidDueAt || undefined,
          requestedCompletionAt: requestedCompletionAt || undefined,
          trades: trades.trim() || undefined,
          scopeNotes: scopeNotes.trim() || undefined,
          estimateType: estimateType || undefined,
          alternatesAllowances: alternatesAllowances.trim() || undefined,
          exclusions: exclusions.trim() || undefined,
          openQuestions: openQuestions.trim() || undefined,
          sharedDocumentLink: sharedDocumentLink.trim() || undefined,
          prevailingWage,
          isPublicProject,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (data.redirect) {
          router.push(data.redirect as string);
          return;
        }
        throw new Error(data.error || "Could not create the project.");
      }

      const { id, companyId } = data as { id: string; companyId: string };

      // 2) Upload files directly to private Storage (bypasses the serverless
      //    body limit) and record each one's metadata.
      if (files.length > 0) {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();

        let done = 0;
        const failed: string[] = [];
        for (const { file, category } of files) {
          setProgress(`Uploading files… (${done + 1}/${files.length})`);
          try {
            const path = buildStoragePath(companyId, id, file.name);
            const { error: upErr } = await supabase.storage
              .from(PROJECT_FILES_BUCKET)
              .upload(path, file, { contentType: file.type || undefined, upsert: false });
            if (upErr) {
              failed.push(file.name);
              continue;
            }
            const { error: metaErr } = await supabase.from("project_files").insert({
              project_id: id,
              company_id: companyId,
              category,
              storage_path: path,
              file_name: file.name,
              mime_type: file.type || null,
              size_bytes: file.size,
              uploaded_by: user?.id ?? null,
            });
            if (metaErr) failed.push(file.name);
            else done += 1;
          } catch {
            // Network-level exceptions (e.g. a dropped connection to Storage)
            // must not escape the loop — an uncaught throw here skips the
            // partial-failure redirect below and strands the project with a
            // consumed credit, no visible file, and no error shown (#stage4-qa).
            failed.push(file.name);
          }
        }

        setProgress("Syncing intake register…");
        const syncRes = await fetch(`/api/projects/${id}/estimate-job-sync`, { method: "POST" });
        if (!syncRes.ok) failed.push("internal document register");

        if (failed.length > 0) {
          // The project exists; surface the partial failure so the user can retry
          // those files from the project page rather than losing their submission.
          router.push(`/portal/projects/${id}?upload=partial`);
          return;
        }
      }

      setProgress("Done.");
      router.push(`/portal/projects/${id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setSubmitting(false);
      setProgress(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-navy">Submit a project</h1>
        <Link href="/portal/projects" className="text-sm font-semibold text-slate-500 hover:text-brand">
          View my projects
        </Link>
      </div>
      <p className="mt-1 text-slate-500">
        Tell us about the project and upload your plans. We&rsquo;ll confirm scope and a
        delivery date before any work begins.
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-6">
        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-base font-bold text-navy">Project details</h2>
          <div className="mt-4 space-y-5">
            <div>
              <label htmlFor="name" className={labelClass}>
                Project name <span className="text-brand">*</span>
              </label>
              <input id="name" type="text" required className={fieldClass}
                value={name} onChange={(e) => setName(e.target.value)} />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="projectType" className={labelClass}>Project type</label>
                <select id="projectType" className={fieldClass}
                  value={projectType} onChange={(e) => setProjectType(e.target.value)}>
                  <option value="">Select…</option>
                  {PROJECT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="bidDueAt" className={labelClass}>Bid due date</label>
                <input id="bidDueAt" type="date" className={fieldClass}
                  value={bidDueAt} onChange={(e) => setBidDueAt(e.target.value)} />
              </div>
            </div>

            <div>
              <label htmlFor="address" className={labelClass}>Project address</label>
              <input id="address" type="text" className={fieldClass}
                placeholder="Street, city, state" value={address}
                onChange={(e) => setAddress(e.target.value)} />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="requestedCompletionAt" className={labelClass}>Requested completion date</label>
                <input id="requestedCompletionAt" type="date" className={fieldClass}
                  value={requestedCompletionAt} onChange={(e) => setRequestedCompletionAt(e.target.value)} />
              </div>
              <div>
                <label htmlFor="estimateType" className={labelClass}>Estimate type</label>
                <select id="estimateType" className={fieldClass}
                  value={estimateType} onChange={(e) => setEstimateType(e.target.value)}>
                  <option value="">Select…</option>
                  <option value="budget">Budget estimate</option>
                  <option value="bid">Bid estimate</option>
                  <option value="change_order">Change order</option>
                  <option value="takeoff_only">Takeoff only</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>

            <div>
              <label htmlFor="trades" className={labelClass}>
                Trades / scopes to estimate <span className="font-normal text-slate-400">(comma-separated)</span>
              </label>
              <input id="trades" type="text" className={fieldClass}
                placeholder="e.g. concrete, framing, electrical" value={trades}
                onChange={(e) => setTrades(e.target.value)} />
            </div>

            <div>
              <label htmlFor="scopeNotes" className={labelClass}>Scope notes & special instructions</label>
              <textarea id="scopeNotes" rows={4} className={fieldClass}
                placeholder="Anything we should know — inclusions, exclusions, alternates, deadlines…"
                value={scopeNotes} onChange={(e) => setScopeNotes(e.target.value)} />
            </div>

            <div>
              <label htmlFor="alternatesAllowances" className={labelClass}>Base bid / alternates / allowances</label>
              <textarea id="alternatesAllowances" rows={3} className={fieldClass}
                placeholder="List alternates, allowances, unit-price requests, or base-bid instructions."
                value={alternatesAllowances} onChange={(e) => setAlternatesAllowances(e.target.value)} />
            </div>

            <div>
              <label htmlFor="exclusions" className={labelClass}>Known exclusions or limitations</label>
              <textarea id="exclusions" rows={3} className={fieldClass}
                placeholder="Anything Mobi should exclude, ignore, or treat as by others."
                value={exclusions} onChange={(e) => setExclusions(e.target.value)} />
            </div>

            <div>
              <label htmlFor="openQuestions" className={labelClass}>Open questions / assumptions</label>
              <textarea id="openQuestions" rows={3} className={fieldClass}
                placeholder="Known unclear scope, missing addenda, site constraints, or assumptions to confirm."
                value={openQuestions} onChange={(e) => setOpenQuestions(e.target.value)} />
            </div>

            <div>
              <label htmlFor="sharedDocumentLink" className={labelClass}>Shared document link</label>
              <input id="sharedDocumentLink" type="url" className={fieldClass}
                placeholder="Optional link for files too large to upload here"
                value={sharedDocumentLink} onChange={(e) => setSharedDocumentLink(e.target.value)} />
              <p className="mt-1 text-xs text-slate-400">We will not fetch links automatically; staff will verify them manually.</p>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={prevailingWage}
                  onChange={(e) => setPrevailingWage(e.target.checked)} />
                Prevailing-wage project
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={isPublicProject}
                  onChange={(e) => setIsPublicProject(e.target.checked)} />
                Public project / public bid
              </label>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-base font-bold text-navy">Plans & documents</h2>
          <p className="mt-1 text-sm text-slate-500">
            Accepted: {ACCEPT_ATTR}. Up to {formatBytes(MAX_FILE_BYTES)} per file, {MAX_FILES} files
            max. For very large plan sets, upload a .zip or add a shared link above.
          </p>

          <div className="mt-4">
            <input ref={inputRef} type="file" multiple accept={ACCEPT_ATTR}
              onChange={(e) => addFiles(e.target.files)}
              className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-full file:border-0 file:bg-brand file:px-4 file:py-2 file:font-semibold file:text-white hover:file:bg-brand-dark" />
          </div>

          {files.length > 0 && (
            <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
              {files.map((f, idx) => (
                <li key={idx} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-navy">{f.file.name}</div>
                    <div className="text-xs text-slate-400">
                      {formatBytes(f.file.size)}
                      {f.error && <span className="ml-2 font-semibold text-red-600">{f.error}</span>}
                    </div>
                  </div>
                  <select value={f.category} onChange={(e) => setCategory(idx, e.target.value)}
                    className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
                    {FILE_CATEGORIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <button type="button" onClick={() => removeFile(idx)}
                    className="text-sm font-semibold text-slate-400 hover:text-red-600">
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {error && (
          <p className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        )}

        <div className="flex items-center gap-3">
          <button type="submit" disabled={submitting}
            className="rounded-full bg-brand px-6 py-3 font-semibold text-white transition hover:bg-brand-dark disabled:opacity-60">
            {submitting ? progress || "Submitting…" : "Submit project"}
          </button>
          <Link href="/portal" className="text-sm font-semibold text-slate-500 hover:text-navy">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
