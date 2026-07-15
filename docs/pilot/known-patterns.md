# Known patterns for pilot work

Updated: 2026-07-15T02:13:33Z

## Evidence normalization
- Normalize external/model/manual outputs once at the boundary.
- Forbid unknown fields in canonical contracts.
- Preserve raw payloads separately for audit/quarantine; do not treat raw provider fields as delivery-ready evidence.
- Prefer typed evidence classes over synonym scanners.

## Provider architecture
- All takeoff sources implement a common provider interface and emit canonical evidence.
- Mobi-native, manual import, human verified, authorized third-party, and future CAD/BIM providers should be interchangeable at the evidence boundary.

## Testing order
1. Schema/unit tests for the active code.
2. Related module tests.
3. Type/build/lint only when frontend/shared code changes.
4. Golden Set or real-project benchmark when estimating capability changes.
5. Codex focused diff review before important PR merge.

## Approval and safety
- Human approval required for production deployments unless specifically covered by current standing approval, and always required for purchases, payments/refunds, external messages/email, pricing/legal/DNS, destructive production data actions, and final construction estimate delivery.
- Pilot estimates remain human-reviewed.

## Cost control
- Use deterministic scripts/search before model calls.
- Use Claude Code for substantive implementation, Codex for focused review, GPT-5.6 only for hard architecture/accuracy/security decisions.
- Cache expensive document processing by source hash, processor/prompt/schema versions, model, page, and region.
