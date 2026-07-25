import type { Metadata } from "next";
import { getIntakeAddressForCompany, getPrimaryCompanyId } from "@/lib/company";
import { createClient } from "@/lib/supabase/server";
import {
  bidDueDateFromText,
  isConvertibleIntakeStatus,
  projectNameFromSubject,
  scopeNotesPrefill,
} from "@/lib/inbound-intake";
import { sharedIntakeAddress } from "@/lib/intake-email";
import { NewProjectForm, type InboundPrefill } from "./NewProjectForm";

export const metadata: Metadata = {
  title: "Submit a project — Mobi Estimates",
  robots: { index: false },
};

interface IntakeMessageRow {
  id: string;
  subject: string | null;
  from_email: string;
  body_preview: string | null;
  status: string;
  sender_verified: boolean;
  received_at: string;
}

/**
 * Build the prefill for a project started from a forwarded bid.
 *
 * Everything derived from the email is a SUGGESTION the contractor edits before
 * submitting — the subject line and deadline come from a third party's
 * unstructured text, so nothing here is treated as confirmed scope.
 */
async function loadInboundPrefill(messageId: string): Promise<InboundPrefill | null> {
  const supabase = await createClient();

  // RLS scopes this to the caller's company.
  const { data } = await supabase
    .from("inbound_intake_messages")
    .select("id, subject, from_email, body_preview, status, sender_verified, received_at")
    .eq("id", messageId)
    .maybeSingle();

  const message = data as IntakeMessageRow | null;
  if (!message || !isConvertibleIntakeStatus(message.status)) return null;

  const { data: attachmentRows } = await supabase
    .from("inbound_intake_attachments")
    .select("id, file_name, size_bytes")
    .eq("message_id", message.id)
    .order("created_at");

  return {
    messageId: message.id,
    subject: message.subject,
    fromEmail: message.from_email,
    senderVerified: message.sender_verified,
    name: projectNameFromSubject(message.subject),
    bidDueAt: bidDueDateFromText(message.body_preview),
    scopeNotes: scopeNotesPrefill({
      fromEmail: message.from_email,
      subject: message.subject,
      receivedAt: message.received_at,
    }),
    attachments: ((attachmentRows ?? []) as { id: string; file_name: string; size_bytes: number | null }[]).map(
      (a) => ({ id: a.id, fileName: a.file_name, sizeBytes: a.size_bytes }),
    ),
  };
}

// Auth, company, and subscription gating are handled by the portal layout
// (requireUser + onboarding/paywall redirects), so this route just renders the form.
export default async function NewProjectPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>;
}) {
  const { from } = await searchParams;
  const [inbound, intakeAddress] = await Promise.all([
    from ? loadInboundPrefill(from) : Promise.resolve(null),
    getPrimaryCompanyId().then(getIntakeAddressForCompany),
  ]);

  return (
    <NewProjectForm
      inbound={inbound}
      intakeAddress={intakeAddress}
      sharedIntakeAddress={sharedIntakeAddress()}
    />
  );
}
