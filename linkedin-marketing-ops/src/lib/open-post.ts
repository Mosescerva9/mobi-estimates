/**
 * User-gesture-safe "open the LinkedIn post" helper.
 *
 * Browsers block window.open() that runs after an awaited network round-trip
 * because it is no longer tied to the click. The reliable pattern is to open a
 * blank tab synchronously inside the click handler, then — only after approval
 * succeeds — navigate that already-open tab to the validated URL. If approval
 * fails or the URL does not validate, the blank tab is closed so the owner is
 * never left staring at a stray tab or, worse, an unvalidated destination.
 *
 * `navigateOpenedTab` is the browser-independent core: it re-validates the URL
 * and drives a minimal tab interface, so it is fully testable without a DOM.
 */

import { validateLinkedInPostUrl } from "./linkedin-url";

export type OpenedTab = {
  location: { href: string };
  close: () => void;
  // Cleared to sever the opener reference (rel="noopener" equivalent) once we
  // hold a handle to the tab.
  opener?: unknown;
};

/**
 * Navigate a pre-opened blank tab to a validated LinkedIn post URL.
 * Returns true only if a real navigation to a validated post happened.
 * On an invalid URL the tab (if any) is closed and false is returned — we never
 * navigate to an unvalidated URL.
 */
export function navigateOpenedTab(
  tab: OpenedTab | null,
  url: string | undefined | null
): boolean {
  const check = validateLinkedInPostUrl(url);
  if (!check.ok) {
    if (tab) tab.close();
    return false;
  }
  if (!tab) return false;
  tab.location.href = check.url;
  return true;
}
