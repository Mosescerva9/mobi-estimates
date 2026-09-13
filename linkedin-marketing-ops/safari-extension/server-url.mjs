export const APPROVED_SERVER_URL = "https://mobi-linkedin-ops.vercel.app";

/**
 * Return the one approved Scout server URL, or null for every other value.
 * Exact string matching (with only one optional trailing slash) prevents URL
 * parser normalization from accepting alternate spellings such as an explicit
 * port, credentials, a path, or a lookalike host.
 */
export function normalizeApprovedServerUrl(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (trimmed === APPROVED_SERVER_URL || trimmed === `${APPROVED_SERVER_URL}/`) {
    return APPROVED_SERVER_URL;
  }
  return null;
}
