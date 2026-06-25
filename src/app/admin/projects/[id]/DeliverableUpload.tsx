"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import {
  DEFAULT_DELIVERABLE_CATEGORY,
  DELIVERABLE_CATEGORIES,
  DELIVERABLES_BUCKET,
  buildStoragePath,
} from "@/lib/projects";

export function DeliverableUpload({ projectId, companyId }: { projectId: string; companyId: string }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [category, setCategory] = useState<string>(DEFAULT_DELIVERABLE_CATEGORY);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onUpload() {
    const list = inputRef.current?.files;
    if (!list || list.length === 0) {
      setError("Choose at least one file to upload.");
      return;
    }
    setError(null);
    setBusy(true);
    const supabase = createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    const failed: string[] = [];
    let done = 0;
    for (const file of Array.from(list)) {
      setMsg(`Uploading… (${done + 1}/${list.length})`);
      const path = buildStoragePath(companyId, projectId, file.name);
      const { error: upErr } = await supabase.storage
        .from(DELIVERABLES_BUCKET)
        .upload(path, file, { contentType: file.type || undefined, upsert: false });
      if (upErr) {
        failed.push(file.name);
        continue;
      }
      const { error: metaErr } = await supabase.from("deliverables").insert({
        project_id: projectId,
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
    }

    setBusy(false);
    setMsg(null);
    if (inputRef.current) inputRef.current.value = "";
    if (failed.length > 0) {
      setError(`Failed to upload: ${failed.join(", ")}`);
    }
    router.refresh();
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select value={category} onChange={(e) => setCategory(e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
          {DELIVERABLE_CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input ref={inputRef} type="file" multiple
          className="block text-sm text-slate-600 file:mr-3 file:rounded-full file:border-0 file:bg-slate-200 file:px-3 file:py-1.5 file:font-semibold file:text-navy hover:file:bg-slate-300" />
        <button type="button" onClick={onUpload} disabled={busy}
          className="rounded-full bg-brand px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60">
          {busy ? msg || "Uploading…" : "Upload deliverable"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
