/**
 * Server-side capture of a forwarded bid invitation.
 *
 * SERVER-ONLY — runs with the service-role client, since an inbound email has no
 * authenticated session to attach RLS to.
 *
 * The capture is intentionally inert: it stores documents and creates a review
 * item, and does NOT create a project or touch any entitlement. Project creation
 * stays behind create_free_offer_project / create_entitled_project (migration
 * 0034), so an email — which anyone who learns the address can send — can never
 * consume a company's one free estimate. See supabase/migrations/0036.
 */

import type { SupabaseClient } from "@supabase/supabase-js";
import { PROJECT_FILES_BUCKET, sanitizeFilename } from "@/lib/projects";
import {
  attachmentSkipReason,
  buildBodyPreview,
  MAX_PENDING_INTAKE_MESSAGES,
} from "@/lib/inbound-intake";
import {
  displayNameFromAddress,
  findIntakeSlug,
  inboundIntakeStorageFolder,
  normalizeEmailAddress,
} from "@/lib/intake-email";
import {
  downloadAttachment,
  getReceivedEmail,
  listReceivedAttachments,
  type EmailReceivedEvent,
} from "@/lib/resend-inbound";

export type CaptureOutcome =
  | { status: "captured"; messageId: string; companyId: string; stored: number; skipped: number; senderVerified: boolean; notifyEmail: string | null; subject: string | null }
  | { status: "ignored"; reason: IgnoreReason }
  | { status: "duplicate"; messageId: string };

export type IgnoreReason =
  | "no_intake_alias"
  | "unknown_company"
  | "intake_queue_full";

