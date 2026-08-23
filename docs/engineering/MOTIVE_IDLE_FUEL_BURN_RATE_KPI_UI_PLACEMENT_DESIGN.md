# Motive Idle Fuel Burn Rate — Dashboard Placement Design

## Status

Design gate only.

This document defines the first Polaris frontend placement for the already production-certified `Observed 7-Day Idle Fuel Burn Rate` KPI.

It does **not** implement frontend runtime code, add provider calls, write database state, change ingestion or scheduler behavior, add snapshots/history, add fuel-cost logic, add business thresholds, alter Daily Brief behavior, or change any executive attention/action surface.

Certified read endpoint:

`GET /api/v1/motive/fleet/vehicle-idle-fuel-burn-rate-kpi`

Production-certified current example:

- value: `0.75 gallons_per_idle_hour`;
- window: `2026-08-16` through `2026-08-22`;
- metric-valid vehicle-days: `70 / 161`;
- metric coverage: `43.48%`;
- `fleet_representative = false`;
- idle-time unit: `seconds`;
- fuel unit: `gallons`;
- request mode: `imperial`.

## Placement decision

Keep the KPI inside the existing **Fleet / Operations** reporting card on the Executive Dashboard.

Do not add:

- a new top-level Dashboard card;
- a new navigation route;
- a Needs Attention item;
- a Watch Item;
- a Daily Brief item;
- an alert banner;
- a fuel-cost, savings, or waste card.

The current Fleet / Operations card already contains three current observations and a utilization-only 30-day history region.

The fourth KPI belongs inside the same **Current Observations** region.

## Four-KPI layout decision

The current one-row three-column layout is readable with three KPIs, but adding a fourth equal column would materially reduce room for:

- long KPI titles;
- descriptors;
- large numeric values with units;
- coverage text;
- completeness pills;
- seven-day window/timezone context.

Therefore the approved wide-screen layout for four KPIs is a **2 × 2 neutral grid**.

Source order:

1. `Observed 7-Day Vehicle Utilization`;
2. `Observed 7-Day Vehicle Idle-Time Share`;
3. `Observed 7-Day Vehicle Idle-Fuel Share`;
4. `Observed 7-Day Idle Fuel Burn Rate`.

Recommended visual grouping:

- row 1: utilization, idle-time share;
- row 2: idle-fuel share, idle fuel burn rate.

This grouping is for readability only. It must not imply that row pairs form one formula, score, causal relationship, or target comparison.

Each observation keeps equal reporting weight and its own independent value, coverage, completeness, description, and seven-day window.

## Responsive behavior

Wide desktop:

- use two equal columns and two rows;
- use neutral vertical and horizontal separators or equivalent spacing;
- preserve all supporting metadata.

Intermediate width:

- two columns remain preferred when readable;
- allow clean spacing reduction rather than shrinking metadata excessively.

Narrow/mobile:

- stack all four observations vertically;
- preserve source order;
- use neutral horizontal separators;
- avoid horizontal overflow;
- do not hide coverage, completeness, or window information.

## Relationship to utilization history

The existing `30-Day Observation History` remains **utilization-only** and stays below the entire four-KPI Current Observations grid.

Do not:

- add burn-rate points to the utilization chart;
- add idle-time-share or idle-fuel-share points to that chart;
- reconstruct burn-rate history from mutable vehicle-utilization rows;
- create an empty burn-rate history placeholder;
- relabel utilization history as a combined fleet trend.

Any burn-rate snapshot/history design requires a separate gate.

## Consumer endpoint and request behavior

The frontend may add exactly one new read request:

`/api/v1/motive/fleet/vehicle-idle-fuel-burn-rate-kpi`

Use the existing authenticated `apiClient.get(...)` path.

Required behavior:

- zero direct Motive provider calls from the browser;
- zero database writes;
- no sync, verify, reconcile, scheduler, ingestion, or internal production route;
- no polling or timer refresh;
- at most one burn-rate GET during initial Dashboard load;
- at most one additional burn-rate GET when the existing Dashboard Refresh action is used.

The Dashboard core request and all Motive KPI requests must remain independent through the existing settled-load pattern or equivalent.

A failure of burn-rate reporting must not hide or reclassify utilization, idle-time share, idle-fuel share, utilization history, Business Status, or attention/action sections.

## Burn-rate presentation contract

Presentation title:

