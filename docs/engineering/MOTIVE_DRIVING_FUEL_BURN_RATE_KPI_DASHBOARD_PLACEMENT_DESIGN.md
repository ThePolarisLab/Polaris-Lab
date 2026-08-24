# Motive Driving Fuel Burn Rate — Dashboard Placement Design

## Status

Design gate only.

This document defines how the already production-certified `Observed 7-Day Driving Fuel Burn Rate` KPI may appear on the Executive Dashboard. It does **not** change frontend/runtime code, backend behavior, provider calls, database state, scheduler/ingestion/reconciliation behavior, snapshot/history persistence, alerts, Daily Brief, Business Status, thresholds, recommendations, or production configuration.

## Production-certified source KPI

Display name:

`Observed 7-Day Driving Fuel Burn Rate`

Machine name:

`observed_7_day_driving_fuel_burn_rate`

Read endpoint:

`GET /api/v1/motive/fleet/vehicle-driving-fuel-burn-rate-kpi`

Permission:

`CONNECTOR_READ`

The endpoint is already implemented as a tenant-scoped, read-only read model over durable Motive vehicle-utilization rows. It performs zero Motive provider calls and zero database writes.

Latest production certification at the time of this design:

- window: `2026-08-16` through `2026-08-22`;
- timezone: `America/Chicago`;
- value: `7.89 gallons_per_driving_hour`;
- selected vehicles: `23`;
- expected requested vehicle-days: `161`;
- provider rollup vehicle-days: `70` / `161` (`43.48%`);
- driving-burn-rate metric-valid vehicle-days: `61` / `161` (`37.89%`);
- missing requested vehicle-days: `91`;
- `fleet_representative = false`;
- `driving_time_unit = seconds`;
- `fuel_unit = gallons`;
- `unit_request_mode = imperial`;
- `secrets_exposed = false`.

These concrete values are certification evidence, not permanent thresholds or targets.

## Placement decision

Keep KPI #5 inside the existing Executive Dashboard `Fleet / Operations` card under the existing `Current Observations` heading.

Do not create a second Fleet card and do not place the KPI in Needs Attention, Today's Plan, Watch Items, Business Status, Daily Brief, System Health, or any action surface.

### Wide-screen structure: neutral 3 + 2 grid

The five current observations should be arranged as two visual rows inside the same observation region.

Row 1 — percentage observations:

1. `Observed 7-Day Vehicle Utilization`
2. `Observed 7-Day Vehicle Idle-Time Share`
3. `Observed 7-Day Vehicle Idle-Fuel Share`

Row 2 — unit-bearing rate observations:

4. `Observed 7-Day Idle Fuel Burn Rate`
5. `Observed 7-Day Driving Fuel Burn Rate`

The second row must use two equal-width columns. Do not leave an empty sixth/orphan tile and do not make KPI #5 span the full card width.

A practical implementation may use one six-column CSS grid where:

- observations 1–3 each span two columns;
- observations 4–5 each span three columns.

Equivalent nested 3-column and 2-column row structures are acceptable if tests prove the same visual order and responsive behavior.

The 3 + 2 structure is a layout decision only. It does **not** assign more or less business importance to any KPI.

## Why not a single five-column row

Do not compress all five KPIs into one row.

The current observation blocks include:

- multi-word titles;
- optional explanatory descriptors;
- large values;
- coverage numerator / denominator / percent;
- partial-observation wording;
- seven-day date window and timezone.

The driving-fuel-burn-rate value is also unit-bearing, for example `7.89 gal/driving-hr`. A five-column row would materially reduce readability and encourage wrapping/clipping.

## Why not keep a plain two-column grid with an orphan fifth tile

A simple two-column auto-flow would produce two full rows plus one single tile. Do not leave the driving burn-rate KPI alone in a third row and do not stretch it across both columns.

An orphan tile would make KPI #5 appear visually exceptional, while a full-width tile would make it appear more important than the other observations.

Pairing the two burn-rate observations in the second row is semantically coherent and visually neutral.

## Source order and semantic grouping

The DOM/source order should remain:

1. utilization;
2. idle-time share;
3. idle-fuel share;
4. idle fuel burn rate;
5. driving fuel burn rate.

