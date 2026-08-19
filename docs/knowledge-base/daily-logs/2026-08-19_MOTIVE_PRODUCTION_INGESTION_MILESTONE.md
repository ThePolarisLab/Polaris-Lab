# Polaris Knowledge Base — Motive Production Ingestion Milestone

**Date:** 2026-08-19

## Executive Summary

Polaris completed the first controlled Motive vehicle-utilization production-ingestion run and closed the manual production-ingestion validation gate. The authorized run completed successfully across seven completed `America/Chicago` calendar-day windows, persisted/reconciled durable utilization data, advanced the ingestion checkpoint, and wrote sync history. Production and scheduler feature flags were then returned to false.

The next roadmap gate is production scheduling. Its architecture is now finalized in merged PR #190, but scheduler implementation/activation remains separate. The scheduler design is default-off and requires Motive Company API-key rotation before any live scheduler execution or persistent scheduling.

## Official Decisions

- The first controlled production-ingestion attempt is complete and must not be rerun under the same authorization.
- The certified production utilization contract remains explicit US Imperial: `X-Metric-Units: false`, returned `vehicle.metric_units == false`, fuel interpreted as gallons, with no unit conversion.
- Provider omissions remain omissions only; they are not synthesized as zero/inactive utilization.
- Production scheduling must reuse the existing validated seven-day production orchestrator; Polaris will not create a second ingestion path.
- GitHub Actions is only the scheduler clock/wakeup mechanism. The backend owns tenant resolution, local-time gating, durable dispatch deduplication, and production execution.
- Motive Company API-key rotation is mandatory before any live scheduler execution or broad/scheduled production enablement.

## Principles Reaffirmed

- Evidence before enablement.
- Fail closed on unit/contract disagreement.
- One canonical ingestion path; orchestration is reused rather than duplicated.
- Durable idempotency before scheduled provider access.
- Provider omissions are not business-state assertions.
- Production activation is a separate gate from implementation or merge.
- Scheduled output/logging must not expose organization/provider identity, raw metrics/payloads, API keys, bearer tokens, HMAC secrets, or database credentials.

## Roadmap Changes

- Seven-day live reconciliation validation: complete.
- Bounded production-ingestion runtime: implemented and merged.
- First controlled production-ingestion execution: complete and verified.
- Production scheduler architecture: finalized and merged as documentation/design.
- Production scheduler implementation: next gate; not yet merged at this milestone snapshot.
- Scheduler activation: blocked pending API-key rotation and separately authorized scheduler-path validation.

## Engineering Decisions

The production ingestion path remains bounded to the latest seven completed `America/Chicago` calendar days, a maximum of 100 organization-owned vehicles, one provider page/call per day, and at most seven provider calls per run with no automatic retries. Existing durable writer, reconciliation identity/policy, production lock, sync-history, checkpoint, timezone, unit, omission, and call-budget semantics remain authoritative.

The finalized scheduler design targets approximately 06:17 `America/Chicago`. Two UTC wakeups (`17 11 * * *` and `17 12 * * *`) accommodate CDT/CST, while an IANA local-time backend gate determines the valid execution opportunity. A durable same-local-day scheduler dispatch claim must be recorded before provider HTTP; a duplicate same-day trigger becomes a no-provider-call no-op. Both production-ingestion and scheduler feature flags must be true for scheduled Motive execution.

## Research / Verification Notes

Sanitized evidence from the first controlled production-ingestion run:

- HTTP 200 / `status: success`.
- 7 `America/Chicago` windows attempted and completed; 0 failed.
- 23 selected vehicles.
- 7 provider calls attempted and completed.
- 72 rollups returned.
- 89 requested-vehicle omissions retained as omissions only.
- 11 rows inserted, 61 updated, 0 unchanged.
- 181 provider-derived fields reconciled.
- Ingestion checkpoint advanced.
- Sync history written.
- Explicit Imperial/gallons policy with `x_metric_units: false`.
- Scheduler remained disabled.
- No failed units and no secrets exposed.

After the authorized attempt, both production feature flags were returned to false and the production service was confirmed live.

## Completed Work

- Merged the bounded production utilization ingestion runtime (PR #187).
- Merged the controlled first-production-ingestion runbook (PR #188).
- Completed and documented the first successful controlled production-ingestion execution (PR #189).
- Finalized and merged the disabled-by-default production scheduler architecture (PR #190).

## Remaining Gates

- Rotate the Motive Company API key before any live scheduler execution or persistent scheduling.
- Complete and merge scheduler implementation under the finalized PR #190 architecture.
- Keep scheduler and production-ingestion flags false until a separately authorized scheduler-path validation.
- Validate machine authentication, configured organization resolution, local-time gate, durable same-day dispatch claim, duplicate-trigger no-op behavior, and sanitized failure handling before activation.
- Do not add retries, catch-up loops, Dashboard/Daily Brief changes, backfills, or broaden provider call budgets as part of scheduler activation unless separately reviewed and authorized.

## Final State

**Manual bounded production ingestion:** implemented, merged, and successfully verified in one controlled production run.

**Production checkpoint/sync history:** successfully exercised in the authorized production run.

**Production scheduler architecture:** finalized and merged.

**Production scheduler runtime/activation:** not yet certified; remains default-off.

**Motive API-key rotation:** mandatory remaining prerequisite for live scheduled production execution.