`Observed 7-Day Idle Fuel Burn Rate`

Neutral descriptor:

`Observed idle fuel volume per observed idle hour.`

When `status == available_observed`, display:

- `value_gallons_per_idle_hour` formatted to two decimals;
- display unit as `gal/idle-hr` or `gallons/idle-hour`;
- coverage as `metric_valid_vehicle_days / expected_requested_vehicle_days vehicle-days (idle_fuel_burn_rate_metric_coverage_percent%)`;
- completeness wording:
  - `Full vehicle-day coverage` only when `fleet_representative == true`;
  - otherwise `Partial observation — not fleet representative`;
- observation window: `window_start to window_end · request_timezone`.

The visible value should read naturally, for example:

`0.75 gal/idle-hr`

The accessible label should preserve the full meaning, for example:

`0.75 gallons per observed idle hour`.

## Interpretation boundary

The burn-rate KPI is descriptive only.

The frontend must not label or imply:

- waste;
- avoidable fuel;
- excessive idle;
- inefficient or efficient;
- high or low;
- good or bad;
- target or benchmark;
- pass or fail;
- savings opportunity;
- cost opportunity;
- driver quality;
- vehicle quality;
- maintenance fault;
- needs attention.

A higher or lower gallons-per-idle-hour value is not automatically better or worse because stationary engine load may vary for legitimate operating reasons not classified by the current Motive rollup.

No fuel-price multiplication or dollar estimate is authorized.

## Valid zero and unavailable

A returned numeric `value_gallons_per_idle_hour = 0` is a valid observed value when the backend otherwise reports `available_observed` and positive metric-valid idle time existed.

Render it as:

`0.00 gal/idle-hr`

Do not confuse valid zero with:

- `status=unavailable`;
- missing payload;
- request failure;
- null/malformed value.

If backend status is unavailable, render `Unavailable` rather than numeric zero.

If the request fails, use neutral wording such as:

`Idle fuel burn-rate reporting temporarily unavailable.`

Do not expose exception text.

## Frontend payload validation

Before rendering an available value, require at minimum:

- `status == available_observed`;
- finite numeric `value_gallons_per_idle_hour >= 0`;
- non-negative integer `metric_valid_vehicle_days`;
- positive integer `expected_requested_vehicle_days`;
- finite numeric `idle_fuel_burn_rate_metric_coverage_percent` within 0–100;
- `metric_valid_vehicle_days <= expected_requested_vehicle_days`;
- non-empty `window_start`;
- non-empty `window_end`;
- `request_timezone == America/Chicago`;
- `idle_time_unit == seconds`;
- `fuel_unit == gallons`;
- `rate_unit == gallons_per_idle_hour`;
- `unit_request_mode == imperial`;
- `secrets_exposed == false` if present.

If any required field is malformed or inconsistent, fail closed to a neutral unavailable presentation.

Do not repair missing coverage or infer units in the browser.

## Coverage and representativeness

Coverage must remain visually attached to the burn-rate value.

Do not display `0.75 gal/idle-hr` by itself when coverage is partial.

`fleet_representative=false` is completeness metadata only. It must not become severity, warning level, business-health state, action recommendation, or alert trigger.

Even with 100% vehicle-day coverage, this KPI describes Motive-reported idle fuel per Motive-reported idle hour only.

## Relationship to the other idle KPIs

The three idle-related observations answer different questions:

- idle-time share: share of observed idle + driving **time** reported as idle;
- idle-fuel share: share of observed idle + driving **fuel volume** reported as idle fuel;
- idle fuel burn rate: observed **idle fuel volume per idle hour**.

The frontend must not:

- subtract or average them;
- infer efficiency from their differences;
- claim one should numerically track another;
- add directional arrows between them;
- create a composite idle score;
- infer waste or savings from the combination.

They may appear together because they describe the same operational domain, but remain independent observations.

## Visual style

Reuse the existing neutral Fleet / Operations style:

- same typography hierarchy;
- same value color family;
- same neutral coverage and completeness treatment;
- no red/green arrows;
- no gauge or target dial;
- no warning icon solely because coverage is partial;
- no dollar icon;
- no flame/fuel icon that implies severity.

The generic `FleetKpiObservation` component may continue to render the block if its presentation helper validates and sanitizes the burn-rate payload first.

A broad frontend refactor is not required or authorized.

