"use server";

import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

/**
 * Customer marks a deliverable as reviewed or approved. RLS
 * (deliverables_update_client) restricts the update to deliverables belonging
 * to a company the user is a member of, so a forged id simply matches no rows.
 */
async function setDeliverableFlag(formData: FormData, field: "reviewed" | "approved") {
  await requireUser();
  const deliverableId = String(formData.get("deliverableId") || "");
  if (!deliverableId) return;

  const supabase = await createClient();
  const now = new Date().toISOString();
  const patch =
    field === "approved"
      ? { client_approved_at: now, client_reviewed_at: now }
      : { client_reviewed_at: now };

  await supabase.from("deliverables").update(patch).eq("id", deliverableId);

  revalidatePath("/portal/estimates");
  const projectId = String(formData.get("projectId") || "");
  if (projectId) revalidatePath(`/portal/projects/${projectId}`);
}

export async function markReviewed(formData: FormData) {
  await setDeliverableFlag(formData, "reviewed");
}

export async function approveDeliverable(formData: FormData) {
  await setDeliverableFlag(formData, "approved");
}
