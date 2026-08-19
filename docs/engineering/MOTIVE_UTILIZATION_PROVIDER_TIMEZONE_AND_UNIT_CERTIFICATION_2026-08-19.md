# Motive Vehicle Utilization Provider Timezone and Unit Certification — 2026-08-19

## Status
Provider-written evidence only. This document does not make a provider call, change runtime behavior, enable ingestion, advance checkpoints, write sync history, enable scheduling, rotate credentials, or authorize a live production run.

## Scope
This evidence applies to Mor Logistics Manitoba Limited's use of Motive `GET /v1/vehicle_utilization` and records two written replies from Motive Dev/API Support received on 2026-08-19.

No API key, bearer token, VIN, vehicle ID, raw utilization metric value, or other secret/PII is reproduced here.

## Provider confirmation A — rollup timezone and calendar dates
Motive API Support confirmed:

- `GET /v1/vehicle_utilization` uses the company's configured/default rollup timezone to resolve `start_date` and `end_date` calendar-day boundaries.
- For the account settings identified as Central Time - Chicago, using the company-level Home terminal timezone as the working reference is appropriate.
- Date boundaries follow that local timezone, including daylight-saving-time rules.
- `end_date` is inclusive.
- Motive does not document a separate customer-configurable rollup timezone for this endpoint.
- The public rollup response does not include a separate timezone for each vehicle or rollup.
- The authoritative IANA identifier for Motive's Central Time - Chicago mapping is `America/Chicago`.
- Motive recommends treating request dates as local calendar dates in `America/Chicago` and using timezone-database rules rather than a fixed UTC offset.
- Motive suggested storing the timezone used for each synchronization request in integration metadata.

### Polaris certification outcome
For this account's production utilization design:

- request-window calendar semantics are certified as `America/Chicago`;
- local-day calculations must use IANA timezone rules including DST;
- `end_date` is inclusive;
- no `X-Time-Zone` header should be invented or required;
- sync metadata should retain the request timezone used;
- no vehicle-level timezone assumption is required.

## Provider confirmation B — `X-Metric-Units` omission and explicit US Imperial
Motive Dev Support separately confirmed:

- the endpoint uses the company's configured/default rollup timezone for date boundaries and does not use an individual user's preference timezone for vehicle-level rollups;
- the endpoint documentation defines `X-Metric-Units` as the request header selecting the returned metric unit system;
- Motive does **not** explicitly certify omission of `X-Metric-Units` as a supported way to select the account/company-configured unit system;
- when `X-Metric-Units: false` is explicitly sent, the expected interpretation is returned `vehicle.metric_units: false` with `idle_fuel` and `driving_fuel` in gallons.

### Polaris certification outcome
The staging-only `ACCOUNT_DEFAULT` / omitted-header mode is no longer the planned production contract.

The next production implementation must instead:

- explicitly send `X-Metric-Units: false` on every production `GET /v1/vehicle_utilization` request;
- require returned `vehicle.metric_units == false` before fuel-bearing rollups are persisted;
- fail closed on missing, malformed, or `true` returned unit context;
- interpret `idle_fuel` and `driving_fuel` as gallons only when the explicit `false` request and returned `false` context agree;
- perform no unit conversion;
- retain safe requested-measurement-system provenance in sync metadata.

Existing certified time-metric semantics remain unchanged: `idle_time` and `driving_time` remain seconds.

## Relationship to prior validation
The successful seven-day staging reconciliation validation remains valid evidence for:

- the bounded recent-window orchestration shape;
- one-day request windows;
- returned-only persistence;
- omission handling;
- writer identity/reconciliation behavior;
- bounded provider-call count;
- no checkpoint/history/scheduler side effects in that validation route.

It does **not** certify header omission as the production unit-request contract. The new provider reply narrows the production design to explicit US Imperial requests.

No previous successful staging rows are reinterpreted or rewritten by this documentation gate.

## Production design consequences
The production-ingestion design should use:

- timezone: `America/Chicago`;
- calendar model: local calendar dates with IANA DST rules;
- current day: never requested;
- `end_date`: inclusive;
- unit request: explicit `X-Metric-Units: false`;
- expected returned unit context: `vehicle.metric_units: false`;
- fuel unit: gallons only under agreeing request/response context;
- omission semantics: absent requested vehicles remain provider omissions only, never zero/no-activity rows;
- sync metadata: safe timezone and requested-measurement-system provenance;
- no `X-Time-Zone` request header;
- no automatic unit conversion.

## Safety and enablement status
This provider certification does not authorize scheduled or broad production ingestion.

Before broad scheduled production enablement:

1. the runtime must implement the certified timezone and explicit-US-Imperial contract;
2. CI and focused tests must prove the fail-closed invariants;
3. the Motive Company API Key must be rotated in secure backend configuration;
4. a zero-write connectivity/configuration preflight must pass;
5. exactly one separately authorized manual production-ingestion validation must produce sanitized evidence;
6. the production-ingestion flag must be returned to false after the validation;
7. scheduler enablement must receive a separate review and authorization.
