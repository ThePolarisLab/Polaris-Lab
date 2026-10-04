# Polaris — Canonical Project State

Status reconciled: **2026-10-04**. This is the current-status authority; dated roadmaps, audits and certification reports remain historical evidence. A merge, passing CI, deployed commit and production certification are different facts.

Verified `main` and deployed API baseline: [`e4775e094e36e0a6b413b1aab2cf35289a1ed6dc`](https://github.com/ThePolarisLab/Polaris-Lab/commit/e4775e094e36e0a6b413b1aab2cf35289a1ed6dc). This is the baseline audited before this documentation PR, not a claim that future `main` remains at that SHA. See the [dated deployment evidence register](docs/deployment/production-baseline-2026-10-04.md).

## Canonical architecture

- **GitHub owns code and history.** Changes flow through reviewed branches and PRs; preserve certification provenance.
- **Neon owns durable structured data.** SQLAlchemy/psycopg and Alembic manage tenant-bound operational evidence, connector state, encrypted credentials, memory and workflows. SQLite is for local development/tests only.
- **Render is disposable runtime.** The deployed application is the Python/FastAPI backend and React/Vite frontend under `chief-of-staff/`. Never rely on runtime filesystem persistence.
- **Source systems remain authoritative.** TorqueAI dispatch, Motive fleet, Outlook mailbox and QuickBooks financial records are evidence sources; copied data and derived intelligence must retain provenance and freshness limits.
- **Polaris owns intelligence, policy, memory and workflows.** Root TypeScript Athena/Atlas/Decision Intelligence/Hermes modules are tested foundations; their tests do not establish a fully deployed management copilot. The Python connector runtime owns live OAuth, encrypted token refresh and ingestion. Hermes contracts/reference adapters must not become a second live token owner; see [ADR-026](docs/architecture/ADR-026-quickbooks-runtime-ownership.md).
- AI providers remain replaceable. MCP/tools are least privilege, fixed-tenant and bounded. Consequential actions require human approval. Prefer free infrastructure where practical, with explicit recovery and availability tradeoffs.

## Capability status

**Production-certified** means bounded, accepted live evidence exists for the behavior described. It does not certify every adjacent feature or guarantee today's freshness. **Merged-awaiting-certification** means code exists but live acceptance is incomplete. **Experimental/limited** covers constrained implementations and tested foundations. **Disabled/HOLD** is an explicit operating boundary. **Historical** records superseded states without deleting evidence.

### Production-certified

| Capability | Accepted boundary and evidence |
| --- | --- |
| Private ChatGPT/Auth0 MCP pickups and loaded trailers | [Issue #323](https://github.com/ThePolarisLab/Polaris-Lab/issues/323), certification recorded 2026-10-03: OAuth, discovery, tools and live results; stale/unknown evidence remains visible. This is MCP resource authentication, not enterprise SSO for the whole application. |
| TorqueAI durable dispatch ingestion | Hourly schedule, server-owned rolling seven-day window, durable org/hour claim and at-most-once provider attempt. [2026-10-04 run](https://github.com/ThePolarisLab/Polaris-Lab/actions/runs/37221365132): executed, 27 rows unchanged. No proof of a complete year of history. |
| Motive daily vehicle utilization | Company API key, seven completed America/Chicago days, imperial contract/unit validation, tenant/vehicle/window persistence and checkpoint boundary. [2026-10-04 run](https://github.com/ThePolarisLab/Polaris-Lab/actions/runs/37214444213): 23 vehicles, 65 rollups, 10 inserted/55 updated; 96 requested records missing. Missing is not zero. |
| Motive vehicle location refresh | [2026-10-04 run](https://github.com/ThePolarisLab/Polaris-Lab/actions/runs/37223514292): 23 known, 14 active, 9 inactive; 12 observed and 2 location-unavailable among active vehicles. Partial coverage is reported, not concealed. |
| Motive observed seven-day business KPIs | Repository certification provenance identifies utilization, idle-time share, idle-fuel share, idle fuel burn rate and driving fuel burn rate as accepted; see the [fifth KPI design](docs/engineering/MOTIVE_DRIVING_FUEL_BURN_RATE_FIFTH_BUSINESS_KPI_DESIGN.md) and [driving KPI placement design](docs/engineering/MOTIVE_DRIVING_FUEL_BURN_RATE_KPI_DASHBOARD_PLACEMENT_DESIGN.md). These are bounded observed ratios/rates, not MPG, full-fleet completeness, readiness or trend certification. The live values were not independently recertified in this baseline. |
| QuickBooks read-only financial reconciliation | Six KPI reconciliation accepted in [PR #256](https://github.com/ThePolarisLab/Polaris-Lab/pull/256) and [issue #61](https://github.com/ThePolarisLab/Polaris-Lab/issues/61): revenue, expenses, net income, cash, AR and AP. Gross profit remains unavailable when the source omits the subtotal ([PR #260](https://github.com/ThePolarisLab/Polaris-Lab/pull/260)); no invented subtotal or FX conversion. |
| Representative fuel invoice ingestion/replay | BVD CAD, Eco CAD and Eco USD bounded import evidence, including Eco USD 135-row certification; [dated milestone](docs/knowledge-base/daily-logs/2026-09-01_FUEL_INVOICE_CERTIFICATION_MILESTONE.md). Representative source/replay acceptance is not an unattended mailbox-wide import guarantee. |

### Merged-awaiting-certification

| Capability | Remaining gate |
| --- | --- |
| TorqueAI lane analytics REST/MCP | [PR #326](https://github.com/ThePolarisLab/Polaris-Lab/pull/326) and [PR #327](https://github.com/ThePolarisLab/Polaris-Lab/pull/327) merged; live Auth0 analytics grant/reauthorization and acceptance of `get_lane_analytics` remain unrecorded. A deployed SHA containing the tool does not certify the client grant. |
| Motive fault lifecycle | [PR #324](https://github.com/ThePolarisLab/Polaris-Lab/pull/324) adds certification tooling. [Issue #325](https://github.com/ThePolarisLab/Polaris-Lab/issues/325) remains open: stable identity across statuses and observed lifecycle transition evidence are absent. A successful workflow run is not a passed lifecycle certification. |
| Motive sixth KPI: observed total fuel burn rate | Runtime endpoint is merged; the [sixth KPI design](docs/engineering/MOTIVE_TOTAL_FUEL_BURN_RATE_SIXTH_BUSINESS_KPI_DESIGN.md) still says design-only. This reconciliation has not located a corresponding accepted live certificate; retain an unresolved certification gate rather than infer acceptance from the first five KPIs. |

### Experimental/limited

| Capability | Operating limit |
| --- | --- |
| Chief-of-Staff UI/API and intelligence foundations | Application runtime exists; TS memory/knowledge/orchestration tests are not end-to-end MOR owner acceptance. No Owner Alpha is certified. |
| Outlook read-only connector | Delegated `Mail.Read`, encrypted tenant credentials, bounded body/attachment metadata and folder checkpoints are merged; mailbox evidence supports specific fuel/ACE uses. General attention processing, cadence and retention acceptance are not consolidated. |
| Connector/system health | Passive sync history and attention indicators; manual integrations must not acquire an invented freshness SLA. |
| Maintenance inspection lifecycle | Durable inspection memory and explicit repaired/no-repair-needed resolution; controlled internal writes require confirmation. Disappearance is not resolution. Historical memory does not certify dispatch readiness or change advisory ranking. |
| ACE automated feed | [2026-10-04 trigger run](https://github.com/ThePolarisLab/Polaris-Lab/actions/runs/37213175749) returned HTTP 200. Trigger success alone does not prove complete source import outcome. |
| Fuel price/comparison preview | Reefer-to-ULSD policy; DEF billed-price comparability and quantity reconciliation remain evidence-dependent. Invoice import is manual; recent BVD schedule skips are not fresh-price certification. |
| Internal password/session authentication | Bootstrap/session implementation is merged: bcrypt, rotating hashed refresh tokens, revocation/rate limits and short access tokens. Broader enterprise IdP rollout is separate from accepted MCP Auth0 certification. |

### Disabled/HOLD

- Durable Motive fault memory stays disabled until identity/transition certification is accepted. Snapshot totals are not lifecycle proof.
- Hosted `/api/v1/auth/local/token` remains disabled; production uses the documented bootstrap/session boundary.
- Motive OAuth is dormant/reference; current production integration uses the Company API key. Driver utilization, IFTA, broad new sync and unsupported provider identity assumptions remain held pending independent evidence.
- No finance/source-system writes, generic proxy/admin MCP scope or autonomous consequential actions are approved by this baseline.
- Owner Alpha, Attention Engine, Dispatch/Training/Finance/Maintenance agents and Safety policy lifecycle feature development are not started by this reconciliation.

### Historical

- `polaris_mvp_v0_1` and early SQLite/runtime descriptions are prototypes/history, not the production persistence architecture.
- July/August roadmaps and release percentages describe their dates, not current certification.
- [2026-08-10 EOD](docs/knowledge-base/daily-logs/2026-08-10_EOD.md) and [2026-08-11 EOD](docs/knowledge-base/daily-logs/2026-08-11_EOD.md) preserve unique #134/#137 evidence. Their utilization HOLD statements describe the earlier contract/schema stages, superseded only within the accepted daily-ingestion boundary above.

## Current integrations and MCP scopes

TorqueAI dispatch; Motive Company API key; Outlook delegated read-only mail; QuickBooks read-only finance; fuel/ACE mailbox and invoice evidence. Configuration, schedules and certificates belong to each integration's bounded operating contract; a configured connector is not proof of fresh data.

| MCP tool | Exact permission | Live acceptance |
| --- | --- | --- |
| `get_pickups` | `operations.pickups.read` | Issue #323 accepted |
| `get_loaded_trailers` | `operations.loaded_trailers.read` | Issue #323 accepted |
| `get_lane_analytics` | `operations.analytics.read` | Merged; live certification pending |

The dedicated MCP role is limited to these read permissions, intersected with token permissions and the fixed MOR tenant. Analytics executes through a read-only database boundary; no financial, connector, admin or generic write access. Auth0 runbook: [rollout and acceptance](docs/integrations/chatgpt-polaris-auth0-rollout.md); [MCP contract](docs/integrations/chatgpt-polaris-mcp.md).

## Deployment and database model

Render API `polaris-executive-api` is Python 3, Free, Oregon; static frontend `polaris-executive`. API starts from `chief-of-staff/backend` with Alembic upgrade followed by Uvicorn; startup rejects unversioned/stale managed schemas. The inspected Neon project has one default branch and one database, PostgreSQL 18, live Alembic `202609120002`, observed 2026-10-04. Private account/project/branch/database identifiers and dashboard URLs are omitted from this public baseline. Staging labels do not create environment isolation.

The Render inventory showed no PostgreSQL service. `render.yaml` still declares the old `polaris-staging-db`; it is unchanged here. Verify Blueprint ownership/resource reconciliation before separately reviewing removal. The database target behind Render's secret and frontend deployed commit were not independently inspected in this reconciliation; do not infer them from matching names alone.

## Known data-quality and freshness limitations

- Torque ingestion covers a rolling seven-day provider window. Analytics supports broader query windows, but historic completeness is unproven; unchanged rows do not imply new source activity.
- Motive has missing utilization records and partial/unavailable locations. Never replace unknowns with zero or use stale coordinates as current observations.
- Pickup/trailer responses can be stale or uncertain; expose their evidence timestamps. Manual sync does not imply hourly freshness.
- Source currencies and omitted QBO report fields must remain explicit. Fuel price evidence and invoice quantity/receipt evidence are different facts.
- HTTP 200 and workflow completion prove only the reported boundary; inspect semantic outcomes, skips, checkpoint changes and partial coverage before declaring a healthy business feed.

## Known Production Risks / Unresolved Gates

1. **Material recovery risk:** Neon has only a six-hour history window, no snapshots and no backup schedule. No successful restore drill was verified. Establish agreed recovery objectives, an affordable independent backup/export policy and an isolated restore drill with evidence before calling recovery certified. GitHub cannot recover business data or encrypted connector state.
2. **Merge protection absent:** `main` is unprotected and the ruleset list was empty at inspection. This PR proposes protection but does not change repository settings; see [protection proposal](docs/governance/repository-protection.md).
3. **Certification gaps:** lane analytics live grant/acceptance and fault stable-identity/transition gates remain unresolved. Preserve accepted #323 certification for the existing two tools.
4. **Deployment ambiguity:** staging labels, old Render DB declaration, unverified frontend SHA and uninspected Render database-secret target need operator reconciliation. No production configuration/removal occurs here.
5. **Availability/freshness:** free runtime/compute suspension and manual/skipped feeds can delay data. Owner-facing answers must disclose unknown, stale and partial evidence.
6. **No global feature readiness claim:** Outlook general processing, broad enterprise auth, TS runtime integration and complete owner acceptance remain unverified.
7. **Stale integration documents:** the Eco USD follow-up still says blocked despite later accepted invoice evidence; the sixth Motive KPI design says design-only despite its merged endpoint. These originals are retained; current status follows the evidence boundaries above, with the sixth KPI certificate still unresolved.

## Next approved milestone

**POLARIS V1 Owner Alpha** — MOR Owner & Management Copilot answering what is happening, what needs attention and what management should do next, from attributable evidence with human approval for consequential actions. This is the next approved milestone designation, not authorization to implement its features in this PR.

Complete baseline review and recovery/protection follow-ups, then obtain the feature-specific acceptance scope. Keep source authority, replaceable AI, tenant isolation, least privilege and free-first operating constraints throughout.
