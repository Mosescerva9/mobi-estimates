"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { engineConfigured, enginePostJson } from "@/lib/engine";

const REVISION_NOTICE_CODES = new Set([
  "recorded",
  "missing_text",
  "engine_unavailable",
  "project_unlinked",
  "failed",
]);

function redirectWithRevisionNotice(projectId: string, code: string): never {
  const safeCode = REVISION_NOTICE_CODES.has(code) ? code : "failed";
  redirect(`/portal/projects/${projectId}?revision=${safeCode}`);
}

/**
 * Customer-facing revision submission.
 *
 * This records customer text in the estimating engine through the dedicated
 * customer-safe endpoint. It does not decide, rescope, price, approve, send,
 * bill, or deliver an estimate. The response body is intentionally discarded;
 * the project page revalidates and shows fixed local notice copy only.
 */
export async function submitCustomerRevision(formData: FormData) {
  await requireUser();
  const projectId = String(formData.get("projectId") || "");
  const text = String(formData.get("revisionText") || "").trim();

  if (!projectId) return;
  if (!text) redirectWithRevisionNotice(projectId, "missing_text");
  if (!engineConfigured()) redirectWithRevisionNotice(projectId, "engine_unavailable");

  const supabase = await createClient();
  const { data: project } = await supabase
    .from("projects")
    .select("id, engine_project_id")
    .eq("id", projectId)
    .is("deleted_at", null)
    .maybeSingle();

  if (!project) return;
  if (!project.engine_project_id) redirectWithRevisionNotice(projectId, "project_unlinked");

  try {
    await enginePostJson(
      `/api/v1/projects/${project.engine_project_id}/customer-revisions/customer-submit`,
      { text },
    );
  } catch {
    redirectWithRevisionNotice(projectId, "failed");
  }

  revalidatePath(`/portal/projects/${projectId}`);
  redirectWithRevisionNotice(projectId, "recorded");
}
