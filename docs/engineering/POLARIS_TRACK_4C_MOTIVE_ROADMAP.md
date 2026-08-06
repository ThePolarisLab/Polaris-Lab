# Polaris Track 4C: Motive Roadmap

## 4C.1E: Company API Key Production Foundation

- Keep `chief-of-staff/` as the only production runtime.
- Replace active Motive OAuth production behavior with Company API Key authentication for Mor Logistics' single-company server-to-server integration.
- Read the production key only from secure backend configuration: `MOTIVE_API_KEY`.
- Retain tenant-owned Motive foundation tables, sync history, checkpoints, normalized internal contracts, organization isolation, idempotency constraints, safe status APIs, frontend connector status, System Health mapping, Evidence mapping, and safe logging controls.
- Use limited read-only verification only: `GET /v1/vehicles?per_page=1&page_no=1`.
- Disable active OAuth connect/callback behavior while retaining deployed OAuth schema unless cleanup is separately reviewed.

## 4C.1F: Provider Contract Completion and Sync Design

Before broad sync is implemented, Polaris must complete design and verification for:

- driver filtering based on real provider role fields observed in sanitized provider data or official documentation
- checkpoint advancement after durable persistence for each resource
- pagination behavior for each resource beyond the confirmed users contract
- production-safe batching and incremental date ranges
- webhook authentication/signature contract
- production evidence certification criteria

## Confirmed Provider Inputs

Motive support confirmed the production Company API Key path, required endpoints, users pagination (`per_page` maximum 100, one-based `page_no`, `pagination.total`), and rate-limit guidance: handle `429`, honor `Retry-After` when present, use exponential backoff with jitter, avoid immediate retry loops, avoid excessive concurrency, and use pagination, caching, batching, incremental ranges, and multi-ID requests where supported.

## Later Tracks

- broad synchronization and scheduled reconciliation
- webhooks with delivery audit trail and dead-letter handling
- executive fleet KPIs
- frontend fleet dashboard
- HOS, safety, DVIR, fault codes, trips, maintenance, and fuel purchases
- future multi-tenant OAuth architecture if Polaris becomes a multi-company or App Marketplace integration
