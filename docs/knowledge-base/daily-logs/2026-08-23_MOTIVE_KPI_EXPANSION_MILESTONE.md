# Polaris Knowledge Base — Motive KPI Expansion Milestone

**Date:** 2026-08-23

## Executive Summary

Polaris advanced the production-certified Motive vehicle-utilization foundation into a broader, deliberately neutral Fleet / Operations observation surface. The Executive Dashboard currently presents four independent seven-day observations—vehicle utilization, idle-time share, idle-fuel share, and idle fuel burn rate—while retaining utilization-only 30-day history. A fifth KPI, Observed 7-Day Driving Fuel Burn Rate, is now implemented and production-certified at the read-only backend/API layer; Dashboard placement remains a separate future gate.

## Official Decisions

- Motive operational KPIs remain descriptive observations, not business judgments.
- Coverage and `fleet_representative` context remain first-class and must accompany KPI values.
- Missing, malformed, partial, or provider-omitted evidence must not be converted into synthetic zero or fleet-wide certainty.
- Dashboard consumers remain read-only and independently fail-open; one KPI request must not take down the other Fleet / Operations observations.
- Fuel burn rate is expressed only as gallons per observed idle/driving hour. It must not be described as MPG, efficiency, waste, cost, good/bad performance, target attainment, or ranking.
- Deferred distance and engine-hours fields remain outside the certified KPI contract.

## Principles Reaffirmed

- Durable provider-certified evidence before consumer interpretation.
- Ratio-of-sums for fleet aggregate share/rate metrics rather than averaging per-row percentages/rates.
- Preserve legitimate numeric zero while failing closed on impossible or non-finite combinations.
- Zero additional Motive provider calls for KPI read models and Dashboard consumers.
- No thresholds, alerts, recommendations, Daily Brief attention, rankings, or Business Status changes without a separate evidence-backed gate.

## Current Production-Certified KPI State

The Fleet / Operations layer now has five production-certified seven-day read models:

1. **Observed 7-Day Vehicle Utilization** — shown on Dashboard.
2. **Observed 7-Day Vehicle Idle-Time Share** — shown on Dashboard.
3. **Observed 7-Day Vehicle Idle-Fuel Share** — shown on Dashboard.
4. **Observed 7-Day Idle Fuel Burn Rate** — shown on Dashboard.
5. **Observed 7-Day Driving Fuel Burn Rate** — backend/API production-certified; Dashboard placement not yet designed or implemented.

The utilization KPI retains the approved 30-day observation history. No historical series has been fabricated for the newer idle/fuel KPIs.

## KPI #5 Production Certification

The read-only endpoint `GET /api/v1/motive/fleet/vehicle-driving-fuel-burn-rate-kpi` is production-certified for the seven-day window `2026-08-16` through `2026-08-22` in `America/Chicago`.

Observed production response:

- `status = available_observed`
- `value_gallons_per_driving_hour = 7.89`
- `selected_vehicle_count = 23`
- `expected_requested_vehicle_days = 161`
- `provider_rollup_vehicle_days = 70`
- `metric_valid_vehicle_days = 61`
- `missing_requested_vehicle_days = 91`
- `provider_rollup_coverage_percent = 43.48`
- `driving_fuel_burn_rate_metric_coverage_percent = 37.89`
- `fleet_representative = false`
- `driving_time_unit = seconds`
- `fuel_unit = gallons`
- `rate_unit = gallons_per_driving_hour`
- `unit_request_mode = imperial`
- `secrets_exposed = false`

The value is descriptive only. It is not MPG and must not be interpreted as fuel efficiency, cost performance, driver performance, or a good/bad threshold.

## Engineering Decisions

Idle fuel burn rate uses durable `idle_fuel` and `idle_time` with a ratio-of-sums and deterministic seconds-to-hours conversion. Driving fuel burn rate mirrors the same certified pattern using durable `driving_fuel` and `driving_time`.

For both burn-rate KPIs:

- positive observed time with zero fuel is a legitimate zero burn-rate observation;
- zero time plus zero fuel has no burn-rate denominator;
- positive fuel with zero corresponding time fails closed;
- negative or non-finite metric values fail closed;
- coverage remains vehicle-day based and independent from the aggregate burn-rate denominator;
- provider omissions remain unknown rather than zero.

The Dashboard keeps the first four current observations inside the existing Fleet / Operations card. Wide screens use a neutral 2×2 current-observation grid and narrow screens stack the observations. The 30-day history below remains utilization-only.

## Completed Work

- Production-certified Observed 7-Day Vehicle Utilization and its prospective 30-day observation history.
- Production-certified and Dashboard-certified Observed 7-Day Vehicle Idle-Time Share.
- Production-certified and Dashboard-certified Observed 7-Day Vehicle Idle-Fuel Share.
- Production-certified and Dashboard-certified Observed 7-Day Idle Fuel Burn Rate.
- Implemented and production-certified the read-only Observed 7-Day Driving Fuel Burn Rate endpoint with zero Motive calls and zero database writes.
- Preserved explicit coverage, partial-observation semantics, tenant isolation, and sanitized responses across the Motive KPI layer.

## Remaining Gates

- Design Dashboard placement for Observed 7-Day Driving Fuel Burn Rate before any frontend implementation.
- If placement is approved, implement an independent read-only Dashboard consumer and production-certify it separately.
- Do not create driving-fuel-burn-rate history or infer trends without a separately certified historical contract.
- Keep distance/engine-hours metrics, fuel-cost interpretation, efficiency/waste classification, thresholds, alerts, rankings, Daily Brief attention, recommendations, and Business Status semantics deferred until separately designed and evidenced.

## Final State

Polaris now has four current Motive Fleet / Operations observations on the Executive Dashboard plus utilization-only 30-day history, and a fifth production-certified read-only Motive KPI available through the backend API. All remain deliberately descriptive, coverage-aware, tenant-scoped, and free of additional provider calls.