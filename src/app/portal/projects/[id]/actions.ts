"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { engineConfigured, engineGetJson, enginePostJson } from "@/lib/engine";

export type CustomerRevisionHistoryItem = {
  id: string;
  status_label: string;
  requested_action_label: string;
  trade_label?: string | null;
  sheet_ref?: string | null;
  summary: string;
  follow_up_label?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  version_count?: number;
  latest_version_created_at?: string | null;
};

export type CustomerRevisionHistoryResult = {
  available: boolean;
  reason?: "engine_unavailable" | "project_unlinked" | "failed";
  items: CustomerRevisionHistoryItem[];
};

const REVISION_NOTICE_CODES = new Set([
  "recorded",
  "missing_text",
  "too_long",
  "engine_unavailable",
  "project_unlinked",
  "failed",
]);

const MAX_CUSTOMER_REVISION_TEXT_LENGTH = 5000;

function redirectWithRevisionNotice(projectId: string, code: string): never {
  const safeCode = REVISION_NOTICE_CODES.has(code) ? code : "failed";
  redirect(`/portal/projects/${projectId}?revision=${safeCode}`);
}

export async function getCustomerRevisionHistory(projectId: string): Promise<CustomerRevisionHistoryResult> {
  await requireUser();
  if (!engineConfigured()) return { available: false, reason: "engine_unavailable", items: [] };

  const supabase = await createClient();
  const { data: project } = await supabase
    .from("projects")
    .select("id, engine_project_id")
    .eq("id", projectId)
    .is("deleted_at", null)
    .maybeSingle();

  if (!project?.engine_project_id) return { available: false, reason: "project_unlinked", items: [] };

  try {
    const history = await engineGetJson<{ items?: CustomerRevisionHistoryItem[] }>(
      `/api/v1/projects/${project.engine_project_id}/customer-revisions/customer-history`,
    );
    return { available: true, items: history.items ?? [] };
  } catch {
    return { available: false, reason: "failed", items: [] };
  }
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
  if (text.length > MAX_CUSTOMER_REVISION_TEXT_LENGTH) redirectWithRevisionNotice(projectId, "too_long");
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
