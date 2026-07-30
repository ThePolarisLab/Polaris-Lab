# Tenant Isolation Model

Status date: 2026-07-29  
Scope: Phase 1.1 Tenant Isolation Hardening.

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
| Dashboard | Aggregation service | Organization | Derived from tenant-owned sources | Dashboard service accepts organization ID and filters notes, missions, trucks, and reasoning evidence. |
| Financial cache | `FinancialAccount`, `FinancialSnapshot`, `FinancialSyncHistory` | Organization | `organization_id` FK | Reads, status, sync, and summaries use principal org; writes require `financial.write`. |
| QuickBooks credentials | `QuickBooksOAuthCredential` | Organization | `organization_id` FK, unique | Credential store requires explicit organization ID and never falls back to environment slug. |
| QuickBooks OAuth state | `QuickBooksOAuthState` | Organization + principal | `organization_id` and `identity_id` FKs | State is signed, persisted, expiring, principal-bound, organization-bound, and atomically consumed. |
| Identities | `Identity` | Platform identity directory | Global identity, visible through membership | Reads require a membership in the caller's organization unless future platform identity APIs are added. |
| Memberships | `OrganizationMembership` | Organization | `organization_id` FK | Membership routes require path org to match principal org and identity permissions. |
| Organizations | `Organization` | Platform tenant registry | Tenant root | Normal users list only their org; platform admins can create/list/read all orgs. |
| Events | In-process `EventBus` | Organization when event is tenant data | Envelope `organization_id` / `tenant_id` | Recent event API returns only events matching the principal org. |
| Connector registry | In-process registry | Platform runtime | Stateless; tenant state must be separate | Tenant-sensitive connector operations instantiate tenant-bound stores from principal org. |
| Future connector storage | Connector-specific persistence | Organization | Required `organization_id` FK | New connector records must follow the QuickBooks credential/state pattern. |

## Query Rule

Any query over tenant-owned data must include an organization predicate equivalent to:

```python
Model.organization_id == principal.organization_id
```

Service-level functions that access tenant data must accept `organization_id` explicitly. API handlers are responsible for deriving that value from the authenticated principal.

## Public Callback Exception

`GET /api/v1/connectors/quickbooks/oauth/callback` remains public at the HTTP authentication layer because Intuit cannot send Polaris bearer headers. The callback is protected by the OAuth state record, which is signed, expiring, single-use, principal-bound, and organization-bound.

## Out of Scope

This hardening branch updates ORM metadata and query enforcement only. Alembic migrations and production data backfills remain a later Database Gate activity.
