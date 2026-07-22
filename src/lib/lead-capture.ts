/**
 * Public lead-capture normalization + abuse controls (pure; no server imports).
 *
 * The homepage email-capture form posts to a server action that builds a record
 * with these helpers before inserting. This module ONLY normalizes/validates —
 * it never sends email or touches the network.
 *
 * Guarantees enforced here:
 *   • email normalized (trim + lowercase) and shape/length bounded,
 *   • source + UTM values constrained to strict allowlists (unknown -> null),
 *   • free-text UTM fields bounded and control-chars stripped,
 *   • honeypot detection (a filled hidden field means a bot),
 *   • explicit consent version is stamped.
 */

/** Bump when the owner-approved consent/disclosure copy changes. */
export const LEAD_CONSENT_VERSION = "2026-07-owner-approved-1";

export const LEAD_CONSENT_COPY =
  "By submitting, you agree Mobi may contact you about your estimate request and related services. You can unsubscribe at any time.";

/** Strict allowlist for the form's declared source. Unknown -> "unknown". */
export const LEAD_SOURCE_ALLOWLIST = [
  "homepage_hero",
  "homepage_footer",
  "homepage_cta",
  "pricing",
  "unknown",
] as const;
export type LeadSource = (typeof LEAD_SOURCE_ALLOWLIST)[number];

/** Strict allowlist for utm_source. Unknown -> null (dropped). */
export const UTM_SOURCE_ALLOWLIST = [
  "google",
  "bing",
  "facebook",
  "instagram",
  "linkedin",
  "youtube",
  "email",
  "newsletter",
  "referral",
  "partner",
  "direct",
] as const;

/** Strict allowlist for utm_medium. Unknown -> null (dropped). */
export const UTM_MEDIUM_ALLOWLIST = [
  "cpc",
  "ppc",
  "paid_social",
  "organic",
  "social",
  "email",
  "referral",
  "affiliate",
  "display",
] as const;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const UTM_FREE_TEXT_MAX = 120;

export function normalizeEmail(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const email = raw.trim().toLowerCase();
  if (email.length < 3 || email.length > 320) return null;
  if (!EMAIL_RE.test(email)) return null;
  return email;
}

export function normalizeSource(raw: unknown): LeadSource {
  return typeof raw === "string" && (LEAD_SOURCE_ALLOWLIST as readonly string[]).includes(raw)
    ? (raw as LeadSource)
    : "unknown";
}

function allowlisted(raw: unknown, allowlist: readonly string[]): string | null {
  if (typeof raw !== "string") return null;
  const v = raw.trim().toLowerCase();
  return allowlist.includes(v) ? v : null;
}

/** Bounded free-text UTM value: strip control chars, cap length; empty -> null. */
export function sanitizeUtmFreeText(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  // Drop ASCII control characters (code points < 0x20 and 0x7F) then bound length.
  let cleaned = "";
  for (const ch of raw) {
    const code = ch.codePointAt(0) ?? 0;
    if (code >= 0x20 && code !== 0x7f) cleaned += ch;
  }
  cleaned = cleaned.trim().slice(0, UTM_FREE_TEXT_MAX);
  return cleaned.length > 0 ? cleaned : null;
}

/** A honeypot is a hidden field real users never fill. Any content => bot. */
export function isHoneypotTripped(raw: unknown): boolean {
  return typeof raw === "string" && raw.trim().length > 0;
}

export interface LeadCaptureInput {
  email?: unknown;
  source?: unknown;
  utmSource?: unknown;
  utmMedium?: unknown;
  utmCampaign?: unknown;
  utmContent?: unknown;
  utmTerm?: unknown;
  honeypot?: unknown;
}

export interface LeadCaptureRecord {
  email: string;
  source: LeadSource;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_content: string | null;
  utm_term: string | null;
  consent_at: string;
  consent_version: string;
}

export type LeadCaptureResult =
  | { ok: true; record: LeadCaptureRecord }
  | { ok: false; reason: "honeypot" | "invalid_email" };

/**
 * Pure parse/normalize of a lead submission into a persistable record. Returns a
 * `honeypot`/`invalid_email` failure the caller should treat as a no-op behind a
 * GENERIC response (never reveal which one), so bots and bad input can't probe.
 */
export function parseLeadCapture(
  input: LeadCaptureInput,
  now: Date = new Date(),
): LeadCaptureResult {
  if (isHoneypotTripped(input.honeypot)) {
    return { ok: false, reason: "honeypot" };
  }
  const email = normalizeEmail(input.email);
  if (!email) {
    return { ok: false, reason: "invalid_email" };
  }
  return {
    ok: true,
    record: {
      email,
      source: normalizeSource(input.source),
      utm_source: allowlisted(input.utmSource, UTM_SOURCE_ALLOWLIST),
      utm_medium: allowlisted(input.utmMedium, UTM_MEDIUM_ALLOWLIST),
      utm_campaign: sanitizeUtmFreeText(input.utmCampaign),
      utm_content: sanitizeUtmFreeText(input.utmContent),
      utm_term: sanitizeUtmFreeText(input.utmTerm),
      consent_at: now.toISOString(),
      consent_version: LEAD_CONSENT_VERSION,
    },
  };
}
