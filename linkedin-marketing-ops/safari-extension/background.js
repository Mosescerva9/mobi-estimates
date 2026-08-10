/*
 * Mobi LinkedIn Scout — background service worker.
 *
 * The service worker is the ONLY place that reads the pairing token and makes
 * authenticated API calls. The token is never injected into the LinkedIn page,
 * never placed in a URL, and never logged.
 *
 * Owner-triggered flows:
 *   Capture visible posts → POST /api/scout/capture
 *   Draft for this post  → extract focused post → POST /api/scout/draft-one
 *   Approve & Post       → POST /api/scout/poster (approve) → inject submit → complete
 *   Post approved        → POST /api/scout/poster (next) → inject submit → complete
 */

import { normalizeApprovedServerUrl } from "./server-url.mjs";
import { isLinkedInMainFeedUrl, isLinkedInScoutableUrl } from "./linkedin-page.mjs";

const ext = typeof browser !== "undefined" ? browser : chrome;

const CAPTURE_PATH = "/api/scout/capture";
const DRAFT_ONE_PATH = "/api/scout/draft-one";
const POSTER_PATH = "/api/scout/poster";

async function getConfig() {
  const { serverUrl, token } = await ext.storage.local.get(["serverUrl", "token"]);
  return { serverUrl: normalizeApprovedServerUrl(serverUrl), token };
}

