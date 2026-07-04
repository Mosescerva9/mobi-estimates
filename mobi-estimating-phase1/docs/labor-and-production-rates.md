# Loaded Labor & Production Rates

**Loaded labor rate ≠ raw wage.** A loaded rate is computed in Python as the base
wage plus each burden component (payroll taxes, workers' comp, GL allocation,
health/retirement, paid time, union fringes, small tools when intentionally treated
as labor burden, other) — each added exactly once (never doubled). A contractor may
instead supply a verified **all-in** rate; rates are flagged `component_calculated`
or `manual_all_in`. Raw wage is never silently substituted for the loaded rate.

**Production rate ≠ program duration.** Production rates describe physical output and
are separate from schedule/program constraints. The system never accelerates
production because a schedule is short; overtime/shift/congestion/restricted access
are explicit adjustments.

## Production bases (never mixed silently)

- `units_per_labor_hour` → labor_hours = qty ÷ value (uses a **loaded labor rate**)
- `labor_hours_per_unit` → labor_hours = qty × value (loaded labor rate)
- `units_per_crew_hour` → crew_hours = qty ÷ value (uses a **loaded crew-hour rate**)
- `crew_hours_per_unit` → crew_hours = qty × value (loaded crew-hour rate)
- `manual_allowance` → explicit labor-hour allowance

Labor hours and crew hours are tracked **separately** on every line item. A missing
production rate or crew blocks labor pricing for that assembly (visible exception).

## Crews

A crew lists member classifications + counts and a loaded crew-hour rate, supplied
directly (verified) or computed in Python as Σ(member.count × member loaded rate).
