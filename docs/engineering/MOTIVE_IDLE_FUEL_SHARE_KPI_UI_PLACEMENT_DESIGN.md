# Motive Vehicle Idle-Fuel Share — Dashboard Placement Design

## Status

Design gate only.

This document defines the first Polaris frontend placement for the already production-certified `Observed 7-Day Vehicle Idle-Fuel Share` KPI.

It does **not** implement frontend runtime code, add provider calls, write database state, change ingestion or scheduler behavior, add snapshots/history, add fuel-cost logic, add business thresholds, alter Daily Brief behavior, or change any executive attention/action surface.

Certified read endpoint:

`GET /api/v1/motive/fleet/vehicle-idle-fuel-share-kpi`

The backend KPI is descriptive only. It reports the share of combined observed `idle_fuel + driving_fuel` volume that Motive reported as idle fuel, with independent vehicle-day coverage and representativeness metadata.

## Placement decision

Extend the existing **Fleet / Operations** reporting card on the Executive Dashboard.

Do not add:

- a second top-level Dashboard card;
- a new navigation route;
- a Needs Attention item;
- a Watch Item;
- a Daily Brief item;
- an alert banner;
- a fuel-cost or savings card.

The current Fleet / Operations card already contains:

1. `Observed 7-Day Vehicle Utilization`;
2. `Observed 7-Day Vehicle Idle-Time Share`;
3. utilization-only `30-Day Observation History`.

The third current KPI belongs inside the same **Current Observations** region.

## Current-observation layout

The Fleet / Operations card should contain three independent KPI blocks:

1. `Observed 7-Day Vehicle Utilization`
2. `Observed 7-Day Vehicle Idle-Time Share`
3. `Observed 7-Day Vehicle Idle-Fuel Share`

Recommended desktop layout:

- one row of three neutral columns with equal reporting weight;
- utilization first;
- idle-time share second;
- idle-fuel share third;
- subtle neutral dividers between adjacent blocks;
- each block owns its own title, value, coverage, completeness, descriptor, and seven-day window.

Recommended tablet/narrow layout:

- wrap or stack the blocks so content remains readable;
- preserve source order: utilization, idle-time share, idle-fuel share;
- no horizontal page overflow;
- do not shrink supporting text to the point that coverage/completeness becomes secondary or illegible.

The three KPI blocks are observations, not a scorecard. Their equal visual weight must not imply they add to 100%, are components of one formula, or represent a combined business-health score.

## Relationship to utilization history

The existing `30-Day Observation History` remains **utilization-only**.

The Fleet / Operations card should remain structured as:

1. `FLEET / OPERATIONS`
2. `Current Observations`
   - current utilization
   - current idle-time share
   - current idle-fuel share
3. subtle divider
4. utilization-only `30-Day Observation History`
5. utilization history state/chart

The idle-fuel KPI has **no certified snapshot/history endpoint** in this gate.

Therefore:

- do not place idle-fuel points on the utilization chart;
- do not reconstruct idle-fuel history from mutable utilization rows;
- do not create an idle-fuel trend placeholder;
- do not relabel the utilization history as a combined fleet trend;
- do not compare idle-time and idle-fuel share as a trend pair.

Any future idle-fuel snapshot/history design requires a separate gate.

## Consumer endpoint and request behavior

The frontend may add exactly one new read request:

`/api/v1/motive/fleet/vehicle-idle-fuel-share-kpi`

Use the existing authenticated `apiClient.get(...)` path so bearer/session and organization context remain centralized.

The frontend must:

- make zero Motive provider calls directly;
- make zero database writes;
- invoke no Motive sync, verify, reconcile, scheduler, ingestion, or internal route;
- add no backend endpoint or migration;
- add no polling or timer refresh;
- issue at most one idle-fuel-share GET during initial Dashboard load;
- issue at most one additional idle-fuel-share GET when the existing Dashboard Refresh action is used.

The Dashboard core request and all three current Motive KPI requests must remain independent.

The existing `Promise.allSettled` pattern or equivalent independent failure behavior is required.

The utilization-history child remains independently responsible for its own read-only history request.

## Independent load/failure semantics

The idle-fuel-share KPI must have its own state:

- payload;
- loading;
- request failure.

It must not reuse utilization or idle-time request state as a proxy.

Required behavior includes:

- all current KPI reads succeed: render all three observations;
- idle-fuel request fails: utilization and idle-time remain normal; idle-fuel block shows neutral reporting-unavailable wording;
- utilization request fails: idle-time and idle-fuel remain normal;
- idle-time request fails: utilization and idle-fuel remain normal;
- any two KPI requests fail: the surviving current observation remains normal;
- all three KPI requests fail while Dashboard core succeeds: Fleet / Operations remains present with neutral unavailable states; attention/action sections remain unaffected;
- Dashboard core failure: existing Dashboard failure behavior remains authoritative.

A failure of one KPI must never overwrite, hide, or reclassify another KPI.

## Idle-fuel-share presentation contract