async function apiPost(serverUrl, token, path, body) {
  const base = normalizeApprovedServerUrl(serverUrl);
  if (!base) throw new Error("Unapproved Scout server URL.");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45000);
  try {
    const res = await fetch(base + path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
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

async function activeLinkedInTab() {
  const tabs = await ext.tabs.query({ active: true, currentWindow: true });
  const tab = tabs && tabs[0];
  if (!tab || !tab.id) return null;
  return tab;
}

async function runExtraction(tabId) {
  await ext.scripting.executeScript({ target: { tabId }, files: ["extract.js"] });
  const results = await ext.scripting.executeScript({
    target: { tabId },
    func: () => self.MobiScout.extractVisiblePosts(document, window),
  });
  const value = results && results[0] ? results[0].result : null;
  return Array.isArray(value) ? value : [];
}

async function runFocusedExtraction(tabId) {
  await ext.scripting.executeScript({ target: { tabId }, files: ["extract.js"] });
  const results = await ext.scripting.executeScript({
    target: { tabId },
    func: () => self.MobiScout.extractFocusedPost(document, window),
  });
  return results && results[0] ? results[0].result : null;
}

async function runSubmitComment(tabId, text) {
  await ext.scripting.executeScript({ target: { tabId }, files: ["submit-comment.js"] });
  const results = await ext.scripting.executeScript({
    target: { tabId },
    func: (commentText) => self.MobiScoutSubmit.submitComment(commentText),
    args: [text],
  });
  return results && results[0] ? results[0].result : { ok: false, error: "Submit script returned nothing." };
}

function authErrorMessage(status) {
  if (status === 401) {
    return "Pairing code rejected. Re-pair with a fresh code from the Scout tab.";
  }
  if (status === 503) {
    return "No pairing is active. Create a code in the Scout tab first.";
  }
  return null;
}

async function handleCapture() {
  const { serverUrl, token } = await getConfig();
  if (!serverUrl || !token) {
    return { ok: false, error: "Not set up yet. Add your pairing code first." };
  }

  const tab = await activeLinkedInTab();
  if (!tab || !isLinkedInMainFeedUrl(tab.url || "")) {
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
    result = await apiPost(serverUrl, token, CAPTURE_PATH, { items });
  } catch (e) {
    return { ok: false, error: "Upload failed. Check your connection and app URL." };
  }

  const authErr = authErrorMessage(result.status);
  if (authErr) return { ok: false, error: authErr };
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

async function handleDraftOne() {
  const { serverUrl, token } = await getConfig();
  if (!serverUrl || !token) {
    return { ok: false, error: "Not set up yet. Add your pairing code first." };
  }

  const tab = await activeLinkedInTab();
  if (!tab || !isLinkedInScoutableUrl(tab.url || "")) {
    return {
      ok: false,
      error: "Open a LinkedIn post (or the feed with a post centered), then try again.",
    };
  }

  let post;
  try {
    post = await runFocusedExtraction(tab.id);
  } catch (e) {
    return { ok: false, error: "Could not read this post. Reload LinkedIn and try again." };
  }

  if (!post || !post.postUrl || !post.sourceText) {
    return {
      ok: false,
      error: "Couldn’t identify the post on screen. Open the post permalink and try again.",
    };
  }

  let result;
  try {
    result = await apiPost(serverUrl, token, DRAFT_ONE_PATH, post);
  } catch (e) {
    return { ok: false, error: "Draft request failed. Check your connection." };
  }

  const authErr = authErrorMessage(result.status);
  if (authErr) return { ok: false, error: authErr };
  if (!result.ok) {
    return {
      ok: false,
      error: (result.data && result.data.error) || "Could not draft a comment (status " + result.status + ").",
    };
  }

  return {
    ok: true,
    reused: Boolean(result.data.reused),
    item: result.data.item,
  };
}

async function postItemOnTab(tabId, serverUrl, token, item) {
  const text = item && item.suggestedText;
  if (!text) return { ok: false, error: "Approved comment text is missing." };

  let submit;
  try {
    submit = await runSubmitComment(tabId, text);
  } catch (e) {
    return {
      ok: false,
      error: "Could not reach the LinkedIn comment box. Reload the post and try again.",
    };
  }

  if (!submit || !submit.ok) {
    return {
      ok: false,
      filled: Boolean(submit && submit.filled),
      error: (submit && submit.error) || "Could not submit the comment on LinkedIn.",
      item,
    };
  }

  let complete;
  try {
    complete = await apiPost(serverUrl, token, POSTER_PATH, {
      action: "complete",
      engageId: item.id,
    });
  } catch (e) {
    return {
      ok: true,
      posted: true,
      warn: "Comment was submitted on LinkedIn, but marking it done in Mobi failed. Mark it commented in Engage.",
      item,
    };
  }

  if (!complete.ok) {
    return {
      ok: true,
      posted: true,
      warn:
        (complete.data && complete.data.error) ||
        "Posted on LinkedIn, but Mobi couldn’t mark it done. Use Mark commented in Engage.",
      item,
    };
  }

  return { ok: true, posted: true, item: complete.data.item || item };
}

async function handleApproveAndPost(message) {
  const { serverUrl, token } = await getConfig();
  if (!serverUrl || !token) {
    return { ok: false, error: "Not set up yet. Add your pairing code first." };
  }

  const item = message && message.item;
  if (!item || !item.id || !item.sourcePostUrl) {
    return { ok: false, error: "No draft loaded. Tap Draft comment for this post first." };
  }

  const tab = await activeLinkedInTab();
  if (!tab || !isLinkedInScoutableUrl(tab.url || "")) {
    return { ok: false, error: "Stay on the LinkedIn post, then Approve & Post." };
  }

  const suggestedText =
    typeof message.suggestedText === "string" ? message.suggestedText : item.suggestedText;

  let approved;
  try {
    approved = await apiPost(serverUrl, token, POSTER_PATH, {
      action: "approve",
      engageId: item.id,
      suggestedText,
      sourcePostUrl: item.sourcePostUrl,
    });
  } catch (e) {
    return { ok: false, error: "Approve failed. Check your connection." };
  }

  const authErr = authErrorMessage(approved.status);
  if (authErr) return { ok: false, error: authErr };
  if (!approved.ok) {
    // Already approved is fine — continue to post.
    if (approved.status !== 409) {
      return {
        ok: false,
        error: (approved.data && approved.data.error) || "Could not approve this comment.",
      };
    }
  }

  const readyItem = (approved.data && approved.data.item) || {
    ...item,
    suggestedText,
    status: "approved",
  };

  return postItemOnTab(tab.id, serverUrl, token, readyItem);
}

async function handlePostApproved() {
  const { serverUrl, token } = await getConfig();
  if (!serverUrl || !token) {
    return { ok: false, error: "Not set up yet. Add your pairing code first." };
  }

  const tab = await activeLinkedInTab();
  if (!tab || !isLinkedInScoutableUrl(tab.url || "")) {
    return { ok: false, error: "Open the LinkedIn post you approved, then try again." };
  }

  let focused;
  try {
    focused = await runFocusedExtraction(tab.id);
  } catch (e) {
    focused = null;
  }

  const postUrl = (focused && focused.postUrl) || undefined;
  let next;
  try {
    next = await apiPost(serverUrl, token, POSTER_PATH, {
      action: "next",
      postUrl,
    });
  } catch (e) {
    return { ok: false, error: "Could not load the approved comment." };
  }

  const authErr = authErrorMessage(next.status);
  if (authErr) return { ok: false, error: authErr };
  if (!next.ok) {
    // If matching by focused URL failed, try any approved comment.
    if (postUrl && next.status === 404) {
      try {
        next = await apiPost(serverUrl, token, POSTER_PATH, { action: "next" });
      } catch (e) {
        return { ok: false, error: "Could not load the approved comment." };
      }
    }
  }
  if (!next.ok) {
    return {
      ok: false,
      error: (next.data && next.data.error) || "No approved comment is waiting.",
    };
  }

  return postItemOnTab(tab.id, serverUrl, token, next.data.item);
}

ext.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !message.type) return false;
  if (message.type === "capture") {
    handleCapture().then(sendResponse);
    return true;
  }
  if (message.type === "draftOne") {
    handleDraftOne().then(sendResponse);
    return true;
  }
  if (message.type === "approveAndPost") {
    handleApproveAndPost(message).then(sendResponse);
    return true;
  }
  if (message.type === "postApproved") {
    handlePostApproved().then(sendResponse);
    return true;
  }
  return false;
});
