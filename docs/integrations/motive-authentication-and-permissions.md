# Motive Authentication and Permissions

## Confirmed

- Mor Logistics has a Motive OAuth 2.0 application with Client ID and Client Secret.
- OAuth 2.0 is the selected Polaris production authentication method.
- The prior API-key design in Draft PR #115 was superseded before merge.
- Motive OAuth authorization URL: `https://gomotive.com/oauth/authorize`.
- Motive OAuth token URL: `https://gomotive.com/oauth/token`.
- Token responses include Bearer access tokens, refresh tokens, and `expires_in`; official docs identify `7200` seconds for issued access tokens.
- Authorization codes expire after 10 minutes per Motive OAuth documentation.
- OAuth refresh uses the same token endpoint with `grant_type=refresh_token`.

## Runtime Configuration

Use environment variables only:

- `MOTIVE_CLIENT_ID`
- `MOTIVE_CLIENT_SECRET`
- `MOTIVE_REDIRECT_URI`

`MOTIVE_REDIRECT_URI` must exactly match the Motive Developer Portal redirect URI. Production should use:

```text
https://<canonical-api-host>/api/v1/motive/callback
```

## Required Secret Handling

- Do not place Motive client secret values, authorization codes, access tokens, refresh tokens, or authorization headers in source, tests, fixtures, docs, GitHub Actions, PR text, comments, or logs.
- Status reads must not decrypt tokens.
- Token decryption is allowed only inside connector operations that explicitly require a provider request.
- Disconnect deletes local encrypted tokens unless Motive revocation is later verified from official documentation.

## Confirmed Endpoint and Scope Surface

| Resource | Endpoint | Scope | Track 4C.1A Status |
| --- | --- | --- | --- |
| Company details | `GET /v1/companies` | `companies.read` | Used for narrow OAuth verification |
| Vehicles | `GET /v1/vehicles` | `vehicles.read` | Persistence contract only |
| Vehicle utilization | `GET /v1/vehicle_utilization` | `utilization.vehicle_utilization` | Persistence contract only |
| Driver utilization | `GET /v2/driver_utilization` | `utilization.driver_utilization` | Persistence contract only |
| IFTA summary | `GET /v1/ifta/summary` | `ifta_reports.summary` | Persistence contract only |
| Drivers | full list-users contract unresolved | `users.read` | Internal identity contract only; no endpoint implementation |

Requested scopes in Track 4C.1A are exactly: `companies.read users.read vehicles.read utilization.vehicle_utilization utilization.driver_utilization ifta_reports.summary`.

## Verification Request

```text
GET https://api.gomotive.com/v1/companies
Accept: application/json
Authorization: Bearer <access token>
```

The raw provider response is not exposed through executive APIs and is not persisted as broad sync data.

## Rate Limits

Motive's exact production rate-limit contract remains unresolved. Future client work must respect `Retry-After` when present. On undocumented `429`, Polaris must stop the current operation, record `rate_limited`, preserve checkpoints, and avoid guessing retry timing.
