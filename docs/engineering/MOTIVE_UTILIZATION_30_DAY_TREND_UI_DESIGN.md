# Motive Vehicle Utilization — 30-Day Trend UI Design

## Status

Design gate only.

This document defines the next read-only Polaris consumer for the already-certified `Observed 7-Day Vehicle Utilization` KPI history. It does **not** implement frontend runtime code, add provider calls, write database state, change ingestion/scheduler behavior, create historical backfill, add business thresholds, or alter any executive attention surface.

Existing certified read endpoints:

- current observation: `GET /api/v1/motive/fleet/vehicle-utilization-kpi`
- bounded history: `GET /api/v1/motive/fleet/vehicle-utilization-kpi/history?days=30`

History collection is prospective. Missing historical snapshots are genuine gaps and must never be synthesized.

## Placement decision

Extend the existing **Fleet / Operations** card on the Executive Dashboard rather than adding a new navigation route.

The current placement remains authoritative:

1. after the summary strip (`Open Notes`, `Active Missions`, `Trucks`);
2. before the attention/action grid (`Needs Attention`, `Carry Forward`, `Today's Plan`, `Coming Up`, `Watch Items`, `Polaris Recommendation`).

The existing current-observation block remains visually primary. The 30-day history appears as a secondary trend region inside the same Fleet / Operations reporting card.

This preserves the distinction between operational reporting and executive action/severity surfaces.

## Consumer endpoints and request behavior

The frontend may call only the two existing read endpoints:

- `/api/v1/motive/fleet/vehicle-utilization-kpi`
- `/api/v1/motive/fleet/vehicle-utilization-kpi/history?days=30`

Use the existing authenticated `apiClient.get(...)` path so the normal bearer session and tenant organization header are applied centrally.

The trend consumer must:

- make zero Motive provider calls directly;
- make zero database writes;
- invoke no Motive sync, verify, reconcile, scheduler, ingestion, or internal route;
- add no backend endpoint or database migration;
- use a fixed 30-day history request in the first implementation;
- introduce no polling or timer refresh.

The existing Dashboard Refresh action may re-read Dashboard, current KPI, and history once each. These reads must remain isolated with `Promise.allSettled` or equivalent behavior so one reporting failure never rejects the primary Dashboard.

## Frontend dependency decision

The current frontend has no chart library dependency. The first trend implementation must **not** add Recharts, Chart.js, D3, or another chart package solely for this KPI.

Use a small dependency-free React component backed by native SVG and normal HTML/CSS.

Reasons:

- the chart is a single bounded series;
- the y-domain is naturally fixed at 0–100 percent;
- native SVG can preserve calendar spacing and intentional gaps without a large dependency;
- avoiding a new package keeps the implementation and security surface narrow;
- accessibility can be provided through explicit text/ARIA alongside the visual SVG.

A chart-library decision may be revisited later if Polaris develops several reusable analytical charts.

## Data contract used by the trend

Use only sanitized aggregate fields returned by the history endpoint.

Top-level fields used:

- `kpi`
- `requested_history_days`
- `history_start`
- `history_end`
- `request_timezone`
- `snapshot_count`
- `points`

Per-point fields used:

- `window_start`
- `window_end`
- `status`
- `value_percent`
- `utilization_metric_coverage_percent`
- `metric_valid_vehicle_days`
- `expected_requested_vehicle_days`
- `fleet_representative`

The UI must not require or attempt to recover source-history IDs, run IDs, provider vehicle IDs, VINs, plates, raw provider payloads, database IDs, credentials, tokens, or vehicle-level data.

## Trend semantics

### X-axis

The x-axis represents the endpoint-provided 30-calendar-day horizon from `history_start` through `history_end` in `America/Chicago`.

Position observations according to their actual `window_end` date within that calendar horizon. Do not pack available snapshots together with equal spacing if calendar dates are missing.

The frontend may parse ISO dates only to calculate relative x positions inside the endpoint-provided horizon. It must not independently redefine which day is the latest completed day.

### Y-axis

The y-axis is utilization percent with a fixed visual domain of `0` through `100`.

This is a measurement scale only. It must not imply a target, pass/fail boundary, healthy range, or business goal.

Do not draw target lines, warning bands, green/amber/red zones, or benchmark bands.

### Missing snapshot dates

If there is no snapshot for a calendar date, that date remains a **gap**.

Do not:

- insert a `0%` point;
- carry forward the previous value;
- interpolate a value;
- manufacture an unavailable record;
- connect a trend line across a missing calendar date as if continuous observation existed.

