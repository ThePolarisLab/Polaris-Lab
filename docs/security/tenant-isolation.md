# Tenant Isolation Model

Status date: 2026-07-30  
Scope: Phase 1.1 Tenant Isolation Hardening, Phase 2 Database Gate lifecycle enforcement, Phase 2.1 persistent deployment hardening, and Phase 3A QuickBooks production adapter.

## Source of Truth

For authenticated requests, `AuthenticatedPrincipal.organization_id` is the authoritative tenant boundary. Protected routes must not derive tenant ownership from `settings.organization_slug`, environment variables, request payload organization fields, or global singleton connector state.

## Ownership Inventory

| Area | Model / Store | Owner | Organization Ownership | Enforcement |
|---|---|---|---|---|
| Company profile | `Company` | Organization | `organization_id` FK | `/company` filters by principal organization and creates defaults only for that organization. |
| Trucks | `Truck` | Organization | `organization_id` FK; unique unit per org | `/trucks` reads by principal org; mutations require `organization.write`. |
| Team notes | `TeamNote` | Organization | `organization_id` FK | CRUD/resolve paths use principal org; mutations require `executive.write`. |
| Memory | `MemoryEntry` | Organization | `organization_id` FK | List/create/search/reasoning evidence are principal-org scoped; create requires `executive.write`. |
| Knowledge relationships | `KnowledgeRelationship` | Organization | `organization_id` FK; unique relationship per org | Relationship reads and entity traversal require principal org. |
| Missions | `Mission`, `Workflow`, `MissionTask` | Organization | `organization_id` FK on each model | Mission lists, detail reads, creates, and task updates are principal-org scoped; mutations require `executive.write`. |
| Dashboard | Aggregation service | Organization | Derived from tenant-owned sources | Dashboard service accepts organization ID and filters notes, missions, trucks, reasoning evidence, and financial cache reads. |
| Financial cache | `FinancialAccount`, `FinancialSnapshot`, `FinancialSyncHistory` | Organization | `organization_id` FK | Reads, status, sync, summaries, resource counts, report availability, and checkpoints use principal org; writes require `financial.write`. |
| QuickBooks credentials | `QuickBooksOAuthCredential` | Organization | `organization_id` FK, unique | Credential store requires explicit organization ID and never falls back to environment slug. Safe metadata includes verification status, last sync, last refresh, and reauthorization state. |
| QuickBooks OAuth state | `QuickBooksOAuthState` | Organization + principal | `organization_id` and `identity_id` FKs | State is signed, persisted, expiring, single-use, principal-bound, organization-bound, and atomically consumed. |
| QuickBooks production verification | Credential metadata + sync history | Organization | Derived from active credential organization | Verification status is safe metadata only; no tokens, OAuth codes, raw state, encryption keys, or realm IDs are exposed. |
| Hermes QuickBooks contract | TypeScript interfaces/evidence model | Contract only in Phase 3A | Evidence envelopes carry organization/tenant scope | Hermes does not own production refresh tokens or realm IDs in Phase 3A. Python owns live tenant credentials. |
| Identities | `Identity` | Platform identity directory | Global identity, visible through membership | Reads require a membership in the caller's organization unless future platform identity APIs are added. |
| Memberships | `OrganizationMembership` | Organization | `organization_id` FK | Membership routes require path org to match principal org and identity permissions. |
| Organizations | `Organization` | Platform tenant registry | Tenant root | Normal users list only their org; platform admins can create/list/read all orgs. |
| Events | In-process `EventBus` | Organization when event is tenant data | Envelope `organization_id` / `tenant_id` | Recent event API returns only events matching the principal org. |
| Connector registry | In-process registry | Platform runtime | Stateless; tenant state must be separate | Tenant-sensitive connector operations instantiate tenant-bound stores from principal org. |
| Future connector storage | Connector-specific persistence | Organization | Required `organization_id` FK | New connector records must follow the QuickBooks credential/state pattern and ship with Alembic migrations. |

## Query Rule

Any query over tenant-owned data must include an organization predicate equivalent to:

```python
Model.organization_id == principal.organization_id
```

Service-level functions that access tenant data must accept `organization_id` explicitly. API handlers are responsible for deriving that value from the authenticated principal.

## Database Lifecycle Rule

Tenant-owned database columns are part of the Alembic-managed schema lifecycle. Existing pre-Alembic databases must be validated with `python -m app.database.validate_schema` before stamping or upgrading. Backfill may assign legacy rows automatically only when exactly one organization exists; otherwise the migration fails unless an operator supplies `POLARIS_TENANT_BACKFILL_ORGANIZATION_ID` after a verified backup and ownership review.

If a legacy database contains tenant-owned rows but no organizations, the migration fails unless the operator supplies all three one-time bootstrap variables documented in `docs/database/tenant-backfill-plan.md`. That path is a verified legacy adoption flow, not a clean-install default and not an ownership guess.

Hosted staging and production must use persistent PostgreSQL. Temporary SQLite paths such as `sqlite:////tmp/polaris.db` are allowed only for disposable local, test, or preview scenarios and must not hold QuickBooks credentials or financial evidence.

## Public Callback Exception

`GET /api/v1/connectors/quickbooks/oauth/callback` remains public at the HTTP authentication layer because Intuit cannot send Polaris bearer headers. The callback is protected by the OAuth state record, which is signed, expiring, single-use, principal-bound, and organization-bound. Phase 3A also verifies the resulting CompanyInfo against the configured Mor Logistics company before accepting synchronized financial data.

## QuickBooks Read-Only Boundary

QuickBooks routes may read Intuit data, refresh/rotate OAuth tokens, verify company identity, cache read-only financial snapshots in Polaris, or disconnect/revoke credentials. They must not create, update, void, delete, or post QuickBooks transactions in Phase 3A.

## Out of Scope

Motive persistence, Outlook persistence, API versioning, and broad deployment automation remain later phases. New tenant-owned persistence must not be added without an Alembic migration and explicit tenant ownership documentation.
