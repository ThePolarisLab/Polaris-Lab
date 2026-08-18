# Motive Vehicle Utilization: Account-Default Unit-Request-Mode Audit

This gate audits whether Polaris can safely support an explicit
**ACCOUNT_DEFAULT** request mode (no `X-Metric-Units` header at all) for
`GET /v1/vehicle_utilization`, alongside the existing certified `METRIC`
request mode. It makes **zero** live Motive calls, **zero** Render changes,
**zero** feature-flag changes, **zero** key rotation, and **zero** database
migration. Every fact below is proven by mocked (`httpx.MockTransport`)
tests only.

## 1. Why this gate exists

A separate, working local Python script pair on the same Motive account
(`motive_dashboard_server.py` and `motive_fuel_ifta_extract.py`, **not part
of this repository**) authenticates with the same certified `x-api-key`
pattern Polaris already uses, and calls `/v1/fuel_purchases` and
`/v1/ifta/summary` **without ever sending an `X-Metric-Units` header**. Both
scripts simply capture whatever unit the provider returns (e.g. `fuel_unit`)
and pass it through as-is -- an "account-default, trust what's returned"
pattern, not a "we decided the unit system" pattern. Both scripts
successfully receive account-configured US Imperial data (gallons, miles)
back from the account without ever forcing a unit system.

**This is supporting evidence only, not proof of `/v1/vehicle_utilization`
behavior.** `/v1/fuel_purchases` and `/v1/ifta/summary` are different
endpoints, different resources, with their own (unaudited-by-Polaris) unit
semantics. Motive API Support's 2026-08-17 written confirmation is specific
to `GET /v1/vehicle_utilization`'s `X-Metric-Units` header and returned
`vehicle.metric_units` indicator; it says nothing about what happens when
`X-Metric-Units` is omitted entirely for that endpoint. **No account-default
`/v1/vehicle_utilization` request has ever been made, live or otherwise.**
This gate motivates *offering* the mode; it does not certify that
account-default `vehicle_utilization` behavior matches the Fuel/IFTA
evidence, matches metric, matches imperial, or is even a supported request
shape server-side.

## 2. The problem with a plain `bool`

Before this gate, "what Polaris requested" was represented everywhere as a
plain `bool` (`requested_metric_units`, defaulting to `True`) --
`vehicle_utilization_requested_measurement_system()`,
`vehicle_utilization_requested_fuel_unit()`,
`vehicle_utilization_unit_context_consistent()`, and critically
`validate_vehicle_utilization_unit_persistence_readiness()`. A `bool`
structurally has only two states and **cannot** represent a third state:
"no `X-Metric-Units` header was sent at all." Overloading the Boolean (e.g.
`None` meaning "account default") would have made every existing
`None`-handling branch (already reserved for "missing returned indicator")
ambiguous. This is why the gate introduces a real, additive, explicit 3-mode
representation rather than reusing or stretching the Boolean.

## 3. The new representation

`app/motive/vehicle_utilization_unit_policy.py` adds
`MotiveVehicleUtilizationUnitRequestMode`, a 3-value `str` `Enum`:

| Mode | Header sent | Expected returned `vehicle.metric_units` | Fuel unit |
| --- | --- | --- | --- |
| `METRIC` | `X-Metric-Units: true` | `True` (else fail closed) | liters |
| `IMPERIAL` | `X-Metric-Units: false` | `False` (else fail closed) | gallons |
| `ACCOUNT_DEFAULT` | *(header omitted entirely)* | either -- no forced expectation | determined only by the returned Boolean |

Every function that predates this gate keeps its exact prior `bool`-based
signature and behavior unchanged. The new mode is purely additive:

- `vehicle_utilization_unit_request_mode_from_bool(requested_metric_units)`
  maps the legacy Boolean onto `METRIC`/`IMPERIAL` for backward compatibility.
- `vehicle_utilization_unit_request_mode_header_value(mode)` returns the
  exact header string for `METRIC`/`IMPERIAL`, and `None` for
  `ACCOUNT_DEFAULT` -- callers must treat `None` as "omit the header," never
  as an empty-string header value.
