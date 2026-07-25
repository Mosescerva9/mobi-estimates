import type { Metadata } from "next";
import Link from "next/link";
import { requireUser } from "@/lib/auth";
import { getIntakeAddressForCompany, getPrimaryCompanyId } from "@/lib/company";
import { createClient } from "@/lib/supabase/server";
import { formatBytes, PROJECT_FILES_BUCKET } from "@/lib/projects";
import {
  intakeStatusBadgeClass,
  intakeStatusLabel,
  isConvertibleIntakeStatus,
} from "@/lib/inbound-intake";
import { sharedIntakeAddress } from "@/lib/intake-email";
import { ForwardingAddressCard } from "@/components/ForwardingAddressCard";
import { dismissForwardedBid } from "./actions";
import { inboxNoticeCopy } from "./notices";

export const metadata: Metadata = {
  title: "Forwarded bids — Mobi Estimates",
  robots: { index: false },
};

interface IntakeMessage {
  id: string;
  subject: string | null;
  from_email: string;
  from_name: string | null;
  body_preview: string | null;
  status: string;
  sender_verified: boolean;
  attachment_count: number;
  skipped_attachment_count: number;
  project_id: string | null;
  received_at: string;
}

interface IntakeAttachment {
  id: string;
  message_id: string;
  file_name: string;
  size_bytes: number | null;
  storage_path: string;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default async function ForwardedBidsPage({
  searchParams,
}: {
  searchParams: Promise<{ notice?: string }>;
}) {
  await requireUser();
  const { notice } = await searchParams;
  const companyId = await getPrimaryCompanyId();
  const intakeAddress = await getIntakeAddressForCompany(companyId);
  const supabase = await createClient();

  // RLS scopes both reads to the caller's company (migration 0036).
  const { data: messageRows } = await supabase
    .from("inbound_intake_messages")
    .select(
      "id, subject, from_email, from_name, body_preview, status, sender_verified, attachment_count, skipped_attachment_count, project_id, received_at",
    )
    .order("received_at", { ascending: false })
    .limit(50);
  const messages = (messageRows ?? []) as IntakeMessage[];

  const attachmentsByMessage = new Map<string, IntakeAttachment[]>();
  const signedByPath = new Map<string, string>();

  if (messages.length > 0) {
    const { data: attachmentRows } = await supabase
      .from("inbound_intake_attachments")
      .select("id, message_id, file_name, size_bytes, storage_path")
      .in(
        "message_id",
        messages.map((m) => m.id),
      )
      .order("created_at");

    for (const row of (attachmentRows ?? []) as IntakeAttachment[]) {
      const list = attachmentsByMessage.get(row.message_id) ?? [];
      list.push(row);
      attachmentsByMessage.set(row.message_id, list);
    }

    const paths = ((attachmentRows ?? []) as IntakeAttachment[]).map((a) => a.storage_path);
    if (paths.length > 0) {
      const { data: signed } = await supabase.storage
        .from(PROJECT_FILES_BUCKET)
        .createSignedUrls(paths, 300);
      for (const entry of signed ?? []) {
        if (entry.path && entry.signedUrl) signedByPath.set(entry.path, entry.signedUrl);
      }
    }
  }

  const waiting = messages.filter((m) => isConvertibleIntakeStatus(m.status));
  const handled = messages.filter((m) => !isConvertibleIntakeStatus(m.status));
  const noticeCopy = inboxNoticeCopy(notice);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold text-navy">Forwarded bids</h1>
      <p className="mt-1 text-slate-500">
        Invitations to bid you’ve forwarded to Mobi, with the documents that came
        with them.
      </p>

      {noticeCopy && (
        <p
          className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
            noticeCopy.tone === "success"
              ? "border-green-200 bg-green-50 text-green-800"
              : noticeCopy.tone === "warning"
                ? "border-amber-200 bg-amber-50 text-amber-800"
                : "border-red-200 bg-red-50 text-red-800"
          }`}
        >
          {noticeCopy.message}
        </p>
      )}

      {intakeAddress && (
        <div className="mt-6">
          <ForwardingAddressCard
            address={intakeAddress}
            sharedAddress={sharedIntakeAddress()}
          />
        </div>
      )}

      {messages.length === 0 && (
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-base font-bold text-navy">Nothing forwarded yet</h2>
          <p className="mt-1 text-sm text-slate-500">
            The next time a general contractor sends you an invitation to bid,
            forward it to the address above. It’ll show up here with the plans and
            specs already saved — usually within a minute or two.
          </p>
          <Link
            href="/portal/projects/new"
            className="mt-4 inline-block text-sm font-semibold text-brand hover:underline"
          >
            Or upload plans directly →
          </Link>
        </div>
      )}

      {waiting.length > 0 && (
        <section className="mt-6 space-y-4">
          <h2 className="text-base font-bold text-navy">Waiting for your review</h2>
          {waiting.map((message) => {
            const attachments = attachmentsByMessage.get(message.id) ?? [];
            return (
              <article
                key={message.id}
                className="rounded-2xl border border-slate-200 bg-white p-6"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold text-navy">
                      {message.subject || "(no subject)"}
                    </h3>
                    <p className="mt-0.5 text-xs text-slate-400">
                      From {message.from_name ? `${message.from_name} · ` : ""}
                      {message.from_email} · {formatDate(message.received_at)}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${intakeStatusBadgeClass(message.status)}`}
                  >
                    {intakeStatusLabel(message.status)}
                  </span>
                </div>

                {!message.sender_verified && (
                  <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    This arrived from an address that isn’t on your Mobi account.
                    Check the sender and the documents before you submit it.
                  </p>
                )}

                {attachments.length > 0 ? (
                  <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
                    {attachments.map((attachment) => {
                      const url = signedByPath.get(attachment.storage_path);
                      return (
                        <li
                          key={attachment.id}
                          className="flex items-center justify-between gap-3 px-4 py-2.5"
                        >
                          <span className="min-w-0 truncate text-sm text-navy">
                            {attachment.file_name}
                          </span>
                          <span className="flex shrink-0 items-center gap-3">
                            <span className="text-xs text-slate-400">
                              {formatBytes(attachment.size_bytes)}
                            </span>
                            {url && (
                              <a
                                href={url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-sm font-semibold text-brand hover:underline"
                              >
                                View
                              </a>
                            )}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="mt-4 text-sm text-slate-500">
                    No documents were attached to this email. You can still start a
                    project from it and upload the plans yourself.
                  </p>
                )}

                {message.skipped_attachment_count > 0 && (
                  <p className="mt-2 text-xs text-amber-700">
                    {message.skipped_attachment_count} attachment(s) weren’t saved
                    because of their file type or size.
                  </p>
                )}

                {message.body_preview && (
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm font-semibold text-slate-500 hover:text-navy">
                      Show forwarded message
                    </summary>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-xs text-slate-600">
                      {message.body_preview}
                    </pre>
                  </details>
                )}

                <div className="mt-5 flex flex-wrap items-center gap-3">
                  <Link
                    href={`/portal/projects/new?from=${message.id}`}
                    className="rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-dark"
                  >
                    Review &amp; submit for an estimate
                  </Link>
                  <form action={dismissForwardedBid}>
                    <input type="hidden" name="messageId" value={message.id} />
                    <button
                      type="submit"
                      className="text-sm font-semibold text-slate-400 hover:text-red-600"
                    >
                      Dismiss
                    </button>
                  </form>
                </div>
              </article>
            );
          })}
        </section>
      )}

      {handled.length > 0 && (
        <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-base font-bold text-navy">Earlier forwards</h2>
          <ul className="mt-4 divide-y divide-slate-100">
            {handled.map((message) => (
              <li key={message.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-navy">
                    {message.subject || "(no subject)"}
                  </div>
                  <div className="text-xs text-slate-400">
                    {formatDate(message.received_at)} · {message.from_email}
                  </div>
                </div>
                {message.project_id ? (
                  <Link
                    href={`/portal/projects/${message.project_id}`}
                    className="shrink-0 text-sm font-semibold text-brand hover:underline"
                  >
                    View project →
                  </Link>
                ) : (
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${intakeStatusBadgeClass(message.status)}`}
                  >
                    {intakeStatusLabel(message.status)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
