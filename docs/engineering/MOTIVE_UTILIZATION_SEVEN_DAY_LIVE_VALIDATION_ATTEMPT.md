# Motive Vehicle Utilization Seven-Day Live Validation Attempt

## Status

Attempted once in staging. The request was rejected at the Polaris authentication layer with HTTP 401 because the browser credential had expired. The seven-day reconciliation validation route therefore did not obtain authenticated execution evidence.

This document records the attempt only. It does **not** classify the result as a Motive provider failure, a reconciliation failure, or a successful seven-day validation.

## Implementation under test

The controlled route was merged in PR #182:

`POST /api/v1/motive/verify/vehicle-utilization-recent-reconciliation-seven-day`

The route is separately feature-gated, requires `CONNECTOR_WRITE`, accepts only `{"confirm": true}`, hardcodes exactly seven completed daily windows, caps eligible vehicles at 100, caps provider calls at seven, and leaves checkpoint/history/scheduling disabled.

## Zero-provider-call preflight evidence

Immediately before the attempted POST, two preflight checks succeeded:

1. `/openapi.json` returned HTTP 200 and confirmed the seven-day route was deployed as `POST`.
2. Authenticated `GET /api/v1/motive/status` returned HTTP 200 with the Motive connection reported as connected and `secrets_exposed: false`.

These preflights did not execute the seven-day reconciliation route.

## Single attempted POST

The operator invoked the seven-day validation route exactly once from the authenticated Polaris browser session using the same browser-storage credential pattern used during preflight.

Observed result:

- HTTP status: `401 Unauthorized`
- safe response detail: `credential expired`

No retry was performed.

## Interpretation

The request failed before the controlled seven-day route could be accepted as an authenticated execution. Therefore:

- no successful seven-day route execution is established;
- no Motive provider-call count is certified by this attempt;
- no persistence/reconciliation result is established by this attempt;
- no inference should be made about Motive API availability, returned rollups, missing vehicles, unit behavior, or writer behavior from this 401 response;
- the result should be classified as **Polaris browser credential expiry before route execution**.

The prior successful one-day validation remains the most recent authenticated live reconciliation evidence.

## Post-attempt shutdown

After the failed authorization attempt, the operator reported that both seven-day-required staging flags were returned to `false` and were live after redeploy:

- `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED=false`
- `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_SEVEN_DAY_VALIDATION_ENABLED=false`

The old one-day validation flag and controlled-write flag were also left disabled.

Because Render configuration is external to the repository, this document records the operator-reported shutdown state rather than independently proving the environment values.

## Next gate

Do not silently rerun the same live validation attempt.

A fresh live attempt requires a separate explicit authorization after:

1. the expired Polaris browser credential is refreshed by normal login/session refresh;
2. zero-provider-call authentication preflight is repeated with the fresh credential;
3. the two seven-day-required flags are explicitly enabled in staging only;
4. the route is invoked exactly once under the new authorization;
5. both flags are immediately returned to false afterward.

No scheduler, checkpoint advancement, sync-history writes, retries, or broader production ingestion are authorized by this record.