- `vehicle_utilization_unit_request_mode_measurement_system(mode)` and
  `vehicle_utilization_unit_request_mode_expected_fuel_unit(mode)` both
  return `None` for `ACCOUNT_DEFAULT`: Polaris never invents an expected
  measurement system or fuel unit before the provider responds.

## 4. Header emission (`request_vehicle_utilization_page`)

`app/connectors/motive_vehicle_utilization_pagination.py::request_vehicle_utilization_page`
gains an additive `unit_request_mode: MotiveVehicleUtilizationUnitRequestMode
| None = None` parameter.

- **Omitted (`None`, the default):** byte-for-byte identical to before this
  gate. The legacy `metric_units: bool = True` parameter is still enforced
  (`metric_units is not True` still raises), and the header is still always
  sent (`X-Metric-Units: true`).
- **Passed explicitly:** the legacy `metric_units is not True` restriction is
  bypassed (the caller made an explicit, separately-typed choice instead),
  and the header is emitted per the table above -- omitted entirely for
  `ACCOUNT_DEFAULT`.

`X-Time-Zone` and `X-User-Id` are never sent in any mode (unchanged), and
`x-api-key` authentication is unchanged. The general certified paginated
reader (`read_vehicle_utilization_pages`) gained the same additive parameter
and passes it straight through for every page.

The verification-only contract probe
(`app/connectors/motive_vehicle_utilization_contract.py::request_vehicle_utilization_payload`)
already supported omitting the header via `metric_units=None` with no
environment override, for its own unrelated read-only-probe purposes. It is
untouched by this gate.

## 5. Writer safety policy

`validate_vehicle_utilization_unit_persistence_readiness` gains an additive
`requested_mode: MotiveVehicleUtilizationUnitRequestMode | None = None`
keyword parameter, and the result dataclass
(`VehicleUtilizationUnitPersistenceReadiness`) gains an additive
`resolved_metric_units: bool | None` field (the unit-context Boolean a
caller should persist when ready; `None` whenever not ready).

- **`requested_mode` omitted:** derived from the legacy `requested_metric_units`
  Boolean via `vehicle_utilization_unit_request_mode_from_bool`, reproducing
  the exact prior resolved values and error codes for every existing caller.
- **`METRIC`/`IMPERIAL`:** unchanged forced-mode semantics -- a returned
  value disagreeing with the forced Boolean fails closed with
  `provider_unit_policy_mismatch`; a missing (`None`) value fails closed
  with `provider_unit_indicator_semantics_unresolved`; a malformed
  (non-Boolean, non-`None`) value fails closed with
  `provider_unit_context_invalid_type`.
- **`ACCOUNT_DEFAULT`:** no unit system was forced, so **there is no
  mismatch to fail closed on** -- a returned `True` or `False` is always
  ready, and `resolved_metric_units` becomes exactly that returned value
  (`True` => metric, `False` => imperial). A missing or malformed returned
  indicator still fails closed with the same two codes as the forced modes:
  account-default trusts only an explicit, well-formed returned Boolean,
  never a guess.
- The `MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED`
  kill switch gates **every** mode uniformly, including `ACCOUNT_DEFAULT`: it
  answers "is the returned Boolean's meaning trusted at all," independent of
  whether a unit system was forced on the request.

`write_vehicle_utilization_transaction`
(`app/motive/vehicle_utilization_writer.py`) gains the same additive
`unit_request_mode` parameter, defaulting to `None` (byte-for-byte identical
behavior to before this gate). Two internal fixes were required to make
`ACCOUNT_DEFAULT` actually persist correctly rather than silently persisting
the wrong value:

1. **`_build_new_row` no longer hardcodes `metric_units=True`.** It now
   persists `rollup.metric_units` -- the rollup's own, already
   readiness-validated returned value. For every canonical (non-account-default)
   caller this is always `True` (validation already fails closed on
   anything else before this point is ever reached), so this is a
   no-behavior-change for every existing caller. It is what lets
   `ACCOUNT_DEFAULT` rollups durably persist their actual observed unit
   context (`True` or `False`) instead of a silently-wrong hardcoded value.
