# Polaris Security and Database Architecture

Status date: 2026-07-29

## Boundary

`AuthenticatedPrincipal` is the boundary object for protected HTTP requests. It contains the authenticated identity, active membership, role permissions, and `organization_id` selected by `X-Polaris-Organization`.

```mermaid
flowchart LR
    Client[Client request] --> Headers[Bearer token + X-Polaris-Organization]
    Headers --> Principal[get_principal]
    Principal --> Membership[Identity + active organization membership]
    Membership --> Permission[require_permission]
    Permission --> Handler[Route handler]
    Handler --> Query[Tenant-owned query filtered by principal.organization_id]
```

## Request Rules

1. Route handlers derive organization context only from `AuthenticatedPrincipal.organization_id`.
2. Tenant-owned service methods accept `organization_id` explicitly.
3. Tenant-owned SQLAlchemy models carry `organization_id` foreign keys.
4. Mutations require write permissions; reads require read permissions.
5. Platform-wide organization administration requires `platform.admin`.

## Database Lifecycle Boundary

Phase 2 moves schema ownership from runtime metadata creation to Alembic migrations.

```mermaid
flowchart LR
    Backup[Verified backup] --> Validate[validate_schema]
    Validate --> Upgrade[alembic upgrade head]
    Upgrade --> Current[alembic current]
    Current --> Startup[FastAPI startup]
    Startup --> Guard[assert database at Alembic head in staging/production]
```

Staging and production never call `Base.metadata.create_all`. The application must start only after migrations have been applied. Development and test may bootstrap isolated schemas explicitly through `POLARIS_AUTO_CREATE_SCHEMA`.

## QuickBooks Architecture

QuickBooks is tenant-sensitive because OAuth credentials and financial cache records grant access to accounting data.

```mermaid
flowchart LR
    User[Connector manager] --> Authorize[/authorize]
    Authorize --> State[Signed OAuth state: org + identity + expiry]
    State --> Callback[/callback]
    Callback --> Atomic[Atomic consume where unused and unexpired]
    Atomic --> Credential[Credential stored by organization_id]
    Credential --> Financial[Financial reads/sync/status scoped by organization_id]
```

The callback remains public at the HTTP layer, but the state record is the authorization artifact. State consumption uses an atomic conditional update so concurrent callbacks cannot both succeed.

## Permission Split

- Read-only surfaces use `*.read` permissions.
- Mutating surfaces use `*.write` permissions.
- Legacy `*.manage` names remain aliases only for compatibility.
- Financial operations use `financial.read` and `financial.write`, not generic connector permissions.

## Data Ownership

The authoritative ownership inventory is `docs/security/tenant-isolation.md`. Database adoption and tenant backfill rules live in `docs/database/database-lifecycle.md` and `docs/database/tenant-backfill-plan.md`.
