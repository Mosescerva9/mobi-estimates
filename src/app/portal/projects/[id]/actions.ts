"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { engineConfigured, engineGetJson, enginePostJson } from "@/lib/engine";
import {
  normalizeCustomerRevisionHistory,
  type EngineRevisionHistoryItem,
} from "./revisionHistory";

export type {
  CustomerRevisionHistoryItem,
  CustomerRevisionHistoryResult,
} from "./revisionHistory";
import type { CustomerRevisionHistoryResult } from "./revisionHistory";

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
    .select("id, engine_project_id, company_id")
    .eq("id", projectId)
    .is("deleted_at", null)
    .maybeSingle();

  if (!project?.engine_project_id) return { available: false, reason: "project_unlinked", items: [] };

  try {
    const companyId = typeof project.company_id === "string" ? project.company_id : "";
    const history = await engineGetJson<{ items?: EngineRevisionHistoryItem[] }>(
      `/api/v1/projects/${project.engine_project_id}/customer-revisions/customer-history`,
      { tenantId: companyId, companyId },
    );
    return { available: true, items: normalizeCustomerRevisionHistory(history.items) };
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
    .select("id, engine_project_id, company_id")
    .eq("id", projectId)
    .is("deleted_at", null)
    .maybeSingle();

  if (!project) return;
  if (!project.engine_project_id) redirectWithRevisionNotice(projectId, "project_unlinked");

  try {
    const companyId = typeof project.company_id === "string" ? project.company_id : "";
    await enginePostJson(
      `/api/v1/projects/${project.engine_project_id}/customer-revisions/customer-submit`,
      { text },
      { tenantId: companyId, companyId },
    );
  } catch {
    redirectWithRevisionNotice(projectId, "failed");
  }

  revalidatePath(`/portal/projects/${projectId}`);
  redirectWithRevisionNotice(projectId, "recorded");
}
