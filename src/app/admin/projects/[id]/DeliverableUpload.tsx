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

export function DeliverableUpload({
  projectId,
  companyId,
  deliveryUnlocked,
  statusLabel,
  gateMessage,
}: {
  projectId: string;
  companyId: string;
  deliveryUnlocked: boolean;
  statusLabel: string | null;
  gateMessage: string;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [category, setCategory] = useState<string>(DEFAULT_DELIVERABLE_CATEGORY);
  const [ownerApprovalConfirmed, setOwnerApprovalConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onUpload() {
    if (!deliveryUnlocked) {
      setError("Locked: this job is not yet ready for owner approval. Uploads are disabled.");
      return;
    }
    if (!ownerApprovalConfirmed) {
      setError("Check the confirmation box to acknowledge internal owner approval before uploading.");
      return;
    }
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
    setOwnerApprovalConfirmed(false);
    if (failed.length > 0) {
      setError(`Failed to upload: ${failed.join(", ")}`);
    }
    router.refresh();
  }

  if (!deliveryUnlocked) {
    return (
      <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
        <p className="text-sm font-semibold text-amber-800">Deliverable upload locked</p>
        <p className="text-sm text-amber-700">{gateMessage}</p>
        <div className="flex flex-wrap items-center gap-2 opacity-60">
          <select disabled className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
            {DELIVERABLE_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <input disabled type="file" multiple className="block text-sm text-slate-400" />
          <button type="button" disabled
            className="rounded-full bg-brand px-4 py-1.5 text-sm font-semibold text-white opacity-60">
            Upload deliverable
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-500">{gateMessage}</p>
      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={ownerApprovalConfirmed}
          onChange={(e) => setOwnerApprovalConfirmed(e.target.checked)}
          className="mt-0.5"
        />
        <span>
          I confirm Moses/internal owner approval has been obtained and this upload may be visible to the customer
          portal{statusLabel ? ` (status: ${statusLabel})` : ""}.
        </span>
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <select value={category} onChange={(e) => setCategory(e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
          {DELIVERABLE_CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input ref={inputRef} type="file" multiple
          className="block text-sm text-slate-600 file:mr-3 file:rounded-full file:border-0 file:bg-slate-200 file:px-3 file:py-1.5 file:font-semibold file:text-navy hover:file:bg-slate-300" />
        <button type="button" onClick={onUpload} disabled={busy || !ownerApprovalConfirmed}
          className="rounded-full bg-brand px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60">
          {busy ? msg || "Uploading…" : "Upload deliverable"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
