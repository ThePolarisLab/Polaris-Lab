# Polaris Track 4C: Motive Roadmap

## 4C.1E: Company API Key Production Foundation

- Keep `chief-of-staff/` as the only production runtime.
- Replace active Motive OAuth production behavior with Company API Key authentication for Mor Logistics' single-company server-to-server integration.
- Read the production key only from secure backend configuration: `MOTIVE_API_KEY`.
- Retain tenant-owned Motive foundation tables, sync history, checkpoints, normalized internal contracts, organization isolation, idempotency constraints, safe status APIs, frontend connector status, System Health mapping, Evidence mapping, and safe logging controls.
- Use limited read-only verification only: `GET /v1/vehicles?per_page=1&page_no=1`.
- Disable active OAuth connect/callback behavior while retaining deployed OAuth schema unless cleanup is separately reviewed.

## 4C.2A: Vehicle Read-Only Production Ingestion

- Adds manual vehicle-only ingestion using `POST /api/v1/motive/sync/vehicles`.
- Uses the confirmed endpoint `GET /v1/vehicles?per_page=100&page_no=N` with Company API Key authentication at the backend HTTP boundary.
- Persists only tenant-owned vehicle records in `motive_vehicles` using `(organization_id, provider_vehicle_id)` as the idempotent provider identity.
- Reuses existing `motive_sync_history` and `motive_sync_checkpoints`; checkpoints advance only after successful durable persistence.
- Exposes safe vehicle sync metadata on Motive status: last vehicle sync time/status, records stored, records read, and pages read.
- Keeps broad sync disabled and production certification false; this track certifies only vehicle endpoint connectivity, pagination, idempotent vehicle upserts, manual vehicle sync, and safe metadata.

## 4C.2B: Company User Read-Only Production Ingestion

- Adds manual company-user ingestion using `POST /api/v1/motive/sync/users`.
- Uses the confirmed endpoint `GET /v1/users?per_page=100&page_no=N` with Company API Key authentication at the backend HTTP boundary.
- Uses Motive support's confirmed pagination contract: `per_page` maximum 100, one-based `page_no`, and `pagination.total`.
- Persists tenant-owned company-user records using `(organization_id, provider_user_id)` as the provider identity. The existing storage column name remains `provider_driver_id` until a separately reviewed schema cleanup is justified.
- Does not classify every `/v1/users` row as a driver. Driver classification remains `unknown` and `driver_classification_certified=false` until Motive documents or production samples certify a role/type discriminator.
- Exposes safe user sync metadata only: last user sync time/status, records stored, records read, pages read, and driver-classification certification state.
- Keeps broad sync disabled and production certification false; this track certifies only `/v1/users` connectivity, pagination, idempotent company-user upserts, manual user sync, and safe metadata.

## 4C.2C+: Provider Contract Completion and Sync Design

Track 4C.2C0 verified the temporary `GET /v1/vehicle_utilization` provider request contract after PR #132 removed `X-Time-Zone`. The successful controlled production request used one stored provider vehicle ID, the two-completed-calendar-day window introduced by PR #131, `per_page=1`, `page_no=1`, backend-only `X-API-Key`, no `X-User-Id`, exactly one provider attempt, no retry, no persistence, and no checkpoint mutation. This verifies only that exact temporary request shape and strongly supports that `X-Time-Zone: America/Winnipeg` caused the earlier provider rejection.

The subsequent zero-item controlled schema capture returned `top_level_type=object`, `top_level_keys=["pagination","vehicle_idle_rollups"]`, `item_container_key=vehicle_idle_rollups`, `item_count_observed=0`, and `pagination_keys=["page_no","per_page","total"]`. PR #135 then bounded the temporary verifier to up to three existing organization-owned stored vehicle IDs in one provider request. The post-PR #135 controlled production request returned HTTP 200 with `provider_vehicle_selected_count=3`, `item_container_key=vehicle_idle_rollups`, `item_wrapper_key=vehicle_idle_rollup`, and `item_count_observed=1`.

