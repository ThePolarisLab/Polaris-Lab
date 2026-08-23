# Motive Vehicle Utilization — First Business KPI Design

## Status

Design gate only.

This document does **not** change runtime behavior, provider calls, scheduler behavior, database state, Dashboard output, Daily Brief output, business status, alerts, thresholds, or production configuration.

The first Motive consumer integration is already merged and production-certified: healthy Motive vehicle-utilization operational state contributes no Daily Brief **System / Data Health** alert, while degraded/not-started/read-failure states are isolated to that health surface.

This gate defines the first business utilization KPI before any utilization metric is exposed as an executive business signal.

## Current source-of-truth precedence

The KPI must use the **current production ingestion contract**, not older pre-production semantics text that remains in historical files or comments.

The current production contract is:

- endpoint: `GET /v1/vehicle_utilization`;
- latest seven completed `America/Chicago` local days;
- one exact one-day request window per day;
- at most 100 stored organization-owned Motive vehicles selected for the production run;
- exactly one aggregate provider request per day;
- `X-Metric-Units: false` / imperial request mode;
- returned `vehicle.metric_units` must be `false` or the production path fails closed;
- fuel unit is gallons;
- `idle_time` / `driving_time` are seconds;
- provider omission means **unknown / no returned rollup**, never zero activity and never an inactive vehicle;
- latest seven completed days are reread because provider history can change;
- durable reconciliation updates existing exact request-window rows in place.

Where an older semantics document, model comment, or historical design says metric mode, Winnipeg request-window behavior, disabled writer state, or unresolved production scheduling, the later production-ingestion/scheduler contracts supersede those statements for this KPI.

## Business question

The first KPI answers one deliberately narrow question:

> Across the vehicle-day rollups Motive actually returned for the latest certified seven-day production window, what was the average provider-reported vehicle utilization percentage, and how much of the requested vehicle-day population did those observations cover?

It does **not** claim to answer:

- total fleet utilization when provider rollups are missing;
- percent of trucks that were active;
- percent of trucks that were inactive;
- driver productivity;
- revenue productivity;
- route productivity;
- fuel efficiency;
- idle-cost efficiency;
- capacity utilization against dispatch/load availability.

Those require separate business semantics and additional data.

## KPI name

Canonical first KPI name:

`Observed 7-Day Vehicle Utilization`

Do not label it `Fleet Utilization`, `Fleet Average Utilization`, `Active Fleet %`, or `Truck Utilization` without the word **Observed** unless 100% vehicle-day metric coverage is proven for that exact window.

The word `Observed` is required because Motive can omit requested vehicles and omission is not zero.

## Atomic measurement

The atomic measurement is one durable Motive utilization row for one organization-owned vehicle and one exact one-day request window:

`organization_id + motive_vehicle_id + request_window_start + request_window_end`

For the first KPI, only rows where:

- `request_window_start == request_window_end`;
- the day belongs to the latest certified seven-day production window;
- `utilization_percent` is non-null;
- `metric_units == false`;
- the row is tenant-owned by the authenticated organization;

may contribute to the KPI numerator/value set.

`utilization_percent` is unitless. The `metric_units == false` requirement is nevertheless retained as a production-provenance guard so older/pre-production unit-context rows cannot silently enter the first business KPI.

## Authoritative window

Do not calculate the KPI from `today - 7 days` independently.

Resolve the window from the latest successful production checkpoint/history:

1. latest production history for:
   - `provider = motive`;
   - `provider_resource = vehicle_utilization`;
   - `mode = production_recent_window_ingestion`;
   - `status = success`;
2. matching successful production checkpoint;
3. `completed_through` from the persisted checkpoint/history;
4. seven exact `America/Chicago` calendar days ending on `completed_through` inclusive.

If production history/checkpoint health is not successful and mutually consistent, the business KPI is unavailable. The business KPI must never try to repair or bypass the operational-health contract.

## Eligible requested population

For the denominator, use the `selected_vehicle_count` persisted in the latest successful production history for the same seven-day run.

Do **not** use the current `motive_vehicles` table count as the historical denominator because the stored fleet population can change after that run.

Expected requested vehicle-days:

`selected_vehicle_count * 7`

If `selected_vehicle_count` is missing, non-positive, greater than the certified production limit, or inconsistent with the production history contract, the KPI is unavailable.

## Coverage measures

The KPI response must carry coverage explicitly. Coverage is not optional metadata.

### 1. Provider rollup coverage

