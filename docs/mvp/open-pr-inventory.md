# Open PR Inventory — MVP Reset

Updated: 2026-07-16T00:10Z

Source: `gh pr list` and `gh pr view` on `Mosescerva9/mobi-estimates`.

| PR | Title | Head | Checks / mergeability | MVP classification | Recommended action |
|---:|---|---|---|---|---|
| #92 | Add Mobi SEO blog quality standard | `mobi-seo-blog-quality-system` | Mergeable; Vercel portal/marketing success; 36 files, +1192/-10 | Useful but later / marketing | Keep out of MVP branch. Should remain open or be closed separately after MVP plan decision; do not merge into MVP customer/product branch now. |
| #89 | P0: reject model-generated release quantities | `p0-release-gate-model-quantity-evidence` | Mergeable; Vercel portal/marketing success; 9 files, +1901/-19 | Needs reduction / reliability-security candidate | It expands release-gate/model-quantity logic. Do not keep expanding this lane. Mine only MVP-critical safety pieces if needed; otherwise keep open but inactive or close after canonical provider/evidence path supersedes it. |
| #88 | P0: preserve readiness delivery-source provenance | `p0-readiness-source-metadata` | Mergeable; Vercel portal/marketing success; 2 files, +62/-57 | Potentially safe reliability/security PR | Small provenance hardening may be useful, but must be checked against new canonical evidence/provider architecture. Candidate for the one reliability/security PR only after focused review. |
| #73 | Normalize quantity extraction candidates | `automation-quantity-candidate-normalization-v1` | Mergeable; portal success; marketing Vercel failure; 2 files, +68/-14 | Obsolete / conflicts with new architecture direction | This expands candidate/synonym-ish extraction. Do not merge into MVP branch. Prefer close/supersede after OpenTakeoff provider boundary is established. |
| #5 | Pay-first checkout: collect payment before account creation | `pay-first-checkout` | Conflicting; old checks from 2026-07-04; 10 files, +533/-64 | Required for MVP conceptually, but obsolete implementation branch | Do not merge directly. Re-implement or port the necessary pay-first pieces onto `mvp-opentakeoff-customer-launch` after current checkout audit. |

## Active MVP PR policy
Keep no more than two active MVP engineering PRs at once:
1. Customer/product capability PR: likely `mvp-opentakeoff-customer-launch` after first implementation slice.
2. Reliability/security PR: only if #88 or a reduced equivalent is truly needed before MVP branch merge.

## Immediate PR decisions
- Freeze #92 and #73 out of MVP.
- Freeze #89 unless reduced to a canonical-provider/evidence-safety need.
- Treat #5 as design input, not merge input.
- Review #88 as the only possibly mergeable old reliability PR, but only after ensuring it does not conflict with canonical evidence work.
