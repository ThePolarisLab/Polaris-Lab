# Motive Vehicle Idle-Time Share — Dashboard Placement Design

## Status

Design gate only.

This document defines the first Polaris frontend consumer placement for the already production-certified `Observed 7-Day Vehicle Idle-Time Share` KPI.

It does **not** implement frontend runtime code, add provider calls, write database state, change ingestion or scheduler behavior, add snapshots/history, add business thresholds, alter Daily Brief behavior, or change any executive attention/action surface.

Certified read endpoint:

`GET /api/v1/motive/fleet/vehicle-idle-time-share-kpi`

The backend KPI is descriptive only. Its production certification returned an observed value with partial vehicle-day coverage and `fleet_representative=false`; the frontend must preserve that distinction rather than converting the number into a fleet-wide or severity claim.

## Placement decision

Extend the existing **Fleet / Operations** reporting card on the Executive Dashboard.

Do not add:

- a second top-level Dashboard card;
- a new navigation route;
- a Needs Attention item;
- a Watch Item;
- a Daily Brief item;
- an alert banner.

The authoritative Executive Dashboard placement remains:

1. summary strip (`Open Notes`, `Active Missions`, `Trucks`);
2. **Fleet / Operations** reporting card;
3. attention/action grid (`Needs Attention`, `Carry Forward`, `Today's Plan`, `Coming Up`, `Watch Items`, `Polaris Recommendation`).

The current Fleet / Operations card already occupies the correct non-attention reporting position. The second KPI belongs inside that same reporting surface.

## Current-observation layout

The Fleet / Operations card should evolve from one current-KPI block into a **Current Observations** region containing two independent KPI blocks:

1. `Observed 7-Day Vehicle Utilization`
2. `Observed 7-Day Vehicle Idle-Time Share`

Recommended desktop layout:

- two neutral columns of equal reporting weight;
- utilization on the left;
- idle-time share on the right;
- each block contains its own title, value, coverage, completeness wording, and observation window.

Recommended narrow/mobile layout:

- stack the two KPI blocks vertically;
- utilization first;
- idle-time share second;
- preserve full coverage/completeness text without horizontal overflow.

The visual design must not imply that one KPI is a component of the other or that either one is a business score.

## Relationship to the approved utilization trend design

`MOTIVE_UTILIZATION_30_DAY_TREND_UI_DESIGN.md` remains authoritative for the future utilization history region.

When that trend is later implemented, the Fleet / Operations card should be structured as:

1. `FLEET / OPERATIONS`
2. current-observation grid
   - current utilization
   - current idle-time share
3. subtle divider
4. utilization-only `30-Day Observation History`
5. utilization trend/history state

The idle-time-share KPI has **no certified snapshot/history endpoint** in this gate.

Therefore:

- do not place idle-time-share points on the utilization history chart;
- do not reconstruct idle-time history from mutable utilization rows;
- do not label the utilization trend as a combined fleet trend;
- do not create an idle-time trend placeholder that suggests history collection already exists.

A future idle-time history/snapshot design requires a separate gate.

## Consumer endpoint and request behavior

The frontend may add exactly one new read request:

`/api/v1/motive/fleet/vehicle-idle-time-share-kpi`

Use the existing authenticated `apiClient.get(...)` path so bearer/session and organization context remain centralized.

The frontend must:

- make zero Motive provider calls directly;
- make zero database writes;
- invoke no Motive sync, verify, reconcile, scheduler, ingestion, or internal route;
- add no backend endpoint or migration;
- add no polling or timer refresh;
- issue at most one idle-time-share GET during the initial Dashboard load;
- issue at most one additional idle-time-share GET when the existing Dashboard Refresh action is used.

The Dashboard core request, utilization KPI request, and idle-time-share KPI request must remain independent.

`Promise.allSettled` or equivalent independent failure behavior is required.

## Independent load/failure semantics

The idle-time-share KPI must have its own state:

- payload;
- loading;
- request failure.

It must not reuse the utilization request's failure flag as a proxy.

Required behavior:

- Dashboard success + utilization success + idle success: render both current observations;
- Dashboard success + utilization success + idle failure: utilization remains normal; idle block shows neutral unavailable/reporting-unavailable wording;
- Dashboard success + utilization failure + idle success: idle block remains normal; utilization retains its existing unavailable/request-failure behavior;
- Dashboard success + both Motive KPI failures: Fleet / Operations remains present with neutral unavailable states; attention/action sections remain unaffected;
- Dashboard core failure: existing Dashboard failure behavior remains authoritative.