`provider_rollup_vehicle_days / expected_requested_vehicle_days * 100`

Where `provider_rollup_vehicle_days` is the number of distinct tenant-owned durable rows for the exact seven one-day request windows, regardless of whether `utilization_percent` is null.

This answers: how many requested vehicle-days produced a durable provider rollup?

### 2. Utilization metric coverage

`metric_valid_vehicle_days / expected_requested_vehicle_days * 100`

Where `metric_valid_vehicle_days` is the number of rows eligible for the KPI value set, including non-null `utilization_percent` and certified current production context.

This answers: how many requested vehicle-days are actually usable for the utilization average?

### 3. Missing requested vehicle-days

`expected_requested_vehicle_days - provider_rollup_vehicle_days`

This count is `unknown / omitted` only.

Never synthesize missing rows with `utilization_percent = 0`.

## KPI calculation

KPI value:

`arithmetic mean(utilization_percent across metric-valid observed vehicle-days)`

The arithmetic mean is intentional because every contributing record represents the same one-day request-window duration and one vehicle-day observation.

Do not weight by:

- driving time;
- idle time;
- fuel consumed;
- vehicle mileage;
- engine hours;
- vehicle age;
- truck class;
- revenue;
- loads;
- driver hours.

Those would create different business metrics and need separate designs.

Return the average with deterministic precision, recommended to two decimal places for display while preserving database precision internally.

## Completeness / representativeness policy

The first KPI has two explicit states:

### `available_observed`

At least one metric-valid vehicle-day exists.

The KPI value may be returned, but it must always be shown together with utilization metric coverage.

### `unavailable`

No metric-valid vehicle-day exists, production operational state is not healthy, the certified seven-day window cannot be established, or the denominator contract is invalid.

Do not return `0%` for unavailable data.

### Fleet-representative flag

`fleet_representative = true` **only when utilization metric coverage is exactly 100%** for the certified window.

At anything below 100%, the KPI remains an observed-sample statistic and must not be renamed or summarized as whole-fleet utilization.

This avoids inventing an arbitrary 70%, 80%, or 90% completeness threshold without business evidence.

## Severity and executive-attention policy

The first KPI has **no HIGH / MEDIUM / CRITICAL business severity threshold**.

No utilization percentage, low utilization percentage, or coverage percentage may enter:

- `business_status`;
- `needs_attention`;
- Today's Priority / Today's Plan;
- `watch_items`;
- Daily Brief System / Data Health;
- email / Slack / notification alerts.

Reason: there is not yet a certified business baseline proving what utilization level should be considered good, poor, or actionable for MOR Logistics, and missing provider rollups can materially affect interpretation.

A later threshold-design gate may add attention semantics only after historical distributions and business-operating context are reviewed.

## First consumer surface

The first implementation should be **read-only operations/reporting**, not an executive-attention surface.

Recommended first implementation:

- backend service: a tenant-scoped read model for `Observed 7-Day Vehicle Utilization`;
- authenticated read-only endpoint under the Motive fleet domain;
- permission: `CONNECTOR_READ`;
- zero provider calls;
- zero database writes;
- no new scheduler behavior;
- no automatic refresh beyond reading already-durable rows.

Recommended endpoint shape:

`GET /api/v1/motive/fleet/vehicle-utilization-kpi`

The first endpoint may be certified before any frontend card is added.

Promotion to Executive Dashboard or Daily Brief is deferred to a separate consumer-placement gate after the KPI has been validated against durable production data.

## Sanitized response contract

Recommended response fields:

- `status`: `available_observed` or `unavailable`;
- `kpi`: `observed_7_day_vehicle_utilization`;
- `window_start`;
- `window_end`;
- `request_timezone`: `America/Chicago`;
- `value_percent` or null;
- `selected_vehicle_count`;
- `expected_requested_vehicle_days`;
- `provider_rollup_vehicle_days`;
- `metric_valid_vehicle_days`;
- `missing_requested_vehicle_days`;
- `provider_rollup_coverage_percent`;
- `utilization_metric_coverage_percent`;
- `fleet_representative`;
- `fuel_unit`: `gallons` as context only, not part of the utilization-percent calculation;
- `unit_request_mode`: `imperial`;
- `secrets_exposed`: false.

Do not expose:

- provider vehicle ids;
- VINs;
- license plates;
- raw provider payloads;
- run ids;
- database row ids;
- API keys;
- bearer/session tokens;
- unrestricted sync-history JSON;
- exception strings.