The non-empty item schema observed keys `driving_fuel`, `driving_time`, `idle_fuel`, `idle_time`, `utilization`, and `vehicle`; nested vehicle schema keys `id`, `make`, `metric_units`, `model`, `number`, `vin`, and `year`; vehicle identity path `vehicle.id`; pagination keys `page_no`, `per_page`, and `total`; unit metadata path `vehicle_idle_rollups[].vehicle_idle_rollup.vehicle.metric_units`; and no provider utilization record ID path. This disproves relying on the old `vehicle_utilization` fixture key as production-certified for success responses. It also shows the production item does not expose true reporting-period start/end fields; the earlier generic period detector incorrectly treated `driving_time` and `idle_time` metric fields as provider period fields. Request-window period identity still requires design review, and broad utilization ingestion remains HOLD/uncertified.

The next non-persistent implementation layer parses the production-observed `vehicle_idle_rollups` envelope into an internal contract and performs read-only association from `vehicle.id` to an existing organization-owned Motive vehicle. It does not write utilization rows, create vehicles, mutate checkpoints, add a sync route, or treat request dates as authoritative reporting periods while Motive Support clarification remains pending.

The first persistence-readiness slice hardens the existing `motive_vehicle_utilization` table additively for the production-observed metrics, optional internal vehicle FK, parser version, and request-window context. It still does not ingest utilization, populate reporting periods, advance checkpoints, enable scheduling, or certify unresolved provider semantics.

The semantics-certification gate uses current official Motive documentation to classify the documented `vehicle_idle_rollups` rollup summary schema as provider-contract compatible. It certifies metric meanings (`utilization` as percent; `idle_time` and `driving_time` as seconds; fuel metrics in the provider-selected unit system) and confirms `start_date` / `end_date` as the request-window summary scope. Durable ingestion remains blocked because `end_date` boundary behavior, row cardinality/no-activity behavior, exact company rollup timezone, durable idempotency, and checkpoint advancement are still unresolved.

The bounded evidence gate adds a separate manual read-only probe for `GET /v1/vehicle_utilization`. It selects up to three stored organization-owned vehicles and makes exactly three provider calls for day A, day B, and the combined A-through-B window. It returns only sanitized cardinality, no-activity-shape, pagination, and additive metric-composition classifications. It does not persist utilization rows, advance checkpoints, request page 2, enable scheduling, or create Dashboard / Daily Brief attention.

The completed bounded production evidence selected three vehicles and observed one returned selected-vehicle rollup in each of the day A (`2026-08-12`), day B (`2026-08-13`), and combined (`2026-08-12` through `2026-08-13`) windows. No duplicate or unexpected vehicles were observed, `pagination.total` matched the one returned item, and the returned vehicle's additive metrics matched exactly across the two single days and combined window. Two requested vehicles were absent in all windows; absence remains `provider_rollup_absent` only and must not be treated as zero activity, inactive state, or a durable row.

The writer-contract gate defines a read-only fail-closed durable-writer contract at `GET /api/v1/motive/fleet/vehicle-utilization-writer-contract`. A future writer may persist only returned, validated rollups mapped to exactly one organization-owned Motive vehicle. The preferred Polaris-owned idempotency boundary is `organization_id + motive_vehicle_id + request_window_start + request_window_end`; it is now certified as a future replay identity under Polaris's fixed canonical metric policy. Durable writes must request `X-Metric-Units: true`, require returned `vehicle.metric_units == true`, and never create parallel imperial rows or silently convert units. This policy is separate from bounded production observations, which confirmed consistent unit context but intentionally did not expose the Boolean value. Request-window dates remain separate from provider reporting-period fields. Scheduled daily ingestion remains blocked until the exact company-configured Motive rollup timezone is known. The vehicle-utilization pagination contract for `GET /v1/vehicle_utilization` is now certified against official Motive documentation, and a reusable read-only paginator exists for future writer use (see `MOTIVE_UTILIZATION_PAGINATION_CONTRACT.md`); broad write ingestion remains blocked pending the durable writer transaction, database uniqueness enforcement, and checkpoint advancement implementation.

