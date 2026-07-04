/* Mobi Estimates — site interactions
   Lightweight, dependency-free, accessible, reduced-motion aware. */
(function () {
  "use strict";
  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var CFG = window.MOBI || {};

  document.addEventListener("DOMContentLoaded", function () {
    initHeaderScroll();
    initMobileNav();
    initReveal();
    initFaq();
    initForms();
    initDropzones();
    initPlanPreselect();
    initMobileBar();
    initAnalytics();
    initYear();
  });

  /* ---- analytics (no-op unless gtag/dataLayer present) ---- */
  function track(name, params) {
    if (!name) return;
    if (typeof window.gtag === "function") window.gtag("event", name, params || {});
    else if (window.dataLayer) window.dataLayer.push(Object.assign({ event: name }, params || {}));
  }
  function initAnalytics() {
    document.addEventListener("click", function (e) {
      var el = e.target.closest("[data-analytics]");
      if (el) track(el.getAttribute("data-analytics"));
    });
  }

  /* ---- header shadow on scroll ---- */
  function initHeaderScroll() {
    var header = document.querySelector(".site-header");
    if (!header) return;
    var onScroll = function () {
      header.classList.toggle("scrolled", window.scrollY > 12);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ---- mobile drawer ---- */
  function initMobileNav() {
    var toggle = document.querySelector(".nav-toggle");
    var drawer = document.querySelector(".mobile-drawer");
    if (!toggle || !drawer) return;
    var scrim = drawer.querySelector(".scrim");
    var closeBtn = drawer.querySelector(".nav-close");
    var open = function () {
      drawer.classList.add("open");
      toggle.setAttribute("aria-expanded", "true");
      document.body.style.overflow = "hidden";
      var first = drawer.querySelector(".m-link, .nav-close");
      if (first) first.focus();
    };
    var close = function () {
      drawer.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
      document.body.style.overflow = "";
    };
    toggle.addEventListener("click", open);
    if (scrim) scrim.addEventListener("click", close);
    if (closeBtn) closeBtn.addEventListener("click", close);
    drawer.querySelectorAll(".m-link, .btn").forEach(function (l) {
      l.addEventListener("click", close);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && drawer.classList.contains("open")) close();
    });
  }

  /* ---- scroll reveal ---- */
  function initReveal() {
    var els = document.querySelectorAll(".reveal, .reveal-left, .reveal-scale");
    if (!els.length) return;
    if (prefersReduced || !("IntersectionObserver" in window)) {
      els.forEach(function (el) { el.classList.add("in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var el = entry.target;
          var delay = el.getAttribute("data-delay");
          if (delay) el.style.transitionDelay = delay + "ms";
          el.classList.add("in");
          io.unobserve(el);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---- FAQ accordion ---- */
  function initFaq() {
    document.querySelectorAll(".faq-item").forEach(function (item) {
      var q = item.querySelector(".faq-q");
      var a = item.querySelector(".faq-a");
      if (!q || !a) return;
      q.addEventListener("click", function () {
        var isOpen = item.classList.toggle("open");
        a.style.maxHeight = isOpen ? a.scrollHeight + "px" : null;
        q.setAttribute("aria-expanded", isOpen ? "true" : "false");
      });
    });
  }

  /* ---- forms: validation, multi-step, submit (endpoint or demo) ---- */
  function validateScope(scope) {
    var valid = true, firstBad = null;
    scope.querySelectorAll("[required]").forEach(function (input) {
      if (input.offsetParent === null && input.type !== "hidden" && !scope.contains(document.activeElement)) {
        // skip validation of fields in hidden steps handled separately
      }
      var ok = input.value && input.value.trim() !== "";
      if (input.type === "email") ok = ok && /.+@.+\..+/.test(input.value);
      var field = input.closest(".field");
      if (field) field.classList.toggle("field-error", !ok);
      if (!ok) { valid = false; if (!firstBad) firstBad = input; }
    });
    if (firstBad) firstBad.focus();
    return valid;
  }

  function showSuccess(form) {
    var success = form.parentElement.querySelector(".form-success");
    if (success) {
      form.style.display = "none";
      success.classList.add("show");
      success.scrollIntoView({ behavior: prefersReduced ? "auto" : "smooth", block: "center" });
    }
  }

  function submitForm(form) {
    if (form.dataset.submitting === "1") return;       // duplicate-submission guard
    if (!validateScope(form)) return;
    form.dataset.submitting = "1";
    var btn = form.querySelector("[type=submit]") || form.querySelector("[data-submit]");
    var label = btn ? btn.innerHTML : "";
    if (btn) {
      btn.classList.add("is-loading");
      btn.setAttribute("aria-busy", "true");
      if (btn.tagName === "BUTTON") btn.disabled = true;
      btn.innerHTML = "Sending…";
    }
    var restore = function () {
      form.dataset.submitting = "";
      if (btn) {
        btn.classList.remove("is-loading");
        btn.removeAttribute("aria-busy");
        if (btn.tagName === "BUTTON") btn.disabled = false;
        btn.innerHTML = label;
      }
    };
    var done = function () {
      track("form_submit", { form: form.getAttribute("data-analytics-form") || form.id });
      showSuccess(form);
    };
    if (CFG.endpoint) {
      fetch(CFG.endpoint, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" } })
        .then(function (r) { if (r.ok) done(); else throw new Error("bad status"); })
        .catch(function () {
          restore();
          alert("Sorry — something went wrong sending your request." + (CFG.email ? " Please email " + CFG.email + "." : ""));
        });
    } else {
      // No backend configured: front-end demo. Shows success without a fake network call.
      setTimeout(done, 700);
    }
  }

  function initForms() {
    document.querySelectorAll("form[data-form]").forEach(function (form) {
      var multistep = form.hasAttribute("data-multistep");
      if (multistep) setupSteps(form);

      form.addEventListener("submit", function (e) {
        e.preventDefault();
        if (multistep) {
          var steps = form.querySelectorAll(".form-step");
          var idx = Number(form.dataset.step || 0);
          if (idx < steps.length - 1) { advance(form, 1); return; }
        }
        submitForm(form);
      });

      // CTA anchors styled as buttons (data-submit) trigger submit
      form.querySelectorAll("[data-submit]").forEach(function (el) {
        if (el.tagName === "A") el.addEventListener("click", function (e) { e.preventDefault(); submitForm(form); });
      });

      // live error clearing + form-start tracking
      var started = false;
      form.querySelectorAll("input, select, textarea").forEach(function (input) {
        input.addEventListener("input", function () {
          var field = input.closest(".field");
          if (field && input.value && input.value.trim()) field.classList.remove("field-error");
          if (!started) { started = true; track("form_start", { form: form.getAttribute("data-analytics-form") || form.id }); }
        });
      });
    });
  }

  function setupSteps(form) {
    var steps = form.querySelectorAll(".form-step");
    form.dataset.step = "0";
    form.querySelectorAll("[data-next]").forEach(function (b) {
      b.addEventListener("click", function () {
        var idx = Number(form.dataset.step || 0);
        if (validateScope(steps[idx])) advance(form, 1);
      });
    });
    form.querySelectorAll("[data-back]").forEach(function (b) {
      b.addEventListener("click", function () { advance(form, -1); });
    });
    paint(form, 0);
  }

  function advance(form, dir) {
    var steps = form.querySelectorAll(".form-step");
    var idx = Number(form.dataset.step || 0);
    var next = Math.min(Math.max(idx + dir, 0), steps.length - 1);
    if (next === idx) return;
    form.dataset.step = String(next);
    paint(form, next);
    if (dir > 0) track("form_step_complete", { form: form.getAttribute("data-analytics-form") || form.id, step: idx + 1 });
    var f = steps[next].querySelector("input, select, textarea");
    if (f) f.focus();
  }

  function paint(form, idx) {
    var steps = form.querySelectorAll(".form-step");
    steps.forEach(function (s, n) { s.hidden = n !== idx; });
    var fill = form.querySelector(".fp-fill");
    var cur = form.querySelector(".fp-current");
    if (fill) fill.style.width = ((idx + 1) / steps.length * 100) + "%";
    if (cur) cur.textContent = String(idx + 1);
  }

  /* ---- file dropzone ---- */
  function initDropzones() {
    document.querySelectorAll(".dropzone").forEach(function (zone) {
      var input = zone.querySelector("input[type=file]");
      var label = zone.querySelector(".dz-label");
      if (input) {
        zone.addEventListener("click", function () { input.click(); });
        input.addEventListener("change", function () {
          if (input.files.length && label) {
            label.textContent = input.files.length === 1 ? input.files[0].name : input.files.length + " files selected";
            track("file_upload", { count: input.files.length });
          }
        });
      }
      ["dragover", "dragenter"].forEach(function (ev) {
        zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add("drag"); });
      });
      ["dragleave", "drop"].forEach(function (ev) {
        zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove("drag"); });
      });
      zone.addEventListener("drop", function (e) {
        if (input && e.dataTransfer && e.dataTransfer.files.length && label) {
          input.files = e.dataTransfer.files;
          label.textContent = e.dataTransfer.files.length + " file(s) ready";
        }
      });
    });
  }

  /* ---- preselect monthly plan from ?plan= ---- */
  function initPlanPreselect() {
    var sel = document.querySelector('select[name="plan"]');
    if (!sel) return;
    var plan = new URLSearchParams(location.search).get("plan");
    if (!plan) return;
    var map = { starter: "Starter", growth: "Growth", department: "Outsourced", pilot: "Not sure" };
    var needle = map[plan.toLowerCase()];
    if (!needle) return;
    Array.prototype.forEach.call(sel.options, function (o) {
      if (o.text.indexOf(needle) === 0 || o.text.indexOf(needle) > -1) sel.value = o.value || o.text;
    });
  }

  /* ---- mobile conversion bar ---- */
  function initMobileBar() {
    var bar = document.getElementById("mobileCtaBar");
    if (!bar) return;
    if (sessionStorage.getItem("mbar_dismissed") === "1") { bar.style.display = "none"; return; }
    var close = bar.querySelector(".mbar-close");
    if (close) close.addEventListener("click", function () {
      bar.style.display = "none";
      try { sessionStorage.setItem("mbar_dismissed", "1"); } catch (e) {}
    });
  }

  function initYear() {
    var y = document.getElementById("year");
    if (y) y.textContent = new Date().getFullYear();
  }
})();
