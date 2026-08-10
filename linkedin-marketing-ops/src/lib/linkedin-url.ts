/**
 * LinkedIn post URL validation and normalization.
 *
 * This is the single, reusable guard for owner-pasted post URLs. It is
 * deliberately strict: the owner clicks a button that opens whatever URL this
 * returns, so we must never hand back a lookalike, a credential-bearing URL, or
 * a non-LinkedIn target. We normalize without inventing a different target —
 * the path and query the owner pasted are preserved; only the URL is
 * canonicalized (scheme/host casing) by the URL parser.
 *
 * Host is not enough: linkedin.com also hosts login, OAuth, checkpoint, and
 * open-redirect ("safety/go", "redir/redirect") endpoints. Opening one of those
 * with attacker-controlled query params would bounce the owner off-site or
 * replay a credential flow. So we additionally allow-list the *path* down to the
 * two shapes this product ever needs: a canonical `/posts/<slug>` permalink and
 * a `/feed/update/urn:li:(activity|share|ugcPost):<id>` permalink. Every other
 * path — including the root feed and profile-only `/in/<handle>` — is rejected.
 */

export type UrlCheck = { ok: true; url: string } | { ok: false; error: string };

// Generous but bounded — real post URLs are well under this. Rejects the
// pathological "overlong" input the task calls out.
const MAX_URL_LEN = 2048;

// The only two post-permalink path shapes we accept. A single optional trailing
// slash is tolerated (LinkedIn emits both). Matched case-insensitively against a
// path whose trailing slashes have already been stripped:
//   /posts/<non-empty-slug>
//   /feed/update/urn:li:(activity|share|ugcPost):<numeric-id>
// The slug and id must be non-empty and contain no further path segment, so
// login/checkpoint/oauth/redirect paths can never satisfy either pattern.
const POST_PATH = /^\/posts\/[^/]+$/;
const FEED_UPDATE_PATH = /^\/feed\/update\/urn:li:(activity|share|ugcpost):\d+$/;

/** Exact host match or a genuine subdomain of linkedin.com (e.g. www., de.). */
function isLinkedInHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return host === "linkedin.com" || host.endsWith(".linkedin.com");
}

/**
 * True only for a canonical LinkedIn post/permalink path. `pathname` is the
 * raw parsed path; we strip a trailing slash and lower-case before matching so
 * casing and an optional trailing slash never change the verdict.
 */
function isPostPath(pathname: string): boolean {
  const path = pathname.replace(/\/+$/, "").toLowerCase();
  return POST_PATH.test(path) || FEED_UPDATE_PATH.test(path);
}

export function validateLinkedInPostUrl(input: unknown): UrlCheck {
  if (typeof input !== "string") {
    return { ok: false, error: "A LinkedIn post URL is required." };
  }
  const raw = input.trim();
  if (!raw) {
    return { ok: false, error: "A LinkedIn post URL is required." };
  }
  if (raw.length > MAX_URL_LEN) {
    return { ok: false, error: "That LinkedIn post URL is too long." };
  }

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    return { ok: false, error: "That does not look like a valid URL." };
  }

  if (parsed.protocol !== "https:") {
    return { ok: false, error: "The LinkedIn post URL must start with https://." };
  }
  // Reject embedded credentials and credential-lookalike hosts
  // (e.g. https://linkedin.com@evil.example/…).
  if (parsed.username || parsed.password) {
    return {
      ok: false,
      error: "The LinkedIn post URL must not contain a username or password.",
    };
  }
  if (!isLinkedInHost(parsed.hostname)) {
    return {
      ok: false,
      error: "That URL is not on linkedin.com. Paste the link to the actual post.",
    };
  }
  // A bare host (no path) is the LinkedIn home page, not a post.
  if (parsed.pathname === "" || parsed.pathname === "/") {
    return {
      ok: false,
      error: "Paste a link to a specific LinkedIn post, not the LinkedIn home page.",
    };
  }
  // Path allow-list: only real post permalinks. This rejects login, checkpoint,
  // OAuth, redirect ("safety/go", "redir/redirect"), the root feed, and
  // profile-only paths even though they are all on linkedin.com.
  if (!isPostPath(parsed.pathname)) {
    return {
      ok: false,
      error:
        "That is not a LinkedIn post link. Paste the URL of a specific post (it looks like linkedin.com/posts/… or linkedin.com/feed/update/…).",
    };
  }

  return { ok: true, url: parsed.toString() };
}

/**
 * Stable comparison key for duplicate detection. Two links to the same post
 * that differ only by trailing slash, query string, fragment, or host casing
 * collapse to the same key. Never used as a navigation target — only for
 * dedup. Returns null for anything unparsable (old/hand-edited records).
 */
export function linkedInPostKey(url: string | undefined | null): string | null {
  if (!url) return null;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  const path = parsed.pathname.replace(/\/+$/, "");
  return `${parsed.hostname.toLowerCase()}${path}`;
}
