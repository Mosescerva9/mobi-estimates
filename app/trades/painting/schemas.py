"""Painting trade schemas: categories, allowed units, and the validated payload."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.estimating.units import Unit

PAINTING_TRADE_CODE = "painting"
PAINTING_MODULE_VERSION = "1.0.0"
PAINTING_SCHEMA_VERSION = "1.0"


class PaintingCategory(str, Enum):
    INTERIOR_WALLS = "interior_walls"
    INTERIOR_CEILINGS = "interior_ceilings"
    EXTERIOR_WALLS = "exterior_walls"
    DOORS = "doors"
    DOOR_FRAMES = "door_frames"
    WINDOW_FRAMES = "window_frames"
    BASE = "base"
    TRIM = "trim"
    COLUMNS = "columns"
    EXPOSED_STRUCTURE = "exposed_structure"
    CONCRETE_COATINGS = "concrete_coatings"
    MASONRY_COATINGS = "masonry_coatings"
    METAL_COATINGS = "metal_coatings"
    WOOD_COATINGS = "wood_coatings"
    FLOOR_COATINGS = "floor_coatings"
    LINE_STRIPING = "line_striping"
    SPECIALTY_COATINGS = "specialty_coatings"
    SURFACE_PREPARATION = "surface_preparation"
    PROTECTION_MASKING = "protection_masking"
    UNCLASSIFIED = "unclassified_painting"


PAINTING_ALLOWED_UNITS: list[Unit] = [
    Unit.SQUARE_FOOT,
    Unit.LINEAR_FOOT,
    Unit.EACH,
    Unit.GALLON,
]

# Categories that do not need a numeric quantity to be approved (qualitative scope).
PAINTING_QUANTITYLESS_CATEGORIES: frozenset[str] = frozenset(
    {
        PaintingCategory.SURFACE_PREPARATION.value,
        PaintingCategory.PROTECTION_MASKING.value,
        PaintingCategory.UNCLASSIFIED.value,
    }
)


class InteriorExterior(str, Enum):
    INTERIOR = "interior"
    EXTERIOR = "exterior"


class PaintingTradeData(BaseModel):
    """Validated Painting-specific payload. All fields optional — never assumed."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    substrate: str | None = Field(default=None, max_length=128)
    existing_condition: str | None = Field(default=None, max_length=255)
    surface_preparation: str | None = Field(default=None, max_length=255)
    primer_required: bool | None = None
    coating_system: str | None = Field(default=None, max_length=255)
    finish_coats: int | None = Field(default=None, ge=0, le=10)
    color_or_finish: str | None = Field(default=None, max_length=128)
    sheen: str | None = Field(default=None, max_length=64)
    interior_exterior: InteriorExterior | None = None
    surface_type: str | None = Field(default=None, max_length=128)
    access_condition: str | None = Field(default=None, max_length=128)
    height_category: str | None = Field(default=None, max_length=64)
    masking_protection_required: bool | None = None
