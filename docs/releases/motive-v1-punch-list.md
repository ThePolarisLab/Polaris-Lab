# Motive v1 / v1.1 Punch List

## v1 Foundation

- API-key credential storage is encrypted and organization-scoped.
- Motive status APIs return metadata only and never expose secrets.
- Limited verification uses `GET /v1/vehicles` with `per_page=1&page_no=1`.
- No broad sync, KPIs, frontend, webhooks, or production certification claims.

## v1.1 Candidate Work

- Complete Motive support escalation for rate limits and driver-list contract.
- Replace temporary Internal test-mode credential with approved production credential through secure configuration.
- Implement durable resource sync only after provider contract gaps are closed.
- Add scheduled reconciliation with conservative retry behavior.
- Add webhook ingestion only after signature/authentication requirements are verified.

## Deferred

HOS, safety, DVIR, fault codes, trips, maintenance, fuel purchases, webhooks, executive fleet KPIs, and frontend fleet dashboard remain out of scope for Track 4C.1A.
