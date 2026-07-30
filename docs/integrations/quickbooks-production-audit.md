# QuickBooks Production Adapter Audit

Status date: 2026-07-30  
Branch: `phase3a/quickbooks-production-adapter`  
Rebased main SHA: `323ea4fc27dbc7c159114c49e3221f18ad442cbf`

## Scope

This audit covers the QuickBooks implementation before Phase 3A code changes on top of the merged Security Gate, Tenant Isolation, Database Gate, and Phase 2.1 deployment-hardening baseline. The repository is the source of truth. Production credentials, authorization codes, refresh tokens, access tokens, and realm/company IDs are intentionally absent from source control.

Phase 2.1 is now a prerequisite for live QuickBooks verification: production must use persistent Render PostgreSQL, run Alembic before startup, keep public `/` and `/health` generic, and avoid `sqlite:////tmp/polaris.db` for durable connector credentials.

## Current Implementation Inventory

| Area | Current files | Current behavior | Gaps against Issue #61 | Required Phase 3A changes |
|---|---|---|---|---|
| Python OAuth initiation and callback | `chief-of-staff/backend/app/api/quickbooks_oauth.py`, `chief-of-staff/backend/app/connectors/quickbooks_oauth.py` | Authenticated `connector.write` users can start OAuth. Callback is public at HTTP auth layer but validates signed, expiring, persisted, single-use state and stores credentials by `organization_id`. | Callback verifies company through the current connector path but does not persist enough production verification metadata. | Keep Python as the authoritative OAuth runtime. Persist company verification result safely. Continue rejecting invalid, expired, replayed, mismatched, and malformed state. |
| Encrypted credential storage | `chief-of-staff/backend/app/connectors/quickbooks_credentials.py` | Stores one encrypted refresh token per `organization_id` with realm ID, scopes, connected/updated timestamps. Uses Fernet key from `POLARIS_QBO_TOKEN_ENCRYPTION_KEY`. | No persisted access-token expiry, last verification state, expected-company verification metadata, last safe error, reauthorization flag, or dedicated atomic rotation helper. | Add safe metadata fields and an atomic rotation/update path. Never expose encrypted or decrypted token values through API responses/logs. |
| Python HTTPS client | `chief-of-staff/backend/app/connectors/quickbooks.py` | Uses Intuit production URLs with `urllib`; refreshes an access token from the encrypted refresh token; reads CompanyInfo, active accounts, and Profit and Loss/Balance Sheet/Cash Flow reports. | Missing explicit sandbox/test mode, reusable HTTP client, request correlation IDs, structured rate-limit/degraded states, disconnect revocation, pagination, Customers, Vendors, Invoices, Payments, Bills, Purchases, Journal Entries, Aged Receivables, Aged Payables, normalized report rows, harmless company-name normalization, safe verification endpoint, and concurrent refresh protection. | Replace with a production-grade Python client behind the existing connector contract. Use `httpx`, timeouts, retries/backoff, rate-limit handling, decimal-safe normalization, and tenant-bound credential store. |
| Financial sync service | `chief-of-staff/backend/app/services/quickbooks_financial_sync.py` | Syncs company, accounts, and three reports into `financial_accounts`, `financial_snapshots`, and `financial_sync_history`. Writes zero records to QuickBooks. | Company comparison is exact only, financial amounts are converted with `float`, only `accounts_imported` is counted, partial failures can leave weak history, no required resource snapshots, no aged AR/AP reports, no concurrent sync guard, no explicit incremental/full mode contract, no checkpoint metadata. | Add full and incremental read-only sync orchestration, resource/report counts, checkpoint preservation, safe failure states, in-process org sync lock, report availability, and Decimal/string-safe amount handling. |
| Financial cache models | `chief-of-staff/backend/app/models/financial_snapshot.py` | Tenant-owned financial accounts, snapshots, and sync history use `organization_id` FKs. `FinancialAccount.current_balance` is `Float`. | Float storage is not decimal-safe. Sync history lacks counts/checkpoint/report availability/connector health fields. | Add an Alembic migration for metadata and decimal-safe account balance storage. Preserve existing IDs, timestamps, encrypted token values, and payloads. |
| FastAPI QuickBooks financial API | `chief-of-staff/backend/app/api/quickbooks_financials.py` | `financial.read` protects reads; `financial.write` protects sync. Uses principal `organization_id`. | Missing resource endpoints for required entities, aged report endpoints, safe production verification endpoint, and Decimal-safe executive summary parsing. | Add protected read endpoints only where needed. Keep sync mutation guarded by `financial.write` or connector manage/write. Do not add accounting-write actions. |
| Connector health/status API | `chief-of-staff/backend/app/api/connectors.py`, `chief-of-staff/backend/app/connectors/models.py` | Connector list/status uses authenticated `connector.read`; connector sync uses `connector.write`. QuickBooks health is tenant-bound via `QuickBooksCredentialStore(principal.organization_id)`. | Health enum is coarse and does not distinguish authorization required, connected-unverified, company mismatch, rate limited, sync failed, or reauthorization required. | Expand detail fields/status messages without exposing realm ID/secrets. Keep detailed connector health authenticated and tenant-bound. |
| Public runtime health | `chief-of-staff/backend/app/main.py`, `chief-of-staff/backend/app/api/system.py` | After Phase 2.1, public `/` and `/health` expose only generic service status. Detailed system endpoints require authentication and permissions. | Phase 3A must not leak company/financial/QuickBooks details through public health. | Do not add QuickBooks details to public routes. Keep public/private health boundary intact. |
| Frontend QuickBooks surfaces | `chief-of-staff/frontend/src/components/ExecutiveViews.jsx`, `chief-of-staff/frontend/src/apiClient.js` | UI can show connector status, start OAuth, sync financial summary, and render dashboard. API helper attaches bearer and `X-Polaris-Organization` headers and handles 401/403. | Some QuickBooks fetches bypass `apiClient`, so they omit bearer/org headers in the current component. UI lacks verified company, safe sync result, reauthorization-required state, and disconnect action. | Route QuickBooks frontend calls through `apiClient`. Add minimal status, verified company, last sync, sync result, reauthorization, and disconnect UI. |
| Hermes QuickBooks contract | `src/hermes/connectors/quickbooks/QuickBooksApiClient.ts`, `src/hermes/connectors/quickbooks/QuickBooksConnector.ts` | Defines connector/evidence/checkpoint contract for resources and reports. Hermes can consume a `QuickBooksApiClient` and emit evidence envelopes. | Contract is useful, but deployed Python API already owns OAuth and credential persistence. Running live HTTPS and refresh-token rotation in Hermes too would duplicate token ownership. | Keep Hermes as a consumer/contract and test harness. Python owns live OAuth, token rotation, persistence, live HTTPS calls, sync, and API exposure. Hermes consumes sanitized Polaris evidence/status rather than raw secrets. |
| Hermes production client | `src/hermes/connectors/quickbooks/IntuitQuickBooksApiClient.ts` | Implements a TypeScript Intuit client with credential resolver, token refresh, company verification, pagination, reports, retries, 401 refresh, and health. | Resolver returns raw client secret, refresh token, and realm ID into Hermes. Company comparison is exact. Refresh-token rotation is in-memory only. Not wired to Python encrypted tenant credential store. | Do not make this a second production token owner. Update docs/tests as needed to mark it as a contract/sandbox adapter unless a future secret-manager bridge is explicitly designed. |
| Tests | `chief-of-staff/backend/tests/test_quickbooks_connector.py`, `tests/hermes/IntuitQuickBooksApiClient.test.ts`, `tests/hermes/QuickBooksConnector.test.ts` | Backend and Hermes tests cover only part of the target behavior. | Missing backend tests for resource pagination, all reports, normalized company names, refresh-token race/rotation persistence, revoked/malformed token responses, provider timeout, checkpoint preservation, concurrent sync, secret leakage, verification endpoint, UI behavior, and tenant permissions. | Add mocked backend and frontend tests; keep production credentials out of CI. |
| Documentation | `docs/integrations/quickbooks-production.md`, `docs/hermes/PGE-009.6-QUICKBOOKS-CONNECTOR.md`, `docs/security/route-security-matrix.md`, `.env.quickbooks.example` | Existing docs describe a Hermes production adapter and environment variables. | Docs need the Python/Hermes boundary, operator smoke test, health states, persistent database prerequisite, and Issue #61 evidence separation. | Add runbook, ADR/runtime ownership, environment guidance, route matrix updates, connector health docs, v1.0 status, and technical-debt updates. |

