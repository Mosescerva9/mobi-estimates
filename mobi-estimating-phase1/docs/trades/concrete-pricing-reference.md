# Concrete Pricing Reference (demonstration)

Reference/development module proving the pricing core is trade-agnostic. Fictional
values only; **not** production-complete.

## `CONC-SLAB` (slab_on_grade, CY) — structurally different from painting

- Material `MAT-CONC-MIX` by **cubic yard** with explicit waste.
- Material `MAT-REBAR` (lbs per CY) with waste.
- **Crew-hour** placement + finishing labor (`PROD-CONC-PLACE`, `PROD-CONC-FINISH`
  on crew `CREW-CONC`) — distinct from painting's labor-hour basis.
- Equipment `EQ-PUMP` (day basis) with a minimum charge.
- Requires `mix_design` trade data.

This demonstrates different units (CY), formulas, components, crew-hour production,
and equipment with no Painting-specific code path.
