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
  MAX_UNROUTED_INTAKE_MESSAGES_PER_DAY,
} from "@/lib/inbound-intake";
import {
  displayNameFromAddress,
  findIntakeRecipient,
  findIntakeSlug,
  inboundIntakeStorageFolder,
  normalizeEmailAddress,
} from "@/lib/intake-email";
import {
  downloadAttachment,
  getReceivedEmail,
  listReceivedAttachments,
  type EmailReceivedEvent,
  type ReceivedEmailAttachment,
} from "@/lib/resend-inbound";

export type CaptureOutcome =
  | {
      status: "captured";
      messageId: string;
      companyId: string;
      stored: number;
      skipped: number;
      senderVerified: boolean;
      notifyEmail: string | null;
      subject: string | null;
    }
  | { status: "unrouted"; messageId: string; reason: UnroutedReason }
  | { status: "ignored"; reason: IgnoreReason }
  | { status: "duplicate"; messageId: string };

export type IgnoreReason = "not_our_domain" | "intake_queue_full" | "unrouted_queue_full";

export type UnroutedReason =
  /** Sender isn't a member of any company, and no company tag was present. */
  | "unknown_sender"
  /** Sender belongs to more than one company — guessing could leak documents. */
  | "ambiguous_sender"
  /** A company tag was present but matches no live company (stale/rotated). */
  | "unknown_alias";

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

/** Live companies whose members include this email address. */
async function companiesForSender(
  admin: SupabaseClient,
  senderEmail: string,
): Promise<string[]> {
  if (!senderEmail) return [];

  // ilike with no wildcards is case-insensitive equality; stored profile emails
  // are not guaranteed to be lowercased.
  const { data: profiles } = await admin.from("profiles").select("id").ilike("email", senderEmail);
  const userIds = (profiles ?? [])
    .map((p) => (p as { id: string }).id)
    .filter((id): id is string => Boolean(id));
  if (userIds.length === 0) return [];

  const { data: members } = await admin
    .from("company_members")
    .select("company_id")
    .in("user_id", userIds);

  const candidateIds = [
    ...new Set(
      (members ?? [])
        .map((m) => (m as { company_id: string | null }).company_id)
        .filter((id): id is string => Boolean(id)),
    ),
  ];
  if (candidateIds.length === 0) return [];

  // Soft-deleted companies must not receive forwards.
  const { data: companies } = await admin
    .from("companies")
    .select("id")
    .in("id", candidateIds)
    .is("deleted_at", null);

  return (companies ?? []).map((c) => (c as { id: string }).id);
}

type Routing =
  | { kind: "routed"; companyId: string; routedBy: "alias" | "sender" }
  | { kind: "unrouted"; reason: UnroutedReason };

/**
 * Resolve which company a forward belongs to.
 *
 * The company tag wins over the sender because it is explicit and unguessable.
 * Sender matching is the fallback for the plain shared address, and it refuses to
 * guess when an address belongs to members of several companies — routing a plan
 * set into the wrong tenant is worse than making staff triage it.
 */
