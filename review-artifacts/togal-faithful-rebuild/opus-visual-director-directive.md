# Authorized Opus 4.8 visual-director directive

Fable 5 was unavailable because the Claude account reported no Fable usage credits. Moses explicitly authorized Claude Opus 4.8 as the substitute visual director. Opus reviewed the controlling prompt, measured spec, audit, raw measurement JSONs, comparison screenshots, and current presentation source.

## Planning verdict

**READY FOR CLAUDE IMPLEMENTATION**

The released redesign currently blocks all 10 visual gates. The Phase 1 evidence is sufficient for implementation with the corrections below.

## Evidence corrections

1. The prior Mobi “390” baseline was actually 414px wide; recapture at a true 390 and gate on `scrollWidth == clientWidth`.
2. Bisect the hero one-column/two-column breakpoint at 900/960/992/1024 and pin an explicit breakpoint.
3. Re-measure the real Togal header selector; the initial automated probe hit a hidden OneTrust element. Target a verified 55–64px white header band, real logo dimensions, and measured nav gap.
4. Ignore the Togal Tuesday popup “Register now” button; it is not part of Togal’s design system. Use only the Demo/Book a Demo button geometry.
5. Treat 1344px as the real content container; ignore noisy unrelated max-width tokens.
6. `hero-structure.jpg` provenance is unproven. Do not use it as the dominant hero image unless ownership/non-AI status is confirmed. Default to a Mobi-owned product/plan-review composition with navy overlay and owned Mobi media.

## Locked visual target

- Poppins exact; weights 400/500/600/700.
- Side padding: 20px mobile, 40px tablet, 48px desktop.
- Container: max 1344px.
- Header: white, sticky, approximately 55–60px after direct remeasurement; centered flat desktop nav; Login + one CTA; hamburger at tablet/mobile.
- Hero: 1 column at 390 and 834, 2 columns at 1440; text left and explainer media right on desktop.
- Eyebrow: 14/500 uppercase.
- Headline: 48/52.8/700 mobile; 60/66/700 tablet/desktop; normal tracking.
- Paragraph: 20/28/400.
- Primary CTA: `Book a Free Estimate`, 16/500, 12×24 padding, 6px radius, approximately 47px tall, no shadow; full-width on mobile.
- Secondary: `See How Mobi Works →` → `#explainer-video`.
- Video: 16:9, 16px radius, centered play; hero-right desktop, directly under text mobile/tablet.
- One dark navy accent band only; otherwise white/near-white page.
- No pills, glows, gradients, blueprint overlays, glass, serif accents, fake proof, unsupported speed/accuracy, or generic stock/AI scenes.
- Full document height at 1440 must be no more than 125% of Togal’s 4,318px target (≈5,398px); analogous ±25% tolerance at 390 and 834.
- Horizontal overflow: zero.

## Locked section order

1. White Togal-style navigation.
2. Hero with integrated explainer-video media.
3. Credibility/logo structure present but hidden until real logos exist.
4. Compact value proposition + six-item capability list; fold owned deliverable imagery into this block rather than creating filler bands.
5. Testimonial structure present but hidden until real testimonials exist.
6. One dark Mobi navy “why Mobi” band with truthful trust items only.
7. Final conversion CTA.
8. Light Togal-style multi-column footer.

Delete/collapse the Services mega-menu, duplicate CTA bands, newsletter as standalone section, multiple dark sections, separate hero estimate frame, glow/blueprint/gradient/serif decoration, and all filler sections that cause the current ~16,813px desktop length.

## CTA ruling

Use **`Book a Free Estimate`** in the nav, hero, and final conversion CTA. This resolves the prompt conflict in favor of the repeated site-wide requirement, final acceptance item, existing offer truth, and non-software-trial positioning. All point to:

`https://portal.mobiestimates.com/signup?offer=first_estimate_free`

## Implementation sequence

S1 tokens/font → S2 buttons → S3 header → S4 hero + breakpoint bisection → S5 video → S6 compact body/hidden proof → S7 light footer → S8 responsive screenshot loops → S9 functional QA → S10 final review packet.

Each stage must be screenshot-compared against live-reference artifacts. Reject any stage with a pill, glow/gradient/blueprint/serif artifact, mega-menu, fake proof, document height over 125%, overflow over zero, unsupported claim, or non-Poppins render. Compilation is not completion.

## Final review format

Only approve with `PASS - all 10 gates`. Otherwise return `BLOCK - <gate#>: <reason>` for each material blocker.
