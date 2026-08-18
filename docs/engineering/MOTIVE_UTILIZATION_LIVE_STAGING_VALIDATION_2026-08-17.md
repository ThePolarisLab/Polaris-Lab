# Motive Vehicle Utilization Live Staging Validation — 2026-08-17

This document records the sanitized outcome of the bounded live-staging
validation of the controlled Motive vehicle-utilization write route and the
follow-up diagnosis/fix. It is an additive evidence record for
`MOTIVE_UTILIZATION_CONTROLLED_WRITE_VALIDATION.md`; it does not authorize a
new provider call and does not change runtime behavior.

## Environment and Build

- Render service: `polaris-executive-api`
- Render configuration observed for this service: `POLARIS_ENV=staging`
- Database binding in `render.yaml`: `polaris-staging-db`
- Live service URL observed in Render: `https://polaris-executive-api.onrender.com`
- Application commit deployed for the controlled attempt:
  `2d893beccc0feb677962bfd7fc7380e04fb30b8a`
- That commit included merged PR #169 and PR #170.
- PR #171 later fixed the controlled-route HTTP status mapping and merged as:
  `607b7329289142aa9a6623bdb4e35935c6837286`

This evidence therefore describes a **live staging** validation, not a
production-environment validation.

## Provisional Timezone Posture

For this bounded validation only, the provisional operational timezone source
was the company-level Fleet Dashboard setting:

`Admin > Compliance > General > Home terminal time zone`

Observed value:

`(GMT-05:00) Central Time - Chicago`

The separate `Account Settings > Preferences > Time Zone` setting was also
observed as `Central Time - Chicago`.

Motive documentation confirms that `GET /v1/vehicle_utilization` is a rollup
endpoint using the company's configured rollup timezone and not
`X-Time-Zone`, but the exact Fleet Dashboard field supplying that rollup
timezone remains pending Motive Support confirmation. This validation did not
send `X-Time-Zone` and does not upgrade the timezone certification from the
previous Outcome B.

## Authentication Smoke Test

Before the controlled attempt, an authenticated harmless application-only
request was executed:

`GET /api/v1/motive/status`

It returned successfully and proved that the fresh Polaris bearer token and
`X-Polaris-Organization` context were valid. This route reads local/persisted
status only and does not make a Motive provider HTTP request.

No credentials, bearer token, API key, VIN, provider vehicle ID, or raw
provider payload are recorded here.

## Request Sequence

Three attempts were visible in Render access logs:

1. `20:24:04 EDT` — controlled POST returned `422 Unprocessable Entity` due
   to malformed local JSON quoting. FastAPI rejected the request body before
   controlled handler execution.
2. `20:27:24 EDT` — controlled POST returned `401 Unauthorized` due to invalid
   or stale Polaris application authentication. The controlled handler did not
   execute.
3. `20:47:05 EDT` — one authenticated controlled POST returned
   `500 Internal Server Error`.

Only the third request reached the controlled route far enough to exercise the
provider/write pipeline.

## Live Provider Call Classification

Follow-up local code-path analysis and deterministic mocked reproduction
established:

**PROVIDER CALL DEFINITELY SENT.**

The raw-looking HTTP 500 was not an unhandled Python crash. The route caught
`MotiveVehicleUtilizationControlledWriteError` and deliberately mapped
writer-stage safe semantic failures, including
`provider_unit_policy_mismatch` and
`provider_unit_indicator_semantics_unresolved`, to HTTP 500.

Reaching that writer-stage status mapping structurally requires the bounded
provider read to have completed first. Therefore the 20:47:05 EDT attempt
consumed the authorized one-provider-call budget.

No retry is authorized by this record.

## Safe Persistence Outcome

The live attempt is classified as a safe provider-semantic failure, not a
successful durable-persistence validation.

The writer's decide-then-apply behavior rejects unit-context conflicts before
staging durable utilization mutations. The follow-up regression tests assert
that the relevant mismatch/unresolved paths leave:

- utilization durable row count unchanged for the attempted identity;
- no partial batch persistence;
- no checkpoint write;
- no sync-history write.

The earlier certified behavior remains unchanged: omitted requested vehicles
must never be synthesized as zero-activity rows, deleted, or reclassified.

## HTTP Status-Mapping Defect

Root cause of the visible 500:

`app/api/motive.py::_controlled_write_http_status`

Before PR #171, writer-stage fail-closed semantic codes were specially mapped
to HTTP 500 even though they represented controlled provider-semantic refusal,
not an application crash.

PR #171 removed that special 500 mapping so these controlled semantic failures
now use the existing sanitized `502 Bad Gateway` classification used for
provider/read semantic failures.

PR #171 exact head:

`b7cd4cf0a44c3bbb0b483b6a1f39c7e1874a5bd7`

PR #171 exact merge commit:

`607b7329289142aa9a6623bdb4e35935c6837286`

## Regression Coverage Added by PR #171

The fix added focused route-level coverage for:

- `provider_unit_policy_mismatch` / returned `metric_units=False` -> HTTP 502;
- `provider_unit_indicator_semantics_unresolved` / missing unit indicator ->
  HTTP 502;
- a guard ensuring controlled-write error codes do not map to HTTP 500.

Reported validation on the fix branch:

- controlled-write tests: 63 passed;
- Motive tests: 436 passed;
- full backend suite: 689 passed, 0 failed;
- `git diff --check`: clean;
- `compileall`: clean;
- secret-hygiene scan: clean.

Exact-head GitHub CI for PR #171 also completed successfully across Backend
Tests, Security Gate, Database Gate, QuickBooks Production Adapter, Polaris
TypeScript CI, and PGE-008 Runtime Verification before merge.

## Feature Flag and Runtime Safety

The controlled route remains protected by:

`MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED`

Required standing state outside an explicitly authorized controlled gate:

`false`

This evidence record does not verify the current Render value independently.
The operator must keep/return the flag to `false`; this document does not
authorize enabling it.

No scheduler, checkpoint advancement, sync-history write, broad utilization
sync, key rotation, or Dashboard/Daily Brief change is authorized or performed
by this documentation update.

## Security Note

A real Motive API key was previously exposed in a provider support email. The
key is intentionally not reproduced, searched for, logged, or stored in this
record. Rotation remains required before broad production enablement, but is
still deferred until the Motive integration is otherwise complete.

## Current Gate Status

- Controlled route implementation: certified and merged.
- Durable database identity: certified and merged.
- Transaction/reconciliation behavior: certified and merged.
- Company API-key auth path: certified and merged.
- Unit request/response policy: provider-confirmed and fail-closed on mismatch.
- Timezone behavior: known; exact Fleet Dashboard binding still pending Support
  confirmation; company Compliance/Home-terminal timezone remains provisional.
- Live staging provider call: completed once; budget consumed.
- Durable persistence from this live staging attempt: **not validated** because
  the provider-semantic unit gate refused persistence safely.
- Checkpoint advancement: not authorized.
- Scheduled/broad utilization ingestion: not authorized.

## Next Gate

Do **not** automatically repeat the live call.

Any additional live controlled validation must be separately authorized after
reviewing this evidence and the merged PR #171 fix. Until then:

- keep the controlled-write flag off;
- do not advance utilization checkpoints;
- do not enable scheduled/broad utilization ingestion;
- do not rotate the Motive key as part of this record;
- do not make another Motive utilization provider call.
