# Motive Vehicle Utilization Consumer Integration Design

## Status

Design gate only. This document does not change production runtime behavior, provider calls, database state, scheduler timing, alerts, dashboard output, or business-status scoring.

## Context

Track 4C vehicle-utilization ingestion is now certified in automatic production operation. The authenticated read-only operational endpoint is also merged and production-validated:

`GET /api/v1/motive/vehicle-utilization/operations-status`

The production validation returned HTTP 200 with `operational_status=healthy`, successful production history, successful durable checkpoint state, and a claimed same-local-day scheduler dispatch, while exposing no secrets and making zero Motive provider calls.

The next question is how Motive utilization should become a Polaris consumer signal without prematurely inventing business KPIs or alert thresholds.

The current executive dashboard already has a clean consumer path:

- backend `build_executive_dashboard(...)` composes `DailyBrief.system_health`;
- `_system_health(...)` currently contributes ACE feed health only;
- frontend `DailyBrief.jsx` renders `daily_brief.system_health` as the existing **System / Data Health** section;
- the executive dashboard already has separate `needs_attention`, `watch_items`, `business_status`, and recommendation semantics.

## Decision for the first consumer slice

Integrate **Motive operational health only** into the existing Daily Brief **System / Data Health** section.

Do **not** yet expose utilization-rate, idle-time, fuel-use, vehicle ranking, productivity, or business-performance KPIs in the Executive Dashboard or Daily Brief.

This keeps the first consumer integration aligned with evidence that is already certified: data-pipeline health, not business meaning.

## Source of truth

The consumer must reuse the existing backend operational-status service directly:

`vehicle_utilization_operational_status(session, organization_id)`

Do not make an internal HTTP request from the dashboard service to the operations-status route.

Benefits:

- zero Motive provider calls;
- zero duplicate authentication logic;
- zero dependency on the application calling itself over HTTP;
- one tenant-scoped operational-health implementation;
- no second interpretation of checkpoint/history/scheduler evidence.

## Proposed dashboard behavior

Extend `_system_health(db, organization_id)` to combine ACE health and Motive utilization operational health.

### Motive `healthy`

Return no Motive health item.

Rationale: the Daily Brief **System / Data Health** section should be attention-oriented. A healthy connector does not need to consume executive attention every morning.

### Motive `degraded`

Return one `DashboardItem`:

- title: `Motive vehicle utilization needs review`
- severity: `HIGH`
- source: `Motive Vehicle Utilization`
- entity_id: null for this first slice

Detail should be derived only from the safe operational-status response. Recommended deterministic detail priority:

1. latest production status if not `success`;
2. production checkpoint status if not `success`;
3. mismatch/staleness between successful history and persisted checkpoint;
4. otherwise a generic sanitized message: `Production utilization state is inconsistent; review Motive operational status.`

Do not include exception strings, raw JSON, run ids, provider vehicle ids, secrets, or unrestricted metadata.

### Motive `not_started`

For this production environment, return one `DashboardItem` only when production ingestion or scheduler configuration is enabled:

- title: `Motive vehicle utilization has no production history`
- severity: `MEDIUM`
- source: `Motive Vehicle Utilization`

If both production ingestion and production scheduler are disabled, return no executive attention item. Disabled/non-configured capability is not automatically an operational incident.

### Scheduler claim semantics

Never generate a health alert solely because the current local day is not claimed.

The durable scheduler dispatch claim proves only that a local-day dispatch was consumed. It does not prove successful ingestion and it should not independently drive executive severity.

## Business-status boundary

The first consumer slice must **not** change `dashboard.business_status`.

Current business status is based on executive attention items such as blockers/compliance/ACE exceptions. Motive operational health should appear in **System / Data Health** without silently changing company-level status until a separate policy explicitly decides whether data-pipeline degradation should affect business status.

## Needs Attention / Watch Items boundary

Do not add Motive utilization health to `needs_attention` or `watch_items` in this first slice.

Reason:

- `needs_attention` is already part of plan/priority generation and can alter Today's Plan;
- `watch_items` is used for business-operational watch semantics;
- the first Motive consumer integration is data-health observability only.

A later policy can promote specific Motive conditions into executive priority if business impact is defined.

## No business KPI thresholds yet

Do not create alerts from raw utilization values such as:

- idle seconds;
- utilization percentage;
- miles or engine time;
- fuel gallons;
- low-activity vehicles;
- changes versus prior days;
- fleet averages;
- missing provider rollups.

Provider omission remains unknown/absent, never zero. A missing rollup cannot be classified as an inactive truck.

Before utilization KPIs are consumed, a separate design must define:

1. the exact business question;
2. eligible vehicle population;
3. denominator and time window;
4. treatment of missing provider rollups;
5. unit policy;
6. minimum data completeness;
7. severity/attention thresholds;
8. whether the signal belongs in Dashboard, Daily Brief, reporting, or an operations-only view.

## Failure isolation

Dashboard availability must not depend on Motive observability being readable.

If the Motive operational-status read raises a database/read exception while the rest of the dashboard can render:

- do not fail `/dashboard/executive`;
- add one sanitized `HIGH` System / Data Health item such as `Motive utilization health could not be read`;
- do not retry;
- do not call Motive;
- do not write any state.

This follows the existing ACE health pattern where dashboard composition degrades safely rather than failing the entire executive surface.

## Tenant isolation

All Motive operational-health reads must use the organization id already passed to `build_executive_dashboard(...)`.

No caller-supplied organization id or slug is added.

Tests must prove that another tenant's newer Motive history/checkpoint rows cannot affect the rendered Daily Brief health item.

## Frontend scope

No new frontend endpoint call is needed.

`DailyBrief.jsx` already renders `dashboard.daily_brief.system_health` using the generic `BriefItems` component. The first implementation should therefore require no new Motive-specific frontend state, auth, polling, or API client behavior.

If a later implementation adds a dedicated Motive operations page, its navigation and user experience should be designed separately.

## Test matrix for implementation gate

At minimum:

1. healthy Motive operational status adds no System / Data Health item;
2. degraded Motive status adds one HIGH sanitized item;
3. not_started + enabled production configuration adds one MEDIUM item;
4. not_started + both production gates disabled adds no item;
5. scheduler unclaimed state alone does not add an item;
6. Motive read exception does not fail the dashboard and adds one sanitized HIGH item;
7. ACE and Motive health items can coexist;
8. Motive health does not alter `business_status` in this slice;
9. Motive health does not enter `needs_attention`, Today's Plan, or `watch_items`;
10. cross-tenant Motive rows never influence another tenant;
11. dashboard request performs zero Motive provider calls and zero database writes;
12. no raw operational-status JSON, secret-like keys, run ids, provider vehicle ids, or exception strings leak into dashboard items;
13. existing Daily Brief frontend renders the new generic health item without Motive-specific frontend code.

## Non-goals

This gate does not:

- add utilization performance KPIs;
- rank drivers or vehicles;
- calculate fleet productivity;
- classify missing provider rows as inactivity;
- send alerts, email, Slack, or notifications;
- change GitHub Actions or Motive scheduler behavior;
- change ingestion units, timezone, horizon, pagination, retries, reconciliation, or omission semantics;
- change `business_status`;
- add a dedicated Motive dashboard page;
- add a new Motive provider domain.

## Recommended rollout

1. Merge this design gate.
2. Implement backend-only Daily Brief System / Data Health integration with focused tests.
3. Run full required CI.
4. Perform one authenticated production GET of `/dashboard/executive` and confirm the healthy Motive state produces no alert while ACE/other dashboard behavior remains unchanged.
5. If a controlled degraded-state test is desired, perform it only in tests/staging; do not perturb production Motive checkpoints/history for validation.
6. After health integration is certified, separately design the first business utilization KPI before exposing raw utilization metrics to executives.