## Accessibility

Accessible text must communicate:

- KPI name;
- numeric value and full unit or unavailable state;
- metric-valid/expected vehicle-day coverage;
- fleet representativeness;
- seven-day window/timezone;
- that the rate is observed idle fuel volume per observed idle hour.

Do not rely on color for meaning.

## Executive-attention boundary

This KPI may not alter or populate:

- `business_status`;
- Needs Attention;
- Today's Plan / Today's Priority;
- Watch Items;
- Polaris Recommendation;
- Daily Brief business status;
- Daily Brief System / Data Health;
- email;
- Slack;
- notifications;
- alerts.

No HIGH/MEDIUM/CRITICAL, GOOD/WATCH, threshold, target-attainment, red/amber/green, or recommendation semantics are authorized.

## Recommended frontend implementation surface

After this design merges, the frontend implementation PR should remain limited approximately to:

1. `chief-of-staff/frontend/src/motiveFrontend.js`
   - add burn-rate presentation helper and validation;
2. `chief-of-staff/frontend/src/components/ExecutiveDashboard.jsx`
   - add independent burn-rate state/load;
   - add one GET to the existing settled refresh group;
   - render the fourth observation;
3. `chief-of-staff/frontend/src/components/MotiveUtilizationKpi.css`
   - change wide current-observation layout from 3 columns to a neutral 2×2 grid;
   - preserve mobile stacking;
4. focused frontend tests, including any existing settled-load count expectation that legitimately changes from four to five Dashboard reads.

No backend file should change.

No package dependency should be added.

No burn-rate history/trend should be added.

## Required frontend test matrix

At minimum, the future implementation must prove:

1. exact GET path `/api/v1/motive/fleet/vehicle-idle-fuel-burn-rate-kpi` through `apiClient.get`;
2. at most one initial burn-rate GET;
3. at most one additional burn-rate GET on Dashboard Refresh;
4. all Dashboard/Motive reads preserve independent settled failure semantics;
5. certified partial payload renders `0.75 gal/idle-hr`, coverage, and neutral non-representative wording;
6. numeric zero remains valid `0.00 gal/idle-hr`;
7. unavailable backend status does not render numeric zero;
8. request failure renders neutral unavailable wording;
9. malformed value fails closed;
10. malformed rate/fuel/time/request units fail closed;
11. coverage outside 0–100 fails closed;
12. metric-valid days greater than expected days fails closed;
13. burn-rate failure does not alter the other three current observations;
14. other KPI failures do not alter burn-rate rendering;
15. all four current observations remain inside one Fleet / Operations card;
16. wide layout is 2×2 and narrow layout stacks without overflow;
17. utilization history remains below the current observations and utilization-only;
18. no direct Motive provider/sync/verify/reconcile/scheduler route is introduced;
19. no HIGH/MEDIUM/CRITICAL, GOOD/WATCH, waste, cost, target, benchmark, alert, or business-status semantics appear;
20. no new npm dependency is added;
21. no burn-rate history/trend is fabricated.

## Production certification after implementation

After the frontend implementation merges and deploys:

1. sign in normally to Polaris;
2. open Executive Dashboard;
3. compare the burn-rate block with one authenticated GET to `/api/v1/motive/fleet/vehicle-idle-fuel-burn-rate-kpi`;
4. verify value, unit, coverage, completeness, window, and timezone match;
5. verify utilization, idle-time share, and idle-fuel share remain correct;
6. verify the utilization 30-day history remains utilization-only;
7. verify Business Status and attention/action sections remain unchanged;
8. verify no burn-rate threshold, waste, cost, severity, benchmark, or recommendation appears;
9. visually verify the 2×2 desktop layout and stacked narrow layout;
10. do not trigger Motive sync, scheduler, reconciliation, or provider verification.

## Non-goals

This gate does not:

- implement frontend code;
- change the backend KPI;
- add burn-rate snapshots/history;
- add a burn-rate chart;
- estimate fuel cost or savings;
- classify burn rate as waste or efficiency;
- rank vehicles or drivers;
- add thresholds, targets, benchmarks, or alerts;
- add provider calls;
- add writes;
- change ingestion, scheduler, reconciliation, or production configuration;
- change Business Status, Daily Brief, or attention sections.

## Next gate

After this design merges, implement only the neutral frontend current-observation placement for idle fuel burn rate.