# PGE-008 — API Contract Inventory

**Status:** Baseline inventory  
**Date:** 2026-07-26

## Purpose

This document records the operational HTTP boundary used by the Chief of Staff frontend and the broader backend router surface. It prevents frontend components from depending on undocumented runtime assumptions and establishes where future versioning work must occur.

## Frontend-consumed contracts

| Consumer | Method | Path | Purpose | Client |
|---|---:|---|---|---|
| Executive Dashboard | GET | `/dashboard/executive?user_name={workspaceUser}` | Executive brief, status, priorities, and recommendation | `apiClient.get` |
| Executive Dashboard | POST | `/team-notes` | Create an executive action/team note | `apiClient.post` |
| Builder Console | GET | `/health` | Runtime and database readiness | `apiClient.get` |
| Builder Console | GET | `/system/info` | Service/runtime information | `apiClient.get` |
| Builder Console | GET | `/system/api-version` | API compatibility/version metadata | `apiClient.get` |

## Registered backend router families

The FastAPI application registers the following router families in `chief-of-staff/backend/app/main.py`:

- company
- truck
- memory
- chat
- missions
- relationships
- memory search
- reasoning
- team notes
- dashboard
- GitHub engine
- code understanding
- refactoring
- work context
- system
- connectors
- events
- organizations
- identity
- authentication

The generated FastAPI OpenAPI document is the machine-readable source of truth for individual endpoint schemas. This inventory is the architectural index and must remain synchronized with frontend usage.

## Contract rules

1. React components use `apiClient`; direct component-level `fetch()` calls are prohibited.
2. API base URLs come only from `runtimeConfig`.
3. User and organization identity come from workspace context, never fixed source literals.
4. New breaking contracts require an explicit versioning decision and migration note.
5. Error responses must be surfaced through the centralized client so components receive consistent `Error` instances.
6. Connector and intelligence-domain integration occurs through documented HTTP contracts or explicit adapters, not cross-runtime internal imports.
7. External-system mutation endpoints require authorization, auditability, and a separate production-readiness review.

## Python/TypeScript integration boundary

- `chief-of-staff/backend` is the operational FastAPI authority.
- `chief-of-staff/frontend` is an HTTP client of that authority.
- `src` contains TypeScript intelligence domains and remains independently tested.
- TypeScript capabilities enter the operational application only through an explicit adapter, event contract, or versioned service endpoint.

## Verification

CI must run:

```bash
cd chief-of-staff/backend && pytest
cd chief-of-staff/frontend && npm test && npm run build
npm test
```

Any frontend contract addition must update this inventory in the same pull request.
