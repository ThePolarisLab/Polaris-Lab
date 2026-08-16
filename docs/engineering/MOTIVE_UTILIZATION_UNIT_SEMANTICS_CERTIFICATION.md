# Motive Vehicle Utilization Unit Semantics Certification

This gate reviews current **official Motive developer documentation** to try
to resolve a question left open by the prior reconciliation gate (PR #163,
see `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md`): for `GET
/v1/vehicle_utilization`, does the `X-Metric-Units` request header control
the unit system of the returned `idle_fuel`/`driving_fuel` values
independent of the returned `vehicle.metric_units` field?

It makes **no** live Motive API call. It does **not** enable durable fuel
persistence. It does **not** merge, and it does **not** add a database
migration.

## Sources Reviewed

Retrieved **2026-08-16** from `developer-docs.gomotive.com` (Motive's
official primary-source developer documentation):

1. `https://developer-docs.gomotive.com/reference/overview-utilization` --
   the utilization endpoints overview page.
2. `https://developer-docs.gomotive.com/reference/fetch-the-utilization-of-the-driver-v2-1`
   -- despite the confusing URL slug, this page's title is "Fetch the
   utilization of a vehicle" and its documented method/path is `GET
   /v1/vehicle_utilization`. This is the authoritative reference page for
   Polaris's certified endpoint.
3. `https://developer-docs.gomotive.com/reference/fetch-the-details-of-a-vehicle-using-its-number`
   -- a different, generic vehicle-details endpoint, reviewed only for
   contrast (its own `metric_units` field description differs in phrasing).
4. `https://developer-docs.gomotive.com/reference/fetch-the-utilization-of-a-vehicle-v2`
   -- explicitly **out of scope**. Despite its title, this documents a
   materially different endpoint (`GET /v2/vehicle_utilization`, ISO8601
   `start_at`/`end_at` datetimes, different pagination) that Source 1's own
   overview page indicates does not exist for vehicle-level utilization the
   way Polaris uses it. Its `metric_units` field description is **not**
   used as evidence for `/v1/vehicle_utilization` in this gate, even though
   it reads more conclusively than Source 2's -- a different endpoint
   version is not authoritative for the endpoint Polaris actually calls.

## Findings (Paraphrased; Short Attributed Quotes Only)

### Source 1 -- utilization overview

Confirms `/v1/vehicle_utilization` is the only vehicle-level utilization
endpoint Motive documents (v1 and v2 both exist for *driver* utilization,
but vehicle utilization only has a v1). This matches Polaris's certified
`MOTIVE_VEHICLE_UTILIZATION_ENDPOINT = "/v1/vehicle_utilization"` constant.

### Source 2 -- the v1 vehicle-utilization reference page (authoritative)

- `X-Metric-Units` header: described as selecting Metric vs. Imperial units
  for the request ("TRUE: Metric units. FALSE: Imperial Units").
- Response schema: `vehicle_idle_rollups[] -> vehicle_idle_rollup -> {
  vehicle: { id, number, year, make, model, vin, metric_units },
  utilization, idle_time, idle_fuel, driving_time, driving_fuel }`.
  `metric_units` is nested **inside** the `vehicle` object, matching
  Polaris's existing parser structure.
- `metric_units` field description on this endpoint: "Indicates whether
  metric units are used (e.g., false for imperial units)."
- `idle_fuel`/`driving_fuel` are each described generically as liters (e.g.
  "Fuel consumed during idle time in liters"), **not** conditioned on the
  request header's value.
- `idle_time`/`driving_time` are each described as seconds -- consistent
  with, and independently corroborating, Motive API Support's 2026-08-12
  written clarification that these are always seconds regardless of
  `X-Metric-Units`.
- `start_date`/`end_date` are both `date`-formatted (calendar dates, not
  datetimes). This page does **not** state whether `end_date` is inclusive;
  that specific fact remains sourced only from Support's 2026-08-12 email
  (the two pieces of evidence are complementary, not contradictory).
- Pagination on this page documents only `per_page` (default 25) and
  `page_no` (default 1); no `total` field is shown here either -- again,
  Support's email remains the source for `pagination.total` semantics.
- No rollup/record ID field appears anywhere on this page.
- The page's worked example response pairs a `"metric_units": false` value
  with fuel figures the field descriptions elsewhere call liters (a metric
  unit). This is suggestive of a "false implies imperial" reading, but nowhere
  on the page is a sentence that actually states or implies whether the
  request header and the response field correspond, conflict, or operate
  independently. **No reconciling statement was found.**

### Source 3 -- generic vehicle-details endpoint (contrast only)

A different, non-utilization endpoint's own `metric_units` field is
described as: "Indicates if the vehicle uses metric units." This phrasing
reads more like a vehicle display/configuration preference than Source 2's
unit-system-framed phrasing for the same field name on the utilization
endpoint. This inconsistency across endpoints is itself informative -- it
shows Motive's own documentation does not describe a same-named field
identically everywhere -- but it does not resolve the ambiguity for
`/v1/vehicle_utilization` specifically, and this gate draws no conclusion
about the utilization endpoint from a different endpoint's docs.

## Conclusion: OUTCOME B (Unresolved)

Official Motive documentation does **not** explicitly and sufficiently
confirm, for `GET /v1/vehicle_utilization` specifically, that
`X-Metric-Units` controls the unit system of returned `idle_fuel`/
`driving_fuel` values independent of (or regardless of) the returned
`vehicle.metric_units` field. The endpoint's own `metric_units` field
description is suggestively unit-system-framed and the worked example is
consistent with a "false implies imperial" reading, but there is no explicit
reconciling statement anywhere on the reference page, and the fuel fields
are described generically as liters without conditioning on the header.

As a result, this gate retains:

