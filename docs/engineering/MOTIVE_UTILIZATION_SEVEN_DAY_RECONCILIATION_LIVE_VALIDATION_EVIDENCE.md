# Motive seven-day vehicle-utilization reconciliation live-validation evidence

Status: **completed — bounded live-staging success**

This document records the single separately authorized seven-day Motive vehicle-utilization reconciliation validation executed after PR #182 was merged and after a prior authentication-expired attempt had been documented in PR #183.

## Scope

The validation route was:

`POST /api/v1/motive/verify/vehicle-utilization-recent-reconciliation-seven-day`

The request body was restricted to:

```json
{"confirm": true}
```

The route remained bounded by the merged implementation contract:

- exactly seven trailing completed daily windows;
- at most 100 eligible tenant vehicles;
- one batch per day;
- one provider page per day;
- at most seven Motive provider calls total;
- no automatic retries;
- ACCOUNT_DEFAULT unit-request mode unchanged;
- provider omissions remain omissions and are never synthesized as zero rows;
- no checkpoint advancement;
- no sync-history writes;
- no scheduler or cron enablement.

## Preflight

Before the successful attempt, the Polaris browser session was refreshed and a zero-provider-call preflight confirmed:

- authenticated Motive status HTTP 200;
- Polaris access token present;
- Polaris organization context present;
- Motive connection status `connected`;
- `secrets_exposed: false`;
- OpenAPI HTTP 200;
- seven-day POST route present.

The seven-day runner flag and dedicated seven-day validation flag were then enabled for the controlled staging attempt. The old one-day validation flag and the controlled-write flag remained disabled.

## Sanitized live result

The single authorized attempt returned HTTP 200 with `status: success`.

| Field | Result |
|---|---:|
| horizon_days | 7 |
| selected_vehicle_count | 23 |
| windows_attempted | 7 |
| windows_completed | 7 |
| windows_failed | 0 |
| vehicle_batches_attempted | 7 |
| vehicle_batches_completed | 7 |
| vehicle_batches_failed | 0 |
| provider_calls_attempted | 7 |
| provider_calls_completed | 7 |
| rollups_returned | 72 |
| missing_requested_vehicle_count | 89 |
| records_inserted | 61 |
| records_updated | 11 |
| records_unchanged | 0 |
| reconciled_fields_count | 24 |
| failed_units | `[]` |
| checkpoint_advanced | false |
| sync_history_written | false |
| scheduled_ingestion_enabled | false |
| secrets_exposed | false |

Resource:

`vehicle_utilization_recent_reconciliation_seven_day_live_validation`

Validation mode:

`controlled_manual_seven_day_recent_reconciliation_live_validation`

## Interpretation

This is a clean bounded seven-day live-staging success.

All seven permitted Motive provider calls were attempted and completed. All seven daily windows and all seven vehicle batches completed with no failed units. The returned rollups were persisted through the existing writer/reconciliation path: 61 new records were inserted and 11 existing records were updated, with 24 mutable provider fields reconciled in place.

The 89 missing requested-vehicle observations are **provider omissions only**. They do not establish zero utilization, inactivity, or any other business interpretation. No rows were synthesized for absent requested vehicles.

The successful result also confirms the validation safety side effects remained disabled: no checkpoint advancement, no sync-history write, no scheduled ingestion, and no secret exposure.

## What this evidence establishes

This evidence supports the following bounded claims only:

1. The merged seven-day route is deployed and reachable under a fresh authenticated Polaris session.
2. The exactly-seven-day, one-batch-per-day staging path can complete within the seven-call provider budget for the observed 23-vehicle tenant set.
3. ACCOUNT_DEFAULT request semantics were accepted by the provider for all seven observed daily requests.
4. Returned-only persistence and historical reconciliation both operated successfully in the same bounded run.
5. Provider omissions remained omissions.
6. No checkpoint, sync-history, or scheduler side effect occurred.

## What this evidence does not establish

This successful validation does **not** by itself authorize or certify:

- scheduled or automatic ingestion;
- checkpoint advancement;
- sync-history enablement;
- a horizon longer than seven completed days;
- more than 100 selected vehicles;
- multi-batch or multi-page execution;
- automatic retry behavior;
- the meaning of an omitted provider vehicle;
- exact provider rollup timezone binding;
- broad production readiness.

Any later production/scheduled ingestion gate requires separate design, review, authorization, and evidence.

## Post-run shutdown

After the result was captured, the operator reported that both seven-day-required Render flags were returned to `false` and the service was live again.

The following remained disabled after shutdown:

- `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED=false`
- `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_SEVEN_DAY_VALIDATION_ENABLED=false`
- `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_VALIDATION_ENABLED=false`
- `MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED=false`

No repeat seven-day POST is authorized by this evidence document.