The database identity gate adds Alembic migration `202608150001`, which creates the `uq_motive_vehicle_util_org_vehicle_request_window` unique constraint on `motive_vehicle_utilization` for `organization_id + motive_vehicle_id + request_window_start + request_window_end`, enforcing at the database level the replay identity the writer-contract gate certified. The four identity columns remain nullable for backward compatibility with historical/pre-contract rows; the migration's duplicate preflight fails closed (raising a sanitized error with only a duplicate-group count) if any fully-populated group already violates the identity, and it performs no backfill, no deduplication, and no row deletion. The legacy `uq_motive_vehicle_util_org_period` reporting-period constraint is retained unchanged and is not certified as a future writer identity. This is enforcement only: `writer_enabled`, `persistence_enabled`, `checkpoint_advancement_enabled`, `scheduled_ingestion_enabled`, and `broad_sync_enabled` all remain `false`. See `MOTIVE_UTILIZATION_DATABASE_IDENTITY.md` for full detail.

The writer-transaction gate adds the internal, all-or-nothing database writer transaction primitive `app.motive.vehicle_utilization_writer.write_vehicle_utilization_transaction`. It makes zero Motive HTTP calls, receives already-parsed/validated rollups, re-validates every writer precondition (organization/request context, per-rollup organization and request-window match, no duplicate or unexpected returned vehicle, canonical `metric_units == true` unit policy, certified `motive_vehicle_idle_rollup_v1` parser/`/v1/vehicle_utilization` source provenance), resolves tenant-owned `MotiveVehicleRecord` associations without ever auto-creating a vehicle, and validates the whole batch before staging any row. It owns exactly one commit and rolls back the entire transaction on any failure, including on the database uniqueness constraint firing as a final concurrency guard. Identical replays are a no-op; conflicting replays and updates to an existing row both fail closed (`records_updated` stays `0` in this gate). It never mutates `MotiveSyncCheckpoint` or `MotiveSyncHistory`, and there is still no `POST /api/v1/motive/sync/vehicle-utilization` route or any other way to reach it publicly. See `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md` for the full contract and test matrix.

The controlled-write-validation gate adds the first caller of that writer transaction: the feature-flagged `POST /api/v1/motive/verify/vehicle-utilization-write` route (`Permission.CONNECTOR_WRITE`), disabled by default via `MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED` and requiring an explicit `{"confirm": true}` request body. It connects the certified pagination reader to the certified writer transaction for exactly one fixed, previously-observed historical day (`2026-08-13`), across up to three deterministic stored organization vehicles (the existing `_vehicles_for_utilization_contract` selection), making at most one Motive provider request (`per_page=100`, `page_no=1`, `X-Metric-Units: true` at the time this gate was written -- **superseded 2026-08-17, see the "Controlled-Route Account-Default Validation" update below**) and never fetching a second page even on malformed pagination metadata. It persists only provider-returned rollups via the unmodified writer transaction, never writes `MotiveSyncCheckpoint` or `MotiveSyncHistory`, and returns a sanitized result/error shape only. This is still not the normal production sync route: there is no `/sync/vehicle-utilization` route, no scheduler, and no automatic date progression. Production validation execution itself (`production_validation_executed`) is explicitly deferred to a separate step after this gate merges. See `MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md` for the full contract and test matrix.

The unit-context reconciliation gate incorporates the first real controlled production execution of that route (`2026-08-16`) and Motive API Support's `2026-08-12` written clarification for `GET /v1/vehicle_utilization`. The production run failed safely: Motive returned one rollup whose `vehicle.metric_units` did not equal the requested `X-Metric-Units: true`, contradicting Polaris's prior assumption that the two must be equal -- zero rows were written and the route failed closed as designed. This gate does not guess what the returned Boolean means (not imperial, not "header ignored," not a parser defect); it downgrades the writer contract's unit-policy certification to `LIVE_PROVIDER_UNIT_INDICATOR_SEMANTICS_UNRESOLVED` and redesigns the unit validator (`app.motive.vehicle_utilization_unit_policy.validate_vehicle_utilization_unit_persistence_readiness`) so that provider schema parse success (the parser still preserves a returned `True`/`False`/`None` as observed context) is distinct from durable persistence readiness: no returned value currently makes a fuel-bearing rollup ready for durable persistence. It also incorporates Motive's confirmation that end-date is inclusive, that at most one aggregate is returned per matching vehicle per requested range, that `pagination.total` is the filtered result-row count, that omitted vehicles mean only "no matching rollup returned" (not proof of inactivity, upgraded from `DEFERRED`), and that completed rollups may legitimately differ later -- which reclassifies (but does not change the runtime behavior of) the writer's conflicting-replay policy as `TEMPORARY_FAIL_CLOSED_PENDING_RECONCILIATION_POLICY` pending a future, separately-authorized historical refresh/upsert design. The certified database identity (`organization_id + motive_vehicle_id + request_window_start + request_window_end`) is unchanged; no migration was made. See `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md` for the full sanitized evidence and reconciliation.