/** Short random suffix for storage-key uniqueness (mirrors lib/projects). */
function randomSuffix(): string {
  const bytes = new Uint8Array(4);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Every address the message was addressed to. A contractor forwarding an ITB
 * usually cc's their own team, and some mail systems only record our address in
 * the `Received: ... for <addr>` clause, so all three sources are considered.
 */
function candidateRecipients(event: EmailReceivedEvent): string[] {
  return [...event.receivedFor, ...event.to, ...event.cc];
}

/** Profile emails of every member of the company, normalized for comparison. */
async function memberEmails(
  admin: SupabaseClient,
  companyId: string,
): Promise<Set<string>> {
  const { data: members } = await admin
    .from("company_members")
    .select("user_id")
    .eq("company_id", companyId);

  const userIds = (members ?? [])
    .map((m) => (m as { user_id: string | null }).user_id)
    .filter((id): id is string => Boolean(id));
  if (userIds.length === 0) return new Set();

  const { data: profiles } = await admin.from("profiles").select("email").in("id", userIds);
  return new Set(
    (profiles ?? [])
      .map((p) => normalizeEmailAddress((p as { email: string | null }).email))
      .filter(Boolean),
  );
}

/**
 * Capture a received email as a reviewable intake item.
 *
 * Throws on infrastructure failure AFTER cleaning up whatever it created, so the
 * caller can return a non-2xx and let the provider redeliver — a redelivery then
 * re-runs cleanly instead of hitting the idempotency guard on a half-written row.
 */
export async function captureForwardedBid(
  admin: SupabaseClient,
  event: EmailReceivedEvent,
): Promise<CaptureOutcome> {
  const slug = findIntakeSlug(candidateRecipients(event));
  if (!slug) return { status: "ignored", reason: "no_intake_alias" };

  const { data: company } = await admin
    .from("companies")
    .select("id")
    .eq("intake_slug", slug)
    .is("deleted_at", null)
    .maybeSingle();
  const companyId = (company as { id: string } | null)?.id;
  if (!companyId) return { status: "ignored", reason: "unknown_company" };

  // Idempotency: a redelivered email.received event must not duplicate the
  // documents. Checked here and enforced by the unique index below.
  const { data: existing } = await admin
    .from("inbound_intake_messages")
    .select("id")
    .eq("provider", "resend")
    .eq("provider_email_id", event.emailId)
    .maybeSingle();
  if (existing) {
    return { status: "duplicate", messageId: (existing as { id: string }).id };
  }

  // Bound how much an unwanted sender can pile up before the contractor notices.
  const { count: pendingCount } = await admin
    .from("inbound_intake_messages")
    .select("id", { count: "exact", head: true })
    .eq("company_id", companyId)
    .in("status", ["pending", "sender_unverified"]);
  if ((pendingCount ?? 0) >= MAX_PENDING_INTAKE_MESSAGES) {
    return { status: "ignored", reason: "intake_queue_full" };
  }

  const email = await getReceivedEmail(event.emailId);
  const fromRaw = email.headers?.from ?? event.from ?? "";
  const fromEmail = normalizeEmailAddress(event.from ?? fromRaw);
  const senderVerified =
    Boolean(fromEmail) && (await memberEmails(admin, companyId)).has(fromEmail);

  const intakeAddress =
    candidateRecipients(event).find((r) => normalizeEmailAddress(r).startsWith(`${slug}@`)) ??
    `${slug}@`;

  const { data: inserted, error: insertError } = await admin
    .from("inbound_intake_messages")
    .insert({
      company_id: companyId,
      provider: "resend",
      provider_email_id: event.emailId,
      intake_address: normalizeEmailAddress(intakeAddress),
      from_email: fromEmail || "unknown",
      from_name: displayNameFromAddress(fromRaw),
      subject: email.subject ?? event.subject,
      body_preview: buildBodyPreview(email.text),
      sender_verified: senderVerified,
      status: senderVerified ? "pending" : "sender_unverified",
    })
    .select("id")
    .single();

  if (insertError || !inserted) {
    // A concurrent delivery of the same event won the unique index.
    const { data: raced } = await admin
      .from("inbound_intake_messages")
      .select("id")
      .eq("provider", "resend")
      .eq("provider_email_id", event.emailId)
      .maybeSingle();
    if (raced) return { status: "duplicate", messageId: (raced as { id: string }).id };
    throw new Error(insertError?.message ?? "Could not record the forwarded bid.");
  }

  const messageId = (inserted as { id: string }).id;
  const folder = inboundIntakeStorageFolder(companyId, messageId);
  const uploadedPaths: string[] = [];
  let stored = 0;
  let skipped = 0;

  try {
    const attachments = await listReceivedAttachments(event.emailId);

    for (const attachment of attachments) {
      if (attachmentSkipReason(attachment, stored) !== null) {
        skipped += 1;
        continue;
      }
      if (!attachment.download_url) {
        skipped += 1;
        continue;
      }

      const bytes = await downloadAttachment(attachment.download_url);
      const fileName = sanitizeFilename(attachment.filename ?? "document");
      const path = `${folder}/${Date.now()}-${randomSuffix()}-${fileName}`;

      const { error: uploadError } = await admin.storage
        .from(PROJECT_FILES_BUCKET)
        .upload(path, new Blob([bytes as BlobPart], { type: attachment.content_type ?? undefined }), {
          contentType: attachment.content_type ?? undefined,
          upsert: false,
        });
      if (uploadError) throw new Error(`Storage upload failed: ${uploadError.message}`);
      uploadedPaths.push(path);

      const { error: attachmentError } = await admin
        .from("inbound_intake_attachments")
        .insert({
          message_id: messageId,
          company_id: companyId,
          file_name: fileName,
          content_type: attachment.content_type,
          size_bytes: attachment.size ?? bytes.byteLength,
          storage_path: path,
        });
      if (attachmentError) throw new Error(attachmentError.message);

      stored += 1;
    }

    const { error: updateError } = await admin
      .from("inbound_intake_messages")
      .update({ attachment_count: stored, skipped_attachment_count: skipped })
      .eq("id", messageId);
    if (updateError) throw new Error(updateError.message);
  } catch (err) {
    // Leave nothing half-captured: a partially-stored forward would show the
    // contractor an incomplete plan set that looks complete.
    if (uploadedPaths.length > 0) {
      await admin.storage.from(PROJECT_FILES_BUCKET).remove(uploadedPaths);
    }
    await admin.from("inbound_intake_messages").delete().eq("id", messageId);
    throw err;
  }

  return {
    status: "captured",
    messageId,
    companyId,
    stored,
    skipped,
    senderVerified,
    // Only a sender we could match to a member is emailed back.
    notifyEmail: senderVerified ? fromEmail : null,
    subject: email.subject ?? event.subject,
  };
}

/**
 * In-app notification for every member of the company. Best-effort: a
 * notification failure must not fail the capture, because the forward and its
 * documents are already safely stored and visible in the portal.
 */
export async function notifyCompanyOfForwardedBid(
  admin: SupabaseClient,
  input: { companyId: string; messageId: string; subject: string | null; storedCount: number },
): Promise<void> {
  const { data: members } = await admin
    .from("company_members")
    .select("user_id")
    .eq("company_id", input.companyId);

  const userIds = (members ?? [])
    .map((m) => (m as { user_id: string | null }).user_id)
    .filter((id): id is string => Boolean(id));
  if (userIds.length === 0) return;

  const documents = input.storedCount === 1 ? "1 document" : `${input.storedCount} documents`;
  await admin.from("notifications").insert(
    userIds.map((userId) => ({
      user_id: userId,
      company_id: input.companyId,
      type: "inbound_intake",
      title: "Forwarded bid received",
      body: input.subject
        ? `${input.subject} — ${documents} saved. Review and confirm the scope to submit it.`
        : `${documents} saved. Review and confirm the scope to submit it.`,
      link: "/portal/inbox",
    })),
  );
}
