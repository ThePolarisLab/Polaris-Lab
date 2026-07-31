# FastAPI Route Security Matrix

Baseline branch: `track4b/outlook-production-activation` based on current `main` after Phase 3B and QuickBooks production verification  
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
| GET | `/` | public | none | Generic liveness response only: `{"status":"ok"}`. No environment, organization, version, capability, database, connector, company, or financial metadata. |
| GET | `/health` | health check | none | External readiness/liveness check. Response is limited to `{"status":"ok"}` or `{"status":"degraded"}` with HTTP status; no runtime metadata. |
| GET | `/api/v1/auth/bootstrap/status` | public | secret-free availability only | Allows the frontend to decide whether to display the first-admin bootstrap form. Exposes only fixed bootstrap target IDs and availability; no secret or user data. |
| POST | `/api/v1/auth/bootstrap` | public bootstrap | strong one-time `POLARIS_BOOTSTRAP_SECRET`, configured admin email, password hashing, completion marker | First-admin onboarding only. Creates `org-mor-logistics` and `mor-admin`, records audit event, then permanently rejects repeat bootstrap. |
| POST | `/api/v1/auth/login` | public auth | email/password, bcrypt hash verification, active identity/membership, rate limiting | Issues short-lived signed access token and hashed refresh-token backed server session. |
| POST | `/api/v1/auth/refresh` | public auth | valid unrevoked refresh token hash; token rotation | Rotates refresh session and returns a new short-lived access token. Reuse of old refresh token is rejected. |
| POST | `/api/v1/auth/logout` | public/authenticated hybrid | bearer token when present; idempotent local cleanup otherwise | Revokes the current server-side session when a valid bearer is present. |
| POST | `/api/v1/auth/local/token` | public in development/test only | local-token secret validation; disabled in production | Local bootstrap for existing development auth model. Must return 404 outside development/test. |
| GET | `/api/v1/connectors/quickbooks/oauth/callback` | OAuth callback | signed, unexpired, atomic single-use, org-bound and principal-bound OAuth state; post-token company verification | Intuit redirects cannot include Polaris bearer headers; authorization comes from validated state. |
| GET | `/api/v1/outlook/callback` | OAuth callback | signed, unexpired, atomic single-use, org-bound and principal-bound OAuth state; Microsoft mailbox identity verification | Microsoft redirects cannot include Polaris bearer headers; authorization comes from validated state. No tokens, codes, or raw state values are returned. |

## Protected Routes