The unit-semantics-certification gate reviewed current official Motive developer documentation (`developer-docs.gomotive.com`, retrieved 2026-08-16) specifically to try to resolve whether `X-Metric-Units` controls returned `idle_fuel`/`driving_fuel` units independent of the returned `vehicle.metric_units` field for `GET /v1/vehicle_utilization`. No reconciling statement was found on Motive's official reference page for this endpoint: its `metric_units` field description is suggestively unit-system-framed but not an explicit causation statement, and its worked example is consistent with more than one reading. This gate makes no live Motive call and changes no certification/readiness behavior -- `response_measurement_system` remains `UNRESOLVED` and durable fuel persistence remains disabled, exactly as PR #163 left them. It formalizes the request-vs-response distinction with explicit names (`requested_measurement_system`, `vehicle_configured_metric_preference`, `response_measurement_system_certification`) in `app.motive.vehicle_utilization_unit_policy`, adds an additive `unit_semantics` block to the writer contract, documents (without migrating) that the persisted `MotiveVehicleUtilizationRecord.metric_units` column stores raw provider-observed vehicle metadata rather than certified fuel-unit provenance, and prepares (but does not send) a provider clarification email draft. See `MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md` for the full sourced review, source URLs, and the draft email.

## 4C.2C+ Update: Authentication + Unit-Mismatch Certification (2026-08-17)

This gate incorporates two written replies from Motive API Support received 2026-08-17. **Authentication**: an exhaustive, repository-wide audit of every Motive request-header code path (`app/connectors/motive.py`, `app/connectors/motive_vehicle_utilization_contract.py`, `app/connectors/motive_vehicle_utilization_pagination.py`) found that all Company API Key requests already used `x-api-key` before this gate started -- no `Authorization: Bearer` was ever sent for this credential type, and the separate, dormant OAuth credential-storage subsystem (`app/connectors/motive_credentials.py`) contains no code path that builds an outgoing HTTP header at all. No auth code change was required; this gate adds a dedicated regression-test file (`tests/test_motive_authentication_certification.py`), sanitized auth metadata on `GET /api/v1/motive/verification-contract`, and `docs/engineering/MOTIVE_AUTHENTICATION_CERTIFICATION.md`. Key rotation remains explicitly deferred (`rotation_status: DEFERRED_UNTIL_MOTIVE_INTEGRATION_COMPLETION_BY_USER_DECISION`) per the user's decision to rotate only after the Motive integration project completes; the real key is never reproduced anywhere in this codebase.

**Unit semantics**: Motive Support's written reply directly resolved the question the unit-semantics-certification gate above left open (Outcome B). It confirmed `X-Metric-Units=true` requests metric (`idle_fuel`/`driving_fuel` in liters), `X-Metric-Units=false` requests imperial (gallons), the returned `vehicle.metric_units` indicator means `true`=metric/`false`=imperial, `idle_time`/`driving_time` are always seconds, and that `X-Metric-Units=true` together with a returned `vehicle.metric_units=false` is not an expected/documented combination -- integrations must fail closed and not persist fuel values on disagreement. `response_measurement_system` upgrades from `UNRESOLVED` to `PROVIDER_CONFIRMED_FAIL_CLOSED_ON_MISMATCH`. `validate_vehicle_utilization_unit_persistence_readiness` in `app.motive.vehicle_utilization_unit_policy` is redesigned accordingly: a returned value that agrees with the requested `X-Metric-Units` Boolean (the canonical writer always requests `true`, so a returned `true` agrees) is now unit-ready; a disagreeing value fails closed with the un-retired `provider_unit_policy_mismatch` code; a missing value still fails closed with `provider_unit_indicator_semantics_unresolved`; a malformed value still fails closed with `provider_unit_context_invalid_type`. The one real 2026-08-16 controlled production observation (`X-Metric-Units: true`, returned `vehicle.metric_units = false`) is reclassified from `SEMANTICS_UNRESOLVED` to `PROVIDER_CONFIRMED_UNIT_CONTEXT_MISMATCH`; its sanitized facts (one provider call, one returned rollup, zero rows inserted, zero checkpoint/history writes, safe failure) are unchanged. This upgrade enables no new route, feature flag, checkpoint behavior, or scheduled ingestion -- the controlled write route stays feature-flagged off by default, checkpoint advancement stays disabled, and scheduled ingestion stays blocked on the still-unresolved exact company rollup timezone. No live Motive call was made, no credential was rotated, and no database migration was added. See `MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md`, `MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md`, `MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`, `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md`, and `MOTIVE_AUTHENTICATION_CERTIFICATION.md` for full detail.