When adjacent returned snapshots have `window_end` dates more than one calendar day apart, break the SVG line between those observations.

### Unavailable snapshot points

A returned snapshot with `value_percent = null` is an explicit unavailable observation, not `0%`.

For the visual trend:

- do not assign it a numerical y-value;
- break the line before and after it;
- represent its date with a neutral unavailable marker/tick on the timeline if practical;
- provide text/ARIA such as `Unavailable observation`.

The current KPI card's existing `Unavailable` semantics remain unchanged.

### Valid zero

A returned `value_percent = 0` is a valid observed measurement and must be plotted at the 0% position.

Do not confuse numeric zero with `null` or missing history.

## Coverage and representativeness

The utilization value and the quality/completeness of that observation must stay visibly distinct.

For each plotted observation, its accessible label/detail should include:

- utilization value to two decimals when available;
- `metric_valid_vehicle_days / expected_requested_vehicle_days`;
- `utilization_metric_coverage_percent` to two decimals;
- `window_end`;
- whether `fleet_representative` is true or false.

Coverage is contextual metadata, not business severity.

Do not color utilization points red/yellow/green based on coverage. Do not call lower coverage `bad`, `high risk`, `critical`, or `needs attention`.

The chart may use one neutral line/point treatment. A visually distinct but still neutral marker may indicate `fleet_representative=true`, but this is optional; explicit text is required where details are exposed.

## History states

### No snapshots

When `snapshot_count == 0`, do not render an empty coordinate chart that implies data exists.

Render a neutral history state such as:

`30-day trend will appear after successful daily utilization snapshots are recorded.`

This is expected during initial prospective accumulation and must not generate an alert.

### One usable snapshot

With one available numerical snapshot:

- render a single point;
- do not draw a trend line suggesting direction;
- label the history as `1 observation` or equivalent;
- retain coverage context.

Do not say increasing/decreasing/stable.

### Two or more usable snapshots

Render line segments only between consecutive calendar-day observations with numerical values.

The chart may visually show shape/direction, but this gate does not authorize textual judgments such as:

- improving;
- worsening;
- strong;
- weak;
- above target;
- below target;
- concerning.

### History request failure

If the history GET fails:

- the current KPI block remains usable;
- the rest of the Executive Dashboard remains usable;
- render a neutral trend-only message such as `Utilization history temporarily unavailable.`;
- do not replace the current KPI with unavailable if its own GET succeeded;
- do not expose raw exception text.

## Current KPI and history independence

The current KPI and history are separate read models and must have separate frontend loading/error state.

Required behavior:

- current KPI success + history failure: current KPI renders normally; trend shows history unavailable;
- current KPI failure + history success: current KPI shows its existing unavailable/request-failure state; history may still render its certified snapshots;
- Dashboard core success + either Motive read failure: Dashboard remains usable;
- Dashboard core failure: existing Dashboard failure behavior remains authoritative and is not changed by this gate.

No trend observation may alter the current KPI value or coverage calculation.

## Visual layout

Keep the current Fleet / Operations heading and current KPI block.

Recommended internal layout:

1. `FLEET / OPERATIONS`
2. `Observed 7-Day Vehicle Utilization`
3. current value / current coverage / completeness / current 7-day window
4. subtle divider
5. `30-Day Observation History`
6. native SVG plot or history-state message
7. concise footer: endpoint-provided history range and `America/Chicago`

The chart should remain secondary to the current certified KPI value.

Do not create a separate dashboard card with severity semantics.

## SVG implementation contract

The implementation should use a small deterministic helper/presentation layer rather than burying data validation inside SVG markup.

Recommended responsibilities:

- validate the history payload shape conservatively;
- preserve `0` and reject non-finite numerical values;
- classify each calendar point as `available`, `unavailable`, or absent/gap;
- calculate x positions from the endpoint-provided calendar horizon;
- calculate y positions from the fixed 0–100 domain;
- generate independent contiguous line segments that break on missing dates or unavailable values;
- expose accessible observation labels including coverage.

Do not use a smoothing algorithm that visually invents intermediate values. Straight line segments are preferred.

## Accessibility

The trend cannot rely on the SVG shape alone.

At minimum:

- provide an accessible chart title such as `30-day observed vehicle utilization history`;
- expose a concise text summary containing snapshot/usable-observation count and history range;
- each rendered usable/unavailable observation must have an accessible label or equivalent detail;
- valid zero and unavailable must be distinguishable in text, not only by vertical position or color;
- keyboard/focus treatment for individual points is preferred if point details are interactive;
- no essential meaning may depend only on color.

