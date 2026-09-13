import { createHash, randomBytes, timingSafeEqual } from "crypto";

/**
 * Token helpers for the Safari Scout integration. Two independent secrets exist
 * and must never be interchangeable:
 *
 *  - The capture token pairs one iPhone to this owner's app. It is generated
 *    here, shown to the owner exactly once, and persisted ONLY as a
 *    domain-separated SHA-256 hash. The capture endpoint hashes the presented
 *    bearer token and compares it, in constant time, against the stored hash.
 *
 *  - The job token (SCOUT_JOB_TOKEN) authorises the Hermes worker. It lives in
 *    the server environment only and is compared, in constant time, against the
 *    presented bearer token. It is never returned to a browser and a capture
 *    token can never satisfy it (different endpoints, different comparison).
 *
 * The domain prefixes below are what make the two hashes non-interchangeable: a
 * capture-token hash can never collide with any other SHA-256 use in the app.
 */

const CAPTURE_TOKEN_DOMAIN = "mobi-linkedin-ops:scout-capture:v1";

/** Generate a high-entropy, URL-safe capture token (32 random bytes). */
export function generateCaptureToken(): string {
  return randomBytes(32).toString("base64url");
}

/** Domain-separated SHA-256 hash of a capture token, as lowercase hex. */
export function hashCaptureToken(token: string): string {
  return createHash("sha256")
    .update(`${CAPTURE_TOKEN_DOMAIN}:${token}`)
    .digest("hex");
}

/** Last four characters, shown so the owner can recognise the active code. Non-secret. */
export function tokenLast4(token: string): string {
  return token.slice(-4);
}

/**
 * Constant-time comparison of two strings. Returns false immediately on a length
 * mismatch (which is not secret) and otherwise runs timingSafeEqual so an
 * attacker cannot learn the secret one character at a time from timing.
 */
export function constantTimeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a, "utf8");
  const right = Buffer.from(b, "utf8");
  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}

/**
 * Extract a bearer token from an Authorization header. Tokens are only ever
 * accepted in this header, never in a URL/query string (so they cannot leak
 * through logs, referrers, or browser history). Returns null when absent/malformed.
 */
export function bearerFromHeader(header: string | null | undefined): string | null {
  if (!header) return null;
  const match = /^Bearer\s+(.+)$/i.exec(header.trim());
  if (!match) return null;
  const token = match[1].trim();
  return token.length ? token : null;
}