| Method | Path | Classification | Permission | Tenant Control |
|---|---|---|---|
| GET | `/api/v1/auth/me` | authenticated | active organization membership | Principal resolved from signed session token and `X-Polaris-Organization`. |
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
| GET | `/api/v1/system/health` | permission-protected | `connector.read` | Detailed runtime/database status is authenticated and org-context bound. |
| GET | `/api/v1/system/info` | permission-protected | `connector.read` | Detailed service metadata is authenticated and org-context bound. |
| GET | `/api/v1/system/version` | permission-protected | `connector.read` | Detailed version/build identity is authenticated and org-context bound. |
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
| GET | `/api/v1/connectors/quickbooks/oauth/authorize-url` | permission-protected | `connector.write` | OAuth state bound to principal org and identity; returns Intuit URL without exposing tokens. |
| GET | `/api/v1/connectors/quickbooks/oauth/authorize` | permission-protected | `connector.write` | OAuth state bound to principal org and identity. |
| DELETE | `/api/v1/connectors/quickbooks/oauth/connection` | permission-protected | `connector.write` | Revokes/deletes credential for principal org only. |
| GET | `/api/v1/qbo/company` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/accounts` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/resources/{resource}` | permission-protected | `financial.read` | Paginated read-only QuickBooks resource reads use principal org credential only. |
| GET | `/api/v1/qbo/reports/profit-loss` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/reports/balance-sheet` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/reports/cash-flow` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/reports/aged-receivables` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/reports/aged-payables` | permission-protected | `financial.read` | Credential store keyed by principal org. |
| GET | `/api/v1/qbo/sync/status` | permission-protected | `financial.read` | Financial cache keyed by principal org. |
| GET | `/api/v1/qbo/executive-summary` | permission-protected | `financial.read` | Financial cache keyed by principal org. |
| GET | `/api/v1/qbo/verification` | permission-protected | `connector.read` | Secret-free connector verification status for principal org. |
| POST | `/api/v1/qbo/verification` | permission-protected | `connector.write` | Active read-only provider verification for principal org. |
| POST | `/api/v1/qbo/sync` | permission-protected | `financial.write` | Financial cache writes use principal org; performs no QuickBooks writes. |
| GET | `/api/v1/outlook/status` | permission-protected | `connector.read` | Secret-free Outlook status for principal org only. |
| GET | `/api/v1/outlook/connect` | permission-protected | `connector.write` | OAuth state bound to principal org and identity; returns Microsoft URL without exposing tokens. |
| POST | `/api/v1/outlook/sync` | permission-protected | `connector.write` | Read-only Microsoft Graph sync writes only to principal-org Polaris Outlook tables. |
| POST | `/api/v1/outlook/disconnect` | permission-protected | `connector.write` | Deletes/disconnects principal-org Outlook credential; performs no mailbox mutation. |
| GET | `/api/v1/outlook/folders` | permission-protected | `connector.read` | `OutlookFolder.organization_id == principal.organization_id`. |
| GET | `/api/v1/outlook/messages` | permission-protected | `executive.read` | `OutlookMessage.organization_id == principal.organization_id`; supports safe filters and pagination. |
| GET | `/api/v1/outlook/messages/{message_id}` | permission-protected | `executive.read` | Message ID plus organization filter. |
| GET | `/api/v1/outlook/attention` | permission-protected | `executive.read` | Derived from principal-org Outlook messages and classifications only. |
| GET | `/api/v1/outlook/sync-history` | permission-protected | `connector.read` | `OutlookSyncHistory.organization_id == principal.organization_id`. |
| POST | `/api/v1/organizations` | admin-only | `platform.admin` | Platform-only tenant creation. |
| GET | `/api/v1/organizations` | admin-only | `organization.read` | Platform admins see all; org users see only their org. |
| GET | `/api/v1/organizations/{organization_id}` | admin-only | `organization.read` | Same org or platform admin only. |
| POST | `/api/v1/identities` | admin-only | `identity.write` | Event scoped to creator principal org. |
| GET | `/api/v1/identities/{identity_id}` | admin-only | `identity.read` | Identity must have membership in principal org. |
| POST | `/api/v1/organizations/{organization_id}/memberships` | admin-only | `identity.write` | Path org must match principal org. |
| GET | `/api/v1/organizations/{organization_id}/memberships` | admin-only | `identity.read` | Path org must match principal org. |

## Tenant-Owned Query Rule

Every query over tenant-owned records must filter by `AuthenticatedPrincipal.organization_id`. See `docs/security/tenant-isolation.md` for the ownership inventory.

## Production Auth Note

Phase 3B keeps `/api/v1/auth/local/token` disabled in production/staging and introduces password-based internal-launch sessions. Bootstrap is a one-time route guarded by a strong Render secret and persistent completion marker. Passwords are bcrypt-hashed; refresh tokens are stored only as hashes and rotate on use.

## Database Gate Note

Phase 2 and Phase 2.1 make tenant-owned schema enforcement Alembic-managed, block staging/production startup when the database is unversioned or stale, require persistent PostgreSQL for hosted staging/production, and keep detailed runtime status authenticated.

## QuickBooks Production Note

Phase 3A keeps QuickBooks accounting write actions out of scope. All QuickBooks routes either read provider data, run read-only verification, synchronize into Polaris-owned financial cache tables, initiate OAuth, handle OAuth callback state, or disconnect/revoke credentials for the active organization.

## Outlook Production Note

Track 4B keeps Outlook mail mutation actions out of scope. Outlook routes initiate delegated read-only OAuth, validate public callbacks through signed one-use state, synchronize only approved folder/message/attachment metadata into Polaris-owned Outlook tables, and expose safe tenant-scoped executive views.

## Remaining Later-Phase Work

- Continue Motive, API versioning, external identity-provider integration, and non-QuickBooks deployment automation outside this phase.
- Any Outlook write capability requires a separate governed workstream and new permission review.
