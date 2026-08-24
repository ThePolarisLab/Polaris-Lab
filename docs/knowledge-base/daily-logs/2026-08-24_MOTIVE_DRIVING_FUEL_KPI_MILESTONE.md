# Polaris Knowledge Base — Motive Driving Fuel KPI Milestone

**Date:** 2026-08-24

## Executive Summary

Polaris advanced the Motive Fleet / Operations read-only KPI surface from four current observations to five. The `Observed 7-Day Driving Fuel Burn Rate` read model and authenticated endpoint were merged, and the already production-certified KPI was subsequently placed on the Dashboard using a neutral five-observation layout.

A sixth KPI, `Observed 7-Day Fuel Burn Rate`, has now passed its design-only architecture gate. Runtime implementation for KPI #6 has not yet occurred.

## Official Decisions

- Driving fuel burn rate is a descriptive observation only: gallons consumed per observed driving hour.
- It must not be presented as MPG, fuel efficiency/economy, cost, waste, target performance, good/bad status, ranking, alert, recommendation, Daily Brief attention, or Business Status.
- KPI coverage must use metric-valid vehicle-days rather than broader provider-rollup coverage.
- Valid zero remains zero; invalid or inconsistent denominator cases fail closed.
- The Dashboard keeps all five current Motive observations inside the existing Fleet / Operations card. On wide screens the layout is neutral `3 + 2`; narrow screens stack all five.
- The existing 30-day history remains utilization-only.
- KPI #6 will be a blended observed fuel burn rate over idle + driving operating time, using ratio-of-sums semantics. It must not use deferred/legacy `distance` or `engine_hours` fields.

## Principles Reaffirmed

- Read durable certified data; do not call Motive to render business KPIs.
- Preserve tenant isolation and `CONNECTOR_READ` authorization.
- Keep provider-rollup coverage separate from metric-valid KPI coverage.
- Preserve null/unknown separately from real zero.
- Fail closed on malformed units, provenance, population, window, or denominator semantics.
- Separate descriptive observations from business judgment, thresholds, alerts, and executive attention.
- Use design → implementation → production certification → placement as separate gates.

## Roadmap Changes

- KPI #5 — Observed 7-Day Driving Fuel Burn Rate: backend read model and endpoint merged; Dashboard placement merged.
- Fleet / Operations Current Observations: expanded from four to five observations.
- KPI #6 — Observed 7-Day Fuel Burn Rate: architecture/design gate merged; runtime implementation is the next gate.
- Driving burn-rate history, total fuel burn-rate history, distance/engine-hours KPIs, thresholds, alerts, rankings, recommendations, and executive-attention semantics remain deferred.

## Engineering Decisions

The driving fuel burn-rate backend uses already-durable Motive vehicle-utilization rows and the same certified seven completed `America/Chicago` calendar-day production window. It computes a ratio of sums:

`sum(driving_fuel) * 3600 / sum(driving_time)`

rather than averaging per-row burn rates. The endpoint is tenant-scoped, `CONNECTOR_READ`, SELECT-only, sanitized, and performs zero Motive calls and zero database writes.

The Dashboard consumer independently validates KPI identity, secrets flag, value, metric-valid coverage, units, request mode, timezone, and window before rendering. Its request/failure state is independent from the other Motive observations.

The sixth KPI design defines:

`sum(idle_fuel + driving_fuel) * 3600 / sum(idle_time + driving_time)`

for metric-valid vehicle-days in the same certified seven-day window. It is explicitly distinct from averaging the existing idle and driving burn-rate KPIs.

## Research / Verification Notes

The merged driving-burn-rate implementation preserves real zero fuel with positive driving time as `0.00 gal/driving-hour`, treats `0 driving time + 0 fuel` as a provider observation without a burn-rate denominator, and fails closed on positive fuel with zero driving time or negative/non-finite metric values.

The Dashboard placement uses the production-certified partial observation example `7.89 gal/driving-hr` with metric-valid coverage `61 / 161 vehicle-days (37.89%)`, explicitly distinct from broader provider-rollup coverage. Partial coverage is shown as not fleet representative rather than extrapolated to the fleet.

## Completed Work

- Merged PR #230: read-only Observed 7-Day Driving Fuel Burn Rate KPI endpoint.
- Merged PR #232: Dashboard placement design for KPI #5.
- Merged PR #233: Dashboard implementation for the fifth Motive observation and neutral `3 + 2` wide-screen layout.
- Merged PR #234: design-only gate for KPI #6, Observed 7-Day Fuel Burn Rate.

## Remaining Gates

1. Implement KPI #6 as one tenant-scoped read-only backend service and one `CONNECTOR_READ` GET endpoint with focused fail-closed tests.
2. Production-certify KPI #6 before considering Dashboard placement.
3. Keep KPI #6 frontend placement as a separate later design/implementation gate.
4. Continue to defer burn-rate history, distance/engine-hours metrics, cost/efficiency judgments, thresholds, alerts, rankings, Daily Brief attention, recommendations, and Business Status effects unless separately designed and authorized.

## End State

Motive Fleet / Operations now has five merged current Dashboard observations, with driving fuel burn rate available through a certified read-only path and neutral UI placement. The next safe expansion is the separately gated implementation and production certification of the sixth blended observed fuel burn-rate KPI.