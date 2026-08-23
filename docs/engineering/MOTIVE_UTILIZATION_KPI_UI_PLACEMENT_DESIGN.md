# Motive Vehicle Utilization — KPI UI Placement Design

## Status

Design gate only.

This document defines the first Polaris UI placement for the already-certified `Observed 7-Day Vehicle Utilization` KPI. It does **not** change runtime behavior, provider calls, database state, scheduler behavior, production ingestion, Daily Brief behavior, business status, attention queues, alerts, thresholds, or production configuration.

The backend KPI endpoint is already merged and production-certified:

`GET /api/v1/motive/fleet/vehicle-utilization-kpi`

Production certification on 2026-08-22 returned an authenticated HTTP 200 with `status=available_observed`, `value_percent=46.74`, `metric_valid_vehicle_days=68`, `expected_requested_vehicle_days=161`, `utilization_metric_coverage_percent=42.24`, and `fleet_representative=false` for the certified 2026-08-15 through 2026-08-21 `America/Chicago` window. Those values are validation evidence only; the UI must always render the live endpoint response rather than hard-code them.

## Placement decision

Place the KPI on the existing **Executive Dashboard** as a neutral read-only **Fleet / Operations** reporting section.

Do not add a new sidebar route for this first KPI.

The current executive navigation already provides Dashboard, Daily Brief, ACE, Evidence, Decision Center, Connectors, and System Health. A new Fleet route for one metric would add navigation and information architecture before a broader fleet reporting surface exists.

### Exact dashboard position

Render the Fleet / Operations section:

1. after the existing summary strip (`Open Notes`, `Active Missions`, `Trucks`);
2. before the existing attention/action grid (`Needs Attention`, `Carry Forward`, `Today's Plan`, `Coming Up`, `Watch Items`, `Polaris Recommendation`).

This position makes the KPI visible as business context without promoting it into an action or severity surface.

## Consumer endpoint

The frontend may call only the already-certified read endpoint:

`GET /api/v1/motive/fleet/vehicle-utilization-kpi`

Use the existing authenticated `apiClient.get(...)` path so normal bearer-session and tenant headers are applied by the shared client.

The UI consumer must:

- make zero Motive provider calls directly;
- make zero database writes;
- invoke no Motive sync or verification route;
- invoke no scheduler or ingestion route;
- require no new backend endpoint or schema change.

## Loading and failure isolation

The KPI is secondary operational reporting and must not become a dependency of the core Executive Dashboard.

The implementation must maintain an independent KPI loading/error state.

Dashboard behavior requirements:

- dashboard content renders even if the KPI endpoint fails;
- a KPI read failure must not turn the whole Dashboard into `Dashboard unavailable`;
- a KPI read failure must not change `business_status`;
- a KPI read failure must not create `needs_attention`, `watch_items`, Today's Plan/Priority, recommendation text, or Daily Brief health;
- dashboard Refresh may re-read both the Dashboard and KPI, but one failure must remain isolated from the other;
- initial page load may read the KPI once from durable data; no polling or automatic timer refresh is introduced in this gate.

Preferred implementation pattern: independent requests or `Promise.allSettled`, never `Promise.all` in a way that makes the KPI failure reject the primary dashboard load.

## Section and card labels

Section label:

`Fleet / Operations`

KPI title:

`Observed 7-Day Vehicle Utilization`

The word **Observed** is mandatory unless `fleet_representative=true` for the exact endpoint response.

Do not label a partial-coverage result as:

- Fleet Utilization;
- Fleet Average Utilization;
- Truck Utilization;
- Active Fleet %;
- Fleet Productivity.

## Available observed — partial coverage

When:

- `status == "available_observed"`; and
- `fleet_representative == false`;

render the numerical value together with coverage and a neutral completeness warning.

Required information:

- KPI title;
- `value_percent`, formatted to two decimal places;
- `metric_valid_vehicle_days / expected_requested_vehicle_days`;
- `utilization_metric_coverage_percent`, formatted to two decimal places;
- window start/end;
- a neutral label that the observation is partial and is not fleet-representative.

Recommended presentation:

> **Observed 7-Day Vehicle Utilization**  
> **46.74%**  
> Coverage: **68 / 161 vehicle-days (42.24%)**  
> Partial observation — not fleet representative  
> Aug 15–21, 2026 · America/Chicago

The example values above are illustrative production evidence only and must not be hard-coded.

### Visual treatment

Partial coverage is **not** an incident severity.

Do not use existing HIGH/MEDIUM/CRITICAL severity badges or red/orange attention styling solely because coverage is below 100%.

Use neutral informational styling consistent with normal KPI/reporting cards.

## Available observed — full coverage

When:

- `status == "available_observed"`; and
- `fleet_representative == true`;

render the same KPI and coverage fields.

Coverage text may become:

`Full vehicle-day coverage`

The title may remain `Observed 7-Day Vehicle Utilization` for consistency. This gate does not authorize renaming it to `Fleet Utilization`, even at full coverage; any terminology promotion should be separately reviewed after sufficient historical operation.

Do not add a GOOD/healthy business judgment simply because coverage is 100%.

## Unavailable state

When `status == "unavailable"`, render a neutral unavailable state rather than a numerical zero.

Recommended presentation:

> **Observed 7-Day Vehicle Utilization**  
> **Unavailable**  
> No certified utilization metric is available for the latest reconciled window.

Rules:

- never display `0%` for unavailable;
- do not infer inactivity;
- do not infer fleet downtime;
- do not create an alert from KPI unavailability in this consumer;
- System / Data Health remains the separately certified surface for operational Motive health.

If the endpoint request itself fails, the card may display:

`Utilization reporting temporarily unavailable.`

Do not expose raw exception messages, tokens, provider IDs, database IDs, run IDs, or provider payloads.

## Coverage semantics

Display **utilization metric coverage**, not only provider-rollup coverage, adjacent to the KPI value because that is the population actually contributing to the arithmetic mean.

Primary coverage line:

`metric_valid_vehicle_days / expected_requested_vehicle_days vehicle-days (utilization_metric_coverage_percent%)`

Provider-rollup coverage may be omitted from the first visual card to keep the card concise. If exposed via a details treatment later, it must remain clearly distinguished from utilization-metric coverage.

Missing vehicle-days remain unknown. The UI must never calculate or display missing requested vehicle-days as zero-utilization vehicle-days.

## Window semantics

Display the endpoint-provided `window_start` and `window_end`.

Do not independently calculate `today - 7 days` in the frontend.

Display timezone context as `America/Chicago` or a user-friendly equivalent that does not imply browser-local dates.

The endpoint remains authoritative for the reconciled production window.

## Business and attention boundaries

This placement does **not** authorize any utilization threshold.

The KPI value or coverage percentage must not alter or populate:

- Executive Dashboard `business_status`;
- `Needs Attention`;
- Today's Plan / Today's Priority;
- `Watch Items`;
- Polaris Recommendation;
- Daily Brief `system_health`;
- Daily Brief `business_status`;
- email, Slack, notification, or other alert delivery.

No HIGH/MEDIUM/CRITICAL, GOOD/WATCH, red/amber/green, pass/fail, or target-attainment semantics are introduced in this gate.

Historical baseline and business operating context remain prerequisites for a later threshold-design gate.

## Refresh behavior

The existing Dashboard Refresh action may refresh this KPI along with the primary Dashboard read.

Requirements:

- one KPI GET per explicit Dashboard refresh;
- no Motive provider request is initiated by that GET;
- no frontend interval/polling is added;
- no separate `Sync Motive` button is added to the card;
- no Verify, Reconcile, or Run Scheduler control is added to the card.

The card is reporting-only.

## Accessibility and responsive behavior

The KPI value must have a text label and not rely on color alone.

Coverage and representativeness text must remain visible on narrow/mobile layouts.

If the implementation uses a progress meter, the numeric coverage text is still mandatory and the meter must not imply a business target. A simple text coverage line is preferred for the first implementation.

## Implementation scope for the next PR

The frontend implementation PR should be narrowly limited to:

1. read the existing KPI endpoint using `apiClient.get`;
2. add independent KPI state to `ExecutiveDashboard` or a small dedicated child component;
3. render the Fleet / Operations section in the fixed position defined above;
4. add only the CSS needed for the neutral reporting card;
5. add focused frontend tests.

No backend service, router, model, database, ingestion, scheduler, Daily Brief, Motive connector, or production configuration change should be required.

## Required frontend test matrix

At minimum, the implementation PR must prove:

1. `available_observed` partial coverage renders the value to two decimal places;
2. partial coverage renders `metric_valid_vehicle_days / expected_requested_vehicle_days` and coverage percent;
3. partial coverage explicitly states it is not fleet representative;
4. partial coverage does not render HIGH/MEDIUM/CRITICAL or GOOD/WATCH severity semantics;
5. `fleet_representative=true` renders full-coverage wording without creating a business judgment;
6. `unavailable` renders `Unavailable`, never `0%`;
7. endpoint failure leaves the rest of the Executive Dashboard usable;
8. KPI failure does not alter Business Status, Needs Attention, Today's Plan, Watch Items, or Recommendation content;
9. card uses the endpoint-provided window rather than browser-calculated dates;
10. card uses only the read-only KPI endpoint and exposes no sync/verify/scheduler control;
11. existing Dashboard Refresh causes at most one additional KPI read;
12. mobile/narrow rendering preserves value, coverage, and representativeness text.

## Production certification after implementation

After the frontend PR is merged and deployed:

1. sign in normally to Polaris;
2. open the Executive Dashboard;
3. verify the Fleet / Operations card appears;
4. compare only its sanitized aggregate values to one authenticated GET of the certified KPI endpoint;
5. verify the displayed coverage warning matches `fleet_representative`;
6. verify the existing Business Status and attention sections are unchanged by the KPI card;
7. do not trigger Motive sync, scheduler, reconciliation, or provider verification for this certification.

## Non-goals

This design does not:

- implement frontend code;
- add a new Fleet navigation route;
- add a trend chart;
- snapshot historical KPI values;
- rank vehicles or drivers;
- add utilization targets;
- add utilization alerts;
- add coverage alerts;
- add idle/fuel KPIs;
- add provider calls;
- change production ingestion;
- change the seven-day horizon;
- change timezone/unit policy;
- change database schema;
- change Daily Brief or System Health semantics.

## Next gate after UI certification

Once the card is production-certified, allow the scheduled production pipeline to accumulate reconciled daily history. A later **historical baseline / trend design gate** should define what historical data can be compared safely despite rolling reconciliation and should review actual distributions before any utilization target, trend judgment, or executive attention threshold is proposed.
