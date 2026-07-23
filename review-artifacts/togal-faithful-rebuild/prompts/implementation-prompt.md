You are Claude Code using exact model `claude-opus-4-8` at high effort. Work in `/home/hermes/work/mobi-estimates-togal-redesign` on branch `redesign/togal-faithful-rebuild`.

Read in full before editing:
1. `/tmp/togal-faithful-rebuild-user-spec.md` — controlling user specification.
2. `docs/togal-visual-spec.md` — measured live Togal specification.
3. `review-artifacts/togal-faithful-rebuild/phase-1-audit.md` — failure diagnosis and functionality preservation contract.
4. `review-artifacts/togal-faithful-rebuild/opus-visual-director-directive.md` — authorized planning ruling and exact implementation sequence.
5. Raw measurement JSONs and 390/834/1440 reference/baseline/comparison PNGs under `review-artifacts/togal-faithful-rebuild/`.

Generate the full answer in this response. Do not refer to previous messages or assume unstated context.

TASK: Perform the complete controlled presentation rebuild now. Do not merely tweak the failed design. Preserve functionality, routes, SEO, lead form, offer semantics, analytics hooks, pricing handoffs, and portal integrations. Do not modify production, Vercel, DNS, pricing, legal terms, customer data, Stripe logic, portal/auth/API implementation, or secrets. Do not commit, push, open/modify PRs, submit forms, send messages, or deploy.

Implementation requirements:
- Modify the canonical source (`marketing-site/config.py`, `build.py`, `generate.py`, CSS/JS/assets) and regenerate outputs deterministically. Do not hand-edit generated HTML as the source of truth.
- Use reusable rendering functions/components and a centralized token system. Remove scattered arbitrary visual values from the homepage path.
- Implement the locked eight-block structure from the director directive.
- Use Poppins only, full legal weight system 400/500/600/700.
- Use exact dominant CTA `Book a Free Estimate` in nav, hero, and final CTA, all to `https://portal.mobiestimates.com/signup?offer=first_estimate_free`; preserve `data-analytics` hooks.
- Hero secondary `See How Mobi Works →` must scroll to `#explainer-video`.
- Integrate the swappable 16:9 video as hero-right media at desktop and directly after hero text on mobile/tablet. Keep one URL and one poster field in config; document exact replacement.
- Do not use `hero-structure.jpg` as dominant media because ownership/non-AI provenance is unverified. Use only owned Mobi product/estimate/plan-review imagery and an honest branded temporary video thumbnail/composition.
- Build logo and testimonial components structurally but keep them genuinely hidden with no empty gap until real proof exists.
- No pills, button shadows, glows, gradients, blueprint overlays, glass effects, oversized radii, serif accent, fake logos/testimonials, unsupported claims, or generic stock/AI imagery.
- Preserve semantic HTML, focus states, keyboard drawer behavior, contrast, image dimensions/aspect ratios, no CLS, no dead controls, no console errors, no horizontal overflow.
- Re-measure the real Togal header selector before locking header dimensions. Bisect the live-reference hero breakpoint at 900/960/992/1024 and set an explicit matching breakpoint.
- Re-capture Mobi at a true 390 viewport; do not repeat the prior 414px emulation mistake.

Mandatory visual loop:
1. S1/S2 tokens + buttons: generate, run local site, capture nav/hero CTA at 390 and 1440, compare to reference, correct.
2. S3 header: capture at 390 and 1440, compare proportions, correct.
3. S4/S5 hero + video: capture at 390, 834, 1440; compare headline wrapping, hero height, columns, media size/radius, button geometry, correct.
4. S6 first content/value/capability block: capture at 390 and 1440, compare density/spacing, correct.
5. S7 final CTA/footer: capture at 390 and 1440, compare stacking/columns/rhythm, correct.
6. Final full page: capture all seven target viewports using `scripts/visual-review/capture.mjs`; produce final side-by-side and practical overlay comparisons against reference. Store under `review-artifacts/togal-faithful-rebuild/final/`, `final-comparison/`, and `final-overlay/`.
7. Measure final document height, scroll width, header, hero, text, buttons, media, sections at 390/834/1440. Reject and fix until within director tolerances (especially full page <=125% of Togal height and overflow 0).

Verification:
- Run generator twice and prove deterministic diff stability.
- Run the full relevant Mobi test suite named in the preservation contract/director directive, plus typecheck, lint, production build, `git diff --check`, and any targeted accessibility/link/console checks supported by the tooling.
- Do not submit the lead form or initiate checkout; verify structure/targets/read-only.
- Ensure non-home marketing routes still render and preserve their content; the new global button/header/footer system may propagate, but do not accidentally collapse every page to the homepage.
- Inspect the final diff for generated-source ownership and unnecessary dependencies.

Deliverables before stopping:
- Working rebuilt homepage source and generated pages.
- Final screenshot/comparison/overlay artifacts at 390, 834, 1440 at minimum plus all seven viewport finals.
- Updated `docs/togal-visual-spec.md` only where implementation-proven measurements correct the Phase 1 estimates.
- `review-artifacts/togal-faithful-rebuild/implementation-report.md` listing stages, iterations, files, measured before/after, tests, functionality preserved, hidden proof sections, video replacement path, remaining Mobi assets needed, and unresolved issues.
- A concise terminal response with real commands/results and either `READY FOR FINAL VISUAL DIRECTOR REVIEW` or `BLOCKED`.

Do not claim completion because code builds. Iterate until the visual proportions are materially close to the measured Togal reference.

