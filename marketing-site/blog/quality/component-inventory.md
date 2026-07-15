# Reusable Blog Component Inventory

Future articles should render through shared components in `marketing-site/blog/scripts/generate_blog.py` and shared styles in `marketing-site/blog/assets/blog.css` instead of rebuilding layouts by hand.

## Components preserved from the approved workflow

| Component | Purpose | Quality rule |
|---|---|---|
| Article hero | Title, excerpt, category, metadata | One H1, no clipped mobile heading, safe-area/header offset. |
| Draft banner | Preview state | Visible only for drafts/previews, never on production articles. |
| Publication metadata | Published/updated dates | Published only after actual release; updated hidden on first launch/equal dates. |
| Breadcrumbs + mobile back | Orientation | Desktop breadcrumb, mobile back link. |
| Table of contents | Long article navigation | Generated from H2 headings; no hash placeholders. |
| Responsive summary table | Compare terms/options | Readable at 320 px; no horizontal overflow unless intentionally accessible. |
| Process cards | Sequential workflow | Mobile-readable and not mistaken for navigation. |
| Calculation blocks | Formulas/examples | State base, formula, and result; arithmetic tested. |
| Estimate cards | Dense estimate examples | Compact mobile cards; avoid repeated labels where possible. |
| Checklist | Contractor action list | Topic-specific, not generic filler. |
| Diagnostic table | Mistake/symptom/fix mapping | Use when it helps decision-making. |
| FAQ | SERP/user questions | Only useful questions; no keyword stuffing. |
| Source section | Further reading | Contextual citations and clear third-party attribution. |
| CTA | Next step | Restrained, approved, relevant to article intent. |
| Related posts | Cluster navigation | Do not live-link unpublished posts. |
| Author/editorial attribution | Accountability | “Prepared by Mobi Estimates editorial team” unless real review occurred. |
| Open Graph image | Sharing preview | Original/rights-safe image; loads from current environment. |

## New component rule
Add a new component only when the topic needs a genuinely different information format. Document why it was needed and add a regression check if it affects layout, accessibility, publication state, or links.