## Runtime Ownership Decision

Python FastAPI is the authoritative production runtime for QuickBooks in Phase 3A.

| Responsibility | Owner | Reason |
|---|---|---|
| OAuth initiation | Python FastAPI | Existing protected route binds state to `AuthenticatedPrincipal.organization_id` and identity. |
| OAuth callback | Python FastAPI | Browser callbacks cannot carry Polaris bearer headers; existing signed, persisted state is the security boundary. |
| Token encryption | Python FastAPI | Existing Fernet credential store persists encrypted refresh tokens by `organization_id`. |
| Refresh-token rotation | Python FastAPI | Rotation must update the same encrypted credential row atomically. |
| Credential persistence | Python FastAPI / SQLAlchemy | Database Gate established Alembic-managed tenant-owned QuickBooks tables. |
| Live Intuit HTTPS calls | Python FastAPI | Deployed API has tenant context, encrypted credentials, and protected routes. |
| Synchronization orchestration | Python FastAPI | Sync writes tenant-owned financial snapshots/history. |
| Evidence/checkpoint production | Python FastAPI for deployed dashboard cache; Hermes remains the TypeScript evidence contract/test harness. | Prevents two runtimes from advancing different checkpoints from the same credential. |
| API exposure | Python FastAPI | Existing frontend and Render service consume FastAPI endpoints. |
| Hermes consumption | Sanitized API/evidence only | Hermes must not receive raw refresh tokens, access tokens, client secrets, OAuth codes, full OAuth state, or realm IDs in Phase 3A. |

