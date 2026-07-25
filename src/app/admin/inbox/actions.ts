"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireStaff } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { isAdminInboxNoticeCode } from "./notices";

function redirectWithNotice(code: string): never {
  redirect(`/admin/inbox?notice=${isAdminInboxNoticeCode(code) ? code : "failed"}`);
}

/**
 * Staff dismissal of a forwarded bid — used mainly to clear spam and misdirected
 * mail out of the unrouted triage queue.
 *
 * Goes through dismiss_inbound_intake (migration 0036) rather than a direct
 * update so the allowed transitions stay enforced in the database. The RPC
 * accepts staff for any tenant, and for an unrouted forward (company_id is null)
 * staff are the only callers it can accept.
 */
export async function dismissIntakeAsStaff(formData: FormData): Promise<void> {
  await requireStaff();

  const messageId = String(formData.get("messageId") ?? "").trim();
  if (!messageId) redirectWithNotice("failed");

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("dismiss_inbound_intake", {
    p_message: messageId,
  });
  const result = data as { ok?: boolean; reason?: string } | null;

  if (error || !result?.ok) {
    redirectWithNotice(result?.reason === "already_converted" ? "already_submitted" : "failed");
  }

  revalidatePath("/admin/inbox");
  redirectWithNotice("dismissed");
}
