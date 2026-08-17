# Polaris Knowledge Base — Motive Vehicle Utilization Milestone

**Milestone date:** 2026-08-16  
**Updated:** 2026-08-17 after Motive API Support clarification and PR #166

## Final State

Polaris completed the bounded Motive vehicle-utilization production-write validation safely. The controlled route made one provider call, returned one utilization rollup, and failed closed before durable persistence because the request used `X-Metric-Units: true` while the returned `vehicle.metric_units` indicator was `false`. Zero utilization rows were inserted, and no checkpoint or sync-history state was mutated.

On 2026-08-17, Motive API Support explicitly clarified the expected unit semantics for `GET /v1/vehicle_utilization`: `X-Metric-Units: true` requests metric values, with `idle_fuel` and `driving_fuel` expected in liters; `X-Metric-Units: false` requests imperial values, with fuel expected in gallons; and returned `vehicle.metric_units` is the provider unit indicator (`true` metric, `false` imperial). Motive further confirmed that a request/response disagreement is not an expected or documented combination and should be treated as unit-inconsistent rather than persisted as definitively metric or imperial.

PR #166 incorporated that provider clarification. Response-unit semantics are therefore no longer unresolved. The canonical request policy remains metric, and unit readiness now requires the returned provider indicator to agree with the requested measurement system. Durable broad utilization ingestion remains disabled pending the remaining rollout gates.

## Official Decisions

- Keep `X-Metric-Units: true` as the canonical vehicle-utilization request policy.
- For the canonical metric request, `vehicle.metric_units: true` is the expected consistent response indicator and fuel values are treated as liters.
- `X-Metric-Units: true` plus `vehicle.metric_units: false` is a provider-confirmed unit-context mismatch and must fail closed.
- `X-Metric-Units: false` plus `vehicle.metric_units: false` is the documented imperial-consistent case, with fuel values in gallons.
- Missing or malformed `vehicle.metric_units` remains fail-closed for durable fuel persistence.
- `idle_time` and `driving_time` are seconds regardless of metric-unit setting.
- Do not auto-convert or guess fuel units when request and response indicators disagree.
- Historical rollups may change; conflicting-replay fail-closed behavior remains temporary pending a dedicated reconciliation/update policy.

## Authentication Certification

Motive API Support also confirmed Company API Key authentication by successfully testing a Motive endpoint with the `x-api-key` header.

The Polaris audit in PR #166 confirmed that production Company-API-Key request paths already used `x-api-key`; no production authentication-code correction was required. Motive OAuth remains a separate credential path and may legitimately use Bearer tokens when enabled.

The current Motive Company API key must be rotated before broad production enablement because it was echoed in plaintext by provider support. Rotation is intentionally deferred until the Motive integration work is complete. No real credential is recorded in this Knowledge Base entry.

## Principles Reaffirmed

- Provider evidence before semantic inference.
- Fail closed at the persistence boundary when request and response measurement context disagree.
- Separate API request policy, provider-returned metadata, and durable persistence provenance.
- Production validation is evidence collection, not automatic activation of broad runtime behavior.
- Never synthesize missing requested vehicles as zero-activity rows.
- Never convert or guess measurement units for a mismatched response.

## Engineering Decisions

The controlled production route remains feature-flagged off by default. The prior validation evidence is retained as:

- provider calls completed: 1
- returned utilization rollups: 1
- durable utilization rows inserted: 0
- checkpoint mutations: 0
- sync-history mutations: 0
- result: safe fail-closed `provider_unit_policy_mismatch`
- evidence classification after PR #166: `PROVIDER_CONFIRMED_UNIT_CONTEXT_MISMATCH`

PR #163 reconciled the initial production evidence with Motive Support's earlier written clarification. Provider-confirmed semantics include inclusive end dates, omitted vehicles, `pagination.total`, one aggregate per vehicle/range, and company-configured/default timezone behavior.

PR #164 completed the official-documentation review and correctly held response-unit certification unresolved because the public documentation did not explicitly reconcile `X-Metric-Units` with `vehicle.metric_units`.

PR #166 closed that semantic gap using Motive API Support's direct 2026-08-17 reply. It also confirmed that Polaris Company API Key requests already use `x-api-key`, added regression coverage, reclassified the production mismatch evidence, and preserved the controlled route, checkpoints, scheduling, and broad utilization sync as disabled.

## Unit Readiness Matrix

| Request policy | Returned `vehicle.metric_units` | Result |
| --- | --- | --- |
| `X-Metric-Units: true` | `true` | consistent; unit-ready; fuel in liters |
| `X-Metric-Units: true` | `false` | `provider_unit_policy_mismatch`; no fuel persistence |
| `X-Metric-Units: false` | `false` | consistent; unit-ready; fuel in gallons |
| `X-Metric-Units: false` | `true` | `provider_unit_policy_mismatch`; no fuel persistence |
| known request policy | `None` | fail closed |
| known request policy | malformed/non-Boolean | fail closed |

## Timezone Status

Motive previously confirmed that v1 vehicle-utilization date boundaries use the company configured/default timezone. The Motive account UI has been observed with the account preference set to **Central Time - Chicago**, selected for the Manitoba-based operation.

This is strong operational evidence, but Polaris has not yet independently certified that this exact account-preference setting is the authoritative timezone source used by `GET /v1/vehicle_utilization` rollup boundaries. Do not add `X-Time-Zone` to this endpoint and do not treat `America/Chicago` or `America/Winnipeg` as a fully certified rollup-zone binding until that final source relationship is resolved.

## Completed Work

- Executed the bounded production utilization-write validation.
- Recorded sanitized production evidence without persisting unit-inconsistent data.
- Merged PR #163 for evidence/semantics reconciliation.
- Merged PR #164 for official-documentation unit-semantics certification.
- Obtained direct Motive API Support clarification of vehicle-utilization unit behavior.
- Merged PR #166 for Company API Key authentication certification and provider-confirmed unit-mismatch handling.
- Preserved tenant isolation, database identity, returned-only persistence, transaction boundaries, and fail-closed behavior.
- Kept the controlled route, checkpoints, scheduling, and broad utilization runtime disabled.

## Remaining Gates

- Define the historical-rollup reconciliation/update policy for legitimately changing Motive rollups.
- Resolve/certify the exact source relationship between Motive's company configured/default rollup timezone and the observed account preference before scheduled daily ingestion.
- Implement and certify checkpoint advancement only after persistence/reconciliation behavior is complete.
- Perform any further controlled live validation only under a separately authorized, bounded gate.
- Rotate the Motive Company API key before broad production enablement.
- Only after those gates, separately review scheduling and broad vehicle-utilization runtime activation.

## Status

**Controlled production evidence:** complete.

**Company API Key authentication:** certified as `x-api-key`; existing Polaris production request paths already complied.

**Canonical request-side metric policy:** certified (`X-Metric-Units: true`).

**Response measurement-system semantics:** provider-confirmed; request/response mismatch fails closed.

**Prior production observation:** provider-confirmed unit-context mismatch.

**Durable broad utilization ingestion:** disabled.

**Historical reconciliation policy:** pending.

**Exact scheduled-rollup timezone binding:** pending final certification.

**Checkpoints / scheduling / broad utilization sync:** disabled.

**Motive API key rotation:** required before broad production enablement; intentionally deferred until Motive integration completion.
