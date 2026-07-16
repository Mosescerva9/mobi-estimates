# OpenTakeoff Provider Adapter Design

Updated: 2026-07-16T00:35Z

## Design goal
Integrate OpenTakeoff without coupling Mobi’s estimating workflow to OpenTakeoff internals. OpenTakeoff is one provider behind Mobi’s provider-neutral takeoff boundary.

## Provider set
Implemented/updated in this slice:

```text
TakeoffProvider
├── OpenTakeoffProvider
├── MobiNativeTakeoffProvider
├── ManualTakeoffImportProvider
├── HumanVerifiedTakeoffProvider
├── CustomerSuppliedProvider
├── AuthorizedThirdPartyProvider
├── FutureCadBimProvider
└── FutureThirdPartyProvider
```

## Canonical schema delta started
The existing `CanonicalEvidence` contract already contained most required fields. This slice added:
- `takeoff_provider = open_takeoff`
- `takeoff_provider = customer_supplied`
- `takeoff_provider = future_third_party`
- optional `condition`
- optional `scale`

Implementation note: these DB changes are carried by forward migrations (`mobi-estimating-phase1` SQLite migration v38 and Supabase `0025_canonical_takeoff_evidence_provider_fields.sql`) rather than mutating the already-merged/applied canonical evidence migrations.

No synonym scanning was added. Unknown provider payload keys still quarantine.

## OpenTakeoff adapter boundary
The production adapter should have these layers:

1. **Project document resolver**
   - Accept Mobi `project_id` / `document_id` / `sheet_id` from server-owned context.
   - Resolve tenant-scoped storage path or signed local worker path.
   - Never trust tenant/company/document identity from OpenTakeoff payloads.

2. **OpenTakeoff execution client**
   - Support MCP first (`npx -y opentakeoff-mcp` only for development/spike).
   - Production target should be stable worker/service, not Claude terminal.
   - Future targets: internal server code, worker service, direct library integration.

3. **Scale workflow**
   - Load plan and capture detected scale as a suggestion.
   - Require explicit confirmation before measured quantities become evidence.
   - Preserve scale source (`detected`, `calibrated`, `manual`, `confirmed_by`).

4. **Measurement commands**
   - `one_click` for area traces.
   - `measure_polygon` for manual/AI-suggested polygons.
   - `measure_line` for linear takeoffs.
   - Count workflow via committed shape/count records where supported.
   - Deductions as `role: deduct`/negative or linked deduction records.

5. **Normalizer**
   - Map only explicit OpenTakeoff fields to canonical payload fields.
   - Preserve shape id as `provider_record_id`.
   - Preserve sheet/page/region/geometry in canonical + raw provider audit store.
   - Map `condition`, `quantity`, `unit`, `scale`, `confidence`, `measurement_method` explicitly.
   - Quarantine unknown/unmapped provider payloads.

6. **Persistence**
   - Write only validated `CanonicalEvidence` rows.
   - Store server-owned tenant/company/project/document/sheet identity.
   - Keep marked-plan output in tenant-scoped storage if available.

7. **Manual correction**
   - Failed/uncertain traces become `review_status=blocked` or quarantined provider records.
   - Estimator correction creates `human_verified` or `corrected` evidence with audit history.

## Service contract sketch

```python
class OpenTakeoffAdapter:
    def load_project_plan(context, document_ref) -> LoadedPlan: ...
    def list_sheets(session) -> list[SheetInfo]: ...
    def suggest_scale(session, sheet) -> ScaleSuggestion | None: ...
    def confirm_scale(session, sheet, scale_confirmation) -> ConfirmedScale: ...
    def one_click_area(session, sheet, point, condition) -> ProviderMeasurement: ...
    def measure_polygon(session, sheet, vertices, condition) -> ProviderMeasurement: ...
    def measure_line(session, sheet, points, condition) -> ProviderMeasurement: ...
    def export_takeoff(session) -> ProviderTakeoffExport: ...
    def normalize(measurement, context) -> CanonicalEvidence: ...
```

## Production constraints
- Customer processing must not depend on Claude Code or a terminal session.
- No customer documents sent to unnecessary AI models.
- OpenTakeoff processing outputs must stay tenant-scoped.
- Raster fallback is required before launch for scanned plan sets.
