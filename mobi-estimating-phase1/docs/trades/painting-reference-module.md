# Painting Reference Trade Module

Painting (CSI Division 09) is the **first reference** trade module. It exists to
prove the shared trade-agnostic architecture works end-to-end; it is not a claim of
complete painting-takeoff automation. Painting logic lives entirely in
`app/trades/painting/`, never in the shared core.

## Categories

`interior_walls, interior_ceilings, exterior_walls, doors, door_frames,
window_frames, base, trim, columns, exposed_structure, concrete_coatings,
masonry_coatings, metal_coatings, wood_coatings, floor_coatings, line_striping,
specialty_coatings, surface_preparation, protection_masking, unclassified_painting`.

`surface_preparation`, `protection_masking`, and `unclassified_painting` do not
require a numeric quantity to be approved.

## Allowed units

`SF`, `LF`, `EA`, `GAL`.

## `trade_data` payload (all optional — never assumed)

`substrate, existing_condition, surface_preparation, primer_required, coating_system,
finish_coats, color_or_finish, sheen, interior_exterior, surface_type,
access_condition, height_category, masking_protection_required`. Unknown fields are
rejected.

## Routing

Multi-signal and conservative: blocks unverified sheets (`blocked_unverified`),
blocks OCR-required sheets (`blocked_ocr`), marks `eligible` when a painting/finish
keyword appears in the verified sheet text, `excluded` for clearly non-painting
disciplines (E/P/M/FP/FA/T) with no painting signal, and `requires_review` otherwise.
Discipline prefixes are one signal among several — never the sole basis.

## Deterministic formulas

See [deterministic-quantity-engine.md](../deterministic-quantity-engine.md). None
assume default dimensions or coat counts.

## Prompts (versioned)

`sheet_classifier_v1`, `schedule_extractor_v1`, `notes_extractor_v1`,
`scope_extractor_v1`. Every prompt carries the mandatory safety block: return only
schema-valid data; no pricing; no derived quantities; no inferred dimensions/sizes;
no invented materials/assemblies/scope; cite every item to supplied evidence; return
null when absent; flag conflicts; do not claim a document was reviewed unless
supplied; no cross-trade scope. A test asserts these instructions remain present.

## What it deliberately does NOT do

No pricing, no markup/profit, no OCR, no computer-vision measurement, no assumed wall
heights/door sizes/opening dimensions/coat counts/waste factors, and no
auto-approval. Detected sheet numbers are candidates; only verified sheets anchor
trusted evidence.
