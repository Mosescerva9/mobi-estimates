# Trade-Assembly Development Guide

An assembly maps a scope item to labor/material/equipment/other-direct **components**
that reference cost-item codes. Assemblies define **structure**, never prices — rates
live in cost books. Trade modules own their assembly templates, mapping rules, and
pricing validation; the shared core stays trade-agnostic.

## Add assemblies to a trade module

1. In `app/trades/<trade>/assemblies.py`, define templates: `assembly_code`, `name`,
   `scope_category`, `input_unit`, `required_trade_data`, and `components` (each with
   `component_type`, `cost_item_ref`, `quantity_factor`, optional `waste_factor`,
   `production_ref`, `crew_ref`, `conditions`, `sequence`).
2. Provide `map_<trade>_scope(category, trade_data) -> [assembly_code]` (deterministic:
   0 = unpriced, 1 = mapped, >1 equal-priority = conflict requiring review).
3. Provide `validate_<trade>_pricing_inputs(...)` for required trade-data fields.
4. Wire the three hooks into the `TradeModule` subclass (`get_assembly_templates`,
   `map_scope_to_assembly`, `validate_pricing_inputs`).

## Rules

- Assemblies reference items only from the same published cost-book version.
- Unit compatibility is validated before publishing; missing component references and
  circular references are rejected.
- No arbitrary Python expressions — only the registered component pricing methods.
- Never assume coats, substrate, coverage, height/access, durations, or crew
  composition; declare them as required inputs instead.
