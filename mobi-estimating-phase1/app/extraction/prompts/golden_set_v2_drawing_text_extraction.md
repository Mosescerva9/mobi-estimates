# Golden Set v2 Drawing Text Extraction Rules

Status: experiment-only, not wired into production behavior.

## Purpose

This prompt/rules artifact is the first mutable target for Mobi AutoResearch experiments against Golden Set v2. It is intended to improve extraction from image-heavy public drawing PDFs while the Golden Set v2 source PDFs, manifest, source log, and evaluator remain locked.

## Target failure mode

Golden Set v2 currently shows that some complete drawing sets can process safely but produce zero or very low scope items. The first AutoResearch loop should focus on:

- sheet title and sheet index recognition;
- OCR/text cleanup for plan sheets;
- drawing note and schedule extraction;
- trade/scope keyword recovery;
- source-backed quantity evidence collection.

## Extraction priorities

When processing drawing text or OCR output, prefer evidence that is explicitly present on the sheet:

1. Sheet number and sheet title.
2. Sheet index entries.
3. Project data tables and code-analysis tables.
4. General notes that name trades or scope items.
5. Schedules and legends listing devices, stalls, fixtures, assemblies, or roof areas.
6. Callouts and keynote legends tied to plan views.

## Guardrails

- Do not invent quantities not visible in source text or sheet evidence.
- Do not treat this file as ground truth; it is only a mutable experiment artifact.
- Do not modify Golden Set v2 PDFs, manifest, source log, or evaluator during an experiment.
- Do not produce customer-facing estimate language from this prompt.
- If evidence is ambiguous, prefer `unknown` with a source note over a fabricated value.

## Current benchmark target

Improve Golden Set v2 score above the current baseline by increasing:

- `scope_keyword_coverage_micro`
- `trade_recall_micro`
- source-backed quantity extraction where `require_engine_quantity=true` in future corpora

while keeping:

- `safety_violation_count = 0`
- `harness_failed_count = 0`
- `trade_unexpected_false_positive_total = 0`
