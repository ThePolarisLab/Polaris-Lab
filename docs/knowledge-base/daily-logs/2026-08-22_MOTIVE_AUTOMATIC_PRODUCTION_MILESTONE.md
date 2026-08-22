# Motive Vehicle Utilization — Automatic Production Milestone

**Date:** 2026-08-22

## Executive Summary

Track 4C vehicle-utilization ingestion has crossed the automatic-production gate. The first scheduled production cycle under the delayed-wakeup-tolerant scheduler completed successfully, and a later same-local-day wakeup was safely deduplicated before provider work. The historical roadmap state was then reconciled so earlier HOLD/disabled/uncertified gates are no longer mistaken for current production status.

The utilization ingestion/scheduler milestone is closed. The next Track 4C slice is operational observability, followed by separately designed consumer integration.

## Official Decisions

- Vehicle-utilization ingestion and its automatic production scheduler are now certified for normal production operation under the current bounded configuration.
- Keep the production ingestion and scheduler gates enabled during normal operation; keep the controlled validation window disabled unless a separately authorized validation is required.
- GitHub Actions remains wake-up-only. Backend `America/Chicago` time gating and the durable organization/local-date dispatch claim remain the execution controls.
- A scheduler dispatch claim is evidence that a dispatch was consumed, not proof that ingestion succeeded; production success must be derived from production history/checkpoint evidence.
- New Motive work must be separately scoped rather than broadening the certified scheduler implicitly.

## Principles Reaffirmed

- Durable state, not cron precision, enforces at-most-once same-local-day provider execution.
- Provider omissions remain unknown/absent rollups and must never be synthesized into zero activity.
- Unit-policy disagreement fails closed; no silent conversion or persistence is allowed.
- Tenant isolation, HMAC machine authentication, production feature gates, claim ordering, and checkpoint/history atomicity remain non-negotiable boundaries.
- Operational observability should be read-only, tenant-scoped, sanitized, zero-provider-call, and zero-write.

## Roadmap Changes

The current Track 4C status is now explicitly reconciled:

- 4C.1E Company API Key production foundation: complete / active.
- 4C.2A vehicle ingestion: complete.
- 4C.2B company-user ingestion: complete for the certified `/v1/users` scope.
- 4C.2C+ durable vehicle-utilization ingestion: complete; automatic production scheduler validated.

Earlier HOLD, disabled, and uncertified statements remain historical audit evidence but are superseded where later certification exists.

Recommended next sequence:

1. operational observability;
2. consumer integration with explicit KPI/business semantics;
3. roadmap cleanup that preserves the audit trail;
4. only then evaluate a new Motive provider domain.

## Engineering Decisions

The certified production scheduler accepts eligible wakeups during `06:00–09:59 America/Chicago`. The first eligible same-local-day wakeup acquires a durable dispatch claim before provider HTTP; later same-day wakeups return `already_claimed` without duplicate provider execution. No scheduler retry or catch-up loop is introduced.

The next observability slice is designed as authenticated `GET /api/v1/motive/vehicle-utilization/operations-status`, requiring `CONNECTOR_READ` and deriving organization exclusively from the authenticated principal. It will use existing tenant-owned `MotiveSyncHistory` and `MotiveSyncCheckpoint` state, expose only allow-listed sanitized fields, perform zero Motive HTTP calls and zero writes, and add no new database table.

## Research / Verification Notes

First certified automatic production observation on 2026-08-22:

- scheduled run #8: HTTP 200, `status=executed`, `dispatch_claimed=true`;
- scheduled run #9: HTTP 200, `status=already_claimed`, `dispatch_claimed=false`.

No manual rerun was used. The evidence validates the intended persistent-production path rather than a controlled/manual substitute. It also closes the earlier delayed-wakeup incident: the widened bounded local-time window tolerates GitHub schedule delay while the durable claim preserves same-day deduplication.

## Completed Work

- Merged PR #199 documenting and certifying the first successful automatic production scheduler observation.
- Merged PR #200 reconciling Track 4C current production status and explicitly superseding stale historical blockers.
- Merged PR #201 defining the next operational-observability design gate with strict tenant, security, and zero-provider-call boundaries.
- Closed the vehicle-utilization ingestion/scheduler milestone as a normal automatic production capability.

## Remaining Gates

- Implement the authenticated read-only operational-status endpoint with the approved allow-list and cross-tenant tests.
- Run CI and perform one authenticated production GET that makes zero Motive provider calls.
- Compare the returned production/checkpoint/scheduler evidence against the already-certified automatic scheduler cycle.
- Define business meaning and attention thresholds before exposing utilization data in Dashboard, System Health, or Daily Brief surfaces.
- Do not infer provider health from scheduler-claim state alone and do not add clock-based alert semantics until thresholds are separately reviewed.

## Final State

Motive vehicle-utilization durable ingestion is in normal automatic production operation. Automatic execution and same-local-day duplicate prevention are certified from scheduled evidence. Track 4C now advances to safe operational observability rather than further scheduler expansion.