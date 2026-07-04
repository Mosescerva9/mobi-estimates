# Cost-Book CSV Import

Lean, validated CSV import for `labor_rates`, `material_rates`, `equipment_rates`,
and `production_rates` into a **draft** version. Preview first, then commit; a failed
file imports nothing (atomic). Unknown columns, invalid decimals, invalid units, and
duplicate identifiers are rejected. All example values below are **fictional**.

## Endpoints

- `POST /api/v1/cost-books/{id}/versions/{vid}/imports/{kind}/preview` (body = CSV text)
- `POST /api/v1/cost-books/{id}/versions/{vid}/imports/{kind}/commit` (body = CSV text)

## Templates (fictional values)

labor_rates:
```
classification,trade_code,loaded_rate,effective_date,source_id
PAINTER,painting,50.00,2026-01-01,<source-uuid>
```

material_rates:
```
material_code,description,trade_code,purchase_unit,unit_cost,effective_date,source_id
MAT-PT-FINISH,Finish coat,painting,GAL,40.00,2026-01-01,<source-uuid>
```

equipment_rates:
```
equipment_code,description,basis,base_rate,effective_date,source_id
EQ-PUMP,Concrete pump,day,1200.00,2026-01-01,<source-uuid>
```

production_rates:
```
production_code,trade_code,scope_category,quantity_unit,basis,value,effective_date,source_id
PROD-PT-FINISH,painting,interior_walls,SF,units_per_labor_hour,150,2026-01-01,<source-uuid>
```