The first three are percentage observations. The final two are gallons-per-observed-hour rate observations.

Do not add visible labels such as `Good`, `Bad`, `Efficiency`, `Waste`, `Fuel Performance`, `Target`, or `Opportunity` around either row.

Visible row subheadings are not required. The grouping should primarily be spatial so the existing `Current Observations` heading remains the single semantic heading for the set.

## Driving fuel burn rate display

Title:

`Observed 7-Day Driving Fuel Burn Rate`

Neutral descriptor:

`Observed driving fuel volume per observed driving hour.`

Preferred value format:

`7.89 gal/driving-hr`

The exact production value must come from the endpoint. Do not hard-code `7.89`.

The frontend presentation must require all of the following before displaying an available numeric observation:

- `status == available_observed`;
- `kpi == observed_7_day_driving_fuel_burn_rate`;
- finite non-negative `value_gallons_per_driving_hour`;
- valid `window_start` and `window_end`;
- `request_timezone == America/Chicago`;
- valid positive `expected_requested_vehicle_days`;
- valid non-negative `metric_valid_vehicle_days` not exceeding expected;
- valid non-negative `driving_fuel_burn_rate_metric_coverage_percent` in `[0, 100]`;
- coverage arithmetic consistent with metric-valid / expected vehicle-days at display precision;
- `driving_time_unit == seconds`;
- `fuel_unit == gallons`;
- `rate_unit == gallons_per_driving_hour`;
- `unit_request_mode == imperial`;
- `secrets_exposed == false`.

If the payload fails presentation validation, render the neutral unavailable state rather than displaying an inferred or partially trusted number.

## Coverage shown on the Dashboard

The primary coverage line for this KPI must use **metric-valid vehicle-days**, not provider-rollup vehicle-days.

For the currently certified production response, the card would show:

`61 / 161 vehicle-days (37.89%)`

Do not show `70 / 161 (43.48%)` as if all provider-returned rows were valid for the driving burn-rate calculation.

The provider rollup count may remain available in the backend response but is not required in the first Dashboard presentation.

## Completeness / representativeness wording

Reuse the same neutral completeness language as the other current observations.

When `fleet_representative == false`:

`Partial observation — not fleet representative`

When the certified backend eventually returns full metric-valid coverage and `fleet_representative == true`, use the existing representative/full-observation presentation contract rather than introducing a new success label.

Do not translate partial coverage into warning severity.

## Zero and unavailable states

A valid backend value of `0.00 gallons_per_driving_hour` must display as a real zero observation, for example:

`0.00 gal/driving-hr`

Do not replace a valid zero with `Unavailable`.

Conversely, an unavailable or malformed response must never display `0.00` as a fallback.

Loading, request failure, malformed response, and backend `unavailable` states must remain neutral and local to this KPI block.

## Independent read behavior

Add exactly one frontend GET for the new observation:

`/api/v1/motive/fleet/vehicle-driving-fuel-burn-rate-kpi`

The Dashboard must not call Motive directly.

The driving-burn-rate request must have independent:

- payload state;
- loading state;
- request-failure state;
- presentation validation.

It should participate in the Dashboard's existing `Promise.allSettled` refresh behavior so failure of KPI #5 cannot fail the Executive Dashboard or the other Motive observations.

With the existing Dashboard read plus four current KPI reads, adding KPI #5 changes the settled refresh group from five load promises to six. Existing tests that assert settled-load count must be updated deliberately rather than left stale.

## Responsive behavior

Wide screens:

- first row: three equal percentage observation columns;
- second row: two equal burn-rate observation columns;
- retain neutral separators between peers;
- do not allow the second row to create a visually empty third slot.

Narrow screens:

- stack all five observations vertically in source order;
- preserve the existing separator rhythm between observations;
- allow long unit-bearing values to fit without horizontal scrolling;
- do not reduce essential coverage/window text solely to keep a compact card.

The existing mobile breakpoint may be reused if it still provides readable behavior under focused tests.

## Utilization history boundary

The existing `30-Day Observation History` remains **utilization-only** and remains below all five current observations.

KPI #5 must not:

