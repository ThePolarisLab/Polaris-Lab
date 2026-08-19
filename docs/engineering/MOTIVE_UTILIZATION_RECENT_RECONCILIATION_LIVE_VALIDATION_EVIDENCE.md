# Motive Vehicle Utilization Recent-Window Reconciliation: Live-Staging Validation Evidence

## Status

**SUCCESSFUL BOUNDED LIVE-STAGING VALIDATION RECORDED — 2026-08-18.**

This document records the single manually authorized live-staging execution of the controlled reconciliation validation route introduced by PR #179. It is evidence only. It does not authorize broader reconciliation, scheduling, checkpoint advancement, retries, or a 7-day live run.

## Deployment / Code Context

- PR #179: `feat(motive): add one-day reconciliation live validation`
- merged PR head: `70de9bbeeb0d3cdb3d34862e2a0b13c75cdcac33`
- merge commit: `92ca0127a9872c9c283e91bea2e7b2633eeebfca`
- route: `POST /api/v1/motive/verify/vehicle-utilization-recent-reconciliation`
- request body: `{"confirm": true}`
- validation mode: `controlled_manual_recent_reconciliation_live_validation`
- horizon: hardcoded `1` completed calendar day
- live-validation bounds: at most 100 selected vehicles, one batch, one page, one provider call, no retry

The existing runner and route-specific feature flags were explicitly enabled only for this controlled staging execution. After the single execution, the operator returned the live-validation environment setting(s) to disabled state. Repository code continues to default both flags to disabled; Render environment state is operational configuration and is not asserted by this repository evidence document.

## Sanitized Live Result

The single authorized POST returned HTTP `200` with the following sanitized result:

| Field | Observed value |
| --- | ---: |
| `status` | `success` |
| `horizon_days` | `1` |
| `windows_attempted` | `1` |
| `windows_completed` | `1` |
| `windows_failed` | `0` |
| `selected_vehicle_count` | `23` |
| `vehicle_batches_attempted` | `1` |
| `vehicle_batches_completed` | `1` |
| `vehicle_batches_failed` | `0` |
| `provider_calls_attempted` | `1` |
| `provider_calls_completed` | `1` |
| `rollups_returned` | `10` |
| `missing_requested_vehicle_count` | `13` |
| `records_inserted` | `10` |
| `records_unchanged` | `0` |
| `records_updated` | `0` |
| `reconciled_fields_count` | `0` |
| `failed_units` | `[]` |
| `checkpoint_advanced` | `false` |
| `sync_history_written` | `false` |
| `scheduled_ingestion_enabled` | `false` |
| `secrets_exposed` | `false` |

No provider vehicle IDs, database IDs, VINs, driver PII, raw utilization metrics, raw provider payloads, API keys, bearer tokens, or organization identifiers are recorded here.

## What This Proves

This bounded live-staging execution provides empirical evidence that, for this one completed-day window and this staging tenant state:

1. The controlled route authenticated and authorized successfully.
2. The route selected 23 eligible tenant vehicles and stayed within its one-batch safety bound.
3. Exactly one Motive provider request was attempted and completed.
4. Motive returned 10 rollups for the 23 requested vehicles.
5. The writer persisted exactly the 10 returned rollups as new durable rows.
6. No existing row required replay reconciliation during this run (`records_updated=0`, `reconciled_fields_count=0`).
7. No checkpoint was advanced, no sync-history row was written, and no scheduler was enabled.
8. The sanitized contract exposed no secrets.

This is empirical bounded validation, not universal provider-contract certification and not authorization for scheduled or broad production ingestion.

## Provider Omissions

Thirteen requested vehicles were absent from the provider response. Under the certified Motive utilization contract, an omitted requested vehicle means only that no matching rollup was returned for that request. Polaris must **not** synthesize a zero row and must **not** interpret omission as proof of inactivity, zero utilization, zero fuel, or inactive vehicle state.

The observed result is therefore correctly represented as:

- 23 requested / selected vehicles
- 10 returned provider rollups
- 13 provider omissions
- 10 persisted rows
- 0 synthesized rows for omitted vehicles

## Unit / Timezone Scope

The reconciliation runner continues to use `MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`. This live result proves that the bounded request/persistence path succeeded under the observed account-default response context for this run. It does not upgrade omitted-header semantics into universal provider certification.

The request window continues to use the existing Polaris completed-calendar-day convention. This evidence does not claim that the exact Motive rollup-timezone configuration field has been provider-certified.

## Safety Outcome

All expected safety indicators remained false:

- `checkpoint_advanced=false`
- `sync_history_written=false`
- `scheduled_ingestion_enabled=false`
- `secrets_exposed=false`

No automatic retry occurred. No second validation POST is authorized by this evidence record.

## Next Gate

The next possible gate is a separately reviewed and explicitly authorized bounded multi-day manual reconciliation validation, such as the previously designed 7 trailing completed days. That gate must remain separate from this evidence record.

Until a later gate is reviewed and authorized:

- scheduled reconciliation remains disabled;
- checkpoint advancement remains disabled;
- broad vehicle-utilization sync remains disabled;
- this one-day controlled validation must not be rerun automatically;
- a 7-day live execution is not authorized by this document.
