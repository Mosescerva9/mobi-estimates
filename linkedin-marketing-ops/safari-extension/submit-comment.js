/*
 * Owner-triggered LinkedIn comment submitter.
 *
 * Injected only after the owner taps Approve & Post in the extension popup.
 * Fills the on-page comment composer and clicks LinkedIn's Post button.
 * Never reads cookies/passwords and never calls the Mobi API.
 */
(function (root) {
  "use strict";

  var COMPOSER_SELECTORS = [
    ".comments-comment-box__form div.ql-editor[contenteditable='true']",
    ".comments-comment-box div.ql-editor[contenteditable='true']",
    ".comment-box div.ql-editor[contenteditable='true']",
    "form.comments-comment-box__form div[contenteditable='true']",
    "div.ql-editor[contenteditable='true'][data-placeholder]",
    "div[role='textbox'][contenteditable='true']",
  ];

  var OPEN_COMMENT_SELECTORS = [
    "button.comment-button",
    "button[aria-label*='Comment' i]",
    "button[aria-label*='comment' i]",
  ];

  var SUBMIT_SELECTORS = [
    "button.comments-comment-box__submit-button--cr",
    "button.comments-comment-box__submit-button",
    ".comments-comment-box button.artdeco-button--primary",
    "form.comments-comment-box__form button[type='submit']",
  ];

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function first(rootNode, selectors) {
    for (var i = 0; i < selectors.length; i++) {
      try {
        var el = rootNode.querySelector(selectors[i]);
        if (el) return el;
      } catch (e) {
        // Invalid selector in older engines — skip.
      }
    }
    return null;
  }

  function visible(el) {
    if (!el || !el.getBoundingClientRect) return !!el;
    var rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function findComposer(doc) {
    for (var i = 0; i < COMPOSER_SELECTORS.length; i++) {
      var nodes;
      try {
        nodes = doc.querySelectorAll(COMPOSER_SELECTORS[i]);
      } catch (e) {
        continue;
      }
      for (var j = 0; j < nodes.length; j++) {
        if (visible(nodes[j])) return nodes[j];
      }
    }
    return null;
  }

  function findSubmitNear(composer) {
    var form = composer.closest ? composer.closest("form") : null;
    var scope = form || (composer.closest && composer.closest(".comments-comment-box")) || document;
    var btn = first(scope, SUBMIT_SELECTORS);
    if (btn && visible(btn)) return btn;
    // Fallback: any enabled primary button labeled Post / Comment inside the box.
    var buttons = scope.querySelectorAll("button");
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      if (!visible(b) || b.disabled) continue;
      var label = ((b.innerText || b.textContent || "") + " " + (b.getAttribute("aria-label") || ""))
        .trim()
        .toLowerCase();
      if (label === "post" || label.indexOf("post") === 0 || label === "comment") {
        return b;
      }
    }
    return null;
  }

  function setComposerText(editor, text) {
    editor.focus();
    // Prefer execCommand for LinkedIn's Quill-like editors.
    try {
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, text);
    } catch (e) {
      // fall through
    }
    if (!(editor.textContent || "").trim()) {
      editor.textContent = text;
      editor.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
    } else {
      editor.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
    }
    editor.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function openComposerIfNeeded(doc) {
    var existing = findComposer(doc);
    if (existing) return existing;

    var openBtn = first(doc, OPEN_COMMENT_SELECTORS);
    if (openBtn && visible(openBtn)) {
      openBtn.click();
      await sleep(450);
    }
    return findComposer(doc);
  }

  /**
   * Fill the visible comment box and click Post.
   * Returns { ok: true } or { ok: false, error: string }.
   */
  async function submitComment(text) {
    if (typeof text !== "string" || !text.trim()) {
      return { ok: false, error: "Comment text is empty." };
    }
    var doc = document;
    var editor = await openComposerIfNeeded(doc);
    if (!editor) {
      return {
        ok: false,
        error: "Could not find LinkedIn’s comment box. Click Comment on the post, then try again.",
      };
    }

    setComposerText(editor, text);
    await sleep(200);

    var written = (editor.innerText || editor.textContent || "").replace(/\s+/g, " ").trim();
    if (!written) {
      return {
        ok: false,
        error: "LinkedIn did not accept the comment text into the box. Try clicking Comment first.",
      };
    }

    var submit = findSubmitNear(editor);
    if (!submit) {
      return {
        ok: false,
        error: "Could not find LinkedIn’s Post button. The text is in the box — click Post yourself.",
        filled: true,
      };
    }
    if (submit.disabled) {
      // Some UIs enable the button a tick after input.
      await sleep(300);
    }
    submit.click();
    return { ok: true, filled: true, submitted: true };
  }

  var api = { submitComment: submitComment, findComposer: findComposer };
  root.MobiScoutSubmit = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof self !== "undefined" ? self : this);
