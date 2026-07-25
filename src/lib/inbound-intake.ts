/**
 * Parsing and presentation helpers for forwarded bid invitations.
 *
 * Everything here is PURE so it can be regression-tested offline
 * (scripts/test-inbound-intake.ts) without a mail provider or a database.
 *
 * These helpers only ever PREFILL the submission form. Nothing derived here is
 * treated as confirmed scope — the contractor reviews and edits every field
 * before the project is submitted, which matters because a forwarded ITB is
 * unstructured text written by a third party.
 */

import { isAllowedExtension, MAX_FILE_BYTES, MAX_FILES } from "@/lib/projects";

/** Cap on documents stored per forwarded message (matches the upload form). */
export const MAX_INBOUND_ATTACHMENTS = MAX_FILES;
/** Cap on a single stored document (matches the bucket's file_size_limit). */
export const MAX_INBOUND_ATTACHMENT_BYTES = MAX_FILE_BYTES;
/** Cap on stored body text, so a long forwarded thread can't bloat a row. */
export const MAX_BODY_PREVIEW_CHARS = 4000;
/**
 * Cap on unconverted forwards held per company. Anyone who learns an address can
 * send to it, so this bounds how much storage a flood could consume before the
 * contractor notices and we rotate their slug.
 */
export const MAX_PENDING_INTAKE_MESSAGES = 50;

/**
 * Cap on unroutable forwards recorded per rolling day, across all tenants. The
 * shared intake address sits on a public domain, so it will receive spam and
 * misdirected mail; this keeps a burst from filling the staff triage queue.
 */
export const MAX_UNROUTED_INTAKE_MESSAGES_PER_DAY = 200;

export const INBOUND_INTAKE_STATUSES = [
  "pending",
  "sender_unverified",
  "unrouted",
  "converted",
  "dismissed",
] as const;
export type InboundIntakeStatus = (typeof INBOUND_INTAKE_STATUSES)[number];

/** Statuses a customer may still turn into a project. */
export const CONVERTIBLE_INTAKE_STATUSES = [
  "pending",
  "sender_unverified",
] as const satisfies readonly InboundIntakeStatus[];

export function isConvertibleIntakeStatus(status: string | null | undefined): boolean {
  return (CONVERTIBLE_INTAKE_STATUSES as readonly string[]).includes(status ?? "");
}

export function intakeStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case "pending":
      return "Ready to review";
    case "sender_unverified":
      return "Unrecognized sender";
    case "unrouted":
      return "Needs routing";
    case "converted":
      return "Submitted as a project";
    case "dismissed":
      return "Dismissed";
    default:
      return "Forwarded bid";
  }
}

export function intakeStatusBadgeClass(status: string | null | undefined): string {
  switch (status) {
    case "pending":
      return "bg-blue-50 text-blue-700";
    case "sender_unverified":
    case "unrouted":
      return "bg-amber-50 text-amber-700";
    case "converted":
      return "bg-green-50 text-green-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

/**
 * Staff-facing explanation of why a forward could not be placed, and the action
 * that resolves it. Never shown to a customer — an unrouted forward has no
 * tenant, so no customer is entitled to see it.
 */
export function unroutedReasonCopy(reason: string | null | undefined): {
  label: string;
  nextStep: string;
} {
  switch (reason) {
    case "unknown_sender":
      return {
        label: "Sender isn't on any account",
        nextStep:
          "Ask them to forward from the email on their Mobi account, or to use the tagged address from their portal. If they're not a client yet, this is a lead.",
      };
    case "ambiguous_sender":
      return {
        label: "Sender belongs to more than one company",
        nextStep:
          "Confirm which company this bid is for, then ask them to resend using that company's tagged address.",
      };
    case "unknown_alias":
      return {
        label: "Tagged address matches no live company",
        nextStep:
          "The tag is stale or the company was removed. Check the company record before replying.",
      };
    default:
      return {
        label: "Could not be routed",
        nextStep: "Review the sender and subject, then follow up manually.",
      };
  }
}

// ---- subject → project name ------------------------------------------------

/** Leading noise on a forwarded ITB subject line, stripped repeatedly. */
const SUBJECT_PREFIXES = [
  /^\s*(fwd?|re|aw|tr)\s*:\s*/i,
  /^\s*\[[^\]]{1,40}\]\s*/, // [EXTERNAL], [SPAM], [Bid], mailing-list tags
  /^\s*(invitation\s+to\s+bid|invite\s+to\s+bid|bid\s+invitation|itb|rfp|rfq|bid\s+request|request\s+for\s+(proposal|quote))\s*[:\-–—]\s*/i,
];

/**
 * Best-effort project name from a forwarded subject line. Falls back to a
 * neutral placeholder rather than an empty field so the form is never blank.
 */
export function projectNameFromSubject(subject: string | null | undefined): string {
  let name = (subject ?? "").replace(/\s+/g, " ").trim();

  let changed = true;
  while (changed && name.length > 0) {
    changed = false;
    for (const re of SUBJECT_PREFIXES) {
      const next = name.replace(re, "").trim();
      if (next !== name) {
        name = next;
        changed = true;
      }
    }
  }

  // Trailing separators left behind by a stripped prefix.
  name = name.replace(/^[\-–—:|]+\s*/, "").replace(/\s*[\-–—:|]+$/, "").trim();

  if (name.length < 2) return "Forwarded bid invitation";
  return name.slice(0, 200);
}

// ---- body → bid due date ---------------------------------------------------

const MONTHS: Record<string, number> = {
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3, apr: 4, april: 4,
  may: 5, jun: 6, june: 6, jul: 7, july: 7, aug: 8, august: 8, sep: 9, sept: 9,
  september: 9, oct: 10, october: 10, nov: 11, november: 11, dec: 12, december: 12,
};

/** Phrases that introduce a bid deadline in an ITB. */
const DUE_CUE = /(bids?\s+(are\s+)?due|due\s+date|due\s+by|proposals?\s+due|quotes?\s+due|bid\s+deadline|deadline|submit\s+by)/i;

/** How far from today a parsed deadline may sit before we distrust it. */
const MAX_PAST_DAYS = 30;
const MAX_FUTURE_DAYS = 730;

function isoDate(year: number, month: number, day: number): string | null {
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const d = new Date(Date.UTC(year, month - 1, day));
  if (
    d.getUTCFullYear() !== year ||
    d.getUTCMonth() !== month - 1 ||
    d.getUTCDate() !== day
  ) {
    return null; // rolled over — e.g. Feb 30
  }
  return d.toISOString().slice(0, 10);
}

function withinTrustedWindow(iso: string, now: Date): boolean {
  const parsed = Date.parse(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed)) return false;
  const days = (parsed - now.getTime()) / 86_400_000;
  return days >= -MAX_PAST_DAYS && days <= MAX_FUTURE_DAYS;
}