## 4C.2C+ Update: Historical-Rollup Reconciliation Policy (2026-08-17)

This gate acts on Motive Support's confirmation (referenced by the unit-context reconciliation gate above) that historical vehicle-utilization rollups may legitimately change slightly as provider-side processing completes, and that production integrations should periodically reread a recent rolling window. It replaces the writer transaction's temporary "any conflicting replay fails closed" posture with an explicit, field-by-field reconciliation policy, audited directly from `app/models/motive.py`, the parser (`app/connectors/motive_vehicle_utilization.py`), and the writer (`app/motive/vehicle_utilization_writer.py`) rather than assumed. Exactly five provider-derived rollup metrics -- `utilization_percent`, `idle_time`, `driving_time`, `idle_fuel`, `driving_fuel` (`MUTABLE_ON_PROVIDER_RECONCILIATION`) -- may now be updated in place on a context-compatible existing row; every identity/context/provenance field (`organization_id`, `motive_vehicle_id`, `request_window_start`, `request_window_end`, `provider_vehicle_id`, `source_endpoint`, `parser_version`, `metric_units`) remains strictly immutable and any disagreement there still fails closed with `conflicting_existing_identity`. Reconciliation is implemented as an explicit, field-by-field comparison and controlled change set -- never a blind ORM `merge()` -- and the writer's whole-batch, all-or-nothing transaction contract is unchanged: every row's insert/unchanged/reconcile/conflict decision is computed before anything is staged or mutated, so one hard conflict still rolls back an entire batch including any otherwise-safe reconciliations in it. A vehicle/window omitted from a later reread is never deleted, zeroed, or reclassified -- the writer only ever processes rows it is explicitly handed. This gate makes no live Motive call, no database migration, no checkpoint or scheduler change, and does not touch the pre-existing, unrelated `MotiveConnector(credential_store=...)` bug in `app/api/connectors.py`. See `MOTIVE_UTILIZATION_HISTORICAL_RECONCILIATION.md` for the full field-level audit and matrix, and the updated `MOTIVE_UTILIZATION_WRITER_TRANSACTION.md` for the transaction-contract detail.

## 4C.2C+ Update: Account-Default Unit-Request-Mode Audit (2026-08-17)

