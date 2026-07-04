# Deterministic Quantity Engine

All canonical quantities are computed by registered Python formulas using `Decimal`
— never binary floating point and never by an AI provider.

## Components

- `app/estimating/units.py` — `Unit` enum + `UnitDimension` with compatibility
  checks (an area is not a length).
- `app/estimating/formulas.py` — shared, trade-agnostic `Decimal` geometry helpers.
- `app/estimating/quantities.py` — `QuantityBasis`, `QuantityResult`,
  `QuantityFormula` (base class), and the `FormulaRegistry`.

## Formula contract

```python
class QuantityFormula(ABC):
    formula_id: str
    version: str
    output_unit: Unit
    supported_trade_codes: frozenset[str]
    required_inputs: tuple[str, ...]
    def validate_inputs(self, inputs) -> dict[str, Decimal]: ...
    def calculate(self, inputs) -> QuantityResult: ...
```

`calculate()` validates inputs, computes with `Decimal`, rejects negative outputs
(unless explicitly allowed), quantizes to 4 dp, and records the formula id, version,
and exact validated inputs. Formulas are side-effect free and reproducible.

## Guarantees

- `Decimal` only — e.g. `0.1 ft × 0.2 ft = 0.0200 SF` exactly.
- Missing required inputs, unexpected inputs, non-numeric, non-finite, and
  (by default) negative inputs are rejected.
- A formula runs only for its `supported_trade_codes`; requesting it for another
  trade raises `FormulaError`.
- Arbitrary/unknown formula ids are rejected — the API never executes client-supplied
  expressions; it only dispatches to registered formulas.
- The registry is populated at startup from **enabled** trade modules only.

## Painting reference formulas

`painting.wall_gross_area`, `painting.ceiling_area`, `painting.opening_deduction`,
`painting.net_wall_area`, `painting.door_leaf_face_area`,
`painting.frame_schedule_count`, `painting.base_length`. None assume wall heights,
door sizes, opening dimensions, coat counts, or waste factors — every value is a
supplied, verified, or reviewer-approved input. No pixel-scale or computer-vision
measurement is performed.

## Second-trade proof

`demo_concrete.slab_volume(length_ft, width_ft, thickness_in) → CY` uses a different
unit (cubic yards) and formula than any Painting formula, demonstrating the engine is
trade-agnostic.
