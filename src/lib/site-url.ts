/**
 * Canonical public origin for the app. Customer-facing absolute URLs — Stripe
 * checkout success/cancel, the billing portal return URL, and email claim
 * links — must resolve to the real website, never to a preview, staging,
 * portal, or GitHub Pages host. Building them from the incoming request origin
 * is unsafe: a customer who reaches a preview/fake URL would be sent back
 * there by Stripe. Use `publicBaseUrl()` instead.
 */

const DEFAULT_PUBLIC_BASE_URL = "https://mobiestimates.com";

// Hosts we must never hand a customer off to, even if an env value points here.
const FORBIDDEN_HOST_PATTERNS = [
  /mosescerva9\.github\.io/i,
  /portal\.mobiestimates\.com/i,
  /\.vercel\.app$/i,
];

/**
 * Returns the canonical public base origin (no trailing slash).
 *
 * Production default is `https://mobiestimates.com`. An explicit
 * `NEXT_PUBLIC_SITE_URL` override is honored for local/dev (e.g.
 * `http://localhost:3000`) only when it is a valid http(s) origin that is not
 * one of the known fake/preview hosts; anything else falls back to the default.
 */
export function publicBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (!raw) return DEFAULT_PUBLIC_BASE_URL;

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return DEFAULT_PUBLIC_BASE_URL;
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return DEFAULT_PUBLIC_BASE_URL;
  }
  if (FORBIDDEN_HOST_PATTERNS.some((re) => re.test(url.host))) {
    return DEFAULT_PUBLIC_BASE_URL;
  }

  // Normalize: strip trailing slash(es) so callers can safely append paths.
  return url.origin;
}