This gate audits whether Polaris can safely support an explicit `ACCOUNT_DEFAULT` request mode (no `X-Metric-Units` header at all) for `GET /v1/vehicle_utilization`, motivated by a separate, working local Motive Fuel/IFTA integration on the same account that never sends `X-Metric-Units` for `/v1/fuel_purchases` or `/v1/ifta/summary` and simply trusts the returned unit -- supporting evidence only, not proof of `/v1/vehicle_utilization` behavior, since no account-default `vehicle_utilization` request has ever been made. It introduces an additive `MotiveVehicleUtilizationUnitRequestMode` enum (`METRIC`/`IMPERIAL`/`ACCOUNT_DEFAULT`) in `app.motive.vehicle_utilization_unit_policy` because a plain `bool` cannot represent "no header sent at all"; every function predating this gate keeps its exact prior `bool`-based signature and behavior when the new mode parameter is omitted. `request_vehicle_utilization_page` gains an additive `unit_request_mode` parameter (omitted header for `ACCOUNT_DEFAULT`, `X-Time-Zone`/`X-User-Id` still never sent, `x-api-key` auth unchanged). `validate_vehicle_utilization_unit_persistence_readiness` gains an additive `requested_mode` parameter and a `resolved_metric_units` result field: for `ACCOUNT_DEFAULT`, no unit system was forced, so a returned `True` or `False` is always ready (never a "mismatch," since Polaris made no request-side claim to disagree with) and the returned Boolean becomes the persisted unit context; a missing or malformed returned indicator still fails closed exactly as the forced modes do. `write_vehicle_utilization_transaction` gains the same additive parameter; `_build_new_row` now persists the rollup's own validated `metric_units` instead of a hardcoded `True`, and `_existing_row_context_compatible` now compares the existing row against the incoming rollup's `metric_units` instead of the literal `True` -- both are no-behavior-change for every existing canonical caller and are what let `ACCOUNT_DEFAULT` correctly persist and replay either observed unit context without conversion, without synthesized rows, and without weakening tenant isolation. The feature-flagged controlled write route (`app/motive/vehicle_utilization_controlled_write.py`) is deliberately **not modified** in this gate -- it keeps requesting the canonical `X-Metric-Units: true` policy unchanged, as a separate scope decision pending its own future gate (**that future gate has since happened -- see the update immediately below**). No live Motive call was made, no migration was needed (`metric_units` was already a nullable Boolean column), no feature flag or Render config changed, and key rotation remains deferred per prior gates. See `MOTIVE_UTILIZATION_ACCOUNT_DEFAULT_UNIT_MODE.md` for the full design, header-emission table, writer-safety-policy table, and recommended next live-staging validation gate.

## 4C.2C+ Update: Controlled-Route Account-Default Validation (2026-08-17)

This gate makes the smallest possible change so that ONLY the existing
bounded controlled vehicle-utilization write validation route now uses
`MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`, closing the scope
gap the account-default audit gate above deliberately left open.
`app/motive/vehicle_utilization_controlled_write.py`'s one provider request
now passes `unit_request_mode=ACCOUNT_DEFAULT` instead of `metric_units=True`
to `request_vehicle_utilization_page` -- `X-Metric-Units` is genuinely
omitted from the outgoing request (proven by a mocked-transport test
asserting the header key is absent from the headers dict, not empty-string
or `None`-valued); `x-api-key`, `Accept: application/json` are unchanged,
and `X-Time-Zone`/`X-User-Id` remain absent. The same call also now passes
`unit_request_mode=ACCOUNT_DEFAULT` into
`write_vehicle_utilization_transaction`, so a returned
`vehicle.metric_units` of `True` *or* `False` both persist successfully
(exactly as returned, never converted); a missing or malformed indicator
still fails closed with the same codes as before. Every other bound is
unchanged: fixed window `2026-08-13..2026-08-13`, at most 3 selected
vehicles, at most 1 provider call, no retry, no page 2, no
checkpoint/sync-history writes, feature flag
(`MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`) still default
`false`. The response shape is unchanged. At the time this gate was written,
no live `/v1/vehicle_utilization` call, in any mode, had been made, and the
next required step was exactly one separately-authorized live-staging call
with the feature flag deliberately enabled for that single invocation
(**that call has since been made and succeeded -- see the update
immediately below**). See `MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`'s
own "Update: Controlled-Route Account-Default Validation Gate" section for
the full detail.

## 4C.2C+ Update: Account-Default Live-Staging Validation Success (2026-08-18)

