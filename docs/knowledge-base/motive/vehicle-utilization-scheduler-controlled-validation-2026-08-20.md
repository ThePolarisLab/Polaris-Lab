# Motive vehicle-utilization scheduler controlled validation — 2026-08-20

## Status

Controlled scheduler-path validation completed successfully on 2026-08-20 and was shut back down immediately afterward.

This document records sanitized operational evidence only. It does not authorize another manual scheduler run, automatic retries, backfill, or persistent production scheduling.

## Preconditions completed

- Motive Company API key was rotated before live scheduler execution.
- The replacement key was verified through the narrow read-only Motive verification route with HTTP 200.
- The previous Motive key was retired after successful verification of the replacement key.
- The Motive scheduler HMAC secret was configured independently in Render and GitHub Actions.
- `POLARIS_PRODUCTION_API_URL` was configured for the production API.
- The scheduler organization was confirmed from the Polaris organization record:
  - organization id: `org-mor-logistics`
  - organization slug: `mor-logistics`
  - status: active
- PR #193 added a default-off controlled-validation window override while preserving the normal production window and existing safety gates.

## Zero-provider machine-path preflight

A manual `Motive Vehicle Utilization Daily` workflow preflight completed successfully while the production-ingestion and scheduler execution gates were disabled.

Evidence:

- workflow: `Motive Vehicle Utilization Daily`
- manual run: `#3`
- branch: `main`
- result: success
- purpose: verify GitHub Actions variable/secret configuration and HMAC-authenticated machine endpoint without provider execution
- production provider execution: disabled by backend gates
- retry: none

## First controlled live-validation attempt

A separately authorized first live scheduler-path attempt was made after enabling the temporary controlled-validation window plus both production execution gates.

Evidence:

- workflow: `Motive Vehicle Utilization Daily`
- manual run: `#4`
- branch: `main`
- result: failure
- workflow HTTP result: `503 Service Unavailable`
- workflow behavior: failed once and did not retry
- Render route evidence: `POST /api/v1/internal/motive/vehicle-utilization/run` returned 503

The 503 occurred in the scheduler configuration/persistence layer rather than as a certified Motive production-ingestion result. The configured scheduled-organization variable was then inspected and found to contain the literal value `false` instead of an organization slug.

No immediate retry was performed. All three live execution/validation gates were returned to `false` before diagnosis continued.

## Root cause and correction

The variable:

`POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG`

had been configured as:

`false`

The scheduler resolves an active organization by `Organization.slug`; the correct active organization record was read from Polaris and confirmed as:

`mor-logistics`

The Render value was corrected to `mor-logistics` while all live execution gates remained disabled.

## Second controlled live-validation attempt

After the configuration correction, a new, separately authorized controlled scheduler-path validation attempt was performed.

Evidence:

- workflow: `Motive Vehicle Utilization Daily`
- manual run: `#5`
- branch: `main`
- deployed scheduler code included merge commit `fb5902951a4235fd2e901aa49a14dc066dfef56e` from PR #193
- result: success
- GitHub Actions summary status: `Success`
- total workflow duration shown: approximately 12 seconds
- trigger job: success
- retry/re-run: none

The successful machine-path result confirms the corrected organization configuration, HMAC-authenticated trigger path, temporary validation-window gate, and production scheduler wrapper could complete one controlled scheduler execution through the existing production vehicle-utilization orchestration path.

This evidence does not change provider semantics or certify a new ingestion implementation. The scheduler continues to reuse the existing bounded production-ingestion orchestrator.

## Shutdown evidence

Immediately after the successful controlled validation, the operator returned all three temporary/live execution gates to `false` and confirmed Render live:

- `MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED=false`
- `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=false`
- `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false`

The following configuration remains in place for future explicitly authorized scheduler activation:

- `POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG=mor-logistics`
- Motive-specific HMAC secret configured in Render and GitHub Actions
- `POLARIS_PRODUCTION_API_URL` configured in GitHub Actions
- rotated Motive Company API key configured in Render

Secret values are intentionally not recorded here.

## Safety conclusions

- The first failed live attempt was not retried automatically or manually in the same authorization scope.
- A second attempt occurred only after root-cause correction and separate explicit authorization.
- No retry loop was introduced.
- The durable same-local-day scheduler claim mechanism remains unchanged.
- The rolling seven-day production-ingestion horizon, maximum vehicle selection, provider-call budget, `America/Chicago` calendar semantics, explicit Imperial unit contract, gallons fuel semantics, checkpoint behavior, omission semantics, and reconciliation rules remain unchanged.
- Missing provider rollups must continue to be treated as omissions, not as zero activity or inactivity.
- The temporary controlled-validation window remains default-off and was returned to `false` after validation.
- Persistent production scheduling remains a separate authorization decision.

## Closed milestone

The controlled scheduler-path validation milestone is complete. Do not rerun workflow `#5` or repeat the controlled validation solely for additional evidence.
