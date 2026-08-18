# Polaris Knowledge Base — Motive Reconciliation Milestone

**Date:** 2026-08-18

## Executive Summary

Polaris crossed a meaningful Motive vehicle-utilization milestone: a bounded, manually invoked recent-window reconciliation path is now implemented on `main`, following successful controlled account-default persistence evidence. The work deliberately stops short of scheduled ingestion.

## Official Decisions

- `ACCOUNT_DEFAULT` is the approved unit-request mode for the bounded reconciliation path: omit `X-Metric-Units`, persist the provider-observed Boolean unit context, perform no conversion, and fail closed on missing or malformed unit indicators.
- Recent-window reconciliation uses a 7-day trailing horizon ending at yesterday, with a 14-day hard maximum.
- Reconciliation operates one completed calendar day at a time, oldest to newest, preserving durable request-window identity.
- Provider requests batch at most 100 organization-owned vehicles.
- There are no automatic provider retries, ingestion checkpoint advances, sync-history writes, or scheduler activation in this gate.

## Principles Reaffirmed

- Evidence before automation.
- Bounded production experiments before broad runtime enablement.
- Fail closed on provider semantic ambiguity.
- Preserve tenant isolation and durable identity.
- Reconcile only provider-derived mutable rollup fields; do not reinterpret omissions as inactivity.
- Keep manual reconciliation, checkpointing, and scheduling as separate authorization gates.

## Roadmap Changes

- Account-default utilization unit mode: complete.
- Controlled account-default production persistence proof: complete.
- Bounded recent-window reconciliation design: complete.
- Bounded manual reconciliation runner: implemented and merged.
- Scheduled utilization ingestion: still deferred.
- Checkpoint advancement: still deferred.

## Engineering Decisions

The manual runner is an internal Python callable guarded by the separate, default-off `MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED` flag. It selects tenant-scoped vehicles deterministically, generates daily windows, batches up to 100 vehicles, reuses the strict multi-page utilization reader, and invokes the existing writer once per day/batch transaction unit.

A runner-level provider-call budget is computed before execution. The authorized maximum is 200 calls, with the default 7-day horizon expected to remain far below that bound for normal fleet sizes. Known provider, pagination, unit, and writer failures are isolated per unit; unexpected exceptions are not swallowed.

The existing reconciliation policy remains authoritative: only utilization percentage, idle/driving time, and idle/driving fuel may reconcile in place. Identity, request context, source endpoint, parser version, and unit provenance remain immutable. Omitted provider rows are not deleted, zeroed, or interpreted as inactivity.

## Research / Verification Notes

A bounded live-staging `ACCOUNT_DEFAULT` validation succeeded before the reconciliation runner was implemented. For the fixed `2026-08-13..2026-08-13` window, three vehicles were selected, one provider call completed, one rollup was returned, two requested vehicles were omitted, and one utilization row was inserted and committed. No checkpoint or sync-history mutation occurred, and the controlled feature flag was returned to false afterward.

The earlier forced `X-Metric-Units: true` safe failure remains valid historical evidence; it is not the current production proof. The successful account-default run is the current bounded persistence evidence.

## Completed Work

- Merged PR #173: account-default utilization unit mode.
- Merged PR #174: controlled validation switched to account-default mode.
- Completed the bounded live-staging account-default validation successfully.
- Merged PR #175: recorded sanitized successful production evidence.
- Merged PR #176: bounded recent-window reconciliation design and roadmap update.
- Merged PR #177: bounded manual recent-window reconciliation runner.

## Remaining Gates

- Execute and inspect a separately authorized bounded manual reconciliation run using the merged runner before considering any scheduler.
- Keep the reconciliation feature flag disabled except during an explicitly authorized run.
- Resolve/certify the exact scheduled-rollup timezone source as needed for future automated windows; current evidence remains provisional where provider configuration mapping is not explicit.
- Design and authorize checkpoint advancement separately.
- Design and authorize scheduling separately; no cron/worker/Render scheduling is enabled by this milestone.
- Rotate the Motive API key before broad production enablement, as previously committed.
- Preserve controlled monitoring and sanitized evidence for the first broader runtime gates.

## Final Status

**Bounded account-default persistence:** verified in controlled staging.

**Recent-window reconciliation design:** complete.

**Manual bounded reconciliation runner:** merged and default-off.

**Checkpointing / scheduled broad utilization ingestion:** disabled and not yet authorized.
