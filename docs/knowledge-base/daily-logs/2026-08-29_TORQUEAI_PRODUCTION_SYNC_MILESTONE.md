# Polaris Knowledge Base — TorqueAI Production Sync Milestone

**Date:** 2026-08-29

## Executive Summary

TorqueAI dispatch integration crossed the automatic-production gate. The durable ingestion/read/dashboard path was completed, the scheduled machine path was implemented and production-certified, and hourly GitHub Actions scheduling was enabled after successful Stage 1 evidence.

The controlled production certification for the 21:00 UTC slot returned HTTP 200 with `status: executed`: one provider page was fetched, 31 provider rows were validated, 23 durable dispatch records were inserted, 1 updated, and 7 were unchanged. The backend durable hourly claim remains the at-most-once provider-execution control; duplicate requests for the same UTC hour return `already_claimed` with zero additional provider calls.

## Official Decisions

- GitHub Actions is the scheduling authority for TorqueAI dispatch sync; Polaris does not add an in-process FastAPI timer/worker.
- The approved persistent cadence is hourly at minute 17 (`17 * * * *`).
- The backend durable hourly claim, not GitHub timing alone, is the duplicate-trigger safety boundary.
- Scheduled execution reuses the certified bounded ingestion path rather than creating a second provider-ingestion implementation.
- Provider retries remain disabled.
- The Dispatch dashboard remains a durable-database read surface and never calls TorqueAI from the browser.

## Principles Reaffirmed

- Production activation follows controlled certification, not code merge alone.
- Tenant identity and query windows are server-owned for machine execution.
- Durable claims are acquired before provider page 1 so duplicate/cold-start triggers fail safe.
- Provider omission is not deletion.
- Provider rows are validated before durable dispatch mutation.
- Persist only minimized approved operational fields; do not persist raw provider payloads.
- Expose sanitized aggregate evidence only; never expose provider secrets or raw dispatch payloads.

## Roadmap Changes

The TorqueAI dispatch track has advanced through:

1. bounded external connector and controlled live certification;
2. durable tenant-scoped dispatch ingestion;
3. authenticated read-only durable Dispatch API;
4. first-class Dispatch dashboard;
5. automatic-sync architecture and machine trigger;
6. successful production Stage 1 scheduler certification; and
7. persistent hourly Stage 2 scheduling enabled.

The prior `workflow_dispatch`-only scheduling blocker is no longer current.

## Engineering Decisions

The scheduled endpoint uses Polaris HMAC job authentication with a dedicated TorqueAI trigger secret. Tenant resolution and the rolling seven-provider-date UTC window are derived server-side. A unique durable `(organization_id, trigger_mode, trigger_slot)` claim is committed before the first provider request, and failed or duplicate slots remain consumed to prevent replay-driven duplicate provider calls.

The provider path retains fixed 100-row pages, bounded pagination, no backend retries, validation-before-mutation, and idempotent insert/update/unchanged persistence. The hourly GitHub workflow retains `workflow_dispatch` for controlled operator use and uses a concurrency group with `cancel-in-progress: false`.

## Research / Verification Notes

Before certification, repeated attempts exposed sanitized `authorization_required` failures. A safe configuration diagnostic was added that inspects configuration shape only, makes zero TorqueAI calls, performs zero scheduler/database work, and never returns token values, fingerprints, base URL values, tenant identifiers, or provider payloads.

After configuration correction, Stage 1 production certification succeeded for the 2026-08-29 21:00 UTC slot:

- HTTP 200;
- `status: executed`;
- 1 page fetched;
- 31 provider rows validated;
- 23 inserted;
- 1 updated;
- 7 unchanged;
- no raw dispatch payload or secret exposure.

That evidence satisfied the explicit gate for enabling Stage 2 hourly scheduling.

The first natural post-merge Stage 2 schedule also succeeded on exact merge SHA `8d46212ba8b13a7f97cb7dc1b8974c23b9d625db`:

- workflow run #8 / run ID `33283222863`;
- created 2026-08-30 00:24 UTC;
- HTTP 200;
- `status: executed`;
- trigger slot `2026-08-30T00:00:00Z`;
- 31 rows validated;
- 0 inserted;
- 1 updated;
- 30 unchanged;
- tenant scope validated;
- no raw dispatch payload or secrets exposed.

This proves the first unattended Stage 2 execution. Continued hourly schedule reliability remains an observation gate rather than an activation blocker.

## Completed Work

- Merged durable TorqueAI dispatch ingestion, read API, and Dispatch dashboard gates.
- Merged automatic-sync architecture and controlled scheduled-sync trigger.
- Added safe sanitized certification/configuration diagnostics during production troubleshooting.
- Completed successful controlled production scheduler certification.
- Merged PR #252 enabling hourly `17 * * * *` scheduling while retaining manual `workflow_dispatch`.
- Confirmed the first natural post-merge hourly Stage 2 execution succeeded on the exact merged `main` SHA.

## Remaining Gates

- Observe continued hourly schedule reliability over a short period and confirm expected `executed` / `already_claimed` behavior without duplicate provider calls; the first natural Stage 2 execution is already proven.
- Monitor sanitized sync evidence for provider/authentication failures and pagination bounds.
- Keep broader operational interpretation, alerts, Daily Brief semantics, billing/financial enrichment, raw stop/address/location persistence, and provider retry policy as separately reviewed future gates.

## End State

**TorqueAI durable dispatch ingestion:** production-certified.

**TorqueAI durable Dispatch API/dashboard:** merged.

**TorqueAI machine scheduler path:** production-certified.

**Persistent hourly dispatch synchronization:** enabled in `main` via PR #252.