async function resolveRouting(
  admin: SupabaseClient,
  event: EmailReceivedEvent,
  senderEmail: string,
): Promise<Routing> {
  const slug = findIntakeSlug(candidateRecipients(event));
  if (slug) {
    const { data: company } = await admin
      .from("companies")
      .select("id")
      .eq("intake_slug", slug)
      .is("deleted_at", null)
      .maybeSingle();
    const companyId = (company as { id: string } | null)?.id;
    if (companyId) return { kind: "routed", companyId, routedBy: "alias" };
    return { kind: "unrouted", reason: "unknown_alias" };
  }

  const companyIds = await companiesForSender(admin, senderEmail);
  if (companyIds.length === 1) {
    return { kind: "routed", companyId: companyIds[0], routedBy: "sender" };
  }
  if (companyIds.length > 1) return { kind: "unrouted", reason: "ambiguous_sender" };
  return { kind: "unrouted", reason: "unknown_sender" };
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
  const recipients = candidateRecipients(event);
  const intakeAddress = findIntakeRecipient(recipients);
  if (!intakeAddress) {
    // Resend only delivers mail for our receiving domain, so this is defensive.
    return { status: "ignored", reason: "not_our_domain" };
  }

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

  const email = await getReceivedEmail(event.emailId);
  const fromRaw = email.headers?.from ?? event.from ?? "";
  const senderEmail = normalizeEmailAddress(event.from ?? fromRaw);
  const routing = await resolveRouting(admin, event, senderEmail);

  const baseRow = {
    provider: "resend",
    provider_email_id: event.emailId,
    intake_address: intakeAddress,
    from_email: senderEmail || "unknown",
    from_name: displayNameFromAddress(fromRaw),
    subject: email.subject ?? event.subject,
    body_preview: buildBodyPreview(email.text),
  };

  if (routing.kind === "unrouted") {
    return captureUnrouted(admin, { baseRow, reason: routing.reason, emailId: event.emailId });
  }

  const { companyId, routedBy } = routing;

  // Bound how much an unwanted sender can pile up in one company's queue before
  // the contractor notices and we rotate their tag.
  const { count: pendingCount } = await admin
    .from("inbound_intake_messages")
    .select("id", { count: "exact", head: true })
    .eq("company_id", companyId)
    .in("status", ["pending", "sender_unverified"]);
  if ((pendingCount ?? 0) >= MAX_PENDING_INTAKE_MESSAGES) {
    return { status: "ignored", reason: "intake_queue_full" };
  }

  // Sender matching already proved membership; an alias-routed forward still has
  // to be checked, because the tag travels with the email and anyone it was ever
  // forwarded to could reuse it.
  const senderVerified =
    routedBy === "sender" ||
    (Boolean(senderEmail) && (await memberEmails(admin, companyId)).has(senderEmail));

  const { data: inserted, error: insertError } = await admin
    .from("inbound_intake_messages")
    .insert({
      ...baseRow,
      company_id: companyId,
      routed_by: routedBy,
      sender_verified: senderVerified,
      status: senderVerified ? "pending" : "sender_unverified",
    })
    .select("id")
    .single();

  if (insertError || !inserted) {
    const raced = await findByProviderId(admin, event.emailId);
    if (raced) return { status: "duplicate", messageId: raced };
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
      if (attachmentSkipReason(attachment, stored) !== null || !attachment.download_url) {
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
    notifyEmail: senderVerified ? senderEmail : null,
    subject: email.subject ?? event.subject,
  };
}

async function findByProviderId(
  admin: SupabaseClient,
  emailId: string,
): Promise<string | null> {
  const { data } = await admin
    .from("inbound_intake_messages")
    .select("id")
    .eq("provider", "resend")
    .eq("provider_email_id", emailId)
    .maybeSingle();
  return (data as { id: string } | null)?.id ?? null;
}

/**
 * Record a forward we could not place, for staff triage.
 *
 * Attachments are counted but NOT stored. The shared intake address is on a
 * public domain and anyone can write to it, so storing files from senders we
 * can't identify would make it a free file host. Counting them still lets staff
 * tell a contractor exactly how many documents didn't make it through.
 */
async function captureUnrouted(
  admin: SupabaseClient,
  input: {
    baseRow: Record<string, unknown>;
    reason: UnroutedReason;
    emailId: string;
  },
): Promise<CaptureOutcome> {
  const since = new Date(Date.now() - 86_400_000).toISOString();
  const { count: recentUnrouted } = await admin
    .from("inbound_intake_messages")
    .select("id", { count: "exact", head: true })
    .eq("status", "unrouted")
    .gte("received_at", since);
  if ((recentUnrouted ?? 0) >= MAX_UNROUTED_INTAKE_MESSAGES_PER_DAY) {
    return { status: "ignored", reason: "unrouted_queue_full" };
  }

  let attachmentCount = 0;
  try {
    const attachments: ReceivedEmailAttachment[] = await listReceivedAttachments(input.emailId);
    attachmentCount = attachments.filter(
      (a) => !a.content_id && a.content_disposition !== "inline",
    ).length;
  } catch {
    // Counting is a nicety for triage; never fail the capture over it.
  }

  const { data: inserted, error } = await admin
    .from("inbound_intake_messages")
    .insert({
      ...input.baseRow,
      company_id: null,
      status: "unrouted",
      unrouted_reason: input.reason,
      attachment_count: 0,
      skipped_attachment_count: attachmentCount,
    })
    .select("id")
    .single();

  if (error || !inserted) {
    const raced = await findByProviderId(admin, input.emailId);
    if (raced) return { status: "duplicate", messageId: raced };
    throw new Error(error?.message ?? "Could not record the unrouted forward.");
  }

  return {
    status: "unrouted",
    messageId: (inserted as { id: string }).id,
    reason: input.reason,
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
