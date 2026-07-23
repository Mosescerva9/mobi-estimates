# Phase 1 Audit — Togal-Faithful Homepage Rebuild

**Branch:** `redesign/togal-faithful-rebuild` · **Date:** 2026-07-22
**Scope:** measured audit + visual-target definition only. **No** homepage code was
restyled in this phase. Companion spec: [`docs/togal-visual-spec.md`](../../docs/togal-visual-spec.md).

Two surfaces exist in this repo:
- **`marketing-site/`** — the public homepage (`mobiestimates.com`), a Python-generated
  static site (`build.py`/`generate.py` + `config.py`). **This is the redesign target.**
- **`src/app/`** — the Next.js **portal** (`portal.mobiestimates.com`): auth, Stripe,
  estimate intake, admin. **Functionality to preserve; not restyled in this project.**

---

## 1. Why the current redesign failed (diagnosis)

The current homepage (shipped in commit `1e294af "complete premium marketing redesign"`)
is not a faithful Togal recreation. Objective, measured problems:

1. **Page is ~4× too long / far too sparse.** Measured full-page height at 1440px:
   **Mobi 16,813px vs Togal 4,318px (+290%)**; mobile 390px: Mobi capped at 22,000px vs
   Togal 5,697px. The desktop side-by-side (`comparison/compare-1440x1000.png`) shows
   Togal's *entire* page fitting where only Mobi's top **quarter** fits — Mobi is ~20
   sections of thin content floating in large whitespace. Togal is a short, dense page.
2. **Horizontal overflow on mobile.** At a 390px viewport Mobi's content width measures
   **414px** (Togal: 390px) — a real overflow/layout defect. Spec forbids horizontal
   overflow.
3. **Button system is wrong.** Mobi buttons are **pills** (`border-radius:999px`) with a
   colored **box-shadow** and oversized padding (`btn-lg 17×30`). Togal buttons are
   **6px** rectangles, **no shadow**, `12×24`, 16px/500. This is the single most visible
   mismatch.
4. **Hero composition diverges.** Mobi hero = a dark navy section stacked with **blur
   "glow" blobs, a blueprint overlay, an italic "serif accent," and a framed estimate
   image below the text**. Togal hero = clean photo-under-dark-overlay, white left-aligned
   text, and a **16:9 video in the right column**. Mobi's decorative effects are
   explicitly on the spec's prohibited list.
5. **Wrong global background model.** Togal's page is **white** with 1 dark accent band;
   Mobi leans on multiple `band-dark`/navy sections, making the page feel heavy and
   un-Togal.
6. **Header heavier than reference.** Mobi header is **76px** with a left-clustered nav +
   Services **mega-menu**; Togal is a ~60px white bar with a **centered flat** nav +
   Login + one CTA.
7. **No centralized geometry discipline.** Dozens of inline `style="…"` literals and
   ad-hoc `clamp()`s are scattered across `index.html`; radii/spacing are not tokenized
   to a Togal-derived system.

Root cause: the redesign was *inspired-by* styling layered onto a long marketing page,
rather than a **measurement-driven** reconstruction of Togal's compact proportions,
flat 6px components, white canvas, and in-hero video.

---

## 2. Retain / Remove / Rebuild / Simplify / Replace matrix

| Element | Verdict | Rationale |
|---|---|---|
| **All backend/portal functionality** (routes, auth, Stripe, intake, leads, SEO, sitemap, robots, blog, redirects) | **Retain (untouched)** | See §4 preservation contract |
| Poppins font + Google Fonts load | **Retain** | Exact match to Togal, already licensed (OFL) |
| Mobi navy/blue brand palette, logos | **Retain** | Brand identity; replaces Togal green |
| `config.py` single-source content model (pricing, CTAs, video field) | **Retain / extend** | Good architecture; add design tokens here |
| Explainer video **placeholder** component + one-field swap | **Retain, re-skin** | Keep swap mechanism; adopt 16:9 / 16px-radius, move to hero-right on desktop |
| `bid-estimate.png`, owned imagery | **Retain, relocate** | Move framed doc into a product/deliverables section |
| Header (76px, left nav, mega-menu, pill CTA) | **Rebuild** | → ~60px, centered flat nav, 6px CTA (§3 spec) |
| Hero (glows/blueprint/serif/stacked doc) | **Rebuild** | → photo+overlay, white left text, video right (§4 spec) |
| Button system (pills + shadow) | **Rebuild** | → 6px, no shadow, 12×24, full-width mobile (§6 spec) |
| Global background (multiple dark bands) | **Simplify** | → white page + 1 dark accent band |
| ~20-section body | **Simplify / remove padding sections** | Collapse to Togal's ~8-block rhythm (§7 spec); remove filler |
| Customer-logo strip / testimonials | **Replace with hidden-until-real** | No fake proof; build correct structure, hide |
| Blur glows, blueprint overlays, gradient text, italic accents | **Remove** | On prohibited list; absent from Togal |
| Inline `style` literals / scattered radii | **Replace with tokens** | Centralize per §2 of spec |
| Footer (dark navy 4-col) | **Rebuild** | → Togal-style light multi-column footer |

