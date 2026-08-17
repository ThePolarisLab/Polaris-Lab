# Motive Authentication Certification

This gate incorporates Motive API Support's **2026-08-17** written reply
confirming the Company API Key authentication mechanism for Mor Logistics'
server-to-server integration. It performs an exhaustive audit of every
Motive request-header code path in the backend, documents the result, and
adds regression tests. It makes **no** live Motive API call, does **not**
rotate the Motive API key, and does **not** merge.

## Provider Evidence

Motive API Support successfully tested the account Company API Key against
`GET /v1/fuel_purchases` using the `x-api-key: <key>` header. The previously
failing client tests (run outside this codebase, by Motive Support) used
`Authorization: Bearer <key>`, which Motive's server rejects for this
credential type. Therefore:

```
company_api_key_authentication:
  header_name: x-api-key
  scheme: raw API key
  bearer_prefix: false

oauth_authentication:
  scheme: bearer token
  separate flow
  not used for current MOR internal server-to-server integration
```

**The real Motive API key value is never reproduced anywhere in this
codebase** -- not in source, tests, fixtures, docs, logs, commit messages,
or this document. Tests use only the obvious synthetic placeholder
`test-motive-api-key`.

## Audit Method (Section 4)

An exhaustive, repository-wide search was performed for: `Authorization`,
`Bearer`, `x-api-key`, `X-API-Key`, `MOTIVE_API_KEY`, `headers`, request
helper functions, and every Motive resource name (`fuel purchases`,
`vehicles`, `users`, `ifta`, `vehicle utilization`) across `app/`,
`migrations/`, and `tests/` -- not a sample. Every Motive HTTP request-
building function in the backend was individually read and traced to its
`httpx.Client.get(...)` call site.

## Audit Result (Section 4): Answer is B -- `x-api-key`, everywhere, already

Every Motive Company API Key request path already used `X-API-Key`
(HTTP header names are case-insensitive; this is the same header as
`x-api-key`) **before this gate started**. No production request path used
`Authorization: Bearer` for the Company API Key. There is no mixed
behavior and no other/duplicated request helper.

| Module | Function | Header sent |
| --- | --- | --- |
| `app/connectors/motive.py` | `MotiveConnector._request_json` (used by `list_vehicles`, `list_users`, `verify_connection`) | `X-API-Key` |
| `app/connectors/motive_vehicle_utilization_contract.py` | `request_vehicle_utilization_payload` | `X-API-Key` (+ `X-Metric-Units` when applicable) |
| `app/connectors/motive_vehicle_utilization_pagination.py` | `request_vehicle_utilization_page` | `X-API-Key` + `X-Metric-Units` |

All three call sites read the key via the same shared helper,
`app.connectors.motive._api_key()`, which reads `MOTIVE_API_KEY` from
backend environment configuration. Auth logic is centralized, not
duplicated: `motive_vehicle_utilization_contract.py` and
`motive_vehicle_utilization_pagination.py` both import `_api_key` from
`app.connectors.motive` rather than re-implementing key retrieval. The
higher-level bounded-evidence probe
(`app/connectors/motive_vehicle_utilization_evidence.py`) and the
controlled write validator
(`app/motive/vehicle_utilization_controlled_write.py`) both funnel through
these same two request functions rather than building their own headers.

**Fuel purchases and IFTA**: `GET /v1/fuel_purchases` and
`GET /v1/ifta/summary` have no request-building code path anywhere in this
backend yet -- only deferred database tables
(`MotiveIftaSummaryRecord` in `app/models/motive.py`) and an endpoint-name
constant (`MOTIVE_CONFIRMED_ENDPOINTS` includes `/v1/ifta/summary` for
future use) exist. There is no auth-header code to fix for those resources
because no request is ever sent for them today. A new regression test
(`tests/test_motive_authentication_certification.py::test_fuel_purchases_and_ifta_have_no_request_helper_yet`)
guards against a future connector addition silently introducing a second,
un-audited request-header code path.

**No fix was required.** Section 5 of this gate's specification ("if
current requests use Bearer, change to x-api-key") does not apply -- the
codebase was already correct. This document records the audit and adds
regression coverage rather than inventing a change that was not needed.

## OAuth Safety (Section 6)

Polaris has both a Company API Key mode (`app/connectors/motive.py` and its
two request-helper modules above, all X-API-Key) and a separate, currently
**dormant** OAuth credential-storage subsystem
(`app/connectors/motive_credentials.py`, `app/models/motive.py`'s
`MotiveCredential` table with a `token_type` column defaulting to
`"Bearer"`, and migration `202608060001_motive_oauth_foundation.py`).

The architecture cleanly distinguishes the two by credential type:

- **Company API Key** -- `MOTIVE_API_KEY` environment variable, read by
  `app.connectors.motive._api_key()`, sent as `X-API-Key` on every live
  request in this backend today.
