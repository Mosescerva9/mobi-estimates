You are Claude Code using exact model `claude-opus-4-8` at high effort. Continue the interrupted implementation in `/home/hermes/work/mobi-estimates-togal-redesign` on branch `redesign/togal-faithful-rebuild`.

Read in full:
- `/tmp/togal-faithful-rebuild-user-spec.md`
- `docs/togal-visual-spec.md`
- `review-artifacts/togal-faithful-rebuild/phase-1-audit.md`
- `review-artifacts/togal-faithful-rebuild/opus-visual-director-directive.md`
- `/tmp/togal-claude-implementation-prompt.md`

The previous Claude Opus run was interrupted by the account session limit before completion. Preserve and inspect its uncommitted implementation; do not restart blindly. Generate the full answer in this response.

HARD STATUS: the current partial implementation is NOT approved.
- Final screenshot height ratios vs Togal: 390 = 1.771, 834 = 1.274, 1440 = 1.438.
- The director requires <=1.25 at every target, so mobile and desktop materially fail.
- The current 1440 full-page screenshot still contains too many standalone blocks: collaboration cards, multi-trade, dashboard milestones, follow-up, internal-hire comparison, FAQ, final CTA/form, footer. This violates the locked compact eight-block rhythm.
- The current hero reads as a plain navy field and does not yet evoke Togal’s photo-under-overlay composition strongly enough.
- The footer CTA button in the current screenshot appears to have low-contrast text; verify and fix.

CONTINUATION TASK:
1. Inspect current diff and current final screenshots before editing.
2. Collapse the homepage to the locked structure:
   - nav
   - hero with integrated video
   - hidden real-logo structure (no gap)
   - ONE compact value/capability block incorporating truthful collaboration, multi-trade, deliverables, and owned `bid-estimate.png` product imagery
   - hidden testimonial structure (no gap)
   - ONE dark why-Mobi/trade-capability band
   - final conversion CTA (keep lead form functional but compact; it may be integrated here or in footer)
   - light footer
3. Remove standalone homepage sections for dashboard milestones, bid follow-up, internal-hire comparison, FAQ, and duplicate collaboration/multi-trade bands. Their dedicated routes/content remain elsewhere; do not delete site routes.
4. Use owned `bid-estimate.png` (or another provably owned product/plan-review asset) as a low-opacity/cropped hero background layer beneath the navy overlay so the hero has Togal-like depth without using Togal/stock/AI assets. Keep the video-right media legible and subordinate background restrained. Do not use unverified `hero-structure.jpg` as dominant media.
5. Ensure nav/hero/final CTA exact text `Book a Free Estimate` and target `https://portal.mobiestimates.com/signup?offer=first_estimate_free`. Secondary link goes to `#explainer-video`.
6. Fix any low-contrast footer/final CTA label, focus states, and all hard reject conditions.
7. Regenerate twice deterministically.
8. Re-run true-390, 834, and 1440 captures first. Iterate until all full-page height ratios are <=1.25, overflow is zero, and visual rhythm closely follows the reference. Then capture all seven targets.
9. Regenerate side-by-side and overlay artifacts in final folders.
10. Run all verification from the original prompt: marketing/product-truth/unsupported-evidence/lead/intro-offer/service-role tests, typecheck, lint, production build, `git diff --check`, console/link/accessibility checks. Do not submit forms or initiate checkout.
11. Write `review-artifacts/togal-faithful-rebuild/implementation-report.md` with real iterations, measurements, tests, changed files, preserved functionality, hidden proof sections, video swap path, and remaining asset needs.
12. Do not commit, push, open/modify PRs, or deploy. End only with `READY FOR FINAL VISUAL DIRECTOR REVIEW` if all implementation and verification requirements truly pass; otherwise `BLOCKED` with exact evidence.