Presentation title:

`Observed 7-Day Vehicle Idle-Fuel Share`

Neutral descriptor:

`Share of observed idle + driving fuel reported as idle fuel.`

This descriptor is required so the value is not mistaken for:

- percent of total company fuel purchases;
- percent of total engine fuel outside Motive's rollup definition;
- avoidable fuel;
- wasted fuel;
- fuel cost;
- percent of clock time.

When `status == available_observed`, display:

- `value_percent` formatted to two decimals;
- coverage as `metric_valid_vehicle_days / expected_requested_vehicle_days vehicle-days (idle_fuel_metric_coverage_percent%)`;
- completeness wording:
  - `Full vehicle-day coverage` only when `fleet_representative == true`;
  - otherwise `Partial observation — not fleet representative`;
- observation window: `window_start to window_end · request_timezone`.

The UI does not need to display raw summed idle or driving gallons because the public backend contract intentionally does not expose them.

A subtle metadata note such as `Fuel basis: gallons` is optional. If displayed, it is unit context only and must not imply the percentage itself is measured in gallons.

## Valid zero and unavailable

A returned numeric `value_percent = 0` is a valid observed value and must render as `0.00%` when the payload otherwise satisfies the certified contract.

A returned `100` is likewise a valid descriptive result if the backend contract is otherwise valid.

Do not confuse valid zero with:

- `status=unavailable`;
- missing payload;
- request failure;
- null/malformed value.

If the backend returns `status != available_observed`, render `Unavailable` rather than a numeric zero.

If the request fails, use neutral wording such as:

`Idle-fuel-share reporting temporarily unavailable.`

Do not expose exception text.

## Frontend payload validation

The presentation layer must fail closed on malformed payloads before displaying a percentage.

For an available observation, require at minimum:

- `status == available_observed`;
- finite numeric `value_percent` within 0–100;
- non-negative integer `metric_valid_vehicle_days`;
- positive integer `expected_requested_vehicle_days`;
- finite numeric `idle_fuel_metric_coverage_percent` within 0–100;
- non-empty string `window_start`;
- non-empty string `window_end`;
- non-empty string `request_timezone`;
- `fuel_unit == gallons`;
- `unit_request_mode == imperial`.

Recommended consistency guard:

- `metric_valid_vehicle_days <= expected_requested_vehicle_days`.

If these checks fail, render a neutral unavailable state.

Do not derive missing coverage or repair malformed fields in the browser.

## Coverage and representativeness

Coverage must remain visually attached to the idle-fuel-share value.

Do not display the percentage alone when coverage is partial.

`fleet_representative=false` is descriptive completeness metadata only.

It must not become:

- severity;
- warning level;
- red/amber/green color;
- business-health state;
- action recommendation;
- alert trigger.

Even at 100% metric-valid vehicle-day coverage, the KPI still describes only provider-reported `idle_fuel + driving_fuel` inside the certified production rollup contract.

## Relationship between idle-time share and idle-fuel share

The two idle-related KPIs answer different questions:

- idle-time share: share of observed idle + driving **seconds** reported as idle;
- idle-fuel share: share of observed idle + driving **fuel volume** reported as idle fuel.

The frontend must not:

- subtract one from the other;
- average them;
- infer efficiency from their difference;
- declare that one should numerically track the other;
- interpret divergence as a fault;
- compare them with directional arrows or severity language.

They may sit next to each other because they describe the same operational domain, but they remain independent observations.

## Business interpretation boundary

The frontend must not introduce these labels or equivalent interpretations for idle-fuel share:

- waste;
- fuel waste;
- avoidable idle;
- avoidable fuel;
- excessive;
- inefficient;
- high;
- low;
- good;
- bad;
- target;
- benchmark;
- pass;
- fail;
- savings opportunity;
- cost opportunity;
- needs attention.

No external benchmark or fuel-price multiplication is authorized.

## Executive-attention boundary

Idle-fuel share and its coverage may not alter or populate:

- `business_status`;
- Needs Attention;
- Today's Plan / Today's Priority;
- Watch Items;
- Polaris Recommendation;
- Daily Brief System / Data Health;
- Daily Brief business status;
- email;
- Slack;
- notifications;
- alerts.

No HIGH/MEDIUM/CRITICAL, GOOD/WATCH, target-attainment, red/amber/green, or recommendation semantics are authorized.

## Visual style

Reuse the existing neutral Fleet / Operations visual language.

The idle-fuel block should use:

- the same typographic hierarchy as the other two current observations;
- the same neutral value color family;
- the same neutral coverage/completeness treatment;
- no severity icon;
- no warning icon solely because coverage is partial;
- no gauge or dial that implies a target;
- no red/green arrows;
- no dollar icon or cost badge.

The existing generic `FleetKpiObservation` component may continue to render all three blocks if the presentation layer keeps their semantics explicit.

A broad frontend refactor is not required or authorized.

## Accessibility

Each KPI block must have an accessible title and readable supporting context.