- `response_measurement_system: UNRESOLVED`
- durable fuel persistence: **DISABLED**
- and prepares (but does not send) a provider clarification artifact (below)

This is consistent with, and does not override, the conclusion already
reached in `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md` from the single
live controlled production observation and Motive API Support's 2026-08-12
written email -- this gate adds official-documentation evidence on top of
that prior evidence, and the combined picture still does not clear the bar
for certification.

## Conceptual Model (Section 6)

The code no longer treats "what Polaris requested" and "what Motive echoed
back about the vehicle" as necessarily the same concept. Three names are
now used consistently in `app/motive/vehicle_utilization_unit_policy.py`
and the writer contract's new `unit_semantics` block:

| Concept | Meaning | Status |
| --- | --- | --- |
| `requested_measurement_system` | What Polaris asks for via `X-Metric-Units` | certified: `metric` |
| `vehicle_configured_metric_preference` | Motive's returned `vehicle.metric_units` Boolean | raw provider metadata; not certified proof of response fuel units |
| `response_measurement_system_certification` | The actual unit system of a response's `idle_fuel`/`driving_fuel` | `UNRESOLVED` |

The raw provider field name `metric_units` does not itself prove what units
the returned fuel values use. The parser field itself is **not** renamed in
this gate (that would be needless churn); only the surrounding conceptual
model, naming, and documentation are enriched.

## DB Field Audit (Section 11)

`MotiveVehicleUtilizationRecord.metric_units`
(`chief-of-staff/backend/app/models/motive.py`, `Mapped[bool | None]`,
nullable) currently stores the raw provider-observed
`vehicle.metric_units` Boolean, unmodified.

Audit result: this is **(B)** -- it currently represents raw provider
`vehicle.metric_units` metadata (vehicle-configured-preference provenance),
**not** a certified statement that "measurement values in this row are
metric." Given Outcome B, it must not be relied upon as proof of a
persisted row's fuel measurement system until Outcome A is someday
certified.

This is a **forward-looking documentation finding only**. Durable fuel
persistence has been disabled since PR #163 (and remains disabled after
this gate), so no row has ever actually been persisted under this
ambiguity -- there is no existing-data cleanup concern.

**No migration is made in this gate.** If a future gate certifies Outcome A,
the existing column may be usable as-is (if the certified relationship turns
out to mean the observed Boolean *is* trustworthy fuel-unit provenance) or
may require a **future migration** introducing a separate, explicitly-named
measurement-system-provenance column so a single Boolean is never asked to
carry two different meanings (vehicle preference vs. persisted-value units)
at once. This gate does not decide which; it only flags the requirement.

## Fuel Provenance (Section 12)

Before durable persistence is allowed, Polaris must be able to say
unambiguously: `idle_fuel` unit = X, `driving_fuel` unit = X, for the
persisted record. Given Outcome B, this cannot yet be said. No unit
conversion is performed. No mixed units are combined. No inference is drawn
from the company's Canadian location or any other contextual signal.

## Time Metrics (Section 13)

`idle_time` and `driving_time` are seconds, independent of
`X-Metric-Units`. This was already confirmed by Motive API Support's
2026-08-12 written email and is now independently corroborated by Source 2
above (the v1 reference page's own field descriptions). This gate does not
change that classification.

## Provider Clarification Draft (Section 9 -- NOT Sent)

The following is prepared as a docs artifact only. **It has not been sent,
and this gate is not authorized to send it.**

```
Subject: RE: 11006147 | Clarification of X-Metric-Units vs vehicle.metric_units for /v1/vehicle_utilization

We sent X-Metric-Units: true to GET /v1/vehicle_utilization and received a
valid rollup whose vehicle.metric_units = false. We are NOT asking Motive to
inspect or change our account. Please confirm specifically:

1. Does X-Metric-Units=true guarantee that idle_fuel and driving_fuel in
   that response are metric/liters regardless of vehicle.metric_units?
2. Does vehicle.metric_units represent the vehicle's configured/display unit
   preference rather than the unit system applied to the returned
   utilization metric values?
3. Is it valid and expected for X-Metric-Units=true and
   vehicle.metric_units=false to coexist in the same response?
4. If yes, should integrations determine numeric measurement units from
   X-Metric-Units rather than from vehicle.metric_units?
5. Are idle_time/driving_time always seconds regardless of X-Metric-Units?
6. For vehicle utilization specifically, what units are idle_fuel and
   driving_fuel when X-Metric-Units=true?
```

No vehicle IDs, VINs, metric values, API key, or authorization data are
included. This artifact is intentionally not wired to any email-sending
code path.

## What Changed In This Codebase

- `app/motive/vehicle_utilization_unit_policy.py`: adds explicitly-named
  section-6 constants (`MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM`,
  `MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH`,
  `MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION`,
  `MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS`) and a new
  `vehicle_utilization_unit_semantics_contract_block()` helper. **No
  behavior change**: `validate_vehicle_utilization_unit_persistence_readiness`
  is untouched, and every existing readiness/status flag (all set by PR
  #163) is unchanged.
- `app/motive/vehicle_utilization_writer_contract.py`: adds an additive
  `unit_semantics` block (alongside the existing `unit_policy` block) built
  from the new helper above, per section 18.
- `app/models/motive.py`: adds an audit/documentation comment directly above
  `MotiveVehicleUtilizationRecord.metric_units` recording the section-11
  finding. No schema change.

## No Live Calls In This Gate

This gate makes **zero** live Motive HTTP calls anywhere -- not during
documentation review (which used previously-gathered, already-authoritative
research, not a live fetch performed by the implementing session), not
during implementation, and not during testing. No Motive API call, live or
otherwise, was made for "verification" purposes. All tests use static
values and mocked/synthetic data only.
