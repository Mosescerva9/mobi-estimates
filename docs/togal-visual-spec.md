# Togal-Faithful Visual Specification — Mobi Estimates Homepage

**Phase:** 1 — measured audit & visual target definition (no implementation yet)
**Reference:** `https://www.togal.ai/` (inspected read-only, 2026-07-22)
**Branch:** `redesign/togal-faithful-rebuild`
**Method:** System Chrome 150 driven over the Chrome DevTools Protocol
(`scripts/visual-review/capture.mjs`), full-page screenshots + live `getComputedStyle`
measurements at 390 / 430 / 768 / 834 / 1024 / 1440 / 1920 widths. Raw numbers:
`review-artifacts/togal-faithful-rebuild/measurements/togal.json`.

All values below are **measured**, not guessed. Where a value could not be measured
directly it is flagged in [§12 Uncertainties](#12-uncertainties). Tolerances for
"close enough" are in [§13](#13-acceptance-tolerances).

> Legal note: this spec records *proportions, geometry and the (openly-licensed)
> font family only*. No Togal source, imagery, video, copy, customer logos or
> testimonials are copied. Green `#3AB65A` is recorded only to document that it is
> replaced by Mobi's brand color.

---

## 1. Font — confirmed exact, legally usable

| Question | Finding |
|---|---|
| Togal computed `font-family` | **`Poppins, sans-serif`** on every measured element (eyebrow/h1, headline/h2, paragraph, nav, buttons, footer). Confirmed at all three measured breakpoints. |
| License | **SIL Open Font License 1.1** (Poppins, Indian Type Foundry / Jonny Pinhorn), authoritatively distributed by Google Fonts. OFL permits commercial web use, self-hosting and bundling. |
| Already in Mobi? | **Yes.** `marketing-site/index.html:21` already loads Poppins from Google Fonts (`wght@0,400;500;600;700;800;1,500;600`). No new dependency or license risk. |
| Verdict | **Use Poppins.** It is an exact match to the reference *and* already the site's font. No "closest equivalent" is needed; do **not** substitute Inter. |

**Weight system to standardize (Poppins):** 400 (body/paragraph), 500 (eyebrow, nav
links, buttons), 600 (sub-headings / emphasized inline), 700 (headlines h1/h2), 800
reserved (unused by Togal hero — avoid unless a Mobi sub-brand element needs it).
The current site also declares an *italic* "serif-accent"; Togal uses **no** italic
accent in headlines — drop it (see audit).

**Glyph comparison rationale (why Poppins is correct, not merely modern):** Togal's
headline is geometric-sans, near-monolinear, circular `o`/`e`/`a` bowls, single-story
`a`, tall x-height, near-square proportions, tight tracking at display sizes — these
are Poppins' defining traits. Numerals are lining and monospaced-in-tables friendly.
Button text is 500-weight, not bold. All of this is Poppins as-shipped; no fallback
substitution alters the match.

---

## 2. Global design tokens (recommended, centralized)

Mobi keeps its **navy/blue** brand; only geometry/typography/rhythm mirror Togal.
Author these once (CSS custom properties in `styles.css :root`, mirrored into
`config.py`/Tailwind if the React portal reuses them). **Do not scatter literals.**

```
/* Brand (Mobi — replaces Togal green everywhere) */
--brand:            #2c5c9e;   /* Mobi primary (existing --brand-600) — CTA fill */
--brand-strong:     #244c84;   /* hover (existing --brand-700) */
--ink:              #141414;   /* body text on light — matches Togal rgb(20,20,20) */
--muted:            #51607a;   /* secondary text */
--page-bg:          #ffffff;   /* Togal page bg is white, NOT tinted navy */
--surface:          #ffffff;   /* cards */
--surface-alt:      #f4f6fa;   /* very light gray alt band (Togal uses near-white) */
--band-dark:        #1e2a4a;   /* Mobi navy for the 1–2 dark feature/CTA bands */
--hero-overlay:     rgba(16,26,48,.72); /* dark overlay over hero photo (Mobi navy) */
--line:             #e4e9f0;   /* borders */

/* Radii — Togal measured */
--radius-btn:       6px;       /* buttons (Togal = 6px, NOT pill) */
--radius-card:      12px;      /* cards (Togal card/list ~10–12px) */
--radius-media:     16px;      /* video + hero media (Togal video = 16px) */

/* Layout */
--container:        1344px;    /* Togal dominant content container */
--pad-mobile:       20px;      /* Togal side padding @390 */
--pad-tablet:       40px;      /* Togal side padding @768 */
--pad-desktop:      48px;      /* Togal side padding @1440 */
--section-y:        clamp(64px, 7vw, 96px);  /* per-section vertical padding */

/* Type scale (Poppins) — Togal measured */
--fs-eyebrow:  14px;  --lh-eyebrow: 1.2;  --fw-eyebrow: 500;  /* uppercase */
--fs-h1-m:     48px;  --fs-h1-d:    60px; --lh-h1: 1.1;       --fw-h1: 700;
--fs-h2:       clamp(30px, 3.4vw, 40px);  --lh-h2: 1.15;      --fw-h2: 700;
--fs-body:     20px;  --lh-body:    1.4;  --fw-body: 400;     /* hero/lead */
--fs-body-sm:  16px;  --lh-body-sm: 1.6;                      /* in-card copy */
--fs-btn:      16px;  --fw-btn:     500;
--fs-nav:      15px;  --fw-nav:     500;

/* Effects — Togal is restrained */
--shadow-card: 0 1px 2px rgba(8,20,39,.06), 0 8px 24px -16px rgba(8,20,39,.18);
--transition:  .15s linear;   /* Togal buttons: color/bg 0.15s linear */
```

Togal uses **no** button box-shadow, **no** gradient text, **no** glow blobs, **no**
blueprint overlays, **no** glassmorphism. Tokens above deliberately omit them.

---

## 3. Header / navigation (measured + visual)

| Property | Togal (measured/observed) | Notes |
|---|---|---|
| Background | Solid **white**, full-width bar | not translucent-over-hero |
| Sticky | Yes (fixed at top on scroll) | |
| Height | **~56–64px** | derived from nav Demo button `y=8, h=37` → ~52–64px band; confirm in Phase 2 |
| Side padding | **48px** desktop (Demo button right edge `x+w = 1392`, `1440−1392 = 48`) | tablet 40, mobile 20 |
| Logo | Left, wordmark, ~**28–32px** tall | Mobi logo drops in unchanged; no card/container around it |
| Nav (desktop) | **Centered** links: Features · Trades · Resources · Pricing | ~15px/500, dark ink |
| Right cluster | Text **"Login"** link + solid **CTA button** | |
| Nav CTA button | **78×37px**, padding **8×16**, radius **6px**, 14px/500, solid fill | Mobi: brand fill, label **"Book a Free Estimate"** (wider) |
| Mobile/tablet | Hamburger appears **≤ ~992px**; logo left, CTA/hamburger right | drawer opens |

**Current Mobi delta:** header height is **76px** (`styles.css:142`) → reduce toward
~60px. Logo 34px ok. Current desktop nav is **left-clustered with a Services mega-menu**;
Togal is **centered, flat**. Nav CTA is currently a **pill** (`radius:999px`) → 6px.

---

## 4. Hero (measured)

| Property | @390 mobile | @768 tablet | @1440 desktop |
|---|---|---|---|
| Layout | 1 col (text, then media below) | 1 col (text, then media) | **2 col: text left / media right** |
| Left/side padding | 20px (`x=20`) | 40px (`x=40`) | 48px (`x=48`) |
| Text column width | 350px | 688px | **640px** |
| Eyebrow | 14px/500 **UPPERCASE**, white, `mb 12px` | same | same |
| Headline size / lh / weight | **48px / 52.8px / 700** | **60px / 66px / 700** | **60px / 66px / 700** |
| Headline `margin-bottom` | 24px | 24px | 24px |
| Paragraph | **20px / 28px / 400**, white, `mb 32px` | same | same |
| Primary CTA | **full-width** (350px), h 47 | hug (159px), h 47 | hug (159px), h 47 |
| Media (video) | 350×197 (16:9) | 688×387 (16:9) | **640×360 (16:9)** at `x=752` |
| Media radius | **16px** | 16px | 16px |
| Vertical order | eyebrow → h → p → CTA → media | same | text block left, media right, vertically centered |

Hero background = photo under a **dark overlay**, text is white, **left-aligned**,
media has a 16px radius. Desktop text column `x=48 … 688`; media column `x=752 … 1392`
→ a ~64px inter-column gap inside the 1344 container.

**Mobi hero mapping (copy fixed by spec):**
- Eyebrow: `AI-POWERED CONSTRUCTION ESTIMATING`
- Headline: `Estimating Department in Your Pocket`
- Paragraph: the approved supporting copy (contractor-facing estimating department).
- Primary CTA: **`Get A Free Estimate Trial`** → `https://portal.mobiestimates.com/signup?offer=first_estimate_free`
- Secondary link: `See How Mobi Works →` scrolls to `#explainer-video`.
- Media: Mobi-owned visual (see §9); **no** Togal image, **no** AI-worker image.

**Current Mobi delta:** hero is a full **navy** section with photo + **blur glows +
blueprint overlay + italic serif accent + a framed estimate-doc image below the text**,
in a `1.15fr/.85fr` "hero-top" grid. Target replaces glows/blueprint/serif with a clean
photo-under-overlay + a **video on the right** (matching Togal), doc imagery moves into a
later product section.

---

## 5. Video component (measured)

| Property | Value |
|---|---|
| Aspect ratio | **16:9** (640×360 desktop, 688×387 tablet, 350×197 mobile) |
| Corner radius | **16px** (`--radius-media`) |
| Desktop placement | **In-hero, right column** (Togal), width = content half (~640) |
| Mobile/tablet | Stacks directly under hero text |
| Control | Centered circular play control over the frame |

Mobi already has a **final, swappable placeholder** component
(`marketing-site/index.html:93–102`) driven by one config field. **Exact replacement
point for the real video (this weekend):**
`marketing-site/config.py` → **`EXPLAINER_VIDEO_URL`** (and optional
`EXPLAINER_VIDEO_POSTER`), then `python3 generate.py` + bump `ASSET_VER`. This is the
single source of truth; no template edit needed. In Phase 2 the placeholder must adopt
the 16:9 / 16px-radius geometry above and (to match Togal) be presentable in the hero
right column on desktop.

---

## 6. Buttons (measured — Togal system)

| Token | Primary CTA | Nav CTA |
|---|---|---|
| Font | 16px / **500** Poppins | 14px / 500 |
| Padding | **12px 24px** | 8px 16px |
| Radius | **6px** | 6px |
| Height | **~47px** | ~37px |
| Fill | solid (Mobi brand replaces green) | solid |
| Text color | #fff | #fff |
| Shadow | **none** | none |
| Transition | bg/color **0.15s linear** | same |
| Mobile | **full-width** | — |
| Desktop | **hug content** (~159px for an 11-char label) | hug |

**Primary CTA text site-wide = `Book a Free Estimate`** (the single dominant button),
**except** the hero primary which the spec fixes as `Get A Free Estimate Trial`. Both
point to `portal.mobiestimates.com/signup?offer=first_estimate_free`.

**Current Mobi delta (critical):** buttons are **pills** (`border-radius:999px`,
`styles.css:97`) with a colored **box-shadow** and `btn-lg` padding `17px 30px`. Togal
is a **6px** rectangle, no shadow, 12×24. This is the most visible single mismatch —
rebuild the button system to the table above.

---

## 7. Section map & rhythm (Togal order → Mobi content)

Measured desktop section tops (`sectionTops` @1440): `797, 1018, 2056, 2613, 3377`;
full document height **4318px** desktop / 5593 tablet / 5697 mobile — i.e. Togal is a
**short, dense** page. Mirror this order and compactness:

| # | Togal section | Mobi equivalent (truthful) | Notes |
|---|---|---|---|
| 1 | White nav | Togal-style nav | centered, flat |
| 2 | Hero (text L / video R) | Hero + explainer video (right on desktop) | copy per §4 |
| 3 | "trusted by…" + logo strip | Credibility / customer-logo strip | **hide until real logos exist** — no fake proof |
| 4 | "#1 tool built by estimators" + 6-item capability list | Mobi value-prop + capability list (estimating dept, human review, collaboration, multi-trade, deliverables, AI-assisted) | left heading + right icon list |
| 5 | Customer testimonials (3 cards) | Real testimonials | **hide until real** |
| 6 | Dark "Revolutionizing…" + awards band | Mobi credibility/why-Mobi band (navy) | use only truthful trust items |
| 7 | Final CTA ("…how much faster…") | Final conversion CTA → `Book a Free Estimate` | |
| 8 | Light multi-column footer | Togal-style multi-column footer (Mobi links) | |

The 12-point content mapping in the user spec collapses onto Togal's real ~8-block
rhythm; **do not pad** the page back out to Mobi's current ~20 sections.

---

## 8. Cards, grids, container

- Content container: **max-width 1344px**, centered, side padding 48/40/20.
- Capability list (§7 #4): two-column on desktop (heading left, list right); single
  column stacked on mobile. Icon + title + one-line description rows.
- Testimonial cards: 3-up desktop grid, radius ~12px, light surface, subtle border, no
  heavy shadow; 1-up stack on mobile.
- Grid gaps ≈ 24–32px (Togal `gap` values cluster there); confirm per component Phase 2.

---

## 9. Mobi content / asset mapping

| Slot | Asset to use | Status |
|---|---|---|
| Logo | `assets/img/mobi-logo.png` (dark) / `mobi-logo-white.png` | ✅ owned |
| Hero media | Explainer video placeholder now; hero photo = a **Mobi-owned** plan-review/estimating visual under a navy overlay | ⚠ need one high-quality owned hero photo; `hero-structure.jpg` exists but verify it isn't generic/AI — see §12 |
| Product imagery | `assets/img/bid-estimate.png` (real Mobi bid/estimate) → move into a product/deliverables section | ✅ owned |
| Customer logos | — | ❌ none yet → **hide strip** |
| Testimonials | — | ❌ none yet → **hide section** |
| Real video | set `EXPLAINER_VIDEO_URL` in `config.py` (this weekend) | ⏳ pending |

---

## 10. Colors, shadows, transitions (summary)

- Page background **white** (Togal), not the current navy-tinted hero-dominant look.
- Exactly **1–2 dark navy bands** (Mobi navy `#1e2a4a`) for emphasis, mirroring Togal's
  single dark "awards" band — not the current multiple `band-dark` sections.
- Shadows: subtle card shadow only; **no** button shadow, **no** glow filters.
- Transitions: `0.15s linear` on button color/bg; light `translateY` hover on cards is
  acceptable but keep motion restrained (no large reveals/parallax).

---

## 11. Responsive breakpoints (measured behavior)

| Breakpoint | Behavior |
|---|---|
| ≤ ~640px | 1-col everything; hero headline **48px**; CTA full-width; side pad 20px |
| ~641–991px (tablet) | hero still **stacked** (video below text) at 768/834; headline **60px**; side pad 40px; nav = hamburger |
| ~992–1439px | hero becomes **2-col** (text left / video right); nav flat/centered; side pad 48px |
| ≥ 1440px | content capped at **1344px**, centered; extra space becomes side margin (see 1920 shot: same 1344 content, wider gutters) |

Explicit rules required — do **not** rely on incidental flex wrapping. The 1920 capture
confirms content does **not** grow past ~1344px.

---

## 12. Uncertainties

1. **Header exact height / logo px / nav gaps** — the automated header probe matched a
   hidden OneTrust `Necessary` `<div>` (`display:none`), so header JSON is unreliable.
   Header geometry above is derived from the nav **Demo button** (`78×37 @ x=1314,y=8`)
   plus the desktop screenshot. Re-measure precisely in Phase 2 with a header-specific
   selector.
2. **Sticky vs. transparent-on-hero** — header reads as solid white; confirm scroll
   behavior (shadow-on-scroll) directly in Phase 2.
3. **Hero two-column exact breakpoint** — stacked at 768/834, side-by-side at 1440;
   the switch is somewhere in 900–1024. Bisect in Phase 2.
4. **Hero photo asset** — must verify `hero-structure.jpg` is Mobi-owned and not
   generic/AI before reuse; otherwise commission/select an owned image.
5. **Section internal vertical padding** — inferred from `sectionTops` deltas as
   ~64–96px; confirm per-section in Phase 2.
6. Togal's green `#3AB65A` and Miami address are **reference-only**; never shipped.

---

## 13. Acceptance tolerances

"Close enough to produce the same visual proportions" is operationalized as:

| Dimension | Tolerance vs. reference |
|---|---|
| Font size | ±1px (or ±5%) |
| Line height | ±0.05 |
| Font weight | exact bucket (400/500/700) |
| Button/card/media radius | ±2px (6/12/16 must read as such) |
| Button height & padding | ±4px |
| Container max-width | ±16px of 1344 |
| Side padding | ±4px per breakpoint |
| Section vertical rhythm | ±10% |
| Hero headline size | ±2px (48 mobile / 60 desktop) |
| Full-page height ratio | Mobi within **±25%** of Togal's height at each breakpoint (today it is ~+290%) |
| Horizontal overflow | **0px** beyond viewport (today Mobi overflows to 414 @390) |

Meeting these across all seven viewports satisfies Fable Gates 1–6 and 9.
```

---

## 14. Implementation-verified corrections (2026-07-23)

Values below were **measured on the built Mobi homepage** and correct/confirm the
Phase 1 estimates (source: `measurements/mobi-rebuilt.json`, `capture.mjs`):

| Item | Phase 1 estimate | Implementation-verified |
|---|---|---|
| Header height | ~55–64px (uncertain, §12.1) | **57px**, solid white — confirmed |
| Hero 1→2 col breakpoint | somewhere 900–1024 (§12.3) | **pinned at 992px** (`--hero-bp`) |
| H1 mobile | 48/52.8/700 | **48px / 52.8 / 700** — exact |
| H1 desktop | 60/66/700 | **60px / 66 / 700** — exact |
| Container | 1344px | **1344px** — confirmed |
| Full-page height @390/834/1440 | target ≤125% of Togal | **0.945 / 0.726 / 0.732×** — all ≤1.25 |
| Horizontal overflow | 0 | **0** at all seven viewports (scrollWidth == viewport) |

Hero background (§4/§9 open item): implemented as the **owned** `bid-estimate.png`
cropped to the right beneath the navy overlay — Togal-like depth without any
Togal/stock/AI asset; `hero-structure.jpg` remains unused (provenance unverified).
