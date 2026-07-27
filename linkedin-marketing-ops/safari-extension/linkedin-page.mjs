export function isLinkedInHost(hostname) {
  if (typeof hostname !== "string" || !hostname) return false;
  const host = hostname.toLowerCase();
  return host === "linkedin.com" || host.endsWith(".linkedin.com");
}

/** Main feed only (batch capture). */
export function isLinkedInMainFeedUrl(value) {
  if (typeof value !== "string" || !value) return false;
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      isLinkedInHost(url.hostname) &&
      (url.pathname === "/feed" || url.pathname === "/feed/")
    );
  } catch (_) {
    return false;
  }
}

const POST_PATH = /^\/posts\/[^/]+$/i;
const FEED_UPDATE_PATH = /^\/feed\/update\/urn:li:(activity|share|ugcPost):\d+$/i;

/** Feed or a single post permalink — pages where draft/post is allowed. */
export function isLinkedInScoutableUrl(value) {
  if (typeof value !== "string" || !value) return false;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !isLinkedInHost(url.hostname)) return false;
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (path === "/feed") return true;
    if (POST_PATH.test(path)) return true;
    if (FEED_UPDATE_PATH.test(path)) return true;
    return false;
  } catch (_) {
    return false;
  }
}
