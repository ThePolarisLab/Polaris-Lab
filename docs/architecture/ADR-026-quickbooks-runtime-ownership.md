# ADR-026: QuickBooks Runtime Ownership

Date: 2026-07-30  
Status: Accepted for Phase 3A

## Context

Polaris now has two QuickBooks-related implementation surfaces:

- Python FastAPI owns the deployed web API, authenticated organization context, encrypted credential persistence, OAuth routes, financial snapshots, and Render runtime.
- Hermes TypeScript owns a provider-neutral connector/evidence/checkpoint contract and a testable `QuickBooksApiClient` adapter abstraction.

Issue #61 originally described a Hermes production adapter. Since Phase 1 and Phase 2 introduced tenant-bound Python OAuth and encrypted SQLAlchemy storage, allowing both Python and Hermes to refresh tokens and advance checkpoints would create duplicate token ownership and rotation races.

## Decision

For Phase 3A, Python FastAPI is the authoritative production runtime for QuickBooks Online.

Python owns:

- OAuth initiation;
- OAuth callback validation;
- OAuth state binding and consumption;
- token encryption;
- refresh-token rotation;
- credential persistence keyed by `AuthenticatedPrincipal.organization_id`;
- live Intuit HTTPS calls;
- read-only synchronization orchestration;
- company identity verification;
- production verification status;
- tenant-owned financial cache and sync history;
- API exposure to frontend clients.

Hermes owns:

- connector contract definitions;
- evidence/checkpoint semantics;
- mocked/sandbox TypeScript adapter tests;
- future consumption of sanitized Polaris evidence/status.

Hermes does not own production refresh tokens, client secrets, realm IDs, OAuth codes, or refresh-token rotation in Phase 3A.

## Consequences

- There is one durable refresh-token owner: Python SQLAlchemy credential storage.
- `AuthenticatedPrincipal.organization_id` remains the source of truth for every QuickBooks operation.
- QuickBooks credentials are never keyed by environment-wide organization slug.
- Frontend calls protected Polaris APIs and never receives Intuit tokens or realm IDs.
- Hermes remains valuable as a contract/runtime model without becoming a second live credential path.

## Future Work

A future Hermes production bridge may consume sanitized Polaris evidence or call protected Polaris APIs. If Hermes ever needs direct Intuit access, a new ADR must define a secret-manager bridge that does not duplicate Python token rotation or weaken tenant isolation.