A failure of one KPI must never overwrite or reclassify the other KPI.

## Idle-time-share presentation contract

Recommended presentation title:

`Observed 7-Day Vehicle Idle-Time Share`

When `status == available_observed`, display:

- `value_percent` formatted to two decimals;
- coverage as `metric_valid_vehicle_days / expected_requested_vehicle_days vehicle-days (idle_time_metric_coverage_percent%)`;
- completeness wording:
  - `Full vehicle-day coverage` only when `fleet_representative == true`;
  - otherwise `Partial observation — not fleet representative`;
- observation window: `window_start to window_end · request_timezone`.

The block should also carry a short neutral descriptor, visually secondary to the title/value, such as:

`Share of observed idle + driving time reported as idle.`

This descriptor is important because `50.97%` must not be mistaken for percent of the full 24-hour day or percent of the whole fleet.

The UI does not need to display raw summed idle or driving seconds because the public backend contract intentionally does not expose them.

## Valid zero and unavailable

A returned numeric `value_percent = 0` is a valid observed value and must render as `0.00%` when the payload otherwise satisfies the certified contract.

Do not confuse valid zero with:

- `status=unavailable`;
- missing payload;
- request failure;
- null/malformed value.

If the backend returns `status != available_observed`, render `Unavailable` rather than a numeric zero.

If the request fails, use neutral wording such as:

`Idle-time-share reporting temporarily unavailable.`

Do not expose exception text.

## Frontend payload validation

The presentation layer must fail closed on malformed payloads before displaying a percentage.

For an available observation, require at minimum:

- `status == available_observed`;
- finite numeric `value_percent` within 0–100;
- non-negative integer `metric_valid_vehicle_days`;
- positive integer `expected_requested_vehicle_days`;
- finite numeric `idle_time_metric_coverage_percent` within 0–100;
- non-empty string `window_start`;
- non-empty string `window_end`;
- non-empty string `request_timezone`.

Recommended additional consistency guard:

- `metric_valid_vehicle_days <= expected_requested_vehicle_days`.

If these checks fail, render a neutral unavailable state.

Do not derive a missing coverage percentage in the browser from other values if the certified backend field is malformed or absent. Fail closed rather than silently repairing the public contract.

## Coverage and representativeness

Coverage must remain visually attached to the idle-time-share value.

Do not show the percentage alone when an available observation has partial coverage.

`fleet_representative=false` must remain descriptive completeness metadata only.

It must not become:

- severity;
- warning level;
- red/amber/green color;
- business-health state;
- action recommendation;
- alert trigger.

Even at 100% metric-valid vehicle-day coverage, the KPI still means only the share of provider-reported idle-plus-driving seconds. It does not mean percent of all clock time or proof of avoidable idle.

## Business interpretation boundary

The frontend must not introduce these labels or equivalent interpretations for the idle-time-share KPI:

- high idle;
- low idle;
- good;
- bad;
- efficient;
- inefficient;
- waste;
- excessive;
- avoidable;
- target;
- benchmark;
- pass;
- fail;
- needs attention.

The production-certified value is an observation, not a judgment.

Do not compare it with an external fleet benchmark in this gate.

## Executive-attention boundary

Neither the idle-time-share value nor its coverage may alter or populate:

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

The idle-time-share block should use:

- the same typographic hierarchy as utilization;
- the same neutral value color family;
- the same neutral coverage/completeness treatment;
- no severity icons;
- no warning icon solely because coverage is partial;
- no gauge/dial that implies target attainment;
- no red/green comparison arrows.

A subtle neutral divider between the two current-observation blocks is acceptable.

The two blocks may share a common reusable presentation component if doing so reduces duplication, but a broad frontend refactor is not required or authorized by this design.

## Accessibility

Each KPI block must have an accessible title and readable supporting context.

The idle-time-share observation should be understandable without relying on color.

At minimum, accessible text must communicate:

- KPI name;
- value or unavailable state;
- metric-valid/expected vehicle-day coverage;
- whether the observation is fleet representative;
- seven-day window/timezone;
- that the percentage is the share of observed idle-plus-driving time reported as idle.

Do not abbreviate the accessible label to only `Idle 50.97%`.

## Responsive behavior

