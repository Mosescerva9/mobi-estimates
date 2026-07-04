"use server";

import { revalidatePath } from "next/cache";
import { requireStaff } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { ALL_STATUSES, PROJECT_FILES_BUCKET } from "@/lib/projects";
import { engineConfigured, engineUploadPlan } from "@/lib/engine";

/** Change a project's status and append a timeline entry (staff only). */
export async function changeStatus(formData: FormData) {
  const staff = await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const toStatus = String(formData.get("status") || "");
  const clientNote = String(formData.get("client_note") || "").trim() || null;
  const internalNote = String(formData.get("internal_note") || "").trim() || null;

  if (!projectId || !(ALL_STATUSES as readonly string[]).includes(toStatus)) {
    return; // invalid input — ignore (the UI only ever submits valid values)
  }

  const supabase = await createClient();

  const { data: current } = await supabase
    .from("projects")
    .select("status")
    .eq("id", projectId)
    .maybeSingle();

  // Update the project status (RLS: staff allowed).
  await supabase.from("projects").update({ status: toStatus }).eq("id", projectId);

  // Append a timeline entry (RLS: status_history insert is staff-only).
  await supabase.from("project_status_history").insert({
    project_id: projectId,
    from_status: current?.status ?? null,
    to_status: toStatus,
    changed_by: staff.id,
    client_note: clientNote,
    internal_note: internalNote,
  });

  revalidatePath(`/admin/projects/${projectId}`);
  revalidatePath("/admin");
}

export interface EngineActionResult {
  ok: boolean;
  message: string;
}

/**
 * Push a project's uploaded PDF plan set into the estimating engine (staff only),
 * creating an engine-side project record and storing its id/status on the row.
 *
 * This is the plumbing between the portal and the engine. The engine currently
 * only ingests the PDF (no automated takeoff/pricing until a cost book is
 * seeded and extraction is enabled), so this does not yet produce a priced
 * estimate — it establishes the linked engine project the pipeline builds on.
 */
export async function sendToEngine(projectId: string): Promise<EngineActionResult> {
  await requireStaff();
  if (!projectId) return { ok: false, message: "Missing project id." };
  if (!engineConfigured()) {
    return { ok: false, message: "The estimating engine is not configured on this deployment." };
  }

  // Service role: read the project + its files and write engine sync fields
  // without depending on the caller's RLS scope.
  const admin = createAdminClient();

  const { data: project, error: projErr } = await admin
    .from("projects")
    .select("id, name, companies(legal_name)")
    .eq("id", projectId)
    .maybeSingle();
  if (projErr || !project) {
    return { ok: false, message: "Project not found." };
  }

  const { data: files } = await admin
    .from("project_files")
    .select("file_name, storage_path, created_at")
    .eq("project_id", projectId)
    .is("deleted_at", null)
    .order("created_at");

  const pdf = (files ?? []).find((f) => f.file_name?.toLowerCase().endsWith(".pdf"));
  if (!pdf) {
    return { ok: false, message: "No PDF plan file found on this project. The engine ingests PDF plan sets." };
  }

  const { data: blob, error: dlErr } = await admin.storage
    .from(PROJECT_FILES_BUCKET)
    .download(pdf.storage_path);
  if (dlErr || !blob) {
    return { ok: false, message: `Could not read the plan file from storage: ${dlErr?.message ?? "unknown error"}.` };
  }

  const company = project.companies as unknown as { legal_name: string | null } | null;

  let result;
  try {
    result = await engineUploadPlan({
      projectName: project.name,
      contractorName: company?.legal_name ?? null,
      file: blob,
      fileName: pdf.file_name,
    });
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Engine upload failed." };
  }

  const { error: updErr } = await admin
    .from("projects")
    .update({
      engine_project_id: result.project_id,
      engine_status: result.status,
      engine_page_count: result.page_count,
      engine_synced_at: new Date().toISOString(),
    })
    .eq("id", projectId);
  if (updErr) {
    return {
      ok: false,
      message: `Uploaded to the engine (${result.project_id}) but could not save the link: ${updErr.message}.`,
    };
  }

  revalidatePath(`/admin/projects/${projectId}`);
  return {
    ok: true,
    message: `Sent to the engine — ${result.page_count} page(s), status "${result.status}".`,
  };
}

/** Assign / reassign estimator and reviewer (staff only). */
export async function assignStaff(formData: FormData) {
  await requireStaff();
  const projectId = String(formData.get("projectId") || "");
  const estimatorId = String(formData.get("estimator_id") || "") || null;
  const reviewerId = String(formData.get("reviewer_id") || "") || null;
  if (!projectId) return;

  const supabase = await createClient();
  await supabase
    .from("project_assignments")
    .upsert(
      { project_id: projectId, estimator_id: estimatorId, reviewer_id: reviewerId },
      { onConflict: "project_id" },
    );

  revalidatePath(`/admin/projects/${projectId}`);
}
