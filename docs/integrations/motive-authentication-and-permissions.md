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

## Production Hosts

- Frontend: `https://polaris-executive.onrender.com`
- Backend API: `https://polaris-executive-api.onrender.com`

The OAuth callback is a FastAPI backend route. Do not configure the Motive callback on the frontend host.

## Runtime Configuration

Use environment variables only:

- `MOTIVE_CLIENT_ID`
- `MOTIVE_CLIENT_SECRET`
- `MOTIVE_REDIRECT_URI`
- `POLARIS_FRONTEND_URL`

Render backend environment values:

```text
MOTIVE_REDIRECT_URI=https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback
POLARIS_FRONTEND_URL=https://polaris-executive.onrender.com
```

## Motive Developer Portal

The Success Redirect URI in the Motive Developer Portal must be exactly:

```text
https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback
```

Exact match is required. Do not add a trailing slash and do not use the frontend host.

## Required Secret Handling

- Do not place Motive client secret values, authorization codes, access tokens, refresh tokens, OAuth state values, or authorization headers in source, tests, fixtures, docs, GitHub Actions, PR text, comments, or logs.
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

## Authorization and Callback Flow

```text
GET https://gomotive.com/oauth/authorize
  ?client_id=<configured client id>
  &redirect_uri=https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback
  &response_type=code
  &scope=companies.read users.read vehicles.read utilization.vehicle_utilization utilization.driver_utilization ifta_reports.summary
  &state=<one-use state>
```

The token exchange reuses the exact redirect URI stored with the OAuth state:

```text
POST https://gomotive.com/oauth/token
grant_type=authorization_code
redirect_uri=https://polaris-executive-api.onrender.com/api/v1/motive/oauth/callback
```

After callback processing, users return to:

```text
https://polaris-executive.onrender.com/#executive/connectors?motive=connected_unverified
```

Safe error and denied redirects use the same hash route with `motive=error` or `motive=denied`.

## Verification Request

```text
GET https://api.gomotive.com/v1/companies
Accept: application/json
Authorization: Bearer <access token>
```

The raw provider response is not exposed through executive APIs and is not persisted as broad sync data.

## Rate Limits

Motive's exact production rate-limit contract remains unresolved. Future client work must respect `Retry-After` when present. On undocumented `429`, Polaris must stop the current operation, record `rate_limited`, preserve checkpoints, and avoid guessing retry timing.
