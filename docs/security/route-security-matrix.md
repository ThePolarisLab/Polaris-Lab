# FastAPI Route Security Matrix

Baseline branch: `phase1/security-gate`  
Scope: Polaris Chief of Staff FastAPI routers mounted from `chief-of-staff/backend/app/main.py`.

## Classification Legend

- `public`: deliberately unauthenticated.
- `health check`: safe runtime readiness endpoint, unauthenticated when it contains no sensitive details.
- `authenticated`: requires `Authorization: Bearer <token>` and `X-Polaris-Organization`.
- `permission-protected`: requires authenticated principal plus an explicit permission.
- `admin-only`: requires administrative management permission.
- `OAuth callback`: unauthenticated browser redirect target that must validate signed, single-use, organization-bound state.
- `internal`: intended for local/runtime diagnostics; must still be authenticated unless explicitly listed public.

## Public Routes

| Method | Path | Classification | Required Control | Justification |
|---|---|---|---|---|
| GET | `/` | public | none | Non-secret service landing metadata. |
| GET | `/health` | health check | none | External readiness/liveness check; response must remain non-secret. |
| POST | `/api/v1/auth/local/token` | public in development/test only | local-token secret validation; disabled in production | Local bootstrap for existing development auth model. Must return 404 outside development/test. |
| GET | `/api/v1/connectors/quickbooks/oauth/callback` | OAuth callback | signed, unexpired, single-use, org-bound OAuth state | Intuit redirects cannot include Polaris bearer headers; authorization must come from validated state. |

## Protected Routes

| Method | Path | Classification | Permission |
|---|---|---|---|
| GET | `/api/v1/auth/me` | authenticated | active organization membership |
| GET | `/company` | permission-protected | `organization.read` |
| GET | `/trucks` | permission-protected | `organization.read` |
| POST | `/trucks` | permission-protected | `organization.manage` |
| GET | `/memory` | permission-protected | `executive.read` |
| POST | `/memory` | permission-protected | `executive.read` |
| POST | `/chat` | permission-protected | `executive.read` |
| GET | `/missions` | permission-protected | `executive.read` |
| GET | `/missions/{mission_id}` | permission-protected | `executive.read` |
| POST | `/missions` | permission-protected | `executive.read` |
| PATCH | `/missions/tasks/{task_id}` | permission-protected | `executive.read` |
| GET | `/relationships` | permission-protected | `executive.read` |
| GET | `/relationships/entity/{entity_key}` | permission-protected | `executive.read` |
| GET | `/memory-search` | permission-protected | `executive.read` |
| GET | `/reasoning/q2-risk` | permission-protected | `executive.read` |
| GET | `/team-notes` | permission-protected | `executive.read` |
| GET | `/team-notes/{note_id}` | permission-protected | `executive.read` |
| POST | `/team-notes` | permission-protected | `executive.read` |
| PATCH | `/team-notes/{note_id}` | permission-protected | `executive.read` |
| POST | `/team-notes/{note_id}/resolve` | permission-protected | `executive.read` |
| GET | `/dashboard/executive` | permission-protected | `executive.read` |
| GET | `/work-context/{work_item_id}` | permission-protected | `executive.read` |
| GET | `/api/v1/system/health` | internal | `organization.read` |
| GET | `/api/v1/system/info` | internal | `organization.read` |
| GET | `/api/v1/system/version` | internal | `organization.read` |
| GET | `/api/v1/events/health` | internal | `organization.read` |
| GET | `/api/v1/events/metrics` | internal | `organization.read` |
| GET | `/api/v1/events/recent` | internal | `organization.read` |
| GET | `/api/v1/github/status` | permission-protected | `connector.read` |
| GET | `/api/v1/github/branches` | permission-protected | `connector.read` |
| GET | `/api/v1/github/repository` | permission-protected | `connector.read` |
| GET | `/api/v1/github/tree` | permission-protected | `connector.read` |
| GET | `/api/v1/github/files/read` | permission-protected | `connector.read` |
| GET | `/api/v1/github/search` | permission-protected | `connector.read` |
| GET | `/api/v1/github/commits` | permission-protected | `connector.read` |
| POST | `/api/v1/github/branches` | permission-protected | `connector.manage` |
| PUT | `/api/v1/github/files` | permission-protected | `connector.manage` |
| POST | `/api/v1/github/pull-requests` | permission-protected | `connector.manage` |
| GET | `/api/v1/code-understanding/analyze` | permission-protected | `connector.read` |
| GET | `/api/v1/code-understanding/explain` | permission-protected | `connector.read` |
| GET | `/api/v1/code-understanding/project` | permission-protected | `connector.read` |
| GET | `/api/v1/refactoring/complexity` | permission-protected | `connector.read` |
| GET | `/api/v1/refactoring/smells` | permission-protected | `connector.read` |
| GET | `/api/v1/refactoring/recommendations` | permission-protected | `connector.read` |
| GET | `/api/v1/refactoring/execution-plan` | permission-protected | `connector.read` |
| GET | `/api/v1/connectors` | permission-protected | `connector.read` |
| GET | `/api/v1/connectors/{name}` | permission-protected | `connector.read` |
| POST | `/api/v1/connectors/{name}/sync` | permission-protected | `connector.manage` |
| GET | `/api/v1/connectors/quickbooks/oauth/authorize` | permission-protected | `connector.manage` |
| DELETE | `/api/v1/connectors/quickbooks/oauth/connection` | permission-protected | `connector.manage` |
| GET | `/api/v1/qbo/company` | permission-protected | `connector.read` |
| GET | `/api/v1/qbo/accounts` | permission-protected | `connector.read` |
| GET | `/api/v1/qbo/reports/profit-loss` | permission-protected | `connector.read` |
| GET | `/api/v1/qbo/reports/balance-sheet` | permission-protected | `connector.read` |
| GET | `/api/v1/qbo/reports/cash-flow` | permission-protected | `connector.read` |
| GET | `/api/v1/qbo/sync/status` | permission-protected | `connector.read` |
| GET | `/api/v1/qbo/executive-summary` | permission-protected | `executive.read` |
| POST | `/api/v1/qbo/sync` | permission-protected | `connector.manage` |
| POST | `/api/v1/organizations` | admin-only | `organization.manage` |
| GET | `/api/v1/organizations` | admin-only | `organization.manage` |
| GET | `/api/v1/organizations/{organization_id}` | admin-only | `organization.manage`; returned organization must match permitted context unless platform-admin support is added |
| POST | `/api/v1/identities` | admin-only | `identity.manage` |
| GET | `/api/v1/identities/{identity_id}` | admin-only | `identity.read` |
| POST | `/api/v1/organizations/{organization_id}/memberships` | admin-only | `identity.manage`; path organization must match principal organization |
| GET | `/api/v1/organizations/{organization_id}/memberships` | admin-only | `identity.read`; path organization must match principal organization |

## Required Implementation Adjustments

- Keep public routes limited to the explicit public table above.
- Split router-level connector permissions so read endpoints require `connector.read` and mutation/sync/OAuth management endpoints require `connector.manage`.
- Split organization/identity reads and writes where the current router-level dependency is too broad.
- Bind QuickBooks OAuth state to the initiating principal and organization; consume it exactly once.
- Reject production startup when `POLARIS_LOCAL_AUTH_SECRET` is unset or equals `polaris-dev-only`.
- Frontend protected screens must not render until a session with token and organization context is present.
