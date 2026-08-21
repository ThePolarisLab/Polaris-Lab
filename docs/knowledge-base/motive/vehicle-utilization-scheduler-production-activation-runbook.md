# Motive vehicle-utilization scheduler — persistent production activation runbook

## Purpose

This runbook defines the controlled activation and first automatic production observation for the Motive vehicle-utilization scheduler.

It is operational guidance only. Merging this document does not itself authorize or enable persistent production scheduling. Enabling the production scheduler requires separate explicit operator authorization after this runbook is reviewed and merged.

## Proven prerequisites

The following prerequisites were completed before this runbook:

- bounded production vehicle-utilization ingestion is already implemented and previously completed a successful controlled production run;
- the scheduler design and implementation are merged;
- the Motive Company API key was rotated and the replacement key was verified before the old key was retired;
- the scheduler HMAC secret is configured independently in Render and GitHub Actions;
- `POLARIS_PRODUCTION_API_URL` is configured in GitHub Actions;
- the active scheduled organization is confirmed as `mor-logistics`;
- zero-provider HMAC/machine-path preflight succeeded;
- controlled scheduler-path validation succeeded after correcting the scheduled organization slug;
- the controlled-validation override was returned to disabled after validation.

See `vehicle-utilization-scheduler-controlled-validation-2026-08-20.md` for the controlled-validation evidence.

## Production configuration target

Persistent scheduler activation uses these Render values:

- `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=true`
- `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=true`
- `MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED=false`
- `POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG=mor-logistics`

The Motive API key and HMAC secret remain configured but their values must never be copied into documentation, screenshots, workflow logs, or chat.

## Normal schedule

The GitHub Actions workflow is `Motive Vehicle Utilization Daily`.

The workflow has two UTC wakeups:

- `17 11 * * *`
- `17 12 * * *`

The backend accepts execution only inside the normal `06:10–06:24 America/Chicago` window. One UTC wakeup is therefore the valid daily execution wakeup and the other is a deliberate zero-provider no-op across daylight-saving changes.

Do not change the cron schedule for activation.

## Activation procedure

Perform activation only after separate explicit authorization.

1. Confirm Render is healthy and live before changing any execution gate.
2. Confirm the scheduled organization slug remains `mor-logistics`.
3. Confirm the controlled-validation override remains `false`.
4. Set `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=true`.
5. Set `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=true`.
6. Wait for Render to redeploy and become live.
7. Do not manually trigger the GitHub workflow for the first persistent-production observation.
8. Leave the workflow to execute from its normal scheduled wakeup.

## First automatic production observation

The first scheduled production execution is an observation gate, not a request for repeated testing.

Expected behavior:

- exactly one of the two daily UTC wakeups reaches the valid Chicago execution window;
- the other wakeup returns as an outside-window no-op and performs no provider work;
- the valid wakeup authenticates through the Motive-specific HMAC machine endpoint;
- the backend resolves the configured active organization internally; no organization is supplied by the GitHub caller;
- the durable same-local-day scheduler dispatch claim is acquired before provider HTTP;
- the existing production ingestion orchestrator is reused unchanged;
- the rolling horizon remains the latest seven completed `America/Chicago` calendar days;
- provider call budget remains bounded to one call per day, maximum seven calls for the run;
- no GitHub, backend, or provider retry loop is introduced;
- missing provider rollups remain omissions/unknown and are not synthesized as zero activity;
- explicit Imperial unit validation remains fail-closed;
- checkpoint advancement still requires complete successful bounded ingestion plus history persistence.

## Evidence to capture

For the first automatic production execution, capture sanitized evidence only:

- GitHub workflow run number and trigger type (`schedule`);
- branch/ref (`main`);
- workflow conclusion;
- machine endpoint HTTP status;
- whether the run executed, was outside-window, or was already claimed;
- bounded production aggregate counters if available from existing sanitized backend evidence;
- confirmation that no retry or rerun occurred;
- confirmation that no secret value, API key, bearer token, raw HMAC signature, or sensitive provider payload was exposed.

Do not rerun the workflow solely to obtain prettier or more complete evidence.

## Success criteria

The first automatic production observation is successful when all of the following are true:

- scheduled GitHub wakeup completes successfully;
- valid local-window execution reaches the scheduler machine endpoint successfully;
- exactly one same-local-day scheduler dispatch is consumed for provider execution;
- the production orchestrator completes without an unsanitized error;
- no automatic or manual retry occurs;
- checkpoint/history semantics remain valid;
- the second UTC wakeup does not create duplicate provider execution;
- the scheduler remains enabled only if the observed result is consistent with these safety constraints.

## Failure or ambiguity procedure

If the first automatic run fails, times out, returns an unexpected non-2xx result, or has ambiguous completion evidence:

1. Do not manually rerun the workflow.
2. Do not use `Re-run jobs`.
3. Do not start a second manual scheduler request.
4. Set `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false` in Render.
5. If provider execution safety is uncertain, also set `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=false`.
6. Keep `MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED=false`.
7. Wait until Render is live with the shutdown configuration.
8. Diagnose from existing workflow/backend evidence before considering any separately authorized future action.

A failed or ambiguous scheduled POST counts as an attempted execution. Do not repeat it merely because the outcome is unclear.

The durable scheduler dispatch claim intentionally remains consumed after an in-window claimed attempt, including partial failure or crash. Recovery is through the next day's normal rolling seven-day reread, not same-day retries.

## Emergency disable

To stop future scheduled provider execution while keeping configuration and credentials intact:

- set `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false`.

For a full ingestion shutdown:

- set `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_SCHEDULER_ENABLED=false`;
- set `MOTIVE_VEHICLE_UTILIZATION_PRODUCTION_INGESTION_ENABLED=false`.

The controlled-validation override must remain `false` in normal production.

## Post-observation documentation

After the first automatic production execution is observed, create a separate evidence-only documentation change recording the sanitized result and exact GitHub run identity.

Do not combine first-run evidence with unrelated scheduler behavior changes.

After persistent scheduling is proven stable, the temporary controlled-validation-window override may be removed in a separate cleanup PR. That cleanup is not required for activation and must not be bundled into the first scheduled production observation.

## Non-goals

This activation does not change:

- Motive endpoint or authentication semantics;
- provider pagination or call budget;
- seven-day rolling horizon;
- `America/Chicago` date semantics;
- explicit Imperial units or gallons fuel semantics;
- omission handling;
- reconciliation rules;
- checkpoint/history atomicity;
- tenant resolution model;
- HMAC machine authentication;
- same-local-day scheduler claim behavior;
- retry policy.

## Authorization boundary

Merging this runbook means only that the activation procedure is documented.

Do not enable persistent production scheduling until the operator separately authorizes activation after this PR is green and merged.
