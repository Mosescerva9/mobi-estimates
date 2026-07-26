/*
 * Mobi LinkedIn Scout — deterministic, read-only extraction of the LinkedIn
 * feed posts currently visible on screen.
 *
 * This file is intentionally dependency-free and works in three places from one
 * source of truth:
 *   - injected into the LinkedIn tab by the extension (browser),
 *   - exercised by Node unit tests via module.exports (no jsdom required),
 *   - available as a window global for a two-step scripting.executeScript call.
 *
 * SAFETY: nothing here scrolls, clicks, likes, connects, comments, or observes
 * the page over time. It reads the DOM ONCE, for containers already on screen,
 * after the owner explicitly taps "Capture". No network calls happen here.
 */
(function (root) {
  "use strict";

  var MAX_ITEMS = 25;
  var SOURCE_TEXT_MAX = 4000;
  var AUTHOR_FIELD_MAX = 400;

  // Only these two canonical permalink shapes are accepted, mirroring the
  // server's strict validator. Everything else (login, checkpoint, oauth,
  // redirect, the raw feed, profile-only paths) is rejected.
  var POST_PATH = /^\/posts\/[^/]+$/;
  var FEED_UPDATE_PATH = /^\/feed\/update\/urn:li:(activity|share|ugcpost):\d+$/;

  function isLinkedInHost(hostname) {
    var host = String(hostname || "").toLowerCase();
    return host === "linkedin.com" || host.endsWith(".linkedin.com");
  }

  /**
   * Validate and canonicalize a candidate permalink. Returns a clean
   * https://<host><path> string (query and fragment dropped) or null. Never
   * throws.
   */
  function normalizePostUrl(href) {
    if (typeof href !== "string" || !href.trim()) return null;
    var parsed;
    try {
      parsed = new URL(href, "https://www.linkedin.com");
    } catch (e) {
      return null;
    }
    if (parsed.protocol !== "https:") return null;
    if (parsed.username || parsed.password) return null;
    if (!isLinkedInHost(parsed.hostname)) return null;
    var path = parsed.pathname.replace(/\/+$/, "");
    var lower = path.toLowerCase();
    if (!POST_PATH.test(lower) && !FEED_UPDATE_PATH.test(lower)) return null;
    // Canonical, tracking-free permalink.
    return "https://" + parsed.hostname.toLowerCase() + path;
  }

  /** Stable dedupe key (host + path), matching the server's linkedInPostKey. */
  function postKey(url) {
    var norm = normalizePostUrl(url);
    if (!norm) return null;
    return norm.replace(/^https:\/\//, "");
  }

  function cleanText(value, max) {
    if (typeof value !== "string") return "";
    var collapsed = value.replace(/\s+/g, " ").trim();
    return collapsed.slice(0, max || SOURCE_TEXT_MAX);
  }

  /**
   * Turn raw extracted records into validated, de-duplicated, capped candidates.
   * Pure: no DOM, no network. A record is {postUrl, sourceText, authorName?,
   * authorHeadline?, authorCompany?}.
   */
  function buildCandidates(records, max) {
    var cap = typeof max === "number" ? max : MAX_ITEMS;
    var out = [];
    var seen = {};
    for (var i = 0; i < records.length; i++) {
      if (out.length >= cap) break;
      var rec = records[i] || {};
      var url = normalizePostUrl(rec.postUrl);
      if (!url) continue;
      var key = postKey(url);
      if (!key || seen[key]) continue;
      var text = cleanText(rec.sourceText, SOURCE_TEXT_MAX);
      if (text.length < 8) continue; // too little to ground a recommendation
      seen[key] = true;
      var candidate = { postUrl: url, sourceText: text };
      var name = cleanText(rec.authorName, AUTHOR_FIELD_MAX);
      var headline = cleanText(rec.authorHeadline, AUTHOR_FIELD_MAX);
      var company = cleanText(rec.authorCompany, AUTHOR_FIELD_MAX);
      if (name) candidate.authorName = name;
      if (headline) candidate.authorHeadline = headline;
      if (company) candidate.authorCompany = company;
      out.push(candidate);
    }
    return out;
  }

  /* ------------------------------------------------------------- DOM layer */

  // Conservative selector fallbacks for mobile + desktop LinkedIn. We only ever
  // read TOP-LEVEL feed post containers; comment threads and DM/message views
  // are excluded by path check and by not descending into reply lists.
  var CONTAINER_SELECTORS = [
    "div.feed-shared-update-v2",
    "div[data-urn^='urn:li:activity']",
    "div[data-id^='urn:li:activity']",
    "article.feed-shared-update-v2",
  ];

  var PERMALINK_SELECTORS = [
    "a[href*='/feed/update/urn:li:']",
    "a[href*='/posts/']",
  ];

  var TEXT_SELECTORS = [
    ".feed-shared-update-v2__description",
    ".update-components-text",
    ".feed-shared-text",
    ".break-words",
  ];

  var AUTHOR_NAME_SELECTORS = [
    ".update-components-actor__title span[aria-hidden='true']",
    ".update-components-actor__name",
    ".update-components-actor__title",
  ];

  var AUTHOR_DESC_SELECTORS = [
    ".update-components-actor__description",
    ".update-components-actor__subtitle",
  ];

  function firstText(node, selectors) {
    for (var i = 0; i < selectors.length; i++) {
      var el = node.querySelector(selectors[i]);
      if (el && el.textContent && el.textContent.trim()) return el.textContent;
    }
    return "";
  }

  function firstElement(node, selectors) {
    for (var i = 0; i < selectors.length; i++) {
      var el = node.querySelector(selectors[i]);
      if (el) return el;
    }
    return null;
  }

  function firstHref(node, selectors) {
    for (var i = 0; i < selectors.length; i++) {
      var el = node.querySelector(selectors[i]);
      if (el) {
        var href = el.getAttribute ? el.getAttribute("href") : el.href;
        if (href) return href;
      }
    }
    return "";
  }

  function isMainFeed(doc) {
    try {
      var path = (doc.location && doc.location.pathname) || "";
      return path === "/feed" || path === "/feed/";
    } catch (e) {
      return false;
    }
  }

  // Best-effort visibility: only containers with a box intersecting the current
  // viewport are captured. When getBoundingClientRect/innerHeight are absent
  // (e.g. in unit tests) we treat the node as visible so pure logic is testable.
  function isVisible(node, win) {
    if (!node.getBoundingClientRect || !win || typeof win.innerHeight !== "number") {
      return true;
    }
    var rect = node.getBoundingClientRect();
    if (!rect) return true;
    var vh = win.innerHeight;
    var vw = win.innerWidth || 10000;
    if (rect.width === 0 && rect.height === 0) return false;
    return rect.bottom > 0 && rect.top < vh && rect.right > 0 && rect.left < vw;
  }

  function selectContainers(doc) {
    for (var i = 0; i < CONTAINER_SELECTORS.length; i++) {
      var nodes = doc.querySelectorAll(CONTAINER_SELECTORS[i]);
      if (nodes && nodes.length) return Array.prototype.slice.call(nodes);
    }
    return [];
  }

  /**
   * Read the visible feed once and return validated candidates. DOM-dependent
   * but tolerant: takes an optional window for the visibility check so tests can
   * pass a minimal fake document with no window.
   */
  function extractVisiblePosts(doc, win) {
    if (!doc || !isMainFeed(doc)) return [];
    var containers = selectContainers(doc);
    var records = [];
    for (var i = 0; i < containers.length; i++) {
      var node = containers[i];
      if (!isVisible(node, win)) continue;
      var permalink = firstElement(node, PERMALINK_SELECTORS);
      var textElement = firstElement(node, TEXT_SELECTORS);
      // A visible wrapper is not enough: both the permalink and post text must
      // themselves intersect the viewport, preventing off-screen descendants
      // from being captured through a large feed wrapper.
      if (!permalink || !textElement) continue;
      if (!isVisible(permalink, win) || !isVisible(textElement, win)) continue;
      var href = permalink.getAttribute ? permalink.getAttribute("href") : permalink.href;
      var url = normalizePostUrl(href);
      if (!url) continue;
      records.push({
        postUrl: url,
        sourceText: textElement.textContent || "",
        authorName: firstText(node, AUTHOR_NAME_SELECTORS),
        authorHeadline: firstText(node, AUTHOR_DESC_SELECTORS),
        authorCompany: "",
      });
    }
    return buildCandidates(records, MAX_ITEMS);
  }

  var api = {
    MAX_ITEMS: MAX_ITEMS,
    SOURCE_TEXT_MAX: SOURCE_TEXT_MAX,
    normalizePostUrl: normalizePostUrl,
    postKey: postKey,
    cleanText: cleanText,
    buildCandidates: buildCandidates,
    extractVisiblePosts: extractVisiblePosts,
  };

  // Browser: expose a namespaced global so the injected runner can call it.
  root.MobiScout = api;
  // Node: export for unit tests.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof self !== "undefined" ? self : this);
