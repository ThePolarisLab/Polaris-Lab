# Motive Authentication and Permissions

## Confirmed

- Mor Logistics has access to Motive API keys through the Motive Developers portal.
- Initial Polaris authentication method is API key.
- Motive API-key requests use the `X-API-Key` header.
- A temporary Internal test-mode key may be used only for limited read-only development verification.
- The production credential is expected to replace the temporary key through secure configuration without code changes.
- OAuth 2.0 is supported by Motive, but OAuth is out of scope for Track 4C.1A.

## Required Secret Handling

- Do not place the API key in source, tests, fixtures, docs, GitHub Actions, PR text, comments, or logs.
- Do not ask for the key in chat or PR comments.
- Read the temporary key only from `MOTIVE_API_KEY` or encrypted organization-scoped credential storage.
- If the Internal key is ever exposed outside the Motive portal or secure runtime configuration, rotate it before use.

## Confirmed Endpoint and Scope Surface

| Resource | Endpoint | Scope / Permission | Track 4C.1A Status |
| --- | --- | --- | --- |
| Vehicles | `GET /v1/vehicles` | `vehicles.read` | Used only for `per_page=1&page_no=1` verification |
| Vehicle utilization | `GET /v1/vehicle_utilization` | `utilization.vehicle_utilization` | Persistence contract only |
| Driver utilization | `GET /v2/driver_utilization` | `utilization.driver_utilization` | Persistence contract only |
| IFTA summary | `GET /v1/ifta/summary` | `ifta_reports.summary` | Persistence contract only |
| Drivers | full list-users contract unresolved | `users.read` appears in docs | Internal identity contract only; no endpoint implementation |

## Verification Request

```text
GET https://api.gomotive.com/v1/vehicles?per_page=1&page_no=1
Accept: application/json
X-API-Key: loaded from encrypted credential storage
```

The raw provider response is not exposed through executive APIs and is not persisted as broad sync data.

## Rate Limits

Motive's exact production rate-limit contract remains unresolved. Future client work must respect `Retry-After` when present. On undocumented `429`, Polaris must stop the current operation, record `rate_limited`, preserve checkpoints, and avoid guessing retry timing.
