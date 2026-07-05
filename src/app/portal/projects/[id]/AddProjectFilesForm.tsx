"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { fieldClass } from "@/components/AuthShell";
import {
  ACCEPT_ATTR,
  DEFAULT_FILE_CATEGORY,
  FILE_CATEGORIES,
  MAX_FILES,
  MAX_FILE_BYTES,
  PROJECT_FILES_BUCKET,
  buildStoragePath,
  formatBytes,
  isAllowedExtension,
} from "@/lib/projects";

interface PickedFile {
  file: File;
  category: string;
  error?: string;
}

export function AddProjectFilesForm({
  projectId,
  companyId,
  defaultOpen,
  partialUpload,
}: {
  projectId: string;
  companyId: string;
  defaultOpen: boolean;
  partialUpload: boolean;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [open, setOpen] = useState(defaultOpen);
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);

  function addFiles(list: FileList | null) {
    if (!list) return;
    setError(null);
    setSuccess(null);
    setSyncError(null);
    const next: PickedFile[] = [];
    for (const file of Array.from(list)) {
      let err: string | undefined;
      if (!isAllowedExtension(file.name)) err = "Unsupported file type";
      else if (file.size > MAX_FILE_BYTES) err = `Too large (max ${formatBytes(MAX_FILE_BYTES)})`;
      next.push({ file, category: DEFAULT_FILE_CATEGORY, error: err });
    }
    setFiles((prev) => {
      const combined = [...prev, ...next];
      return combined.slice(0, MAX_FILES);
    });
    if (inputRef.current) inputRef.current.value = "";
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  function setCategory(idx: number, category: string) {
    setFiles((prev) => prev.map((f, i) => (i === idx ? { ...f, category } : f)));
  }

  async function syncIntakeRegister(): Promise<boolean> {
    setSyncing(true);
    setSyncError(null);
    try {
      const syncRes = await fetch(`/api/projects/${projectId}/estimate-job-sync`, { method: "POST" });
      if (!syncRes.ok) {
        let message = "The files uploaded, but the internal document register did not sync. Please retry the register sync.";
        try {
          const body = await syncRes.json();
          if (body?.error) message = `The files uploaded, but the internal document register did not sync: ${body.error}`;
        } catch {
          // Keep the generic message when the response body is not JSON.
        }
        setSyncError(message);
        return false;
      }
      setSyncError(null);
      return true;
    } catch {
      setSyncError("The files uploaded, but the internal document register did not sync. Please retry the register sync.");
      return false;
    } finally {
      setSyncing(false);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSyncError(null);

    if (files.length === 0) {
      setError("Please choose at least one file.");
      return;
    }
    if (files.some((f) => f.error)) {
      setError("Please remove the files flagged below before uploading.");
      return;
    }

    setSubmitting(true);
    try {
      const supabase = createClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();

      const failedNames: string[] = [];
      const succeededIdx = new Set<number>();
      for (let i = 0; i < files.length; i++) {
        const { file, category } = files[i];
        setProgress(`Uploading files… (${i + 1}/${files.length})`);
        try {
          const path = buildStoragePath(companyId, projectId, file.name);
          const { error: upErr } = await supabase.storage
            .from(PROJECT_FILES_BUCKET)
            .upload(path, file, { contentType: file.type || undefined, upsert: false });
          if (upErr) {
            failedNames.push(file.name);
            continue;
          }
          const { error: metaErr } = await supabase.from("project_files").insert({
            project_id: projectId,
            company_id: companyId,
            category,
            storage_path: path,
            file_name: file.name,
            mime_type: file.type || null,
            size_bytes: file.size,
            uploaded_by: user?.id ?? null,
          });
          if (metaErr) failedNames.push(file.name);
          else succeededIdx.add(i);
        } catch {
          // A dropped connection to Storage must not escape the loop and skip
          // the partial-failure summary below.
          failedNames.push(file.name);
        }
      }

      let synced = true;
      if (succeededIdx.size > 0) {
        setProgress("Syncing intake register…");
        synced = await syncIntakeRegister();
      }

      setFiles((prev) => prev.filter((_, i) => !succeededIdx.has(i)));

      if (failedNames.length > 0) {
        setError(
          `${succeededIdx.size > 0 ? `${succeededIdx.size} file(s) uploaded. ` : ""}` +
            `The following failed and are still listed below: ${failedNames.join(", ")}. Please try again.`,
        );
      } else if (synced) {
        setSuccess(`${succeededIdx.size} file(s) uploaded.`);
        setOpen(false);
      } else {
        setSuccess(`${succeededIdx.size} file(s) uploaded.`);
      }

      if (succeededIdx.size > 0) router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
      setProgress(null);
    }
  }

  if (!open) {
    return (
      <div className="mt-4">
        {success && (
          <p className="mb-3 rounded-lg border border-green-300 bg-green-50 px-4 py-3 text-sm text-green-700">
            {success}
          </p>
        )}
        {syncError && (
          <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <p>{syncError}</p>
            <button
              type="button"
              onClick={async () => {
                if (await syncIntakeRegister()) {
                  setSuccess("Internal document register synced.");
                  router.refresh();
                }
              }}
              disabled={syncing}
              className="mt-2 rounded-full bg-amber-700 px-3 py-1 text-xs font-semibold text-white disabled:opacity-60"
            >
              {syncing ? "Syncing…" : "Retry register sync"}
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand"
        >
          {partialUpload ? "Retry / add documents" : "Add documents"}
        </button>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm text-slate-500">
        Accepted: {ACCEPT_ATTR}. Up to {formatBytes(MAX_FILE_BYTES)} per file, {MAX_FILES} files max.
      </p>

      <div className="mt-3">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTR}
          onChange={(e) => addFiles(e.target.files)}
          className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-full file:border-0 file:bg-brand file:px-4 file:py-2 file:font-semibold file:text-white hover:file:bg-brand-dark"
        />
      </div>

      {files.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {files.map((f, idx) => (
            <li key={idx} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-navy">{f.file.name}</div>
                <div className="text-xs text-slate-400">
                  {formatBytes(f.file.size)}
                  {f.error && <span className="ml-2 font-semibold text-red-600">{f.error}</span>}
                </div>
              </div>
              <select
                value={f.category}
                onChange={(e) => setCategory(idx, e.target.value)}
                className={`${fieldClass} w-auto py-1.5`}
              >
                {FILE_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => removeFile(idx)}
                className="text-sm font-semibold text-slate-400 hover:text-red-600"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p className="mt-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {syncError && (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <p>{syncError}</p>
          <button
            type="button"
            onClick={async () => {
              if (await syncIntakeRegister()) {
                setSuccess("Internal document register synced.");
                setOpen(false);
                router.refresh();
              }
            }}
            disabled={syncing}
            className="mt-2 rounded-full bg-amber-700 px-3 py-1 text-xs font-semibold text-white disabled:opacity-60"
          >
            {syncing ? "Syncing…" : "Retry register sync"}
          </button>
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={onSubmit}
          disabled={submitting || files.length === 0}
          className="rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-60"
        >
          {submitting ? progress || "Uploading…" : "Upload files"}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setFiles([]);
            setError(null);
          }}
          disabled={submitting}
          className="text-sm font-semibold text-slate-500 hover:text-navy"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
