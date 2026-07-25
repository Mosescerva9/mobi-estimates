/**
 * Minimal dependency-free Resend *receiving* client, mirroring the style of
 * lib/stripe.ts and lib/email.ts (REST via fetch, Node crypto for signatures).
 *
 * Resend signs webhooks with the Svix / Standard Webhooks scheme rather than
 * Stripe's, so the verification below is deliberately a separate implementation
 * from verifyStripeSignature: different signed content, base64 (not hex) digest,
 * and a header that may carry several candidate signatures during key rotation.
 *
 * SERVER-ONLY.
 */

import crypto from "crypto";

const RESEND_API = "https://api.resend.com";

/** Replay window for a webhook delivery, in seconds. */
const SIGNATURE_TOLERANCE_SECONDS = 300;

export function inboundIntakeConfigured(): boolean {
  return !!process.env.RESEND_API_KEY && !!process.env.RESEND_INBOUND_WEBHOOK_SECRET;
}

export interface SvixHeaders {
  id: string | null;
  timestamp: string | null;
  signature: string | null;
}

/**
 * Read the signature headers. Resend documents the `svix-*` names; the
 * vendor-neutral `webhook-*` aliases are accepted too so a provider-side rename
 * cannot silently start rejecting every forward.
 */
export function readSvixHeaders(headers: Headers): SvixHeaders {
  return {
    id: headers.get("svix-id") ?? headers.get("webhook-id"),
    timestamp: headers.get("svix-timestamp") ?? headers.get("webhook-timestamp"),
    signature: headers.get("svix-signature") ?? headers.get("webhook-signature"),
  };
}

function secretKeyBytes(secret: string): Buffer {
  // Signing secrets are presented as `whsec_<base64>`; the raw key is the
  // decoded base64 body, not the printable string.
  const body = secret.startsWith("whsec_") ? secret.slice("whsec_".length) : secret;
  return Buffer.from(body, "base64");
}

function timingSafeEqualString(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  return bufA.length === bufB.length && crypto.timingSafeEqual(bufA, bufB);
}

/**
 * Verify a Svix-signed webhook and return the parsed payload. Throws on any
 * mismatch. `rawBody` must be the exact bytes received — re-serialized JSON will
 * not match the signature.
 */
export function verifySvixSignature(
  rawBody: string,
  headers: SvixHeaders,
  secret: string,
  now: Date = new Date(),
): Record<string, unknown> {
  const { id, timestamp, signature } = headers;
  if (!id || !timestamp || !signature) {
    throw new Error("Missing webhook signature headers.");
  }

  const sentAt = Number(timestamp);
  if (!Number.isFinite(sentAt)) {
    throw new Error("Malformed webhook timestamp.");
  }
  if (Math.abs(Math.floor(now.getTime() / 1000) - sentAt) > SIGNATURE_TOLERANCE_SECONDS) {
    throw new Error("Webhook timestamp outside tolerance.");
  }

  const expected = crypto
    .createHmac("sha256", secretKeyBytes(secret))
    .update(`${id}.${timestamp}.${rawBody}`, "utf8")
    .digest("base64");

  // The header holds space-separated `v1,<signature>` pairs — more than one
  // while a signing secret is being rotated.
  const candidates = signature
    .split(" ")
    .map((part) => part.trim())
    .filter((part) => part.startsWith("v1,"))
    .map((part) => part.slice("v1,".length));

  if (candidates.length === 0) {
    throw new Error("No v1 webhook signature present.");
  }
  if (!candidates.some((candidate) => timingSafeEqualString(expected, candidate))) {
    throw new Error("Webhook signature verification failed.");
  }

  return JSON.parse(rawBody) as Record<string, unknown>;
}

// ---- receiving API ---------------------------------------------------------

export interface ReceivedEmailAttachment {
  id: string;
  filename: string | null;
  content_type: string | null;
  content_disposition: string | null;
  content_id: string | null;
  size: number | null;
  download_url?: string | null;
}

export interface ReceivedEmail {
  id: string;
  from: string | null;
  to: string[];
  cc: string[];
  subject: string | null;
  text: string | null;
  headers: Record<string, string> | null;
  attachments: ReceivedEmailAttachment[];
}

async function resendGet<T>(path: string): Promise<T> {
  const key = process.env.RESEND_API_KEY;
  if (!key) throw new Error("RESEND_API_KEY is not configured (server-only).");
  const res = await fetch(`${RESEND_API}${path}`, {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend GET ${path} failed (${res.status}): ${body}`);
  }
  return (await res.json()) as T;
}

function asStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === "string");
  if (typeof value === "string") return [value];
  return [];
}

/**
 * Fetch the full received email. The webhook payload carries metadata only —
 * body and attachment bytes are fetched separately so large plan sets don't have
 * to fit in a serverless request body.
 */
export async function getReceivedEmail(emailId: string): Promise<ReceivedEmail> {
  const raw = await resendGet<Record<string, unknown>>(
    `/emails/receiving/${encodeURIComponent(emailId)}`,
  );
  return {
    id: String(raw.id ?? emailId),
    from: typeof raw.from === "string" ? raw.from : null,
    to: asStringArray(raw.to),
    cc: asStringArray(raw.cc),
    subject: typeof raw.subject === "string" ? raw.subject : null,
    text: typeof raw.text === "string" ? raw.text : null,
    headers: (raw.headers as Record<string, string> | undefined) ?? null,
    attachments: Array.isArray(raw.attachments)
      ? (raw.attachments as ReceivedEmailAttachment[])
      : [],
  };
}

/**
 * List attachments with short-lived signed download URLs. The URLs expire (about
 * an hour), so download during the same request that lists them.
 */
export async function listReceivedAttachments(
  emailId: string,
): Promise<ReceivedEmailAttachment[]> {
  const raw = await resendGet<{ data?: unknown }>(
    `/emails/receiving/${encodeURIComponent(emailId)}/attachments`,
  );
  return Array.isArray(raw.data) ? (raw.data as ReceivedEmailAttachment[]) : [];
}

/** Download one attachment's bytes from its signed URL. */
export async function downloadAttachment(url: string): Promise<Uint8Array> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Attachment download failed (${res.status}).`);
  }
  return new Uint8Array(await res.arrayBuffer());
}

// ---- webhook payload -------------------------------------------------------

export interface EmailReceivedEvent {
  emailId: string;
  from: string | null;
  to: string[];
  cc: string[];
  receivedFor: string[];
  subject: string | null;
}

/** Narrow an `email.received` payload, or null for any other event type. */
export function parseEmailReceivedEvent(
  payload: Record<string, unknown>,
): EmailReceivedEvent | null {
  if (payload.type !== "email.received") return null;
  const data = (payload.data as Record<string, unknown> | undefined) ?? {};
  const emailId = data.email_id;
  if (typeof emailId !== "string" || !emailId) return null;

  return {
    emailId,
    from: typeof data.from === "string" ? data.from : null,
    to: asStringArray(data.to),
    cc: asStringArray(data.cc),
    receivedFor: asStringArray(data.received_for),
    subject: typeof data.subject === "string" ? data.subject : null,
  };
}