- **OAuth** -- `MotiveCredentialStore` encrypts and stores `access_token`,
  `refresh_token`, and `token_type` (default `"Bearer"`) per organization
  in the `motive_credentials` table. `app/motive/fleet_foundation.py`
  explicitly documents this as "OAuth production path disabled." The OAuth
  `/api/v1/motive/connect` and `/api/v1/motive/oauth/callback` routes both
  return `410 Gone` with `error_code: "oauth_disabled"`
  (`app/api/motive.py`).

Critically, `MotiveCredentialStore` is a **pure encrypted-storage layer** --
`inspect.getsource` of the entire module contains no `Authorization` string
and no `x-api-key` string. There is no function anywhere in this codebase
that reads a stored OAuth token and builds an outgoing HTTP header from it.
The two schemes cannot be conflated because the OAuth path never reaches
the point of building a request at all today
(`tests/test_motive_authentication_certification.py::test_no_code_path_builds_an_outgoing_header_from_the_oauth_credential_store`
and
`::test_oauth_credential_store_records_bearer_token_type_as_metadata_only`
prove both facts). Per section 6, credential type is never inferred from
string shape -- it is determined entirely by which of the two disjoint code
paths a caller uses, and only the Company API Key path is ever invoked by
live code today.

Because the architecture already cleanly distinguishes the two, this gate
did **not** need to STOP under section 6.

## Public Contract Endpoint (Section 18)

`GET /api/v1/motive/verification-contract`
(`app/api/motive.py::motive_verification_contract`) now includes:

```json
"company_api_key_authentication": {
  "provider_confirmed": true,
  "header": "x-api-key",
  "bearer_prefix": false,
  "authorization_bearer_used": false,
  "real_secret_exposed": false,
  "current_key_rotation_required_before_production_broad_enablement": true,
  "rotation_status": "DEFERRED_UNTIL_MOTIVE_INTEGRATION_COMPLETION_BY_USER_DECISION"
},
"oauth_authentication": {
  "scheme": "bearer_token",
  "header": "Authorization",
  "bearer_prefix": true,
  "separate_flow": true,
  "used_for_current_mor_internal_server_to_server_integration": false,
  "runtime_enabled": false
}
```

No key value, key prefix, key suffix, key length, email content, or
credential identifier is exposed anywhere in this block or the surrounding
endpoint.

## Key Rotation: Deferred, Not Performed (Sections 3/24)

The current Motive API key was echoed in plaintext by Motive Support in a
support-email reply the user received. **This gate does not touch, rotate,
regenerate, or delete that key anywhere** -- no code, no environment
variable, no secret store. Per the user's explicit decision, rotation is
recorded as required before broad production enablement, but is
intentionally deferred until the Motive integration project is complete:

```
current_key_rotation_required_before_production_broad_enablement = true
rotation_status: DEFERRED_UNTIL_MOTIVE_INTEGRATION_COMPLETION_BY_USER_DECISION
```

## Tests (Section 19)

`tests/test_motive_authentication_certification.py` proves, against
synthetic values only (`test-motive-api-key`), with every provider call
mocked via `httpx.MockTransport` (never live):

- `MotiveConnector.list_vehicles` / `list_users` / `verify_connection` send
  `x-api-key` and never `Authorization`;
- the vehicle-utilization contract request and the paginated-reader request
  both send `x-api-key`, never `Authorization`, and preserve
  `Accept: application/json` and `X-Metric-Units` alongside it;
- fuel purchases / IFTA / driver utilization have no request helper to
  audit yet, and a regression test guards that fact;
- the real (synthetic, in tests) secret never appears in a raised
  connector exception's `str()`, in any captured log record, or in the
  public verification-contract endpoint's response;
- the verification-contract endpoint's new `company_api_key_authentication`
  and `oauth_authentication` blocks have the exact documented shape;
- `MotiveCredentialStore` records OAuth's own `Bearer` `token_type` as
  storage metadata only, never leaks the stored token value, and contains
  no code path that ever builds an outgoing HTTP header.

Existing test files already covered `x-api-key` presence and header
preservation per-endpoint before this gate
(`tests/test_motive_foundation.py`, `tests/test_motive_user_ingestion.py`,
`tests/test_motive_vehicle_utilization_contract.py`,
`tests/test_motive_vehicle_utilization_pagination.py`); this gate's new
file consolidates and extends that coverage into one dedicated,
authentication-focused suite matching the specification's section 19.

## No Live Calls In This Gate

This gate makes **zero** live Motive HTTP calls anywhere -- not during the
audit (static code reading only), not during implementation, and not
during testing. Motive API Support already confirmed the auth mechanism
via their own testing against `GET /v1/fuel_purchases`; this gate does not
replicate that call.