Idle-fuel share must be understandable without color.

At minimum, accessible text must communicate:

- KPI name;
- value or unavailable state;
- metric-valid/expected vehicle-day coverage;
- whether the observation is fleet representative;
- seven-day window/timezone;
- that the percentage is the share of observed idle-plus-driving fuel volume reported as idle fuel.

Do not abbreviate the accessible label to only `Idle fuel X%`.

## Responsive behavior

Wide desktop:

- prefer three equal current-observation columns.

Intermediate width:

- wrapping to two-plus-one or stacking is acceptable if needed for readability;
- preserve source order and full metadata.

Narrow/mobile:

- stack all three KPI blocks;
- use neutral horizontal dividers between stacked observations;
- preserve readable title/value/coverage/window;
- avoid horizontal page overflow.

The utilization history region remains below the current observations and stays responsive independently.

## Recommended frontend presentation helper

Add a dedicated helper such as:

`motiveIdleFuelShareKpiPresentation(payload, options)`

It should mirror the defensive presentation shape already used by utilization and idle-time share while using fuel-specific fields and wording.

Recommended output shape:

- `status`;
- `title`;
- `value`;
- `coverage`;
- `completeness`;
- `window`;
- neutral `description`.

Do not pass the raw backend payload deep into visual markup when the presentation helper can validate and sanitize it first.

## Implementation scope for the next PR

After this design merges, the frontend implementation PR should remain limited to the existing Dashboard consumer surface, approximately:

1. `chief-of-staff/frontend/src/motiveFrontend.js`
   - add idle-fuel-share presentation helper/validation;
2. `chief-of-staff/frontend/src/components/ExecutiveDashboard.jsx`
   - add independent idle-fuel KPI state/load;
   - add its GET to the existing settled refresh group;
   - render the third current-observation block;
3. `chief-of-staff/frontend/src/components/MotiveUtilizationKpi.css`
   - extend neutral grid/responsive styling from two to three observations;
4. focused frontend tests.

No backend file should change.

No package dependency should be added.

No idle-fuel history/trend should be added.

## Required frontend test matrix

At minimum, the future implementation must prove:

1. idle-fuel KPI uses exactly `/api/v1/motive/fleet/vehicle-idle-fuel-share-kpi` via `apiClient.get`;
2. initial Dashboard load makes at most one idle-fuel KPI GET;
3. Dashboard Refresh makes at most one additional idle-fuel KPI GET;
4. Dashboard/utilization/idle-time/idle-fuel reads preserve independent settled failure semantics;
5. certified partial payload presents value, idle-fuel metric coverage, and neutral non-representative wording;
6. numeric `0%` remains a valid observation;
7. numeric `100%` remains a valid observation;
8. unavailable backend status never renders `0%`;
9. request failure renders neutral idle-fuel-reporting-unavailable wording;
10. malformed available payload fails closed;
11. malformed fuel unit/request mode fails closed;
12. coverage outside 0–100 fails closed;
13. metric-valid vehicle-days greater than expected vehicle-days fails closed;
14. idle-fuel value remains independent when utilization or idle-time requests fail;
15. utilization and idle-time values remain independent when idle-fuel request fails;
16. all three current KPI blocks are inside the one Fleet / Operations reporting card;
17. utilization history remains below the current-observation region and utilization-only;
18. responsive layout avoids horizontal overflow;
19. no Motive POST/DELETE/sync/verify/reconcile/scheduler route is introduced;
20. no HIGH/MEDIUM/CRITICAL, GOOD/WATCH, target, alert, waste, cost, or business-status semantics appear;
21. no new npm dependency is added;
22. no idle-fuel history/trend is fabricated.

## Production certification after implementation

After the frontend implementation merges and deploys:

1. sign in normally to Polaris;
2. open Executive Dashboard;
3. compare the displayed idle-fuel-share block with one authenticated GET to `/api/v1/motive/fleet/vehicle-idle-fuel-share-kpi`;
4. verify displayed value, coverage, completeness, window, and timezone match the sanitized endpoint;
5. verify utilization and idle-time share remain unchanged;
6. verify the existing utilization 30-day history remains utilization-only;
7. verify Business Status and all attention/action sections remain unchanged;
8. verify no fuel threshold, waste, cost, severity, or recommendation appears;
9. test narrow layout visually;
10. do not trigger Motive sync, scheduler, reconciliation, or provider verification for certification.

## Non-goals

This gate does not:

- implement frontend code;
- change the backend KPI;
- add idle-fuel snapshots/history;
- add an idle-fuel chart;
- mix idle-fuel share into utilization history;
- estimate fuel cost or savings;
- classify idle fuel as waste or avoidable;
- rank vehicles or drivers;
- add thresholds, targets, benchmarks, or alerts;
- add provider calls;
- add writes;
- change ingestion, scheduler, reconciliation, or production configuration;
- change Business Status, Daily Brief, or attention sections.

## Next gate

After this design merges, implement only the neutral frontend current-observation placement for idle-fuel share.