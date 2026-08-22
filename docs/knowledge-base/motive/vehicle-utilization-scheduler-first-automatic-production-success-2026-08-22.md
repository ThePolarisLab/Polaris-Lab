# Motive Vehicle Utilization — First Automatic Production Scheduler Success

**Date:** 2026-08-22

## Summary

The first automatic production observation after the delayed-wakeup fix completed successfully under the corrected `06:00–09:59 America/Chicago` backend acceptance window.

The observed scheduled-run sequence demonstrates both successful automatic production execution and durable same-local-day deduplication:

- `Motive Vehicle Utilization Daily #8` completed with HTTP `200`, `Scheduler result status: executed`, and `Scheduler dispatch claimed: true`.
- The later scheduled `Motive Vehicle Utilization Daily #9` completed with HTTP `200`, `Scheduler result status: already_claimed`, and `Scheduler dispatch claimed: false`.

Because the machine endpoint returns `executed` only after the production vehicle-utilization orchestrator returns successfully, #8 is the first certified automatic production scheduler execution under the corrected window. The later #9 wakeup proved the existing durable same-local-day dispatch claim prevented duplicate provider execution.

## Production conclusion

The persistent scheduler is now operationally certified for automatic daily execution with the following controls intact:

- production ingestion gate enabled;
- production scheduler gate enabled;
- controlled validation override disabled;
- configured scheduled organization unchanged;
- backend time gate uses `America/Chicago` and accepts `06:00–09:59` local time;
- GitHub Actions remains wakeup-only and may arrive late;
- the first eligible same-local-day wakeup claims the dispatch before provider HTTP;
- subsequent same-local-day wakeups return `already_claimed` without provider work;
- no scheduler retry or catch-up loop was added;
- provider endpoint, pagination, seven-day rolling horizon, units, omission handling, reconciliation, checkpoint/history semantics, HMAC authentication, and provider credentials remain unchanged.

## Evidence observed

### Scheduled run #8

Observed in GitHub Actions logs:

- workflow: `Motive Vehicle Utilization Daily #8`
- event: Scheduled
- machine endpoint HTTP result: `200`
- scheduler status: `executed`
- dispatch claimed: `true`

This establishes that the corrected scheduler window admitted the delayed GitHub wakeup, the durable dispatch claim was acquired, and the production ingestion path completed successfully.

### Scheduled run #9

Observed in GitHub Actions logs:

- workflow: `Motive Vehicle Utilization Daily #9`
- event: Scheduled
- machine endpoint HTTP result: `200`
- scheduler status: `already_claimed`
- dispatch claimed: `false`

This establishes that the later same-day wakeup did not perform a second provider execution.

## Safety interpretation

No manual rerun was used to obtain this evidence. The successful result therefore validates the intended persistent-production operating model rather than a controlled/manual path.

The earlier delayed-wakeup issue is considered closed: widening the bounded local-time acceptance window removed dependence on precise GitHub cron start timing, while the durable dispatch claim preserved at-most-once provider execution per organization/local date.

## Ongoing operating rule

Leave the production ingestion and scheduler gates enabled during normal operation. Keep the controlled validation window disabled unless a separately authorized validation is required.

For future scheduled observations, a normal same-day pair may show one `executed` result and one `already_claimed` result. If a scheduled run fails or evidence is ambiguous, do not manually rerun the same day; disable the scheduler if provider safety is uncertain and diagnose existing evidence first.

## Final state

The Motive vehicle-utilization production scheduler has now passed its first automatic production observation under the delayed-wakeup-tolerant design. Automatic daily execution and same-day duplicate prevention are both certified from scheduled GitHub Actions evidence.