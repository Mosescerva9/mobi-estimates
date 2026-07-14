# Autonomous Mobi Blog Workflow

## State machine
`idea → researching → brief_ready → drafting → validating → review_required|approved|blocked → scheduled → publishing → published|failed → updating|archived`

## Executable workflow stages
1. Select eligible topic from `automation/opportunity-queue.json`.
2. Claim and lock the article/task.
3. Validate topic map and cannibalization.
4. Research current SERP and audience questions without fabricating volume, difficulty, CPC, or trend data.
5. Retrieve canonical Mobi documentation.
6. Verify source freshness.
7. Create content brief.
8. Draft article from canonical Markdown front matter and body.
9. Add original value: at least two of worked example, calculation, checklist, comparison table, decision tree, template, diagnostic table, downloadable resource, original Mobi diagram, product screenshot, annotated sample estimate, workflow, original analysis, expert review, first-party data.
10. Add contextual internal links.
11. Add authoritative sources.
12. Generate SEO metadata.
13. Generate visual requirements.
14. Run deterministic checks.
15. Run semantic evaluations.
16. Run risk classification.
17. Route medium/high-risk content for review.
18. Generate responsive preview.
19. Schedule eligible low-risk article.
20. Publish atomically through `blog/scripts/hermes_blog.py publish`, never improvised production commands.
21. Run live QA.
22. Roll back if critical checks fail.
23. Monitor indexing and performance.
24. Create updates and supporting-topic tasks.

## Required run record fields
Every stage records inputs, outputs, sources, decisions, validation results, status, errors, retries, next action, related commit, deployment, and rollback point under `blog/automation/run-records/`.

## Shadow mode
Shadow mode performs the workflow through dry-run publication and rollback simulation only. It stops before live deployment and before any sitemap/indexing/social/email action.

## Controlled rollout
Autonomous production publishing can only be enabled after activation criteria in `publication-policy.json` pass and Moses explicitly authorizes activation. Initial rollout is low-risk only, max two articles/week, one article/event, no pricing/offers/testimonials/regulatory topics, rollback enabled, alerts required.
