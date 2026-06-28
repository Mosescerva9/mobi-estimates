"""Pricing enums, API request/response models, and result value objects.

Canonical financial math happens in the engine using ``Decimal`` (see ``money``).
These Pydantic models validate the API boundary (``extra="forbid"``) and accept
documented JSON decimal strings.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class CostBookStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class VersionStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SourceType(str, Enum):
    CONTRACTOR_RATE = "contractor_rate"
    SUPPLIER_QUOTE = "supplier_quote"
    VENDOR_CATALOG = "vendor_catalog"
    HISTORICAL_JOB_COST = "historical_job_cost"
    SUBCONTRACTOR_QUOTE = "subcontractor_quote"
    EQUIPMENT_RENTAL_QUOTE = "equipment_rental_quote"
    INTERNAL_PRICE_BOOK = "internal_price_book"
    REVIEWER_ENTERED = "reviewer_entered"
    LICENSED_DATABASE = "licensed_database"
    OTHER = "other"


class LaborRateType(str, Enum):
    COMPONENT_CALCULATED = "component_calculated"
    MANUAL_ALL_IN = "manual_all_in"


class ProductionBasis(str, Enum):
    UNITS_PER_LABOR_HOUR = "units_per_labor_hour"
    LABOR_HOURS_PER_UNIT = "labor_hours_per_unit"
    UNITS_PER_CREW_HOUR = "units_per_crew_hour"
    CREW_HOURS_PER_UNIT = "crew_hours_per_unit"
    UNITS_PER_SHIFT = "units_per_shift"
    MANUAL_ALLOWANCE = "manual_allowance"


CREW_BASES = frozenset(
    {ProductionBasis.UNITS_PER_CREW_HOUR, ProductionBasis.CREW_HOURS_PER_UNIT}
)
LABOR_BASES = frozenset(
    {ProductionBasis.UNITS_PER_LABOR_HOUR, ProductionBasis.LABOR_HOURS_PER_UNIT}
)


class EquipmentRateBasis(str, Enum):
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    EACH = "each"
    SHIFT = "shift"


DURATION_EQUIPMENT_BASES = frozenset(
    {EquipmentRateBasis.HOUR, EquipmentRateBasis.DAY,
     EquipmentRateBasis.WEEK, EquipmentRateBasis.MONTH, EquipmentRateBasis.SHIFT}
)


class ComponentType(str, Enum):
    LABOR = "labor"
    MATERIAL = "material"
    EQUIPMENT = "equipment"
    SUBCONTRACT = "subcontract"
    OTHER_DIRECT = "other_direct"


class AdjustmentType(str, Enum):
    DISCOUNT = "discount"
    ESCALATION = "escalation"
    SALES_TAX = "sales_tax"
    BOND = "bond"
    INSURANCE = "insurance"
    OVERHEAD = "overhead"
    PROFIT = "profit"
    CONTINGENCY = "contingency"
    ROUNDING = "rounding"
    MANUAL = "manual"


class MarkupMethod(str, Enum):
    MARKUP = "markup"
    MARGIN = "margin"


class IndirectBasis(str, Enum):
    FIXED = "fixed"
    QUANTITY_RATE = "quantity_rate"
    DURATION_RATE = "duration_rate"
    PERCENT = "percent"
    MANUAL_ALLOWANCE = "manual_allowance"


class ExceptionSeverity(str, Enum):
    INFORMATION = "information"
    WARNING = "warning"
    BLOCKING = "blocking"


class ExceptionCode(str, Enum):
    SCOPE_NOT_APPROVED = "scope_not_approved"
    MISSING_ASSEMBLY_MAPPING = "missing_assembly_mapping"
    AMBIGUOUS_ASSEMBLY_MAPPING = "ambiguous_assembly_mapping"
    MISSING_MATERIAL_RATE = "missing_material_rate"
    MISSING_LABOR_RATE = "missing_labor_rate"
    MISSING_PRODUCTION_RATE = "missing_production_rate"
    MISSING_CREW = "missing_crew"
    MISSING_EQUIPMENT_DURATION = "missing_equipment_duration"
    MISSING_UNIT_CONVERSION = "missing_unit_conversion"
    INCOMPATIBLE_UNIT = "incompatible_unit"
    EXPIRED_RATE = "expired_rate"
    UNVERIFIED_SOURCE = "unverified_source"
    MISSING_SUBCONTRACT_REVIEW = "missing_subcontract_review"
    CIRCULAR_ASSEMBLY = "circular_assembly"
    MISSING_INDIRECT_DURATION = "missing_indirect_duration"
    MISSING_TAX_TREATMENT = "missing_tax_treatment"
    MISSING_ASSEMBLY_INPUT = "missing_assembly_input"
    INCOMPLETE_TRADE_DATA = "incomplete_trade_data"
    CALCULATION_FAILURE = "calculation_failure"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class EstimateStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class EstimateVersionStatus(str, Enum):
    DRAFT = "draft"
    PRICING = "pricing"
    NEEDS_REVIEW = "needs_review"
    PRICED = "priced"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


# ---------------------------------------------------------------------------
# API base
# ---------------------------------------------------------------------------
class PricingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ---- Cost books -----------------------------------------------------------
class CostBookCreate(PricingModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    currency: str = "USD"
    region: str | None = Field(default=None, max_length=128)
    market: str | None = Field(default=None, max_length=128)
    organization: str | None = Field(default=None, max_length=255)


class CostBookVersionCreate(PricingModel):
    version_label: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)
    effective_date: date
    expiration_date: date | None = None
    pricing_date: date
    source_notes: str = Field(default="", max_length=2000)


# ---- Cost inputs ----------------------------------------------------------
class CostSourceCreate(PricingModel):
    source_type: SourceType
    source_name: str = Field(min_length=1, max_length=255)
    contact: str | None = Field(default=None, max_length=255)
    reference_number: str | None = Field(default=None, max_length=128)
    quote_date: date | None = None
    effective_date: date
    expiration_date: date | None = None
    region: str | None = Field(default=None, max_length=128)
    project_specific: bool = False
    notes: str = Field(default="", max_length=2000)
    attachment_ref: str | None = Field(default=None, max_length=512)
    verified: bool = False


class LaborBurdenComponents(PricingModel):
    payroll_taxes: Decimal | None = None
    workers_comp: Decimal | None = None
    general_liability: Decimal | None = None
    health_benefits: Decimal | None = None
    retirement: Decimal | None = None
    paid_time: Decimal | None = None
    union_fringes: Decimal | None = None
    small_tools: Decimal | None = None
    other: Decimal | None = None


class LaborRateCreate(PricingModel):
    classification: str = Field(min_length=1, max_length=64)
    trade_code: str = Field(min_length=2, max_length=64)
    region: str | None = Field(default=None, max_length=128)
    rate_type: LaborRateType = LaborRateType.COMPONENT_CALCULATED
    base_hourly_wage: Decimal | None = None
    burden: LaborBurdenComponents = Field(default_factory=LaborBurdenComponents)
    manual_all_in_rate: Decimal | None = None
    effective_date: date
    expiration_date: date | None = None
    source_id: UUID
    notes: str = Field(default="", max_length=1000)


class CrewMember(PricingModel):
    classification: str = Field(min_length=1, max_length=64)
    count: int = Field(ge=1)


class CrewCreate(PricingModel):
    crew_code: str = Field(min_length=1, max_length=64)
    trade_code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    members: list[CrewMember] = Field(min_length=1)
    # A verified all-in loaded crew-hour rate. If omitted, it is computed in Python
    # from member counts × their loaded labor rates in the same cost-book version.
    loaded_crew_hour_rate: Decimal | None = None
    notes: str = Field(default="", max_length=1000)


class ProductionRateCreate(PricingModel):
    trade_code: str = Field(min_length=2, max_length=64)
    scope_category: str = Field(min_length=1, max_length=64)
    assembly_code: str | None = Field(default=None, max_length=64)
    production_code: str = Field(min_length=1, max_length=64)
    quantity_unit: str = Field(min_length=1, max_length=16)
    basis: ProductionBasis
    value: Decimal
    crew_code: str | None = Field(default=None, max_length=64)
    conditions: dict[str, Any] = Field(default_factory=dict)
    height_class: str | None = None
    complexity_class: str | None = None
    source_id: UUID
    effective_date: date
    expiration_date: date | None = None
    verified: bool = False
    notes: str = Field(default="", max_length=1000)


class MaterialRateCreate(PricingModel):
    material_code: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    manufacturer: str | None = None
    product_identifier: str | None = None
    trade_code: str = Field(min_length=2, max_length=64)
    purchase_unit: str = Field(min_length=1, max_length=16)
    coverage_per_unit: Decimal | None = None
    coverage_unit: str | None = Field(default=None, max_length=16)
    unit_cost: Decimal
    taxable: bool = True
    freight_included: bool = False
    waste_included: bool = False
    source_id: UUID
    effective_date: date
    expiration_date: date | None = None
    region: str | None = None
    notes: str = Field(default="", max_length=1000)


class EquipmentRateCreate(PricingModel):
    equipment_code: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    trade_code: str | None = None
    basis: EquipmentRateBasis
    base_rate: Decimal
    delivery: Decimal | None = None
    pickup: Decimal | None = None
    fuel: Decimal | None = None
    operator_included: bool = False
    mobilization_included: bool = False
    minimum_charge: Decimal | None = None
    source_id: UUID
    effective_date: date
    expiration_date: date | None = None
    notes: str = Field(default="", max_length=1000)


class SubcontractQuoteCreate(PricingModel):
    project_id: UUID | None = None
    trade_code: str = Field(min_length=2, max_length=64)
    vendor_label: str = Field(min_length=1, max_length=255)
    quote_reference: str | None = None
    quote_date: date | None = None
    expiration_date: date | None = None
    base_amount: Decimal
    alternates: Decimal | None = None
    taxes: Decimal | None = None
    bonds: Decimal | None = None
    insurance: Decimal | None = None
    included_scope: str = Field(default="", max_length=2000)
    excluded_scope: str = Field(default="", max_length=2000)
    clarifications: str = Field(default="", max_length=2000)
    leveling_adjustment: Decimal | None = None
    source_id: UUID
    verified: bool = False
    reviewer_notes: str = Field(default="", max_length=2000)


class OtherDirectCostCreate(PricingModel):
    # A cost-book "other direct cost" rate item referenced by assembly components.
    odc_code: str = Field(min_length=1, max_length=64)
    cost_type: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    unit: str = Field(min_length=1, max_length=16)
    unit_rate: Decimal
    trade_code: str | None = None
    taxable: bool = False
    source_id: UUID
    notes: str = Field(default="", max_length=1000)


# ---- Assemblies (structure only; no prices) -------------------------------
class AssemblyComponentInput(PricingModel):
    component_type: ComponentType
    cost_item_ref: str = Field(min_length=1, max_length=64)
    quantity_factor: Decimal = Decimal("1")
    waste_factor: Decimal | None = None
    production_ref: str | None = None
    crew_ref: str | None = None
    conversion_id: str | None = None
    minimum_charge: Decimal | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    sequence: int = 0


class AssemblyCreate(PricingModel):
    trade_code: str = Field(min_length=2, max_length=64)
    assembly_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    scope_category: str = Field(min_length=1, max_length=64)
    input_unit: str = Field(min_length=1, max_length=16)
    output_basis: str = Field(default="per_input_unit", max_length=64)
    required_trade_data: list[str] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)
    required_quantity_basis: list[str] = Field(default_factory=list)
    components: list[AssemblyComponentInput] = Field(default_factory=list)
    notes: str = Field(default="", max_length=1000)


# ---- Mappings / adjustments / indirects -----------------------------------
class AssemblyMappingRequest(PricingModel):
    assembly_code: str = Field(min_length=1, max_length=64)
    reviewer_id: str = Field(default="system", max_length=128)
    notes: str = Field(default="", max_length=1000)


class AdjustmentInput(PricingModel):
    adjustment_type: AdjustmentType
    name: str = Field(min_length=1, max_length=128)
    method: MarkupMethod | None = None  # for overhead/profit
    percent: Decimal | None = None
    fixed_amount: Decimal | None = None
    base_categories: list[str] = Field(default_factory=list)
    sequence: int = 0
    rationale: str = Field(default="", max_length=1000)


class IndirectInput(PricingModel):
    name: str = Field(min_length=1, max_length=128)
    basis: IndirectBasis
    amount: Decimal | None = None
    rate: Decimal | None = None
    quantity: Decimal | None = None
    duration: Decimal | None = None
    percent: Decimal | None = None
    base_categories: list[str] = Field(default_factory=list)
    taxable: bool = False
    notes: str = Field(default="", max_length=1000)


# ---- Estimates ------------------------------------------------------------
class EstimateCreate(PricingModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    cost_book_version_id: UUID
    currency: str = "USD"
    trade_codes: list[str] | None = None
    scope_item_ids: list[UUID] | None = None
    inclusions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    clarifications: list[str] = Field(default_factory=list)
    indirects: list[IndirectInput] = Field(default_factory=list)
    adjustments: list[AdjustmentInput] = Field(default_factory=list)
    markup_method: MarkupMethod = MarkupMethod.MARKUP


class LineItemOverride(PricingModel):
    field: str = Field(min_length=1, max_length=64)
    new_value: Decimal
    reason: str = Field(min_length=1, max_length=1000)
    reviewer_id: str = Field(default="system", max_length=128)


class ApproveRequest(PricingModel):
    reviewer_id: str = Field(default="system", max_length=128)
    notes: str = Field(default="", max_length=2000)