## Explicit Python-Hermes Contract

Python exposes tenant-bound, authenticated REST endpoints and durable financial cache records. Hermes continues to define the connector evidence/checkpoint model and may consume sanitized Polaris records in future phases. In Phase 3A, Hermes must not be the live token owner or refresh-token rotator. Any TypeScript `QuickBooksApiClient` usage is restricted to tests, sandbox adapters, or a future secret-manager bridge that does not duplicate Python persistence.

## Production Risks Before Phase 3A

1. Duplicate token-ownership architecture between Python and Hermes could lead to refresh-token rotation races if both are used live.
2. Python resource/report coverage is incomplete against Issue #61.
3. Refresh-token rotation is not guarded against concurrent refresh attempts.
4. Financial values are converted to `float` in backend cache/dashboard paths.
5. Company identity verification is not persisted and only uses exact case-sensitive comparison.
6. Existing QuickBooks frontend calls bypass the authenticated API helper.
7. Connector health does not expose enough safe operational detail for production verification.
8. No production smoke-test runbook exists for Render + Intuit setup.
9. Public health must remain free of QuickBooks company, realm, financial, and credential details.
10. Production OAuth/sync must not begin unless `DATABASE_URL` points to persistent PostgreSQL and Alembic is at head.

## Out Of Scope

- Motive and Issue #62.
- Outlook.
- QuickBooks accounting writes.
- API versioning migration.
- Deployment infrastructure changes beyond documentation and required environment guidance.
- Production credential handling in GitHub Actions.
