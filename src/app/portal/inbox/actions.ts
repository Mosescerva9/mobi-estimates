"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { isInboxNoticeCode } from "./notices";

function redirectWithNotice(code: string): never {
  redirect(`/portal/inbox?notice=${isInboxNoticeCode(code) ? code : "failed"}`);
}

/**
 * Dismiss a forwarded bid the contractor doesn't want estimated.
 *
 * The status transition runs in dismiss_inbound_intake (migration 0036) rather
 * than a direct update, so membership and the allowed transitions are enforced
 * in the database instead of only here.
 */
export async function dismissForwardedBid(formData: FormData): Promise<void> {
  await requireUser();

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

  revalidatePath("/portal/inbox");
  revalidatePath("/portal");
  redirectWithNotice("dismissed");
}
