# FastAPI Route Security Matrix

Baseline branch: `phase1.1/tenant-isolation-hardening`  
Scope: Polaris Chief of Staff FastAPI routers mounted from `chief-of-staff/backend/app/main.py`.

## Classification Legend

- `public`: deliberately unauthenticated.
- `health check`: safe runtime readiness endpoint, unauthenticated when it contains no sensitive details.
- `authenticated`: requires `Authorization: Bearer <token>` and `X-Polaris-Organization`.
- `permission-protected`: requires authenticated principal plus an explicit permission.
- `admin-only`: requires organization or platform administration permission.
- `OAuth callback`: unauthenticated browser redirect target that must validate signed, single-use, organization-bound state.
- `internal`: intended for local/runtime diagnostics; must still be authenticated unless explicitly listed public.

## Public Routes

| Method | Path | Classification | Required Control | Justification |
|---|---|---|---|---|
| GET | `/` | public | none | Non-secret service landing metadata. |
| GET | `/health` | health check | none | External readiness/liveness check; response must remain non-secret. |
| GET | `/api/v1/system/health` | health check | none | Builder/runtime readiness check with API/database status only. |
| GET | `/api/v1/system/info` | public | none | Non-secret runtime metadata used by the Builder runtime contract. |
| GET | `/api/v1/system/version` | public | none | Non-secret build identity used by the Builder runtime contract. |
| POST | `/api/v1/auth/local/token` | public in development/test only | local-token secret validation; disabled in production | Local bootstrap for existing development auth model. Must return 404 outside development/test. |
| GET | `/api/v1/connectors/quickbooks/oauth/callback` | OAuth callback | signed, unexpired, atomic single-use, org-bound OAuth state | Intuit redirects cannot include Polaris bearer headers; authorization comes from validated state. |

## Protected Routes