A single, separately-authorized live-staging controlled validation was
executed against the deployed `ACCOUNT_DEFAULT` controlled route (PR #174)
and **succeeded**: one provider call, one returned rollup (of three selected
vehicles; the other two were `provider_rollup_absent`, not synthesized as
zero-activity rows), one durable row inserted, the writer transaction
committed, zero checkpoint writes, zero sync-history writes, scheduled
ingestion still disabled, no retry, and no secret exposed in the sanitized
response. The controlled feature flag was returned to `false` and
redeployed immediately afterward. See
`MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`'s "Update:
Account-Default Live-Staging Validation Success (2026-08-18)" section for
the full sanitized record, and for the explicit list of what this single
observation does and does not prove (it does not certify account-default
behavior for every vehicle or account, does not certify the exact provider
rollup timezone binding, and does not enable broad or scheduled ingestion).
The prior forced-metric validation failure recorded in
`MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md` remains documented as
historical evidence for the request mode that was in effect at that earlier
time -- it is not erased or reinterpreted by this success.

The next proposed engineering gate is **not** scheduled ingestion. It is a
**bounded recent-window reconciliation design** gate (design only, no
implementation): how many recent days to reread, batching/vehicle-count and
pagination bounds for a reread, reconciliation/update semantics building on
the existing historical-reconciliation policy, transaction boundaries and
failure isolation across a multi-window reread, and checkpoint policy
(still deliberately unimplemented). See
`MOTIVE_UTILIZATION_ACCOUNT_DEFAULT_UNIT_MODE.md` section 9 for the full
list. No live Motive call, Render change, feature-flag enablement,
migration, or key rotation was made by this documentation update.

## 4C.2C+ Update: Bounded Recent-Window Reconciliation Design (2026-08-18)

**This design gate is complete.** It produced
`MOTIVE_UTILIZATION_RECENT_WINDOW_RECONCILIATION_DESIGN.md`, a full design
document (not an implementation) for a future bounded, manually-invoked
reconciliation runner, grounded in a fresh audit of the current durable
identity, writer, and pagination code rather than assumption. Key decisions:
a 7-day trailing horizon ending at "yesterday" (never "today"); one
calendar-day window per request (`start == end`), required by the existing
day-level durable identity (`organization_id + motive_vehicle_id +
request_window_start + request_window_end`) rather than a multi-day
aggregate window, which would produce a different, non-reconcilable
identity on every run; vehicle batching up to the provider's 100-vehicle
page size (distinct from the controlled route's unrelated 3-vehicle safety
cap); reuse of the existing general certified paginated reader
(`read_vehicle_utilization_pages`) and the existing writer's
already-implemented five-mutable-field reconciliation policy, unmodified;
one writer transaction per vehicle-batch-per-day (not one giant multi-day
transaction) for failure isolation; no automatic provider retry; and an
explicit rule that reconciliation must never advance a forward-moving
ingestion checkpoint, since its purpose is to repeatedly revisit
already-visited days. No unexpected repo contradiction was found. **No
runtime code, test, migration, feature flag, Render config, scheduler, or
checkpoint was changed or implemented by this gate** — it is design
documentation only.

The next gate is implementation of the bounded, manually-invoked
reconciliation runner itself (still not a scheduler, still not a public
route, still requiring its own separate authorization before any live
call). **Scheduled ingestion remains a later gate still**, after that
runner's own bounded validation and after the timezone-binding question
(`MOTIVE_UTILIZATION_TIMEZONE_CERTIFICATION.md`) is resolved.

Before broader sync is implemented, Polaris must complete design and verification for:

- durable vehicle-utilization persistence mapping, identity/period semantics, units, checkpoint strategy, unknown vehicle handling, KPI interpretation, and production ingestion certification
- driver filtering based on real provider role fields observed in sanitized provider data or official documentation
- durable ingestion for driver utilization and IFTA summary
- production-safe batching and incremental date ranges per resource
- webhook authentication/signature contract
- production evidence certification criteria beyond vehicle/user-only persistence

## Confirmed Provider Inputs

Motive support confirmed the production Company API Key path, required endpoints, users pagination (`per_page` maximum 100, one-based `page_no`, `pagination.total`), and rate-limit guidance: handle `429`, honor `Retry-After` when present, use exponential backoff with jitter, avoid immediate retry loops, avoid excessive concurrency, and use pagination, caching, batching, incremental ranges, and multi-ID requests where supported.

For vehicles, Track 4C.2A uses the confirmed `/v1/vehicles` endpoint with `per_page=100` and one-based `page_no`; it uses `pagination.total` when returned, stops on empty pages, and enforces a maximum-page guard.

For company users, Track 4C.2B uses the confirmed `/v1/users` endpoint with `per_page=100` and one-based `page_no`; it uses `pagination.total` when returned, stops on empty pages, and enforces a maximum-page guard. Driver role classification is not certified.

## Later Tracks

- driver classification after role filtering is verified
- vehicle utilization, driver utilization, and IFTA summary ingestion
- broad synchronization and scheduled reconciliation
- webhooks with delivery audit trail and dead-letter handling
- executive fleet KPIs
- frontend fleet dashboard
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
- future multi-tenant OAuth architecture if Polaris becomes a multi-company or App Marketplace integration
