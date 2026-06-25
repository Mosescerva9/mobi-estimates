"use server";

import { revalidatePath } from "next/cache";
import { requireStaff } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { ALL_STATUSES } from "@/lib/projects";

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
