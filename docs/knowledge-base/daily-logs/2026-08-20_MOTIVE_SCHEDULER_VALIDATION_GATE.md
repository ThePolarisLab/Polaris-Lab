# Polaris Knowledge Base — Motive Scheduler Validation Gate

**Date:** 2026-08-20

## Executive Summary

Polaris advanced the Motive vehicle-utilization production scheduler to the next controlled-validation gate. PR #193 merged a temporary, default-off scheduler time-window override that permits one separately authorized signed scheduler-path validation outside the normal morning production window without changing the certified production schedule itself.

This is an enablement mechanism for controlled evidence collection, not production scheduler activation. No Render values, GitHub cron schedule, provider contract, ingestion semantics, checkpoint behavior, HMAC model, organization selection, retry policy, or durable same-local-day dispatch claim were changed.

## Official Decisions

- The normal certified scheduler window remains 06:10–06:24 `America/Chicago` when the validation override is off.
- Controlled validation may temporarily use 11:00–23:59 `America/Chicago` only when `MOTIVE_VEHICLE_UTILIZATION_SCHEDULER_CONTROLLED_VALIDATION_WINDOW_ENABLED=true`.
- The override is default-off and must be returned to false after the authorized validation.
- Both existing production-ingestion and scheduler feature flags remain mandatory before provider execution.
- Persistent scheduler activation is not authorized by this merge.

## Principles Reaffirmed

- Evidence before enablement.
- Production activation is separate from implementation and merge.
- Temporary validation controls must be explicit, bounded, default-off, and reversible.
- Reuse the canonical scheduler/ingestion path rather than creating a second validation path.
- Preserve durable same-local-day deduplication and no-retry behavior during validation.

## Roadmap Changes

- Manual bounded production ingestion: complete and previously production-verified.
- Production scheduler architecture/runtime: complete and merged, default-off.
- Controlled scheduler-path validation mechanism: implemented and merged in PR #193.
- Controlled scheduler-path production evidence: still pending.
- Persistent daily scheduler activation: still pending successful validation and remaining production prerequisites.

## Engineering Decisions

PR #193 adds only a temporary scheduler time-gate override. With the override disabled, the existing DST-aware 06:10–06:24 `America/Chicago` gate is unchanged. With it enabled, the scheduler accepts execution between 11:00 and 23:59 local time for the controlled validation.

The durable dispatch claim, one canonical production orchestrator, HMAC-authenticated machine endpoint, configured-organization requirement, provider-call budget, units/timezone semantics, checkpoint/sync-history behavior, and prohibition on automatic retries remain unchanged.

## Research / Verification Notes

Focused tests were added to prove that the temporary validation window begins at 11:00 and ends after 23:59 `America/Chicago`, and that the normal DST-aware production window remains unchanged when the override is false.

PR #193 merged on 2026-08-20. No later merged engineering PR was found at the time of this Knowledge Base update.

## Completed Work

- Merged PR #193: `feat(motive): add controlled scheduler validation window`.
- Added a bounded, default-off validation window without changing the certified production schedule.
- Preserved the existing production-ingestion and scheduler safety gates.
- Preserved durable same-local-day dispatch deduplication and no-retry behavior.

## Remaining Gates

1. Complete all production prerequisites carried forward from the prior milestone, including Motive Company API-key rotation where not already completed and safe scheduler configuration.
2. Keep the controlled-validation override and production flags off except during a separately authorized bounded validation.
3. Perform exactly one controlled scheduler-path validation and capture sanitized evidence for machine authentication, organization resolution, time gating, dispatch claim behavior, provider execution, ingestion outcome, checkpoint/sync-history behavior, and duplicate-trigger no-op behavior.
4. Return the validation override and production flags to false immediately after the controlled attempt.
5. Review the evidence and separately authorize persistent daily scheduler activation only if the scheduler path is verified end to end.

## Final State

**Controlled scheduler validation mechanism:** merged and default-off.

**Normal production schedule:** unchanged.

**Scheduler-path live validation:** pending.

**Persistent daily scheduler activation:** not authorized.