| Method | Path | Classification | Permission | Tenant Control |
|---|---|---|---|---|
| GET | `/api/v1/auth/me` | authenticated | active organization membership | Principal resolved from `X-Polaris-Organization`. |
| GET | `/company` | permission-protected | `organization.read` | `Company.organization_id == principal.organization_id`. |
| GET | `/trucks` | permission-protected | `organization.read` | `Truck.organization_id == principal.organization_id`. |
| POST | `/trucks` | permission-protected | `organization.write` | Created with principal organization. |
| GET | `/memory` | permission-protected | `executive.read` | `MemoryEntry.organization_id == principal.organization_id`. |
| POST | `/memory` | permission-protected | `executive.write` | Created with principal organization. |
| POST | `/chat` | permission-protected | `executive.read` | No persisted tenant data in current implementation. |
| GET | `/missions` | permission-protected | `executive.read` | `Mission.organization_id == principal.organization_id`. |
| GET | `/missions/{mission_id}` | permission-protected | `executive.read` | Mission ID plus organization filter. |
| POST | `/missions` | permission-protected | `executive.write` | Mission/workflow/task tree created with principal organization. |
| PATCH | `/missions/tasks/{task_id}` | permission-protected | `executive.write` | Task ID plus organization filter. |
| GET | `/relationships` | permission-protected | `executive.read` | `KnowledgeRelationship.organization_id == principal.organization_id`. |
| GET | `/relationships/entity/{entity_key}` | permission-protected | `executive.read` | Entity traversal constrained by organization. |
| GET | `/memory-search` | permission-protected | `executive.read` | Candidate memories and relationship expansion constrained by organization. |
| GET | `/reasoning/q2-risk` | permission-protected | `executive.read` | Evidence collection constrained by organization. |
| GET | `/team-notes` | permission-protected | `executive.read` | `TeamNote.organization_id == principal.organization_id`. |
| GET | `/team-notes/{note_id}` | permission-protected | `executive.read` | Note ID plus organization filter. |
| POST | `/team-notes` | permission-protected | `executive.write` | Created with principal organization. |
| PATCH | `/team-notes/{note_id}` | permission-protected | `executive.write` | Note ID plus organization filter. |
| POST | `/team-notes/{note_id}/resolve` | permission-protected | `executive.write` | Note ID plus organization filter. |
| GET | `/dashboard/executive` | permission-protected | `executive.read` | Aggregates only organization-filtered sources. |
| GET | `/work-context/{work_item_id}` | permission-protected | `executive.read` | Existing work-context read surface. |
| GET | `/api/v1/events/health` | internal | `organization.read` | Metrics only; no event payloads. |
| GET | `/api/v1/events/metrics` | internal | `organization.read` | Metrics only; no event payloads. |
| GET | `/api/v1/events/recent` | internal | `organization.read` | Retained events filtered by principal organization. |
| GET | `/api/v1/github/status` | permission-protected | `connector.read` | Repository connector metadata; no tenant-owned persistence. |
| GET | `/api/v1/github/branches` | permission-protected | `connector.read` | Repository connector metadata. |
| GET | `/api/v1/github/repository` | permission-protected | `connector.read` | Repository connector metadata. |
| GET | `/api/v1/github/tree` | permission-protected | `connector.read` | Repository connector metadata. |
| GET | `/api/v1/github/files/read` | permission-protected | `connector.read` | Repository connector read. |
| GET | `/api/v1/github/search` | permission-protected | `connector.read` | Repository connector read. |
| GET | `/api/v1/github/commits` | permission-protected | `connector.read` | Repository connector read. |
| POST | `/api/v1/github/branches` | permission-protected | `connector.write` | Sensitive connector mutation. |
| PUT | `/api/v1/github/files` | permission-protected | `connector.write` | Sensitive connector mutation. |
| POST | `/api/v1/github/pull-requests` | permission-protected | `connector.write` | Sensitive connector mutation. |
| GET | `/api/v1/code-understanding/analyze` | permission-protected | `connector.read` | Repository analysis surface. |
| GET | `/api/v1/code-understanding/explain` | permission-protected | `connector.read` | Repository analysis surface. |
| GET | `/api/v1/code-understanding/project` | permission-protected | `connector.read` | Repository analysis surface. |
| GET | `/api/v1/refactoring/complexity` | permission-protected | `connector.read` | Repository analysis surface. |
| GET | `/api/v1/refactoring/smells` | permission-protected | `connector.read` | Repository analysis surface. |
| GET | `/api/v1/refactoring/recommendations` | permission-protected | `connector.read` | Repository analysis surface. |
| GET | `/api/v1/refactoring/execution-plan` | permission-protected | `connector.read` | Repository analysis surface. |
| GET | `/api/v1/connectors` | permission-protected | `connector.read` | Tenant-sensitive connector health uses principal org. |
| GET | `/api/v1/connectors/{name}` | permission-protected | `connector.read` | Tenant-sensitive connector health uses principal org. |
| POST | `/api/v1/connectors/{name}/sync` | permission-protected | `connector.write` | Tenant-sensitive sync uses principal org. |
| GET | `/api/v1/connectors/quickbooks/oauth/authorize` | permission-protected | `connector.write` | OAuth state bound to principal org and identity. |
| DELETE | `/api/v1/connectors/quickbooks/oauth/connection` | permission-protected | `connector.write` | Deletes credential for principal org only. |
| GET | `/api/v1/qbo/company` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/accounts` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/reports/profit-loss` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/reports/balance-sheet` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/reports/cash-flow` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/sync/status` | permission-protected | `financial.read` | Financial cache keyed by principal org. |
| GET | `/api/v1/qbo/executive-summary` | permission-protected | `financial.read` | Financial cache keyed by principal org. |
| POST | `/api/v1/qbo/sync` | permission-protected | `financial.write` | Financial cache writes use principal org. |
| POST | `/api/v1/organizations` | admin-only | `platform.admin` | Platform-only tenant creation. |
| GET | `/api/v1/organizations` | admin-only | `organization.read` | Platform admins see all; org users see only their org. |
| GET | `/api/v1/organizations/{organization_id}` | admin-only | `organization.read` | Same org or platform admin only. |
| POST | `/api/v1/identities` | admin-only | `identity.write` | Event scoped to creator principal org. |
| GET | `/api/v1/identities/{identity_id}` | admin-only | `identity.read` | Identity must have membership in principal org. |
| POST | `/api/v1/organizations/{organization_id}/memberships` | admin-only | `identity.write` | Path org must match principal org. |
| GET | `/api/v1/organizations/{organization_id}/memberships` | admin-only | `identity.read` | Path org must match principal org. |

## Tenant-Owned Query Rule

Every query over tenant-owned records must filter by `AuthenticatedPrincipal.organization_id`. See `docs/security/tenant-isolation.md` for the ownership inventory.

## Remaining Later-Phase Work

- Backfill/migrate existing persistent environments through the Database Gate.
- Replace `Base.metadata.create_all` with migrations in the Database Gate.
- Continue Motive, Outlook, API versioning, deployment, and CI expansion outside this phase.