---

## 3. Captured artifact inventory

All under `review-artifacts/togal-faithful-rebuild/`. Screenshots captured at device
scale (Retina) so pixel dimensions = viewport × DPR. Cookie/marketing overlays were
hidden locally in the DOM before capture (verified: 1,071 overlay nodes suppressed on
Togal; screenshots are unobstructed). **File existence & dimensions confirmed.**

### reference/ — Togal.ai (7 files)
| File | Pixels (w×h) | Size |
|---|---|---|
| togal-390x844.png | 1170×17091 | 2.3 MB |
| togal-430x932.png | 1290×16572 | 2.3 MB |
| togal-768x1024.png | 1536×11186 | 2.3 MB |
| togal-834x1194.png | 1668×10948 | 2.5 MB |
| togal-1024x1366.png | 2048×9382 | 2.7 MB |
| togal-1440x1000.png | 1440×4318 | 1.2 MB |
| togal-1920x1080.png | 1920×4318 | 1.3 MB |

### baseline/ — Mobi production `mobiestimates.com` (7 files)
| File | Pixels (w×h) | Size |
|---|---|---|
| mobi-390x844.png | 1242×66000 | 11 MB |
| mobi-430x932.png | 1290×64878 | 12 MB |
| mobi-768x1024.png | 1536×31282 | 7.6 MB |
| mobi-834x1194.png | 1668×31278 | 8.0 MB |
| mobi-1024x1366.png | 2048×29892 | 9.1 MB |
| mobi-1440x1000.png | 1440×16813 | 4.0 MB |
| mobi-1920x1080.png | 1920×16813 | 4.7 MB |

*(Note the height blow-up and the 390→414 CSS-px overflow, both diagnostic.)*

### comparison/ — side-by-side reference vs baseline (7 files)
`compare-<viewport>.png` (1064×4234 each), reference left / baseline right, generated by
`scripts/visual-review/compare.py`.

### measurements/
- `togal.json` — live `getComputedStyle`/geometry at 390 / 768 / 1440.
- `mobi.json` — same probe on production baseline.

### tooling (new, dependency-free)
- `scripts/visual-review/cdp.mjs` — minimal CDP client over Node 22 global `WebSocket`.
- `scripts/visual-review/capture.mjs` — multi-viewport full-page capture + measurement.
- `scripts/visual-review/compare.py` — side-by-side sheet builder (Pillow).

All three pass syntax checks (`node --check`, `py_compile`).

---

## 4. Functional preservation contract (must survive the rebuild)

The rebuild touches **only** `marketing-site/` presentation. These must remain intact
and are to be re-verified after Phase 2:

**Marketing site (static):**
- Routes/pages: `index, services, pricing, sample-estimate, how-it-works, about, faq,
  contact, quantity-takeoffs, construction-cost-estimating, general-contractor-estimating,
  subcontractor-estimating, overflow-estimating, multi-trade-estimating,
  construction-estimating-services, commercial/residential/civil/multifamily-estimating,
  monthly-estimating-support, upload-plans, request-a-quote, capacity-plan, industries,
  privacy, terms, disclaimer` + `blog/`.
- **SEO:** `<title>`, meta description, `robots`, `link rel=canonical`
  (`https://mobiestimates.com/`), OpenGraph, Twitter card, **JSON-LD `ProfessionalService`**.
- **`sitemap.xml`** (canonical URLs) and **`robots.txt`** (+ Sitemap directive).
- **Lead form** → `POST https://portal.mobiestimates.com/api/leads` (endpoint injected via
  `window.MOBI.leadEndpoint`; honeypot `company_website`; CORS allows
  `mobiestimates.com`/`www`). Keep the form markup + `data-lead-form`/`data-lead-status`.
- **Primary CTA target:** `https://portal.mobiestimates.com/signup?offer=first_estimate_free`
  (from `INTRO_OFFER_URL`). Confirmed as the site-wide dominant CTA.
- **Pricing CTAs:** `pricing.html` → `/start?plan={pay_per_project|starter|growth|estimating_department}`.
- **Analytics hooks:** `data-analytics="…"` attributes on every CTA (nav/hero/drawer/
  offer/footer/mobile-bar). `ANALYTICS_ID` currently blank (no GA tag emitted) — preserve
  the hook attributes so a future tag works.
- Contact email `estimates@mobiestimates.com`; footer legal links.

**Portal (Next.js — not restyled here, but the marketing site hands off to it):**
- `/signup`, `/login`, `/reset`, `/start` (server-validated Stripe handoff),
  `/checkout/complete`, `/billing`, `/portal/*`, `/admin/*`, `/onboarding`.
- API: `/api/stripe/{checkout,portal,webhook}`, `/api/leads`, `/api/projects`,
  `/api/projects/[id]/estimate-job-sync`, `/auth/signout`.