function normalizeYear(raw: string, now: Date): number {
  const n = Number(raw);
  if (raw.length === 4) return n;
  // Two-digit years in ITBs are always near-present.
  return Math.floor(now.getUTCFullYear() / 100) * 100 + n;
}

/**
 * Pull a bid due date out of forwarded ITB text.
 *
 * Only dates that appear on a line mentioning a deadline are considered, and
 * only when they land in a believable window — a forwarded thread is full of
 * unrelated dates (signatures, prior correspondence, permit numbers) and a
 * silently wrong deadline on a bid is worse than no deadline at all. Returns
 * `YYYY-MM-DD` (what <input type="date"> expects) or null.
 */
export function bidDueDateFromText(
  text: string | null | undefined,
  now: Date = new Date(),
): string | null {
  if (!text) return null;

  for (const rawLine of text.split(/[\r\n]+/)) {
    const line = rawLine.trim();
    if (!line || !DUE_CUE.test(line)) continue;

    // Month D, YYYY  /  Mon D YYYY
    const named = line.match(
      /\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,)?\s+(\d{4})\b/,
    );
    if (named) {
      const month = MONTHS[named[1].toLowerCase()];
      if (month) {
        const iso = isoDate(Number(named[3]), month, Number(named[2]));
        if (iso && withinTrustedWindow(iso, now)) return iso;
      }
    }

    // M/D/YYYY or M-D-YY (US ordering — this is a US contractor product)
    const numeric = line.match(/\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})\b/);
    if (numeric) {
      const iso = isoDate(
        normalizeYear(numeric[3], now),
        Number(numeric[1]),
        Number(numeric[2]),
      );
      if (iso && withinTrustedWindow(iso, now)) return iso;
    }
  }

  return null;
}

// ---- attachment filtering --------------------------------------------------

export interface InboundAttachmentCandidate {
  filename?: string | null;
  size?: number | null;
  content_disposition?: string | null;
  content_id?: string | null;
}

export type AttachmentSkipReason =
  | "inline_image"
  | "unsupported_type"
  | "empty"
  | "too_large"
  | "over_limit";

/**
 * Whether a received attachment should be stored as a bid document.
 *
 * Inline parts are dropped because a forwarded email carries the sender's
 * signature logos as attachments; storing them would clutter the document
 * register that staff and the takeoff engine read.
 */
export function attachmentSkipReason(
  attachment: InboundAttachmentCandidate,
  storedSoFar: number,
): AttachmentSkipReason | null {
  if (storedSoFar >= MAX_INBOUND_ATTACHMENTS) return "over_limit";
  if (attachment.content_id || attachment.content_disposition === "inline") {
    return "inline_image";
  }
  const name = attachment.filename ?? "";
  if (!name || !isAllowedExtension(name)) return "unsupported_type";
  const size = attachment.size ?? 0;
  if (size <= 0) return "empty";
  if (size > MAX_INBOUND_ATTACHMENT_BYTES) return "too_large";
  return null;
}

// ---- body preview ----------------------------------------------------------

/** Collapse and truncate a forwarded body for storage/display. */
export function buildBodyPreview(text: string | null | undefined): string | null {
  if (!text) return null;
  const cleaned = text.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  if (!cleaned) return null;
  return cleaned.length > MAX_BODY_PREVIEW_CHARS
    ? `${cleaned.slice(0, MAX_BODY_PREVIEW_CHARS)}\n…(truncated)`
    : cleaned;
}

/**
 * Prefill text for the submission form's scope notes. Records where the request
 * came from so staff reviewing the project can trace it back to the forward,
 * and leaves the contractor's own instructions to be typed underneath.
 */
export function scopeNotesPrefill(input: {
  fromEmail: string;
  subject: string | null;
  receivedAt: string | null;
}): string {
  const lines = ["Forwarded bid invitation."];
  if (input.subject) lines.push(`Subject: ${input.subject}`);
  lines.push(`Forwarded by: ${input.fromEmail}`);
  if (input.receivedAt) {
    lines.push(`Received: ${new Date(input.receivedAt).toISOString().slice(0, 10)}`);
  }
  return lines.join("\n");
}