If point hover/focus details are implemented, use normal HTML/SVG labels; do not add a tooltip dependency.

## Responsive behavior

The current card already collapses metadata for narrow screens. The trend must remain usable on mobile/narrow layouts.

Requirements:

- SVG width is responsive to the card/container;
- preserve a practical minimum chart height;
- avoid dense daily x-axis labels; show only a small number of date anchors while preserving actual daily x positioning;
- current value/coverage text remains visible above the trend;
- no horizontal page overflow.

## Business and attention boundaries

This design does **not** authorize utilization thresholds or trend judgments.

Neither current value nor historical movement may alter or populate:

- Executive Dashboard `business_status`;
- `Needs Attention`;
- Today's Plan / Today's Priority;
- `Watch Items`;
- Polaris Recommendation;
- Daily Brief `system_health`;
- Daily Brief `business_status`;
- email, Slack, notification, or other alert delivery.

Do not add:

- HIGH/MEDIUM/CRITICAL;
- GOOD/WATCH;
- green/amber/red status;
- utilization targets;
- target attainment;
- increasing/decreasing quality judgments;
- benchmarking against an external fleet average.

A later threshold-design gate requires sufficient MOR operating history and explicit approval.

## Implementation scope for the next PR

After the first production snapshot is certified, the frontend implementation PR should be narrowly limited to:

1. add a separate read of `/api/v1/motive/fleet/vehicle-utilization-kpi/history?days=30`;
2. add independent history loading/error state to the existing Executive Dashboard consumer;
3. add a deterministic history presentation/geometry helper in the existing Motive frontend presentation layer or a small dedicated module;
4. extend the existing Fleet / Operations card with the neutral native-SVG trend/history states;
5. extend the existing Motive utilization CSS only as needed;
6. add focused frontend tests.

No backend, migration, provider, ingestion, scheduler, Daily Brief, alerting, or production configuration file should change.

No new npm dependency should be required.

## Required frontend test matrix

At minimum, the implementation PR must prove:

1. history request uses exactly `/api/v1/motive/fleet/vehicle-utilization-kpi/history?days=30` through `apiClient.get`;
2. history loading/error state is independent from current KPI and core Dashboard state;
3. `snapshot_count=0` renders a neutral accumulation message and no fabricated `0%` point;
4. one numerical snapshot renders one point and no directional line/judgment;
5. valid `0%` is retained as a numerical observation;
6. `value_percent=null` renders unavailable semantics and breaks line continuity;
7. missing calendar dates create visible/structural gaps and are not interpolated;
8. points are positioned from endpoint-provided `history_start`, `history_end`, and `window_end` dates;
9. y geometry is fixed to 0–100 without targets or threshold bands;
10. each usable point retains utilization-metric coverage context;
11. `fleet_representative=false` never becomes a severity/action classification;
12. malformed history payload fails closed to a neutral history-unavailable state;
13. Dashboard Refresh causes at most one additional history GET;
14. no frontend Motive POST/DELETE/sync/verify/reconcile/scheduler route is introduced;
15. no chart dependency is added to `package.json`;
16. no HIGH/MEDIUM/CRITICAL, GOOD/WATCH, target, or alert semantics are introduced in the trend component.

## Production certification after implementation

After the implementation PR is merged and deployed:

1. sign in normally to Polaris;
2. open the Executive Dashboard;
3. compare the trend against one authenticated `GET .../history?days=30` response;
4. verify returned snapshots map to the correct calendar positions;
5. verify any missing dates remain gaps;
6. verify `null` remains unavailable and numeric `0` remains zero;
7. verify displayed coverage details match the sanitized aggregate history response;
8. verify the existing current KPI, Business Status, and attention sections remain independent;
9. do not trigger Motive sync, scheduler, reconciliation, or provider verification for this certification.

## Non-goals

This gate does not:

- implement the chart;
- add a chart dependency;
- add a new Fleet navigation route;
- backfill snapshots;
- change the 7-day KPI calculation;
- change the 30-day/90-day history endpoint contract;
- rank vehicles or drivers;
- display vehicle-level history;
- add idle/fuel KPIs;
- add utilization thresholds or targets;
- create trend alerts;
- change Business Status or Daily Brief;
- add provider calls or writes.

## Next gate

After this design is merged and the first automatic production snapshot is certified, implement the frontend trend as a separate PR. Allow real snapshots to accumulate before any later baseline/threshold-design gate.