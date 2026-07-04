# Trade-Module Development Guide

A trade module is a self-contained plugin that teaches the shared core how to route
sheets, validate candidates, compute quantities, and prompt a provider for one
trade. Adding a trade means **writing a new module, not editing the core**.

## Anatomy

```text
app/trades/<trade_code>/
├── __init__.py        # exports the TradeModule subclass
├── definition.py      # the TradeModule subclass tying everything together
├── schemas.py         # categories, allowed units, validated trade_data payload
├── routing.py         # deterministic sheet-routing rules
├── validation.py      # candidate + payload validation
├── quantities.py      # deterministic QuantityFormula subclasses
├── conflicts.py       # trade conflict detection
└── prompts/           # versioned *.txt prompt templates
```

Smaller trades may collapse this into a single module file (see `demo_concrete`).

## Steps to add a trade (e.g. `drywall`)

1. **Pick a stable code** (`drywall`) and bump nothing else.
2. **Define categories + units + payload** in `schemas.py`. The payload is a Pydantic
   model with `extra="forbid"`; every field optional (never assume).
3. **Implement routing** returning one of `eligible | excluded | blocked_unverified
   | blocked_ocr | requires_review`. Use multiple signals (verified number, title,
   embedded text), not prefixes alone.
4. **Implement validation**: `validate_trade_data()` (versioned) and
   `validate_candidate()` returning a `ValidationResult` (errors, blocking issues,
   normalized payload, requires_review).
5. **Implement formulas** as `QuantityFormula` subclasses with
   `supported_trade_codes={"drywall"}`, `Decimal`-only math, validated inputs.
6. **Write versioned prompts** that include the mandatory safety block (no pricing,
   no derived quantities, no inferred dimensions, cite evidence, return null, flag
   conflicts).
7. **Subclass `TradeModule`** in `definition.py` implementing every abstract method.
8. **Register the code** in `app/trades/__init__.py` `AVAILABLE_TRADE_MODULES`.
9. **Enable it** via `MOBI_ENABLED_TRADES=painting,drywall`.
10. **Test** with the mock provider (add candidates for the trade) and unit-test the
    formulas + routing.

## The interface (abridged)

```python
class TradeModule(ABC):
    trade_code: str; trade_name: str; module_version: str; schema_version: str
    def get_definition(self) -> TradeDefinition: ...
    def get_scope_categories(self) -> list[str]: ...
    def get_allowed_units(self) -> list[Unit]: ...
    def route_sheet(self, sheet: SheetContext) -> SheetRoutingResult: ...
    def validate_trade_data(self, payload, *, schema_version=None) -> dict: ...
    def validate_candidate(self, candidate: CandidateContext) -> ValidationResult: ...
    def detect_conflicts(self, candidate, related_items) -> list[Conflict]: ...
    def get_quantity_formulas(self) -> list[QuantityFormula]: ...
    def category_requires_quantity(self, category_code: str) -> bool: ...
    def allowed_quantity_bases(self, category_code: str) -> set[QuantityBasis]: ...
    def get_prompt_version(self, task_type: str) -> str: ...
    def get_prompt(self, task_type: str) -> str: ...
```

## Rules

- Never reach into another trade's module or into core internals.
- Formulas must be deterministic, `Decimal`-only, side-effect free, and registered
  for your trade code only.
- A provider may transcribe explicit/schedule numbers; derived quantities must be
  recomputed by your formulas.
- Keep prompts trade-specific and versioned; the core has no universal prompt.
- Store the schema version with every payload and handle old versions explicitly.
