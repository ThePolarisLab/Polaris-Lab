# Polaris Track 4C — Motive Current Status

**Status date:** 2026-08-22

This document is the current-status companion to `POLARIS_TRACK_4C_MOTIVE_ROADMAP.md`.

The roadmap intentionally preserves the historical gate-by-gate development record. Earlier `HOLD`, disabled, and uncertified statements in that history describe the state at the time of those gates and must not be read as the current production state when a later certified milestone supersedes them.

## Current production status

### 4C.1E — Company API Key Production Foundation

**Status: COMPLETE / PRODUCTION FOUNDATION ACTIVE**

- Production Motive access uses backend-only Company API Key configuration.
- Provider authentication remains `X-API-Key`; secrets are not exposed to frontend or workflow logs.
- The production runtime remains under `chief-of-staff/` with organization isolation and safe connector status/evidence boundaries.
- API-key rotation and one-time post-rotation provider verification have been completed.

### 4C.2A — Vehicle Read-Only Production Ingestion

**Status: COMPLETE**

- Vehicle ingestion foundation, provider identity, pagination, tenant-owned persistence, and safe sync metadata are established.
- Vehicle records are the organization-owned association boundary used by later vehicle-utilization ingestion.

### 4C.2B — Company User Read-Only Production Ingestion

**Status: COMPLETE FOR THE CERTIFIED `/v1/users` SCOPE**

- Company-user ingestion and pagination are established for the provider contract described in the roadmap.
- This completion does not broaden the historical driver-classification claim: `/v1/users` rows are not automatically reclassified as drivers without a separately certified discriminator.

### 4C.2C+ — Vehicle Utilization Durable Production Ingestion

**Status: COMPLETE / AUTOMATIC PRODUCTION SCHEDULER VALIDATED**

The historical 4C.2C+ section records the staged path from provider-contract discovery through durable production operation. The current certified state is:

- Production provider endpoint: `GET /v1/vehicle_utilization`.
- Provider response contract: `vehicle_idle_rollups[] -> vehicle_idle_rollup`, vehicle identity at `vehicle.id`.
- Production measurement policy uses explicit imperial requests (`X-Metric-Units: false`) and fails closed unless the returned provider unit indicator agrees.
- Returned fuel values are treated as gallons under the certified production request policy; time metrics remain seconds.
- Provider omission is preserved as unknown/absent rollup and is never synthesized into a zero-activity row.
- Durable replay identity is organization + Motive vehicle + exact request window.
- The writer validates the entire batch, preserves tenant ownership, is idempotent, and reconciles provider-corrected mutable values.
- Production ingestion reads the latest seven completed `America/Chicago` local days, with one provider request per day, no provider retries, independent day transactions, sanitized run history, and checkpoint advancement only after full success.
- Manual production ingestion is feature-gated and uses the authenticated production sync route.
- Automatic scheduling is production-enabled behind the separate ingestion and scheduler gates.
- GitHub Actions is only the wake-up mechanism. Backend local-time gating uses the bounded `06:00–09:59 America/Chicago` production window.
- A durable organization/local-date dispatch claim is acquired before provider HTTP and enforces at-most-once same-local-day provider execution even when multiple wakeups land inside the window.
- Workflow output exposes sanitized scheduler outcomes (`executed`, `already_claimed`, `outside_window`, or safe failure metadata) without exposing credentials or provider payloads.

## First certified automatic production observation

The first automatic observation under the delayed-wakeup-tolerant scheduler design succeeded on 2026-08-22:

- Scheduled run #8 returned HTTP 200 with `status: executed` and `dispatch_claimed: true`.
- The later same-day scheduled run #9 returned HTTP 200 with `status: already_claimed` and `dispatch_claimed: false`.
- This demonstrates that the corrected local-time window admitted the delayed wakeup and that the durable same-day claim prevented duplicate provider execution.

The evidence milestone is recorded by merged PR #199.

## Superseded historical states

When reading `POLARIS_TRACK_4C_MOTIVE_ROADMAP.md`, treat earlier statements such as the following as historical unless a later section explicitly reopens the gate:

- utilization ingestion `HOLD` / uncertified;
- no durable writer or no production sync route;
- checkpoint advancement disabled;
- scheduled ingestion disabled;
- unresolved unit semantics that were later provider-certified and reconciled;
- the former narrow scheduler acceptance window;
- scheduler disabled pending first automatic observation.

Those statements remain valuable engineering evidence for why later controls exist, but they are not the current runtime state.

## Controls that remain intentionally unchanged

Current production certification does **not** authorize broadening these boundaries:

- no synthesis of omitted provider rollups into zero activity;
- no silent unit conversion or persistence on unit-policy disagreement;
- no automatic vehicle creation from utilization responses;
- no provider retry loop in the seven-day production run;
- no same-day manual retry merely because a scheduled wakeup is delayed or ambiguous;
- no weakening of tenant isolation, HMAC machine authentication, production feature gates, durable claim ordering, checkpoint/history atomicity, or provider pagination limits.

## Next Track 4C work

The utilization ingestion/scheduler milestone is closed. New Motive work should start as a separately scoped Track 4C item rather than modifying the certified scheduler without a new requirement.

Recommended next sequence:

1. **Operational observability:** add/read a safe authenticated production status surface for latest utilization ingestion history, checkpoint, and scheduler dispatch outcome so normal daily certification does not depend on manually opening GitHub logs.
2. **Consumer integration:** feed certified utilization data into Polaris operational views only after defining the business meaning and attention thresholds for each KPI; do not infer inactivity from omitted provider rows.
3. **Roadmap cleanup:** progressively mark historical gates as superseded with links to their later certification milestones, while preserving the audit trail rather than deleting it.
4. **New provider domains:** only after the utilization consumer contract is settled, evaluate the next Motive endpoint/domain as a new bounded provider-contract track.

## Production disposition

Track 4C's vehicle-utilization path is now in normal automatic production operation. The scheduler and ingestion gates should remain enabled under the certified configuration unless an operational failure requires the fail-closed runbook. Further scheduler/provider changes require a separately reviewed change with focused tests and production evidence.