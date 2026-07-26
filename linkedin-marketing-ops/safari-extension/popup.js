/*
 * Mobi LinkedIn Scout — popup UI.
 *
 * Handles one-time setup (app URL + pairing code, stored in browser.storage.local)
 * and the owner-triggered Capture action. The pairing token is written to local
 * storage once and is never displayed back or logged here; the actual upload and
 * token use happen in the background service worker.
 */
import { APPROVED_SERVER_URL, normalizeApprovedServerUrl } from "./server-url.mjs";

const ext = typeof browser !== "undefined" ? browser : chrome;

const els = {
  setup: document.getElementById("setup"),
  ready: document.getElementById("ready"),
  token: document.getElementById("token"),
  save: document.getElementById("save"),
  capture: document.getElementById("capture"),
  repair: document.getElementById("repair"),
  result: document.getElementById("result"),
};

function show(view) {
  els.setup.hidden = view !== "setup";
  els.ready.hidden = view !== "ready";
}

function setResult(text, kind) {
  els.result.textContent = text;
  els.result.className = "result" + (kind ? " " + kind : "");
}

async function refresh() {
  const { serverUrl, token } = await ext.storage.local.get(["serverUrl", "token"]);
  if (normalizeApprovedServerUrl(serverUrl) && token) {
    show("ready");
  } else {
    // Remove any stale or tampered destination before asking for a fresh code.
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
  setResult("Paired. You can capture posts now.", "ok");
  show("ready");
});

els.capture.addEventListener("click", async () => {
  setResult("Reading the posts on screen…", "");
  els.capture.disabled = true;
  try {
    const res = await ext.runtime.sendMessage({ type: "capture" });
    if (!res || !res.ok) {
      setResult((res && res.error) || "Something went wrong.", "err");
    } else if (res.empty) {
      setResult("No posts were visible. Scroll to some posts and try again.", "err");
    } else {
      setResult(
        "Saved " + res.accepted + " new post(s). " +
          (res.duplicates ? res.duplicates + " already saved. " : "") +
          (res.invalid ? res.invalid + " skipped. " : ""),
        "ok"
      );
    }
  } catch (e) {
    setResult("Could not reach the extension. Try again.", "err");
  } finally {
    els.capture.disabled = false;
  }
});

els.repair.addEventListener("click", async () => {
  await ext.storage.local.remove(["token"]);
  setResult("Pairing cleared. Enter a fresh code.", "");
  show("setup");
});

refresh();