2. **`_existing_row_context_compatible` no longer hardcodes
   `existing.metric_units is not True`.** It now compares
   `existing.metric_units is not rollup.metric_units`. For every existing
   canonical caller both sides are always `True` there, so this is
   identical behavior. It is required for `ACCOUNT_DEFAULT`: without this
   fix, an identical replay of a legitimately-persisted `metric_units=False`
   row would have been wrongly treated as an identity conflict (since the
   old check only ever asked "is the existing row's stored value literally
   `True`?", never "does the existing row agree with what the incoming
   rollup actually says?").

**No conversion is ever performed.** Fuel values are persisted exactly as
the rollup carries them, in whatever unit context `metric_units` records.
**No synthesized rows.** A selected-but-not-returned vehicle still creates no
row, no zero metrics, and no inactive/no-activity classification, in every
mode. **Replay identity is unchanged**: an unchanged account-default row
replayed again is still a true no-op (CASE 2); a later reread that returns a
*different* observed unit context for the same identity is still a hard
conflict (`conflicting_existing_identity`), never a silent overwrite of
`metric_units` in place. **Tenant isolation is unchanged**: a
cross-organization vehicle is still `unknown_vehicle` regardless of mode.

See `tests/test_motive_vehicle_utilization_writer_transaction.py`'s
`unit_readiness_gate`-marked account-default tests for the full proof of
every claim in this section.

## 6. Controlled write route: unchanged in this gate

`app/motive/vehicle_utilization_controlled_write.py` (the feature-flagged
`POST /api/v1/motive/verify/vehicle-utilization-write` route) is **not
modified by this gate**. It still calls `request_vehicle_utilization_page(...,
metric_units=True, ...)` and `write_vehicle_utilization_transaction(...)`
without `unit_request_mode`, so it continues to behave exactly as it did
before this gate -- fixed window `2026-08-13..2026-08-13`, at most 3
selected vehicles, at most 1 provider call, no checkpoint/history writes,
feature flag default `false`, no scheduler/general sync.

This was a deliberate scope decision, not an oversight: the underlying
request/unit-policy/writer stack now supports `ACCOUNT_DEFAULT`, proven
entirely by mocked tests, but switching the one route that can reach a real
Motive account to that mode is a separate, higher-stakes decision that
deserves its own narrowly-scoped review rather than being folded into this
audit gate. No live account-default `/v1/vehicle_utilization` request has
ever been made.

## 7. What this gate does NOT claim

- vehicle_utilization account-default behavior is **not** certified
- gallons are **not** guaranteed for any account-default response until a
  specific call's returned `vehicle.metric_units=false` is actually observed
- no timezone field is finally provider-certified by this gate (unchanged
  from prior gates -- see `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md`)
- no live `/v1/vehicle_utilization` call, in any mode, was made during this
  gate's implementation or testing

## 8. Migration

**None.** `MotiveVehicleUtilizationRecord.metric_units` was already a
nullable `Boolean` column able to store `True`, `False`, or `None`; no
schema change was needed to persist an account-default-observed `False`. No
Alembic migration is included in this gate.

## 9. Recommended next gate

A single, separately-authorized, narrowly-scoped live-staging validation
that:

1. explicitly opts the controlled write route (or a dedicated, equally
   bounded probe) into `ACCOUNT_DEFAULT` for exactly one bounded call
   (respecting the existing fixed-window / max-vehicle / max-call / no-retry
   bounds already enforced by the controlled route), and
2. records the sanitized outcome (provider calls, returned rollup count,
   observed `vehicle.metric_units`, rows inserted, safe-failure status) the
   same way the prior `PRODUCTION_WRITE_VALIDATION_EVIDENCE` entry did,

before any decision is made about switching the controlled route's default
mode, enabling the feature flag more broadly, or building any scheduled
ingestion on top of account-default. This gate does not perform that
validation and does not request it be performed as part of merging this PR.
