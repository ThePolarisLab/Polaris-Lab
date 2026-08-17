# Polaris Knowledge Base — Motive Utilization Reconciliation Milestone

**Date:** 2026-08-17

## Final State

August 17 materially advanced the Motive vehicle-utilization production-readiness track. Provider guidance is now authoritative for Company API Key authentication and metric-unit consistency, historical rollup reconciliation has a merged deterministic policy, and a connector-status construction defect discovered during the work has been corrected. Broad utilization runtime remains intentionally disabled pending the remaining production gates.

## Official Decisions

- Company API Key requests use `x-api-key`; OAuth bearer-token handling remains a separate subsystem.
- The canonical utilization request policy remains `X-Metric-Units: true`.
- Under Motive's written clarification, a metric request is expected to return `vehicle.metric_units: true`, with utilization fuel interpreted as liters. Request/response disagreement is a provider-confirmed unit-context mismatch and fails closed with no fuel persistence.
- Historical rereads may reconcile only five provider-derived rollup fields in place: `utilization_percent`, `idle_time`, `driving_time`, `idle_fuel`, and `driving_fuel`.
- Durable identity/context/provenance fields remain immutable. Omitted provider rows are never deleted, zeroed, or interpreted as inactivity.
- The current Motive API key must be rotated before broad production enablement, but rotation remains deliberately deferred until the Motive integration is complete.

## Principles Reaffirmed

- Fail closed when provider unit context is inconsistent.
- Separate authentication mechanisms by contract rather than convenience.
- Reconcile mutable provider facts without mutating durable identity or provenance.
- Use explicit field-by-field decisions rather than blind ORM merge behavior.
- Preserve whole-batch atomicity and exact Decimal comparisons.
- Production enablement remains a separate gate from code merge.

## Roadmap Change

The historical vehicle-utilization reconciliation gate is complete. Authentication and response-unit semantics are now provider-certified. The remaining utilization production gates are narrower: exact scheduled-rollup timezone binding, database/transaction readiness as applicable, checkpoint advancement, scheduling, broad runtime enablement, and credential rotation before broad production use.

## Engineering Decisions

PR #166 certified that existing Company API Key request paths already use `x-api-key`, so no production authentication-code rewrite was required. It also encoded the provider-confirmed unit policy and retained `provider_unit_policy_mismatch` as the fail-closed boundary for inconsistent responses.

PR #167 implemented safe rolling-window reread reconciliation using the existing durable identity `organization_id + motive_vehicle_id + request_window_start + request_window_end`. Only the five certified provider-derived rollup values may update; identity, endpoint, parser version, metric-unit provenance, and other context remain immutable. Decisions are planned before mutations are staged, preserving whole-batch atomicity.

PR #168 fixed a generic connector-status API crash caused by passing unsupported `credential_store=` construction into `MotiveConnector`. The supported Company API Key path is now constructed with `organization_id`, while the OAuth credential store remains separate.

## Research / Verification Notes

Motive API Support's August 17 written guidance resolved two previously open questions: Company API Key authentication is `x-api-key`, and `X-Metric-Units: true` is expected to produce metric utilization output with `vehicle.metric_units: true` and fuel in liters. The earlier controlled production observation with a metric request and false returned indicator is therefore classified as `PROVIDER_CONFIRMED_UNIT_CONTEXT_MISMATCH`; the prior safe outcome remains valid: one provider call, one returned rollup, zero durable rows, and no checkpoint/history mutation.

Reported validation included 401 Motive tests and 664 full-backend tests for PR #166, 677 full-backend tests for PR #167, and 686 full-backend tests for the connector-constructor regression fix in PR #168. Secret-hygiene reviews were reported clean.

## Completed Work

- Merged PR #166: API-key authentication and utilization unit-mismatch certification.
- Merged the updated prior milestone documentation in PR #165.
- Merged PR #167: deterministic historical utilization reconciliation policy.
- Merged PR #168: supported Motive connector construction in the generic status API.
- Closed the historical reconciliation policy gate without enabling broad production ingestion.

## Remaining Gates

- Bind and certify the exact scheduled-rollup timezone behavior.
- Complete any remaining durable writer/database transaction and uniqueness readiness required by the production path.
- Keep checkpoint advancement and scheduling disabled until production-readiness gates are complete.
- Rotate the current Motive API key before broad production enablement.
- Perform controlled production verification of the final enabled path before broad runtime activation.

## End-of-Milestone Status

**Authentication contract:** provider-certified and existing production request path compliant.

**Utilization metric-unit contract:** provider-certified; inconsistent responses fail closed.

**Historical reconciliation policy:** merged.

**Connector status constructor defect:** resolved.

**Broad utilization runtime:** still disabled pending remaining gates.
