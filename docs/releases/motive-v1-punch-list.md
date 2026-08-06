# Motive v1 / v1.1 Punch List

## v1 Foundation

- Company API Key is the selected Motive production authentication architecture for Mor Logistics' internal server-to-server integration.
- Backend configuration uses secure Render environment variable `MOTIVE_API_KEY`.
- The Motive request header is `X-API-Key: <secret>` and is constructed only at the HTTP boundary.
- Motive status APIs return metadata only and never expose the key, request headers, tokens, client secrets, OAuth state, or authorization headers.
- Frontend connector card shows administrator-managed configuration and never accepts or displays the key.
- Limited verification uses `GET /v1/vehicles?per_page=1&page_no=1` with at most one record read.
- System Health is Healthy only after successful API-key verification.
- Evidence is Available only after successful verification and does not claim broad ingestion.
- Existing OAuth runtime routes are disabled for active production behavior.
- OAuth schema is retained unless cleanup receives a separate migration safety review.
- No broad sync, KPIs, webhooks, or production certification claims.

## v1.1 Candidate Work

- Complete broad sync design for vehicles, users, vehicle utilization, driver utilization, and IFTA summary.
- Define driver filtering only from real provider role fields observed in sanitized production responses or official documentation.
- Implement durable resource sync with checkpoint advancement only after successful persistence.
- Add scheduled reconciliation with bounded retry, `Retry-After`, exponential backoff with jitter, low concurrency, batching, caching, and incremental date ranges.
- Add webhook ingestion only after signature/authentication requirements are verified.
- Add production evidence certification criteria.

## Deferred

HOS, safety, DVIR, fault codes, trips, maintenance, fuel purchases, webhooks, executive fleet KPIs, frontend fleet dashboard, and future multi-tenant OAuth architecture remain out of scope for Track 4C.1E.
