# Motive v1 / v1.1 Punch List

## v1 Foundation

- OAuth 2.0 is the selected production authentication architecture.
- OAuth state is organization-scoped, one-use, and expiration-bound.
- OAuth access and refresh token storage is encrypted and organization-scoped.
- Motive status APIs return metadata only and never expose secrets.
- Limited verification uses `GET /v1/companies` with a Bearer access token.
- API-key design was superseded before merge and is not represented in the final migration.
- No broad sync, KPIs, frontend, webhooks, or production certification claims.

## v1.1 Candidate Work

- Complete Motive support escalation for rate limits and driver-list contract.
- Implement durable resource sync only after provider contract gaps are closed.
- Add scheduled reconciliation with conservative retry behavior.
- Add webhook ingestion only after signature/authentication requirements are verified.
- Add remote token revocation only if Motive official documentation confirms the contract.

## Deferred

HOS, safety, DVIR, fault codes, trips, maintenance, fuel purchases, webhooks, executive fleet KPIs, and frontend fleet dashboard remain out of scope for Track 4C.1A.
