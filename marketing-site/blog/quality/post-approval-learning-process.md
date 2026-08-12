# Post-Approval Learning Process

Create a postmortem after Moses approves, rejects, or requests changes to any SEO blog article.

## Required fields
- Article ID
- Review outcome: approved / rejected / changes requested
- Correction requested
- Reason
- Applies globally or article-only
- Workflow stage that should have caught it
- Validator or rubric that missed it
- Proposed system improvement
- Test added
- Documentation changed
- Component changed
- Gold standard update needed? yes/no
- Owner and due date

## Promotion rule
Promote a correction into the main workflow only when it:
- prevents a factual error;
- prevents a repeated quality issue;
- improves publication safety;
- represents a durable Mobi preference;
- appears across multiple reviews;
- or is explicitly marked by Moses as a permanent rule.

Do not blindly convert every subjective one-time preference into a global rule.

## Template

```json
{
  "article_id": "",
  "review_outcome": "approved|rejected|changes_requested",
  "correction_requested": "",
  "reason": "",
  "scope": "global|article_only|unknown",
  "missed_by_stage": "",
  "missed_by_validator_or_rubric": "",
  "proposed_system_improvement": "",
  "test_added": "",
  "documentation_changed": "",
  "component_changed": "",
  "gold_standard_update_needed": false,
  "decision": "promote|do_not_promote|revisit_after_repeat"
}
```