Desktop/tablet:

- prefer a two-column current-observation region when width permits.

Narrow/mobile:

- stack KPI blocks;
- preserve readable title/value/coverage/window;
- align metadata left;
- avoid horizontal page overflow.

The future utilization history SVG remains below the stacked/current-observation region and must remain responsive independently.

## Recommended frontend presentation helper

Add a dedicated presentation helper, for example:

`motiveIdleTimeShareKpiPresentation(payload, options)`

It should mirror the proven defensive shape of `motiveUtilizationKpiPresentation` while using idle-specific fields and wording.

Recommended output shape:

- `status`;
- `title`;
- `value`;
- `coverage`;
- `completeness`;
- `window`;
- optional neutral `description`.

Do not pass raw backend payloads deep into visual markup when a small presentation layer can validate/sanitize the fields first.

## Implementation scope for the next PR

After this design merges, the frontend implementation PR should be limited to the existing Motive Dashboard consumer surface, approximately:

1. `chief-of-staff/frontend/src/motiveFrontend.js`
   - add idle-time-share presentation helper/contract;
2. `chief-of-staff/frontend/src/components/ExecutiveDashboard.jsx`
   - add independent idle KPI state/load;
   - add its GET to the existing settled refresh group;
   - evolve Fleet / Operations current observation layout to two blocks;
3. `chief-of-staff/frontend/src/components/MotiveUtilizationKpi.css`
   - extend neutral current-observation layout/responsive styling only as needed;
4. focused frontend test file(s).

No backend file should need to change.

No package dependency should be added.

No utilization-history implementation is required in the same PR; the already-approved trend gate may remain separately sequenced behind first-snapshot certification.

## Required frontend test matrix

At minimum, the future implementation must prove:

1. idle KPI uses exactly `/api/v1/motive/fleet/vehicle-idle-time-share-kpi` via `apiClient.get`;
2. initial Dashboard load makes at most one idle KPI GET;
3. Dashboard Refresh makes at most one additional idle KPI GET;
4. Dashboard/utilization/idle reads use independent settled failure semantics;
5. certified partial payload presents value, idle metric coverage, and neutral non-representative wording;
6. numeric `0%` remains a valid observation;
7. unavailable backend status never renders `0%`;
8. request failure renders neutral idle-reporting-unavailable wording;
9. malformed available payload fails closed;
10. coverage outside 0–100 fails closed;
11. metric-valid vehicle-days greater than expected vehicle-days fails closed if the consistency guard is implemented;
12. idle value remains independent when utilization request fails;
13. utilization value remains independent when idle request fails;
14. Fleet / Operations stays between summary and attention sections;
15. both current KPI blocks are inside the one Fleet / Operations reporting card;
16. mobile layout stacks without horizontal overflow;
17. no Motive POST/DELETE/sync/verify/reconcile/scheduler route is introduced;
18. no HIGH/MEDIUM/CRITICAL, GOOD/WATCH, target, alert, or business-status semantics appear in the KPI reporting component;
19. no new npm dependency is added;
20. no idle-time history/trend is fabricated.

## Production certification after implementation

After the frontend implementation merges and deploys:

1. sign in normally to Polaris;
2. open the Executive Dashboard;
3. compare the displayed idle-time-share block with one authenticated GET to `/api/v1/motive/fleet/vehicle-idle-time-share-kpi`;
4. verify displayed value, coverage, completeness, window, and timezone match the sanitized endpoint;
5. verify utilization remains unchanged;
6. verify Business Status and all attention/action sections remain unchanged;
7. verify no idle threshold/severity/recommendation appears;
8. test narrow/mobile layout visually;
9. do not trigger Motive sync, scheduler, reconciliation, or provider verification for certification.

## Non-goals

This gate does not:

- implement frontend code;
- change the backend KPI;
- add idle-time snapshots/history;
- add an idle-time chart;
- mix idle-time share into the utilization history chart;
- add thresholds, targets, benchmarks, or alerts;
- classify idle as avoidable or wasteful;
- estimate idle fuel cost;
- rank vehicles or drivers;
- add provider calls;
- add writes;
- change ingestion, scheduler, reconciliation, or production configuration;
- change Business Status, Daily Brief, or attention sections.

## Next gate

After this design merges, implement only the neutral frontend current-observation placement for idle-time share. Keep the previously approved utilization 30-day history implementation on its separate snapshot-certification track.