/*
 * Mobi LinkedIn Scout — background service worker.
 *
 * The service worker is the ONLY place that reads the pairing token and makes
 * the authenticated upload. The token is never injected into the LinkedIn page,
 * never placed in a URL, and never logged.
 *
 * Flow (all owner-triggered from the popup):
 *   popup "Capture" → background reads config → injects extract.js into the
 *   active LinkedIn tab and runs a one-shot extractor → POSTs the visible
 *   candidates to the app's capture endpoint with a Bearer token → returns
 *   counts to the popup.
 */

import { normalizeApprovedServerUrl } from "./server-url.mjs";
import { isLinkedInMainFeedUrl } from "./linkedin-page.mjs";

// `browser` on Safari/Firefox, `chrome` on Chromium. Same MV3 surface.
const ext = typeof browser !== "undefined" ? browser : chrome;

const CAPTURE_PATH = "/api/scout/capture";

async function getConfig() {
  const { serverUrl, token } = await ext.storage.local.get(["serverUrl", "token"]);
  return { serverUrl: normalizeApprovedServerUrl(serverUrl), token };
}

async function runExtraction(tabId) {
  // Step 1: load the shared extractor into the page (defines self.MobiScout).
  await ext.scripting.executeScript({ target: { tabId }, files: ["extract.js"] });
  // Step 2: run a one-shot read and return the validated candidates.
  const results = await ext.scripting.executeScript({
    target: { tabId },
    func: () => self.MobiScout.extractVisiblePosts(document, window),
  });
  const value = results && results[0] ? results[0].result : null;
  return Array.isArray(value) ? value : [];
}

async function uploadCandidates(serverUrl, token, items) {
  const base = normalizeApprovedServerUrl(serverUrl);
  if (!base) throw new Error("Unapproved Scout server URL.");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(base + CAPTURE_PATH, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Token only ever travels in this header, never a URL.
        Authorization: "Bearer " + token,
      },
      body: JSON.stringify({ items }),
      signal: controller.signal,
      // Never follow a server redirect while carrying the capture bearer token.
      redirect: "error",
      credentials: "omit",
      referrerPolicy: "no-referrer",
      cache: "no-store",
    });
    let data = {};
    try {
      data = await res.json();
    } catch (e) {
      data = {};
    }
    return { status: res.status, ok: res.ok, data };
  } finally {
    clearTimeout(timer);
  }
}

async function handleCapture() {
  const { serverUrl, token } = await getConfig();
  if (!serverUrl || !token) {
    return { ok: false, error: "Not set up yet. Add your app URL and pairing code first." };
  }

  const tabs = await ext.tabs.query({ active: true, currentWindow: true });
  const tab = tabs && tabs[0];
  if (!tab || !tab.id || !isLinkedInMainFeedUrl(tab.url || "")) {
    return { ok: false, error: "Open the main LinkedIn feed, then tap Capture." };
  }

  let items;
  try {
    items = await runExtraction(tab.id);
  } catch (e) {
    return { ok: false, error: "Could not read the page. Reload LinkedIn and try again." };
  }

  if (!items.length) {
    return { ok: true, empty: true, accepted: 0, message: "No visible posts found on screen." };
  }

  let result;
  try {
    result = await uploadCandidates(serverUrl, token, items);
  } catch (e) {
    // Never include the token or response body in the surfaced error.
    return { ok: false, error: "Upload failed. Check your connection and app URL." };
  }

  if (result.status === 401) {
    return { ok: false, error: "Pairing code rejected. Re-pair with a fresh code from the Scout tab." };
  }
  if (result.status === 503) {
    return { ok: false, error: "No pairing is active. Create a code in the Scout tab first." };
  }
  if (!result.ok) {
    return { ok: false, error: "Upload was not accepted (status " + result.status + ")." };
  }

  const d = result.data || {};
  return {
    ok: true,
    found: items.length,
    accepted: d.accepted || 0,
    duplicates: d.duplicates || 0,
    invalid: d.invalid || 0,
  };
}

ext.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "capture") {
    handleCapture().then(sendResponse);
    return true; // keep the channel open for the async response
  }
  return false;
});