- `src/middleware.ts` auth gate on `/portal|/onboarding|/admin|/billing`.
- Existing guard tests (`npm run test:*`, e.g. `test:marketing-launch`,
  `test:lead-capture`, `test:product-truth-posture`, `test:intro-offer-*`) must stay green.

**Offer semantics (must not drift):** "one qualifying estimate free per new company, no
card"; **no promised turnaround time**; human-reviewed; no guaranteed bid wins. Copy
changes in Phase 2 must keep these truthful (guarded by `test:product-truth-posture` /
`test:unsupported-evidence-guard`).

---

## 5. Measurement evidence (headline numbers)

| Metric | Togal | Mobi (current) | Action |
|---|---|---|---|
| Font family | Poppins, sans-serif | Poppins (already) | ✅ keep |
| Hero headline | 48px→60px / 700 / lh 1.1 | `clamp(2.3rem,5.2vw,4rem)` ≈ 37→64px / 700 | align to 48/60 |
| Hero paragraph | 20px / lh 28 / 400 white | `clamp(1.05,1.5vw,1.22rem)` | bump to 20px |
| Eyebrow | 14px / 500 / UPPERCASE | pill chip w/ border+shadow | flatten to text eyebrow |
| Primary button | 6px radius, 12×24, no shadow, h47 | **999px pill**, shadow, 15–17×24–30 | **rebuild** |
| Nav CTA | 6px, 8×16, h37 | pill | rebuild |
| Container | 1344px | 1200px | widen to 1344 |
| Side padding | 48 / 40 / 20 | 22 (all) | breakpoint-specific |
| Video | 16:9, radius 16px, in-hero right | separate section, own radius | re-place + 16px |
| Header height | ~60px | 76px | reduce |
| Footer | light, multi-column | dark navy | rebuild light |
| Page height @1440 | 4,318px | 16,813px | cut ~4× |
| Overflow @390 | none | 414px (overflows) | fix to 0 |

---

## 6. Staged implementation plan (for Fable review & direction)

Each stage ends with a screenshot-comparison loop (capture Mobi → diff vs the matching
`reference/*` shot) before proceeding. Fable reviews the artifacts and may reject.

- **Stage 0 — Safety (done this phase):** branch created; audit + measured spec written;
  reference/baseline/comparison artifacts captured; functional contract recorded.
- **Stage 1 — Tokens & font system:** add the §2 token block to `styles.css :root` (+
  mirror keys into `config.py`); wire the Poppins weight system; remove glow/blueprint/
  gradient/serif utilities. *No visual layout change yet beyond tokens.*
- **Stage 2 — Button system:** rebuild `.btn/.btn-primary/.btn-lg/.nav-cta` to 6px, no
  shadow, 12×24, full-width mobile. Compare header + hero CTAs.
- **Stage 3 — Header:** ~60px white bar, centered flat nav, Login + one brand CTA,
  hamburger ≤992px. Compare vs `*-1440` and `*-390`.
- **Stage 4 — Hero:** photo + navy overlay, white left text (eyebrow/48–60 headline/20px
  paragraph), primary CTA `Get A Free Estimate Trial` + `See How Mobi Works →`, **video in
  right column on desktop**. Compare hero at 390/768/1440.
- **Stage 5 — Video section/component:** 16:9, 16px radius, centered play, one-field swap
  documented; confirm `EXPLAINER_VIDEO_URL` path.
- **Stage 6 — Body sections:** rebuild to Togal's ~8-block rhythm on a white canvas
  (value-prop + capability list, 1 dark accent band, final CTA); **hide** logo strip &
  testimonials until real. Delete filler sections; kill mobile overflow.
- **Stage 7 — Footer:** light multi-column, Mobi links.
- **Stage 8 — Responsive passes:** mobile → tablet → desktop comparison loops against all
  seven `reference/*` shots; enforce §13 tolerances; verify height within ±25% and 0
  overflow.
- **Stage 9 — Functional QA:** re-run marketing/portal guard tests (§4); click-through
  CTAs, lead form, pricing handoff; confirm SEO/sitemap/robots/JSON-LD unchanged.
- **Stage 10 — Fable final visual review** → fix material issues → preview deploy →
  return review package.

---

## 7. Readiness status

**Phase 1 is COMPLETE and ready for Fable planning.** Delivered: measured visual spec,
14 reference+baseline screenshots (7 viewports each), 7 side-by-side comparisons, 2
measurement JSONs, a reusable dependency-free capture/measure/compare toolchain, a
retain/remove/rebuild matrix, and a functional-preservation contract. No production
code, DNS, pricing, integrations, or customer data were modified; nothing was committed,
pushed, deployed, or submitted. **Blockers for Phase 2:** (a) confirm/obtain a
Mobi-owned, non-AI hero photo; (b) real customer logos & testimonials remain unavailable
(sections will be hidden); (c) the explainer video arrives this weekend via
`config.py:EXPLAINER_VIDEO_URL`.
```
