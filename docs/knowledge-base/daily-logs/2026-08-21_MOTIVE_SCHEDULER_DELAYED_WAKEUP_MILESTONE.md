# Polaris Knowledge Base — Motive Scheduler Delayed-Wakeup Milestone

**Date:** 2026-08-21

## Executive summary

The first persistent Motive vehicle-utilization scheduler observation exposed an operational timing mismatch rather than a provider, authentication, ingestion, or reconciliation defect: GitHub scheduled workflow wakeups arrived after the backend's previous narrow `06:10–06:24 America/Chicago` acceptance window and therefore completed as HTTP 200 outside-window no-ops.

PR #197 is merged and resolves that lasting scheduler reliability issue by widening the normal backend acceptance window to `06:00–09:59 America/Chicago`, while retaining the durable same-local-day dispatch claim as the at-most-once provider-execution control. Persistent scheduler reactivation remains a separate operator action after the fix.

## Official decisions

- GitHub Actions is a wake-up mechanism, not a precise execution clock; backend time gating must tolerate normal delayed scheduled-workflow starts.
- The normal scheduler acceptance window is now `06:00–09:59 America/Chicago`.
- At-most-once same-local-day provider execution continues to be enforced by the durable dispatch claim, not by assuming only one wakeup can land inside the time window.
- No same-day manual rerun is authorized merely because a scheduled wakeup was delayed or produced an outside-window no-op.
- Persistent scheduler reactivation remains an explicit production operation after the merged fix; merge alone does not activate it.

## Principles reaffirmed

- Fail closed before provider HTTP when scheduler gates are not satisfied.
- Separate wake-up timing from durable execution deduplication.
- Prefer recovery through the next normal rolling-window ingestion over automatic or manual same-day retry loops.
- Keep operational evidence sanitized: expose scheduler status, dispatch-claim state, and safe error codes only.
- Do not broaden provider, ingestion, reconciliation, checkpoint, authentication, or unit semantics when correcting an orchestration-timing defect.

## Roadmap / production-status change

The scheduler moved from a validated narrow-window design to a delayed-wakeup-tolerant production design. The persistent-production activation runbook is now aligned with the wider bounded morning window and same-local-day deduplication behavior.

The scheduler remains disabled pending explicit reactivation and first automatic observation under the corrected window.

## Engineering decisions

The two existing UTC wakeups remain unchanged. More than one wakeup may now reach the backend inside the valid Chicago morning window. Before provider HTTP, the backend acquires the durable organization/local-date dispatch claim; any later in-window wakeup for the same organization and local date returns `already_claimed` without provider work.

PR #197 also adds sanitized workflow output for `status`, `dispatch_claimed`, and optional `error_code`, making HTTP 200 scheduler outcomes operationally distinguishable without exposing credentials or sensitive provider payloads.

The fix does not change provider endpoints, pagination, the seven-day rolling horizon, unit semantics, omission handling, reconciliation, checkpoint/history semantics, HMAC authentication, organization resolution, provider credentials, or retry policy.

## Research / verification notes

The observed failure mode was a scheduler-timing assumption: scheduled GitHub Actions jobs can start later than their nominal cron minute. A narrow minute-level backend window can therefore convert a healthy delayed wakeup into a safe but ineffective outside-window no-op.

The corrected design uses a bounded multi-hour backend window plus a durable same-local-day dispatch claim. This preserves bounded execution while removing dependence on precise GitHub cron start time. Tests cover delayed wakeups and the new window boundaries.

## Completed work

- Merged PR #196: persistent-production scheduler activation runbook.
- Observed the first persistent scheduler timing issue and isolated it from provider/ingestion behavior.
- Disabled scheduler execution before changing the contract.
- Merged PR #197: delayed-wakeup tolerance, new window-boundary tests, sanitized scheduler outcome logging, and runbook alignment.

## Remaining gates

1. Explicitly authorize and perform persistent scheduler reactivation under the corrected configuration.
2. Observe the first automatic scheduled execution without manually rerunning it.
3. Verify sanitized evidence shows one same-local-day provider execution at most; later in-window wakeups must return `already_claimed` without provider work.
4. Verify production orchestrator, persistence, checkpoint/history, omission, and unit safety semantics remain intact.
5. If the first automatic observation fails or is ambiguous, disable the scheduler and diagnose existing evidence rather than retrying the same day.

## Final state

The lasting delayed-wakeup defect is fixed in `main`. The scheduler architecture now tolerates normal GitHub Actions scheduling delay while preserving durable at-most-once daily provider execution. Persistent scheduler execution is not yet reactivated; the next milestone is a successful first automatic production observation under the corrected window.