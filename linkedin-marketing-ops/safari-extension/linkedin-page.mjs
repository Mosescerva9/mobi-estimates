export function isLinkedInMainFeedUrl(value) {
  if (typeof value !== "string" || !value) return false;
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      /(^|\.)linkedin\.com$/.test(url.hostname) &&
      (url.pathname === "/feed" || url.pathname === "/feed/")
    );
  } catch (_) {
    return false;
  }
}
