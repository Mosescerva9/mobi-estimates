from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Decimal-based quantities and money avoid binary floating-point drift.
PositiveQuantity = Annotated[
    Decimal,
    Field(gt=0, max_digits=18, decimal_places=4),
]
NonNegativeMoney = Annotated[
    Decimal,
    Field(ge=0, max_digits=18, decimal_places=2),
]
ConfidenceScore = Annotated[
    Decimal,
    Field(ge=0, le=1, max_digits=4, decimal_places=3),
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    """Base model used by all canonical Mobi schemas."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )


class ProjectStatus(str, Enum):
    CREATED = "created"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    COMPLETE = "complete"
    FAILED = "failed"


class SheetDiscipline(str, Enum):
    COVER = "cover"
    GENERAL = "general"
    ARCHITECTURAL = "architectural"
    STRUCTURAL = "structural"
    CIVIL = "civil"
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    SPECIFICATION = "specification"
    ADDENDUM = "addendum"
    UNKNOWN = "unknown"


class TradeCode(str, Enum):
    PAINTING = "painting"


class PaintingUnit(str, Enum):
    SQUARE_FOOT = "SF"
    LINEAR_FOOT = "LF"
    EACH = "EA"
    DOOR = "DOOR"
    FRAME = "FRAME"
    GALLON = "GAL"
    LOT = "LOT"


class PaintingSurface(str, Enum):
    WALL = "wall"
    CEILING = "ceiling"
    FLOOR = "floor"
    DOOR = "door"
    FRAME = "frame"
    TRIM = "trim"
    EXTERIOR_WALL = "exterior_wall"
    STRUCTURAL_STEEL = "structural_steel"
    OTHER = "other"


class PricingStatus(str, Enum):
    UNPRICED = "unpriced"
    PRICED = "priced"
    NEEDS_REVIEW = "needs_review"


class SourceReference(StrictModel):
    """
    Mandatory evidence anchor for every extracted quantity.

    Both page_number and sheet_number are required. This prevents a quantity
    from entering the estimate without a traceable plan location.
    """

    page_number: Annotated[int, Field(ge=1, description="1-based PDF page number")]
    sheet_number: Annotated[str, Field(min_length=1, max_length=64)]
    drawing_reference: Annotated[str | None, Field(max_length=128)] = None
    detail_reference: Annotated[str | None, Field(max_length=128)] = None
    evidence: Annotated[
        str,
        Field(
            min_length=3,
            max_length=1000,
            description="What on the referenced page supports the quantity",
        ),
    ]


class Sheet(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    page_number: Annotated[int, Field(ge=1)]
    sheet_number: Annotated[str, Field(min_length=1, max_length=64)]
    title: Annotated[str, Field(min_length=1, max_length=255)]
    discipline: SheetDiscipline = SheetDiscipline.UNKNOWN
    source_file_name: Annotated[str, Field(min_length=1, max_length=255)]
    page_width_points: Annotated[Decimal | None, Field(gt=0)] = None
    page_height_points: Annotated[Decimal | None, Field(gt=0)] = None
    created_at: datetime = Field(default_factory=utc_now)


class PaintingScopeItem(StrictModel):
    """Canonical scope item for the initial Painting trade."""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    trade: Literal[TradeCode.PAINTING] = TradeCode.PAINTING
    description: Annotated[str, Field(min_length=3, max_length=500)]
    location: Annotated[str, Field(min_length=1, max_length=255)]
    surface: PaintingSurface
    substrate: Annotated[str, Field(min_length=1, max_length=128)]
    coating_system: Annotated[str, Field(min_length=1, max_length=255)]
    coats: Annotated[int, Field(ge=1, le=10)]
    quantity: PositiveQuantity
    unit: PaintingUnit
    source: SourceReference
    confidence_score: ConfidenceScore
    review_required: bool = True
    assumptions: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = ()
    exclusions: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = ()
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def low_confidence_must_be_reviewed(self) -> PaintingScopeItem:
        if self.confidence_score < Decimal("0.900") and not self.review_required:
            raise ValueError(
                "Scope items below 0.900 confidence must set review_required=true"
            )
        return self


# Public canonical name requested for the MVP. The alias keeps the schema
# explicitly painting-focused without sacrificing a stable domain name.
ScopeItem = PaintingScopeItem


class Trade(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    code: Literal[TradeCode.PAINTING] = TradeCode.PAINTING
    name: Literal["Painting"] = "Painting"
    csi_division: Literal["09"] = "09"
    scope_items: tuple[PaintingScopeItem, ...] = ()

    @field_validator("scope_items")
    @classmethod
    def scope_items_must_match_project(
        cls, items: tuple[PaintingScopeItem, ...], info
    ) -> tuple[PaintingScopeItem, ...]:
        project_id = info.data.get("project_id")
        if project_id is not None:
            for item in items:
                if item.project_id != project_id:
                    raise ValueError("Every scope item must belong to the trade project_id")
        return items


class PricingBreakdown(StrictModel):
    """
    Values supplied only by the deterministic Python pricing engine.

    This schema validates stored results; it performs no pricing arithmetic.
    """

    currency: Literal["USD"] = "USD"
    material_cost: NonNegativeMoney
    labor_cost: NonNegativeMoney
    equipment_cost: NonNegativeMoney = Decimal("0.00")
    subcontract_cost: NonNegativeMoney = Decimal("0.00")
    indirect_cost: NonNegativeMoney = Decimal("0.00")
    direct_cost: NonNegativeMoney
    overhead_amount: NonNegativeMoney
    profit_amount: NonNegativeMoney
    total_price: NonNegativeMoney
    calculation_engine_version: Annotated[str, Field(min_length=1, max_length=64)]
    calculated_at: datetime = Field(default_factory=utc_now)


class EstimateLineItem(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    scope_item_id: UUID
    trade: Literal[TradeCode.PAINTING] = TradeCode.PAINTING
    cost_code: Annotated[str, Field(min_length=1, max_length=64)]
    description: Annotated[str, Field(min_length=3, max_length=500)]
    quantity: PositiveQuantity
    unit: PaintingUnit
    source: SourceReference
    pricing_status: PricingStatus = PricingStatus.UNPRICED
    pricing: PricingBreakdown | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def pricing_state_is_consistent(self) -> EstimateLineItem:
        if self.pricing_status == PricingStatus.PRICED and self.pricing is None:
            raise ValueError("pricing is required when pricing_status='priced'")
        if self.pricing_status == PricingStatus.UNPRICED and self.pricing is not None:
            raise ValueError("pricing must be null when pricing_status='unpriced'")
        return self


class Project(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    name: Annotated[str, Field(min_length=1, max_length=255)]
    contractor_name: Annotated[str | None, Field(max_length=255)] = None
    status: ProjectStatus = ProjectStatus.CREATED
    original_file_name: Annotated[str | None, Field(max_length=255)] = None
    page_count: Annotated[int, Field(ge=0)] = 0
    sheets: tuple[Sheet, ...] = ()
    trades: tuple[Trade, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def child_records_must_match_project(self) -> Project:
        for sheet in self.sheets:
            if sheet.project_id != self.id:
                raise ValueError("Every sheet must belong to this project")
        for trade in self.trades:
            if trade.project_id != self.id:
                raise ValueError("Every trade must belong to this project")
        return self


class ProjectStatusResponse(StrictModel):
    project_id: UUID
    name: str
    status: ProjectStatus
    original_file_name: str | None
    page_count: int
    file_sha256: str | None = None
    file_size_bytes: int = 0
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None
