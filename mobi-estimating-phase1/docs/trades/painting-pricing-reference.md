# Painting Pricing Reference

The first **complete reference** assembly set. Structure only — no market prices
(populate a cost book; tests use fictional values).

## Assemblies (templates)

- `PT-INT-WALL` (interior_walls, SF): surface-prep labor, primer material, finish
  labor, finish material, masking other-direct. Requires `coating_system`, `finish_coats`.
- `PT-INT-CEILING` (interior_ceilings, SF): finish labor + material.
- `PT-DOOR-FRAME` (door_frames, EA): frame labor + finish material. Requires `coating_system`.
- `PT-SURFACE-PREP` (surface_preparation, SF): prep labor only.

## Cost-item codes referenced

Labor `PAINTER`; production `PROD-PT-PREP`, `PROD-PT-FINISH`, `PROD-PT-FRAME`;
material `MAT-PT-PRIMER`, `MAT-PT-FINISH` (with coverage); other-direct `ODC-MASKING`.

Never assumes coats, substrate, surface prep, coverage, or height/access — missing
required trade data blocks automatic mapping. The module proves the architecture; it
is not nationwide production pricing.
