/*
 * Mobi LinkedIn Scout — popup UI.
 *
 * Primary flow: Draft comment for this post → review → Approve & Post.
 * The pairing token is stored locally and never displayed back or logged here;
 * authenticated calls happen only in the background service worker.
 */
import { APPROVED_SERVER_URL, normalizeApprovedServerUrl } from "./server-url.mjs";

const ext = typeof browser !== "undefined" ? browser : chrome;

const els = {
  setup: document.getElementById("setup"),
  ready: document.getElementById("ready"),
  token: document.getElementById("token"),
  save: document.getElementById("save"),
  draft: document.getElementById("draft"),
  draftPanel: document.getElementById("draftPanel"),
  draftText: document.getElementById("draftText"),
  draftMeta: document.getElementById("draftMeta"),
  approvePost: document.getElementById("approvePost"),
  postApproved: document.getElementById("postApproved"),
  capture: document.getElementById("capture"),
  repair: document.getElementById("repair"),
  result: document.getElementById("result"),
};

/** @type {null | { id: string, suggestedText: string, sourcePostUrl: string, targetName?: string, status?: string }} */
let currentItem = null;

function show(view) {
  els.setup.hidden = view !== "setup";
  els.ready.hidden = view !== "ready";
}

function setResult(text, kind) {
  els.result.textContent = text;
  els.result.className = "result" + (kind ? " " + kind : "");
}

function setBusy(busy) {
  els.draft.disabled = busy;
  els.approvePost.disabled = busy;
  els.postApproved.disabled = busy;
  els.capture.disabled = busy;
}

function showDraft(item) {
  currentItem = item;
  els.draftPanel.hidden = false;
  els.draftText.value = item.suggestedText || "";
  const who = item.targetName ? " for " + item.targetName : "";
  const status =
    item.status === "approved"
      ? "Already approved — tap Approve & Post to submit on LinkedIn."
      : "Review the draft" + who + ", then Approve & Post.";
  els.draftMeta.textContent = status;
}

async function refresh() {
  const { serverUrl, token } = await ext.storage.local.get(["serverUrl", "token"]);
  if (normalizeApprovedServerUrl(serverUrl) && token) {
    show("ready");
  } else {
    if (serverUrl && !normalizeApprovedServerUrl(serverUrl)) {
      await ext.storage.local.remove(["serverUrl", "token"]);
    }
    show("setup");
  }
}

els.save.addEventListener("click", async () => {
  const token = (els.token.value || "").trim();
  if (!token) {
    setResult("Paste the pairing code from the Scout tab.", "err");
    return;
  }
  await ext.storage.local.set({ serverUrl: APPROVED_SERVER_URL, token });
  els.token.value = "";
  setResult("Paired. Open a LinkedIn post and draft a comment.", "ok");
  show("ready");
});

els.draft.addEventListener("click", async () => {
  setResult("Reading this post and drafting a comment…", "");
  setBusy(true);
  try {
    const res = await ext.runtime.sendMessage({ type: "draftOne" });
    if (!res || !res.ok) {
      setResult((res && res.error) || "Something went wrong.", "err");
      return;
    }
    showDraft(res.item);
    setResult(
      res.reused
        ? "Loaded your existing draft for this post."
        : "Draft ready. Edit if you want, then Approve & Post.",
      "ok"
    );
  } catch (e) {
    setResult("Could not reach the extension. Try again.", "err");
  } finally {
    setBusy(false);
  }
});

els.approvePost.addEventListener("click", async () => {
  if (!currentItem) {
    setResult("Draft a comment for this post first.", "err");
    return;
  }
  const text = (els.draftText.value || "").trim();
  if (!text) {
    setResult("Add some comment text before posting.", "err");
    return;
  }
  setResult("Approving and posting on LinkedIn…", "");
  setBusy(true);
  try {
    const res = await ext.runtime.sendMessage({
      type: "approveAndPost",
      item: currentItem,
      suggestedText: els.draftText.value,
    });
    if (!res || !res.ok) {
      setResult((res && res.error) || "Could not post.", "err");
      if (res && res.filled) {
        els.draftMeta.textContent = "Text is in the LinkedIn box — click Post there if needed.";
      }
      return;
    }
    setResult(
      res.warn || "Posted. Comment submitted on LinkedIn.",
      res.warn ? "" : "ok"
    );
    currentItem = res.item || null;
    if (currentItem && currentItem.status === "sent") {
      els.draftPanel.hidden = true;
      currentItem = null;
    }
  } catch (e) {
    setResult("Could not reach the extension. Try again.", "err");
  } finally {
    setBusy(false);
  }
});

els.postApproved.addEventListener("click", async () => {
  setResult("Looking for an approved comment to post…", "");
  setBusy(true);
  try {
    const res = await ext.runtime.sendMessage({ type: "postApproved" });
    if (!res || !res.ok) {
      setResult((res && res.error) || "Nothing to post.", "err");
      return;
    }
    setResult(res.warn || "Posted the approved comment on LinkedIn.", res.warn ? "" : "ok");
  } catch (e) {
    setResult("Could not reach the extension. Try again.", "err");
  } finally {
    setBusy(false);
  }
});

els.capture.addEventListener("click", async () => {
  setResult("Reading the posts on screen…", "");
  setBusy(true);
  try {
    const res = await ext.runtime.sendMessage({ type: "capture" });
    if (!res || !res.ok) {
      setResult((res && res.error) || "Something went wrong.", "err");
    } else if (res.empty) {
      setResult("No posts were visible. Scroll to some posts and try again.", "err");
    } else {
      setResult(
        "Saved " +
          res.accepted +
          " new post(s). " +
          (res.duplicates ? res.duplicates + " already saved. " : "") +
          (res.invalid ? res.invalid + " skipped. " : "") +
          "Use Draft comments now in Scout, or draft one post at a time here.",
        "ok"
      );
    }
  } catch (e) {
    setResult("Could not reach the extension. Try again.", "err");
  } finally {
    setBusy(false);
  }
});

els.repair.addEventListener("click", async () => {
  await ext.storage.local.remove(["token"]);
  currentItem = null;
  els.draftPanel.hidden = true;
  setResult("Pairing cleared. Enter a fresh code.", "");
  show("setup");
});

refresh();
