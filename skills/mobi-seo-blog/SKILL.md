---
name: mobi-seo-blog
description: Use when creating, updating, refreshing, previewing, publishing, monitoring, or improving any Mobi SEO blog/resource article, topic cluster, YouTube-to-blog transformation, or blog workflow.
version: 1.0.0
author: Mobi Estimates / Hermes
license: Proprietary
metadata:
  hermes:
    tags: [mobi, seo, blog, content-quality, publishing]
    related_skills: [mobi-conversion-growth, browser-verification]
---

# Mobi SEO Blog Skill

## Overview
Use this skill for all Mobi blog work. The goal is predictable quality, not repetitive content. Future articles must match or exceed the approved gold-standard article’s usefulness, evidence discipline, responsive behavior, publication safety, and restrained promotion without copying its wording, examples, or layout.

Gold standard: `marketing-site/blog/reference/gold-standard-article/`.
Rubric: `marketing-site/blog/quality/rubric.json`.
Controlled wrapper: `python3 marketing-site/blog/scripts/hermes_blog.py`.

## When to Use
- New SEO blog posts or resource articles.
- Blog updates, refreshes, or performance improvements.
- YouTube/video-to-blog transformations.
- Topic-cluster planning.
- Preview, publication, rollback, or live QA.
- Post-approval corrections or learning-loop updates.

## Mandatory Workflow

1. **Select or receive topic.**
   - Inputs: user topic, opportunity queue, product/customer questions, Search Console/analytics when available.
   - Outputs: candidate topic ID, primary query, audience, search intent, pillar.
   - Checks: no fabricated search volume/difficulty/CPC.
   - Blocking failures: unknown audience/intent, unsupported metric claims.
   - Tools: web/search APIs, local queue files, Obsidian/vault docs when relevant.
   - Run record: topic source, selected/deferred reason.

2. **Check cannibalization.**
   - Inputs: `topic-map.json`, published posts, drafts, scheduled posts, service pages, landing pages, YouTube drafts.
   - Outputs: cannibalization decision: proceed, narrow, merge, update, reject.
   - Blocking failures: same intent as an existing page without a merge/update decision.
   - Run record: compared pages and decision.

3. **Research current search intent and competitors.**
   - Inputs: SERP results, People Also Ask, related searches, competitor articles.
   - Outputs: brief notes on intent, expected sections, gaps, differentiation.
   - Checks: cite source URLs; do not copy competitor structure blindly.
   - Blocking failures: no current intent evidence for publication-track articles.

4. **Verify Mobi documentation and source freshness.**
   - Inputs: canonical Mobi docs for capabilities, offers, approved claims, current blog policy.
   - Outputs: allowed Mobi claims and disallowed claims list.
   - Blocking failures: pricing/offer/performance claim without canonical approval.

5. **Create content brief.**
   - Inputs: topic, intent, SERP, sources, risk, CTA, original-utility plan.
   - Outputs: brief saved under blog research/brief location.
   - Checks: includes audience, query, outline, original utility, source list, CTA, risk.

6. **Draft article.**
   - Inputs: brief and canonical metadata model.
   - Outputs: Markdown with `---json` front matter.
   - Checks: metadata complete; no draft-only production claims; no generic AI filler.

7. **Add original utility.**
   - Required: at least two topic-appropriate elements such as worked example, calculation, checklist, comparison table, decision tree, diagnostic table, template, original diagram, annotated sample, workflow, expert review, or approved first-party data.
   - Blocking failures: article only summarizes SERP or rewrites transcript.

8. **Add citations, internal links, and CTA.**
   - Inputs: verified sources, topic map, approved CTA policy.
   - Outputs: contextual citations, safe related links, restrained CTA.
   - Blocking failures: unpublished related post as live link; CTA resolves incorrectly from final URL; free-estimate/pricing claim without approval.

9. **Generate metadata and schema.**
   - Outputs: title, SEO title, description, canonical, OG image, Article schema.
   - Blocking failures: schema contradicts visible content, false publish/update date, wrong canonical.

10. **Render through reusable components.**
    - Use shared hero, metadata, breadcrumb/mobile back, TOC, responsive tables/cards, process cards, checklists, FAQ, sources, CTA, related posts, attribution, and OG behavior.
    - Blocking failures: hand-built layout that bypasses responsive/publication-state components without justification.

11. **Run deterministic validation.**
    - Commands: `python3 marketing-site/blog/scripts/generate_blog.py`; `python3 marketing-site/blog/tests/test_blog_system.py`; relevant Marketing OS preflight.
    - Blocking failures: test failure, generated-file drift, broken links, noindex/publication-state mismatch.

12. **Run semantic evaluation and gold-standard comparison.**
    - Use rubric and comparison template. If possible, use independent reviewer/model for final semantic score.
    - Blocking failures: overall score <85; any blocking category below minimum.

13. **Classify risk.**
    - Low: general workflow/definitions with reliable support.
    - Medium: labor burden, overhead, contingency, financial calculations, operational advice that could mislead.
    - High: legal/tax/licensing/labor law/insurance/bonding/safety/state-specific/competitor accusations/pricing/offers/customer results/guarantees.
    - Blocking failures: weakened classification to increase output.

14. **Create preview.**
    - Use controlled preview workflow. Verify the remote URL itself when browser-accessible preview is requested.
    - Blocking failures: only local file path when user requested browser URL.

15. **Publish only through controlled wrapper.**
    - Use dry-run/preview/scheduled/publish wrapper; never raw production edits when wrapper exists.
    - Approval: production publishing requires explicit scope; autonomous publishing remains disabled unless separately activated.

16. **Run live QA.**
    - Verify HTTP 200, title/H1, canonical, noindex state, sitemap/archive, schema, OG image, links, CTA, mobile rendering, no horizontal overflow, analytics, and rollback point.
    - Blocking failures: rollback or repair according to user authorization; do not retry indefinitely.

17. **Record lessons.**
    - Create post-approval postmortem for approval, rejection, or changes.
    - Promote corrections only when durable/global under `post-approval-learning-process.md`.

## Approval Requirements
- Drafting and previews: allowed when requested.
- Production publication: explicit article-specific approval required unless a future autonomous policy is separately activated.
- Medium/high risk: domain/human review required before publication.
- Social/email/YouTube promotion: separate approval/policy required.

## Common Pitfalls
1. Copying the gold standard’s surface form instead of matching its utility.
2. Letting draft/publication state drift between Markdown, HTML, schema, and sitemap.
3. Linking from a production article to unpublished drafts.
4. Using relative links that resolve under `/blog/` incorrectly.
5. Treating Vercel preview success as phone-accessible without checking auth redirects.
6. Publishing with `updated_at` equal to `published_at` on first launch.
7. Allowing educational dollar examples to be treated as official Mobi pricing, or official pricing claims to slip through as examples.

## Verification Checklist
- [ ] Skill was loaded for the task.
- [ ] Gold-standard reference checked for quality principles, not copied wording.
- [ ] Rubric score and comparison report generated.
- [ ] Deterministic tests passed.
- [ ] Risk classification recorded.
- [ ] Draft/production state matches intended state.
- [ ] Links resolve from final URL.
- [ ] Responsive screenshots exist for publication-track work.
- [ ] Post-approval lesson recorded when Moses reviews.
