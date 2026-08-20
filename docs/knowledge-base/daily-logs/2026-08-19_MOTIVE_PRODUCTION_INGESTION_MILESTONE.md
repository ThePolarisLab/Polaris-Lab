# Polaris Knowledge Base — Motive Production Ingestion Milestone

**Date:** 2026-08-19

## Executive Summary

Polaris completed the first controlled Motive vehicle-utilization production-ingestion run and closed the manual production-ingestion validation gate. The authorized run completed successfully across seven completed `America/Chicago` calendar-day windows, persisted/reconciled durable utilization data, advanced the ingestion checkpoint, and wrote sync history. Production and scheduler feature flags were then returned to false.

Production scheduling has now progressed through both architecture and implementation. PR #190 finalized the scheduler design, and PR #191 merged the disabled-by-default scheduler runtime. No live scheduler-path validation or persistent scheduled production activation has occurred. Motive Company API-key rotation remains mandatory before any live scheduler execution or broad/scheduled production enablement.

## Official Decisions

- The first controlled production-ingestion attempt is complete and must not be rerun under the same authorization.
- The certified production utilization contract remains explicit US Imperial: `X-Metric-Units: false`, returned `vehicle.metric_units == false`, fuel interpreted as gallons, with no unit conversion.
- Provider omissions remain omissions only; they are not synthesized as zero/inactive utilization.
- Production scheduling reuses the existing validated seven-day production orchestrator; Polaris does not create a second ingestion path.
- GitHub Actions is only the scheduler clock/wakeup mechanism. The backend owns tenant resolution, local-time gating, durable dispatch deduplication, and production execution.
- Motive Company API-key rotation is mandatory before any live scheduler execution or broad/scheduled production enablement.
- Scheduler implementation/merge does not authorize scheduler activation.

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
- Production scheduler architecture: finalized and merged as PR #190.
- Production scheduler implementation/runtime: implemented and merged as PR #191, default-off.
- Scheduler-path live validation: not yet completed.
- Persistent scheduler activation: blocked pending API-key rotation and separately authorized scheduler-path validation.

## Engineering Decisions

The production ingestion path remains bounded to the latest seven completed `America/Chicago` calendar days, a maximum of 100 organization-owned vehicles, one provider page/call per day, and at most seven provider calls per run with no automatic retries. Existing durable writer, reconciliation identity/policy, production lock, sync-history, checkpoint, timezone, unit, omission, and call-budget semantics remain authoritative.

The merged scheduler runtime uses a machine-only HMAC-authenticated endpoint, one configured active organization, an IANA `America/Chicago` local-time execution gate, and a durable same-local-day scheduler dispatch claim before provider HTTP. GitHub Actions provides two UTC wakeups (`17 11 * * *` and `17 12 * * *`) so the backend can preserve the intended local schedule across CDT/CST. A duplicate same-day trigger becomes a zero-provider-call no-op. Both production-ingestion and scheduler feature flags must be true for scheduled Motive execution. The workflow performs one HTTP attempt only and has no automatic retry or catch-up loop.

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
- Implemented and merged the disabled-by-default production scheduler runtime (PR #191).

## Remaining Gates

1. Rotate the Motive Company API key before any live scheduler execution or persistent scheduling.
2. Confirm the backend is live with the rotated key using zero-provider/status checks first.
3. Configure the Motive scheduled-organization slug and Motive-specific HMAC trigger secret in Render, and the matching HMAC secret/API URL in GitHub Actions configuration, without exposing values.
4. Keep scheduler and production-ingestion flags false and perform a machine-endpoint zero-provider preflight.
5. Separately authorize exactly one bounded scheduler-path controlled validation.
6. Return both production flags to false immediately after that validation and document the result.
7. Only after successful evidence, separately authorize persistent daily scheduler enablement.

Do not add retries, catch-up loops, Dashboard/Daily Brief changes, backfills, multi-batch behavior, unit conversion, or broader provider-call budgets as part of scheduler activation unless separately reviewed and authorized.

## Final State

**Manual bounded production ingestion:** implemented, merged, and successfully verified in one controlled production run.

**Production checkpoint/sync history:** successfully exercised in the authorized production run.

**Production scheduler architecture:** finalized and merged.

**Production scheduler implementation/runtime:** merged and default-off.

**Production scheduler live validation/activation:** not yet completed; remains blocked.

**Motive API-key rotation:** mandatory remaining prerequisite for live scheduled production execution.
