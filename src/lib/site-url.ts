/**
 * Canonical authenticated-app origin. Stripe Checkout success/cancel URLs,
 * Billing Portal return URLs, and account-claim links must return to the portal
 * application—not to the static marketing site and never to a preview host.
 */

const DEFAULT_PORTAL_BASE_URL = "https://portal.mobiestimates.com";

const FORBIDDEN_HOST_PATTERNS = [
  /mosescerva9\.github\.io/i,
  /\.vercel\.app$/i,
];

/** Returns the canonical portal origin with no trailing slash. */
export function portalBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_PORTAL_URL?.trim();
  if (!raw) return DEFAULT_PORTAL_BASE_URL;

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return DEFAULT_PORTAL_BASE_URL;
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return DEFAULT_PORTAL_BASE_URL;
  }
  if (FORBIDDEN_HOST_PATTERNS.some((re) => re.test(url.host))) {
    return DEFAULT_PORTAL_BASE_URL;
  }

  const isCanonicalPortal = url.protocol === "https:" && url.hostname === "portal.mobiestimates.com";
  const isLocalDev =
    process.env.NODE_ENV !== "production" &&
    (url.hostname === "localhost" || url.hostname === "127.0.0.1");

  if (!isCanonicalPortal && !isLocalDev) {
    return DEFAULT_PORTAL_BASE_URL;
  }
  return url.origin;
}