## Query and deduplication rules

The read model must:

- scope every query by authenticated `organization_id`;
- use only the seven exact one-day request windows established from the successful production checkpoint;
- count distinct durable vehicle-day identities;
- fail closed on duplicate fully-populated durable identity if database invariants are unexpectedly violated;
- ignore reporting-period columns for period identity;
- exclude rows outside the certified window;
- exclude rows with null `motive_vehicle_id` from the metric-valid set;
- exclude rows with non-production unit provenance from the metric-valid set;
- never join another tenant's vehicle or history rows.

## Historical reconciliation behavior

Provider historical values can change, and production intentionally rereads the latest seven completed days.

Therefore the KPI is a **current durable view of the latest reconciled seven-day window**, not a frozen audit snapshot of what Motive first returned.

If a later production run reconciles a prior day, the KPI may change without that being considered a KPI bug.

Any trend/comparison implementation must compare reconciled windows using a separately designed snapshot/versioning policy; do not infer stable historical time series from mutable latest-window rows yet.

## Missing-data semantics

The following are forbidden:

- omitted provider rollup => `0% utilization`;
- omitted provider rollup => inactive vehicle;
- omitted provider rollup => parked vehicle;
- omitted provider rollup => no miles;
- omitted provider rollup => no fuel;
- omitted provider rollup => out of service.

Omission means only that the provider did not return a rollup for that requested vehicle/day.

## Why fuel and idle KPIs are not first

`idle_fuel`, `driving_fuel`, `idle_time`, and `driving_time` are certified fields, but a first fuel/idle business KPI would require additional policy such as:

- what constitutes avoidable idle;
- PTO/reefer/yard/maintenance treatment;
- denominator selection;
- cost-per-gallon assumptions;
- engine-on operational context;
- thresholds by equipment/use case.

Those semantics are not yet certified. `utilization_percent` is therefore the narrowest provider-defined business metric suitable for a first read-only KPI.

## Implementation test matrix

At minimum, the future implementation PR must prove:

1. healthy successful production state + valid rows returns `available_observed`;
2. arithmetic mean is correct across exact one-day rows;
3. selected-vehicle denominator comes from matching production history, not current vehicle-table count;
4. expected vehicle-days equals selected vehicles × 7;
5. provider-rollup coverage is correct;
6. utilization-metric coverage is correct;
7. missing provider rows are never synthesized as zero;
8. zero-valued **returned** `utilization_percent` remains a valid zero and is not treated as missing;
9. null utilization is excluded from the value set and reflected in metric coverage;
10. rows outside the checkpoint-derived seven-day window are excluded;
11. multi-day request-window rows are excluded;
12. non-current unit-context rows are excluded from the metric-valid set;
13. no metric-valid rows returns `unavailable`, never `0%`;
14. unhealthy/inconsistent production operational state returns `unavailable`;
15. cross-tenant history, checkpoint, vehicle, and utilization rows cannot influence the result;
16. response does not expose provider ids, VINs, run ids, raw JSON, secrets, or exception strings;
17. endpoint performs zero Motive provider calls;
18. endpoint performs zero database writes;
19. KPI does not change Dashboard `business_status`, `needs_attention`, Today's Plan/Priority, watch items, or Daily Brief health;
20. `fleet_representative` is false at any coverage below 100% and true only at exactly 100% metric coverage.

## Non-goals

This design does not:

- implement the KPI;
- add a frontend card;
- add utilization alerts;
- add idle/fuel efficiency metrics;
- add vehicle rankings;
- add driver rankings;
- classify inactive vehicles;
- change production ingestion;
- change the seven-day horizon;
- change timezone or unit policy;
- change pagination;
- change provider retry behavior;
- change reconciliation;
- change scheduler behavior;
- change database schema;
- backfill data;
- call Motive;
- mutate production state.

## Recommended rollout

1. Merge this design gate.
2. Implement the tenant-scoped read-only KPI service and endpoint only.
3. Add focused tests for denominator, coverage, missing-data semantics, tenant isolation, sanitization, and zero-write/zero-provider-call behavior.
4. Run full required CI.
5. Perform one authenticated production GET of the KPI endpoint after deployment.
6. Compare only sanitized aggregate output against the latest operational-status metadata; do not expose vehicle-level data during certification.
7. After production certification, separately decide whether and how to surface the KPI in an operations view or executive UI.
8. Only after a historical baseline exists, design thresholds/trends/attention behavior in a separate gate.