- add a driving-burn-rate history line;
- add a second chart;
- add an empty history placeholder;
- reconstruct historical driving burn rate from mutable vehicle-utilization rows;
- connect driving burn rate to the current utilization snapshot series.

Any driving-burn-rate snapshot/history contract requires a separate future design and persistence gate.

## Interpretation boundary

`gallons per driving hour` is a descriptive observed rate only.

Do not label or interpret it as:

- MPG;
- fuel efficiency;
- fuel economy;
- good / bad;
- high / low;
- waste;
- avoidable fuel;
- savings opportunity;
- expected burn;
- target burn;
- driver performance;
- truck performance;
- dispatch performance;
- route performance.

Driving fuel per hour can vary with speed, payload, traffic, terrain, weather, operating conditions, and other factors that are not represented in this KPI contract.

## Executive-attention boundary

This placement must not alter or populate:

- `business_status`;
- Needs Attention;
- Today's Plan / Today's Priority;
- Watch Items;
- Polaris Recommendation;
- Daily Brief;
- System / Data Health;
- notifications;
- email;
- Slack;
- alerts.

No HIGH/MEDIUM/CRITICAL, GOOD/WATCH, red/amber/green, pass/fail, benchmark, threshold, target, or recommendation semantics are authorized.

## Implementation scope after merge

The next implementation gate should be frontend/read-only only:

- add defensive driving-burn-rate presentation helper;
- add one independent authenticated GET/state path;
- add the fifth observation to the existing Fleet / Operations card;
- implement the approved 3 + 2 wide-screen layout and stacked mobile layout;
- preserve utilization-only history;
- update focused frontend/regression tests, including settled-load count;
- no backend change;
- no provider call;
- no database write;
- no package dependency;
- no history/snapshot change;
- no alerts/thresholds/business judgment.

## Required implementation tests

At minimum, the frontend gate must prove:

1. certified partial production-shaped payload renders the numeric rate;
2. `7.89` formats with the approved `gal/driving-hr` unit label;
3. metric coverage renders `61 / 161 vehicle-days (37.89%)` for the certified-shaped payload;
4. provider coverage is not substituted for metric-valid coverage;
5. `fleet_representative=false` renders the partial/non-representative wording;
6. valid `0.00` remains a displayed zero;
7. backend unavailable renders unavailable rather than zero;
8. request failure remains local to KPI #5;
9. malformed/non-finite/negative value fails closed;
10. malformed coverage fails closed;
11. wrong `driving_time_unit`, `fuel_unit`, `rate_unit`, request mode, timezone, KPI name, or `secrets_exposed` fails closed;
12. exactly one fixed GET path is used for KPI #5;
13. no Motive write/action route is called;
14. refresh uses six independently settled load promises after adding KPI #5;
15. all five observations remain in one Fleet / Operations card;
16. wide layout is three percentage columns followed by two equal burn-rate columns with no orphan/full-width fifth tile;
17. narrow layout stacks all five in source order;
18. utilization-only 30-day history remains below the five observations;
19. no driving-burn-rate history route/chart is introduced;
20. no MPG, efficiency, good/bad, waste, cost, target, alert, ranking, recommendation, Daily Brief, or Business Status semantics are introduced.

## Production certification after implementation

After a future frontend implementation merges and deploys:

1. refresh the production Dashboard without triggering Motive sync;
2. verify all five current observations render in the approved 3 + 2 layout;
3. verify Driving Fuel Burn Rate displays the live backend value and metric-valid coverage;
4. verify the window/timezone matches the backend response;
5. verify partial/non-representative wording is preserved when coverage is partial;
6. verify utilization history remains unchanged and utilization-only;
7. verify no business judgment, warning color, target, cost, or MPG/efficiency wording appears.

## Non-goals

This gate does not:

- implement frontend code;
- modify backend code;
- call Motive;
- write database state;
- add history or snapshots;
- estimate cost or savings;
- define thresholds or targets;
- rank drivers or vehicles;
- alter Daily Brief or Business Status;
- create alerts, actions, or recommendations.

## Next gate

After this design is merged, implement only the neutral frontend consumer and 3 + 2 Current Observations layout for `Observed 7-Day Driving Fuel Burn Rate`. Production-certify the Dashboard before considering any further KPI or trend work.