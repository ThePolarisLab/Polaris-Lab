# Polaris Knowledge Base — Motive Vehicle Utilization Milestone

**Date:** 2026-08-16

## Final State

Polaris crossed an important Motive vehicle-utilization gate today: the controlled provider-to-writer validation was executed in production and failed closed before durable persistence when returned unit provenance could not be certified. Follow-up reconciliation incorporated Motive API Support evidence and a review of official documentation. The resulting architecture deliberately separates request-side measurement policy, provider-observed vehicle metadata, and durable response measurement-system certification.

Durable utilization fuel persistence remains disabled. This is the intended safety outcome until Motive explicitly reconciles `X-Metric-Units` request semantics with the returned `vehicle.metric_units` Boolean for `GET /v1/vehicle_utilization`.

## Official Decisions

- Keep `X-Metric-Units: true` as the canonical request-side metric policy.
- Treat returned `vehicle.metric_units` only as raw provider-observed vehicle metadata; do not infer durable fuel-unit provenance from `True`, `False`, or `None`.
- Keep `response_measurement_system` unresolved and durable fuel persistence disabled until authoritative semantics are available.
- Preserve fail-closed behavior: ambiguous unit provenance must stop persistence before any utilization row, checkpoint, or sync-history mutation.
- Historical rollups may change; conflicting-replay fail-closed behavior is therefore temporary pending a dedicated reconciliation/update policy.

## Principles Reaffirmed

- Provider evidence before semantic inference.
- Fail closed at the persistence boundary when durable meaning is unresolved.
- Separate transport/request policy from provider payload metadata and Polaris-certified persistence semantics.
- Production validation is evidence collection, not automatic activation of broad runtime behavior.
- Do not convert or guess measurement units.

## Roadmap Change

The controlled production-write validation gate is complete as an evidence-gathering milestone. It did not authorize normal utilization ingestion. The next gate is explicit certification of response measurement-system semantics, followed by a deliberate reconciliation/update policy for historical rollups before checkpointing, scheduling, or broad sync can be enabled.

## Engineering Decisions

The controlled route made at most one Motive request against a fixed historical window and existing organization-owned vehicles. The production execution completed one provider call and returned one rollup, then stopped with `provider_unit_policy_mismatch`: zero rows were inserted and no checkpoint or sync-history state was mutated.

PR #163 reconciled this evidence with Motive API Support's written clarification. Provider-confirmed semantics now include inclusive end dates, omitted vehicles, `pagination.total`, one aggregate per vehicle/range, and company-configured/default timezone behavior. Parsing and durable-persistence readiness are separate concerns.

PR #164 completed the documentation/source review and confirmed that currently available official Motive documentation does not explicitly reconcile the request header with the returned Boolean. The existing database `metric_units` field is therefore audited as raw provider-observed metadata, not certified response measurement-system provenance.

## Research / Verification Notes

Controlled production evidence:

- 1 provider call completed.
- 1 utilization rollup returned.
- 0 durable utilization rows inserted.
- 0 checkpoint mutations.
- 0 sync-history mutations.
- Safe result: `provider_unit_policy_mismatch`.

Validation reported by the merged reconciliation work reached 620 backend tests for PR #163 and 627 backend tests for PR #164, with no additional live Motive calls during implementation/testing and no migration introduced by either reconciliation gate.

## Completed Work

- Executed the bounded production utilization-write validation.
- Recorded sanitized production evidence without persisting ambiguous data.
- Merged PR #163, reconciling production evidence with Motive API Support semantics.
- Merged PR #164, certifying the remaining unit-semantics ambiguity and documenting the provider clarification needed.
- Preserved the existing database identity while keeping runtime persistence disabled.

## Remaining Gates

- Obtain authoritative clarification that reconciles `X-Metric-Units` with returned `vehicle.metric_units` for this endpoint.
- Certify durable response measurement-system provenance before fuel persistence.
- Define a reconciliation/update policy for historical rollups that may legitimately change.
- Only after those gates, separately review checkpoint advancement, scheduling, and broad utilization runtime activation.

## Status

**Controlled production evidence:** complete.

**Request-side metric policy:** certified (`X-Metric-Units: true`).

**Response measurement-system semantics:** unresolved.

**Durable fuel persistence:** disabled.

**Checkpoints / scheduling / broad utilization sync:** disabled.