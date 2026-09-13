# Private Polaris MCP operational intelligence

Phase 1 is tool-only, internal, and read-only. ChatGPT calls Polaris `/mcp`,
which calls `app.services.pickup_planning.query_pickup_plan` directly and reads
the durable Polaris database. The existing REST pickup endpoint uses that same
service. The adapter does not call TorqueAI, initiate ingestion, or assign anything.
**ChatGPT does not receive TorqueAI credentials.** No OpenAI API key is required.

## Implementation and current documentation

Official documentation checked September 11–12, 2026 (the former Apps SDK URLs now
redirect to the Plugins documentation):

- [MCP server and deployment](https://developers.openai.com/plugins/build/mcp-server)
- [Tool design](https://developers.openai.com/plugins/plan/tools)
- [Reference: annotations and structured results](https://developers.openai.com/plugins/reference)
- [OAuth authentication](https://developers.openai.com/plugins/build/auth)
- [Connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [Security and privacy](https://developers.openai.com/plugins/guides/security-privacy)
- [Official examples](https://developers.openai.com/plugins/build/examples)
- [Python SDK ASGI integration](https://py.sdk.modelcontextprotocol.io/run/asgi/)

Use the official Python MCP SDK 2.2.0, with its Streamable HTTP transport,
stateless requests and JSON responses. The existing FastAPI lifespan starts and
stops the MCP session manager. There is no separate application, widget, SSE-only
endpoint, custom JSON-RPC implementation, or HTTP loopback to the REST endpoint.
The low-level SDK tool registration provides explicit schemas and sanitized error
contracts. Pydantic is updated to 2.12.5 to satisfy SDK 2.x requirements. HTTPX for
existing connectors stays at its existing version; SDK 2.x uses its own HTTPX2.
The private tool surface contains `get_pickups` and `get_loaded_trailers`;
there are no write tools or generic provider proxy tools.

## Authentication and tenant isolation

Polaris is an OAuth **resource server**, not a new authorization server. Configure
an organization-controlled OAuth 2.1 issuer with authorization code + PKCE S256,
discovery metadata, and a predefined dedicated ChatGPT OAuth client. A static
shared bearer token or a Polaris admin token is not the connection mechanism.

Create the Polaris identity `polaris-chatgpt-readonly` with one active MOR
membership and role `polaris_chatgpt_readonly`. This role has exactly
`operations.pickups.read` and `operations.loaded_trailers.read`, with no connector,
financial, admin, or write permissions. Each request receives only the intersection
of those permissions and its signed OAuth token scopes. A pickup-only token
cannot call the loaded-trailer tool; a loaded-trailer-only token cannot read pickups. Do not give this identity a password, local token, or ordinary
Polaris login. There are no new login or token-issuing routes.

The dedicated OAuth client and explicitly authorized owner's external `sub`
map to this service identity using server configuration. The owner authenticates
at the issuer and consents to this operational read permission. This Phase 1
mapping deliberately supports one approved external subject. Do not configure a
shared unrestricted subject or reuse an admin OAuth client.

Every MCP HTTP request (including initialization, listing and calls) verifies:

1. RS256 signature against **pinned public JWKS**; `kid` must select a configured
   key and `typ` must be `at+jwt`. Private/symmetric verification keys are rejected.
2. Exact issuer and audience, expiry, issued-at, optional not-before, and an
   integer token lifetime no longer than one hour.
3. Exact dedicated `client_id`, approved external `sub`, and required scope.
4. The existing `SecurityService` active identity/membership and permission checks.
5. The configured organization is active, has slug `mor-logistics`, and the
   membership has **exactly** the dedicated restricted role and permissions.

An owner/admin role on the service identity is rejected, not accepted as a
superset. Organization claims and `X-Polaris-Organization` cannot change scope.
`organization_id` is not a tool argument; extra arguments are rejected.
Parent and serialized child records are tenant checked. Query values use bound
SQLAlchemy parameters. Each authentication/query session blocks non-SELECT SQL;
PostgreSQL also receives `SET TRANSACTION READ ONLY`. The handler never commits.
No identity provisioning or dispatch write runs from an MCP request.

Public discovery: `GET /.well-known/oauth-protected-resource/mcp`. A missing or
invalid token returns HTTP 401 with a `WWW-Authenticate` resource-metadata
challenge. Insufficient scope, disallowed client/subject, tenant or membership
access returns 403. Responses and logs omit credentials, claims and exception
details. Host and Origin are restricted to the configured resource's origin;
requests without Origin (normal server clients) are supported.

## Tool contract

Endpoint: **`https://<polaris-backend-host>/mcp`** (exact path `/mcp`, no redirect).
`get_pickups` input schema is generated from
`PickupInput`; the semantic schema below omits generated title/description labels:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["date", "province"],
  "properties": {
    "date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$", "format": "date"},
    "province": {"type": "string", "minLength": 1, "maxLength": 120, "pattern": "\\S"},
    "city": {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 255, "pattern": "\\S"}, {"type": "null"}], "default": null}
  }
}
```

Dates must be real calendar dates. Province/territory names and two-letter postal
abbreviations are accepted case-insensitively. The query matches both stored
forms (`Manitoba` and `MB`) on the **same certified Pick Up stop**. Cities match
case-insensitively after trimming input. Blank locations and control characters
are rejected. REST retains its existing literal province matching behavior.

Annotations: `readOnlyHint: true`, `destructiveHint: false`,
`idempotentHint: true`, `openWorldHint: false`. A bounded private dataset is not
open-world simply because it is remotely hosted. OAuth security metadata names
only `operations.pickups.read`. The Python SDK 2.x standard Tool type preserves
OpenAI's documented `_meta.securitySchemes` compatibility metadata; it strips
nonstandard top-level fields. HTTP resource discovery and authentication are
enforced independently of this descriptive metadata. The tool also advertises
an explicit `outputSchema` for both success and safe error structured results.

Example call arguments:

```json
{"date":"2026-09-11","province":"Manitoba"}
```

Sanitized illustrative `structuredContent` (also returned as JSON text for
compatible clients; no UI metadata or raw provider payload):

```json
{
  "status": "success",
  "source": "polaris_durable_torqueai",
  "as_of": "2026-09-11T21:17:00+00:00",
  "freshness": {
    "basis": "organization_last_successful_sync",
    "status": "recent",
    "requested_window_start": "2026-09-01",
    "requested_window_end": "2026-09-12"
  },
  "request": {"date": "2026-09-11", "province": "Manitoba", "city": null},
  "summary": {"pickup_load_count": 1, "attention_required_count": 1, "missing_driver_count": 1, "missing_truck_count": 0},
  "loads": [{
    "load_number": "EXAMPLE-101",
    "order_number": "EXAMPLE-ORDER",
    "customer": "Example Customer",
    "status": "Dispatched",
    "driver": null,
    "truck": "EXAMPLE-TRUCK",
    "trailer": "EXAMPLE-TRAILER",
    "pickups": [{"city": "Winnipeg", "province": "MB", "country": "Canada", "scheduled": {"is_window": true, "date": "2026-09-11", "date2": null, "time": "08:00", "time2": "09:00"}}],
    "deliveries": [{"city": "Laredo", "province": "TX", "country": "USA", "scheduled": {"is_window": null, "date": "2026-09-12", "date2": null, "time": null, "time2": null}}],
    "attention_flags": ["missing_driver"],
    "last_changed_at": "2026-09-11T20:00:00+00:00"
  }]
}
```

Arrays preserve multiple pickup/drop-off stops and time windows; they are not
silently flattened to the first stop. Load/order numbers are actual durable
identifiers, not invented IDs. Driver assignment is needed for this use case;
dispatcher details, addresses, postal codes, notes, billing, contact details and
raw provider payloads are not returned. Treat every returned text field as
untrusted data, never as tool instructions.

`as_of` is the organization's `last_successful_completed_at`, not response time
or a guarantee of requested-date coverage. Sync windows have provider ingestion
semantics and must not be interpreted as pickup-date coverage. Missing sync
evidence returns null/unknown. Data older than two hours is marked stale but
remains available with the warning; unchanged loads may have old
`last_changed_at` values despite a recent successful sync. Never label an old
row change timestamp as “last synchronized.”

Zero results are success with an empty list, not proof that a stale or incomplete
sync has no pickups. Tool errors use `isError: true` and
`{"status":"error","error":{"code":"..."}}`. Codes include `AUTH_REQUIRED`,
`FORBIDDEN`, `INVALID_DATE`, `INVALID_PROVINCE`, `INVALID_INPUT`, `UNKNOWN_TOOL`,
`RESULT_LIMIT_EXCEEDED`, and `INTERNAL_ERROR`. Queries over 500 loads return
`RESULT_LIMIT_EXCEEDED`; narrow by city rather than treating a partial list as
complete. This limit applies only to MCP. Protocol-level errors remain SDK JSON-RPC errors. No stack
traces or input values are reflected by the tool's validation/error adapter.

## Required production configuration (not applied by this PR)

Keep the feature OFF until all setup and staging checks are complete. No DNS,
Render, database migration, scheduler, provider credential or production secret
change is made by this implementation.

| Environment variable | Required value |
| --- | --- |
| `POLARIS_CHATGPT_MCP_ENABLED` | `false` by default; set `true` only after setup |
| `POLARIS_CHATGPT_RESOURCE_URL` | Canonical `https://<backend-host>/mcp`; also the token audience/resource |
| `POLARIS_CHATGPT_ISSUER` | Exact HTTPS OAuth issuer from its discovery document |
| `POLARIS_CHATGPT_CLIENT_ID` | New predefined OAuth client dedicated to this integration |
| `POLARIS_CHATGPT_SUBJECT` | Issuer's stable subject for the one approved MOR owner |
| `POLARIS_CHATGPT_IDENTITY_ID` | Dedicated active Polaris service identity ID |
| `POLARIS_CHATGPT_ORGANIZATION_ID` | Existing MOR organization ID, with slug `mor-logistics` |
| `POLARIS_CHATGPT_PUBLIC_JWKS` | JSON object `{"keys":[<public RSA JWKs>]}` copied from the issuer's trusted JWKS; no private key fields |

There is no Polaris `CLIENT_SECRET` setting: token issuance and code exchange
belong to the issuer. If the predefined OAuth client uses a secret, configure
it only in the issuer and ChatGPT's connection configuration. Do not paste it
into chat or commit it. Refresh tokens also stay between ChatGPT and the issuer.
Pinned public JWKS avoids network/SSRF in the query path and permits deliberate
key revocation; publish rotations to all Polaris workers before issuer rollover.

Provision the identity once using an authorized backend operator session. This
is an explicit **deployment action**, never an MCP operation. From the backend
directory, run the following Python in a trusted administrative environment
after confirming the target database. It creates only the dedicated identity
and membership, and refuses to create a replacement MOR organization:

```python
from app.database.database import SessionLocal
from app.database.models import register_models
from app.identity.models import Identity, OrganizationMembership
from app.organizations.models import Organization

register_models()
with SessionLocal.begin() as session:
    org = session.query(Organization).filter_by(slug="mor-logistics", status="active").one()
    identity = Identity(email="polaris-chatgpt-readonly@service.invalid", display_name="polaris-chatgpt-readonly")
    session.add(identity)
    session.flush()
    session.add(OrganizationMembership(organization_id=org.id, identity_id=identity.id, role="polaris_chatgpt_readonly", status="active"))
    print("POLARIS_CHATGPT_ORGANIZATION_ID:", org.id)
    print("POLARIS_CHATGPT_IDENTITY_ID:", identity.id)
```

Identity email uniqueness intentionally prevents accidental duplicate runs.
The role is a deployment-managed role, not exposed through the ordinary
membership-creation form. The loaded-trailer extension requires migration
`202609120002`; identity provisioning itself does not need a migration.

Issuer requirements: HTTPS OAuth/OIDC discovery, authorization code flow,
PKCE S256 advertised and enforced, predefined client registration,
`resource` accepted at authorization and token endpoints and reflected in `aud`,
scopes `operations.pickups.read` and `operations.loaded_trailers.read`, and signed JWT access tokens (`typ: at+jwt`,
RS256, `kid`, integer `iat`/`exp`, `iss`, `aud`, `sub`, `client_id`, space-delimited
`scope`). Token lifetime must not exceed 3600 seconds. Do not use an ID token.
Restrict client consent/login to the approved owner. If the chosen issuer uses
opaque tokens or different claim names, it must be configured to this contract
before enabling this route; this PR does not guess an issuer or fake OAuth.

Render/backend requirements: install requirements, use the existing ASGI startup
command with lifespan enabled, serve `/mcp` and the metadata path through HTTPS,
preserve Authorization/Accept/MCP-Protocol-Version headers, disable response
caching, and apply appropriate per-client rate limits at the edge. The configured
host must reach Polaris unchanged; no wildcard Host/Origin allowlist. Existing
CORS does not need to be broadened for server-to-server ChatGPT requests. Protect
access logs from query/body/header capture. Keep the hourly TorqueAI workflow
and its credentials unchanged.

## Surinder: connect Polaris to ChatGPT

1. Have the operator configure the issuer, service identity and environment above
   in staging first. Confirm missing authentication gets 401 and the resource
   metadata URL returns the expected issuer/audience.
2. Open ChatGPT **Settings → Security and login → Developer mode** and turn it on
   (workspace policy must permit it). Go to **ChatGPT Plugins**, select **+**,
   enter the name `Polaris` and a description, then enter the deployed HTTPS
   `/mcp` URL under **Connection**. Configure OAuth authentication with the
   dedicated predefined client ID in the connection's authentication settings.
   Create the connection and review its discovered tools and metadata.
3. Copy the **exact redirect URI displayed by that management page** into the
   issuer's allowed callbacks. Do not guess a callback ID. If the issuer advertises
   and implements RFC 9207 issuer identification in every authorization response,
   current ChatGPT can use its stable callback; otherwise the callback is specific
   to the connection. Configure any client secret directly in the connection UI.
4. Sign in as the configured approved owner and consent to
   `operations.pickups.read` and `operations.loaded_trailers.read`. Keep
   access private to the authorized MOR workspace/owner.
5. Inspect the tool list: `get_pickups` and `get_loaded_trailers`, both read-only.
   Refresh/reconnect the MCP definition after schema changes.
6. In a conversation with Polaris enabled ask “Check tomorrow's pickup in
   Manitoba.” ChatGPT resolves tomorrow in the user's timezone and calls with
   an absolute date. Compare its loads/counts/attention flags with Polaris's REST
   view for that date using the appropriate stored province form. Have it disclose
   stale/unknown freshness and summarize cities, time windows, destinations,
   driver, truck and trailer. Do not infer a timezone for provider time strings.
7. Test another date, a city filter, zero results and an attempted driver assignment.
   No assignment tool exists. After staging verification, configure production
   the same way and enable the feature flag through the normal release process.

End-to-end ChatGPT OAuth linking requires that deployment and the owner's login;
local signed-token tests are not a substitute for that acceptance test.

## Rotate or revoke access

- Rotate OAuth client credentials at the issuer and update ChatGPT's saved client
  configuration; reauthorize. Client-secret rotation alone may leave existing
  access tokens valid until expiry (at most one hour here).
- For routine signing-key rotation, add the new **public** JWK to Polaris's pinned
  set on all workers, roll issuer signing to the matching `kid`, then remove the
  old public key after the last old token expires. For compromised keys remove
  the old public key immediately and restart all workers.
- For immediate access revocation, set the dedicated Polaris identity status to
  `disabled` or membership status to `revoked` using the operator's normal
  administrative process. Membership is checked on every new request, including
  tool listing. Already executing requests may finish.
- Set `POLARIS_CHATGPT_MCP_ENABLED=false` and restart all backend instances to
  remove both new routes. Disable the issuer's dedicated client, revoke its
  grants/refresh tokens, and remove/disconnect the private ChatGPT connection.
- Changing the allowed subject/client configuration and restarting also prevents
  old subject/client tokens from being used. Nothing here rotates TorqueAI keys.

## Local validation

Use Python 3.12 or 3.13 and an isolated test database, never production credentials:

```sh
cd chief-of-staff/backend
python -m pip install -r requirements.txt
POLARIS_ENV=test POLARIS_LOCAL_AUTH_SECRET=test-local-auth-secret-with-enough-length \
  DATABASE_URL=sqlite:///./polaris-test.db PYTHONPATH=. \
  python -m pytest tests/test_chatgpt_mcp.py tests/test_torqueai_pickup_planning.py tests/test_torqueai_scheduled_sync.py -q
python -m pytest -q
python -m compileall -q app/chatgpt_mcp app/services/pickup_planning.py
python -m pip check
```

The MCP tests generate ephemeral RSA keys and an isolated SQLite database, run
the actual SDK transport through FastAPI, and test protocol initialization,
discovery, registration, filters, tenant isolation, authentication, revocation,
error sanitization and write blocking. No real OAuth account or provider is called.
For manual deployed checks use `npx @modelcontextprotocol/inspector@latest` with
Streamable HTTP and the same OAuth settings. Test invalid tokens and inputs as
well as a real authorized call. Verify PostgreSQL read-only transactions in
staging before production enablement.


## Loaded trailer city intelligence

Example question: “How many loaded trailers are in Winnipeg?”

```json
{"city":"Winnipeg","province":"Manitoba","country":"Canada"}
```

`get_loaded_trailers` requires `city` (1–255 characters); `province` and `country`
are optional nullable strings (1–120 characters). Empty/control-character values,
wrong types, and extra fields are rejected. City matching is exact after trimming
and case folding. Province aliases include all Canadian postal abbreviations and
full names (MB/Manitoba, ON/Ontario, etc.); other region strings match literally.
Country aliases include CA/CAN/Canada and US/USA/United States. Omitting a region
can match more than one city of the same name; returned regions disambiguate.
There is no caller-supplied organization, date, URL, radius, or SQL expression.

### Loaded and confirmed definitions

The normalized dispatch status must be exactly **Loaded**, **In Transit**, or
**Picked Up** (case, spaces, underscores and hyphens normalize). Unknown status,
Assigned, Dispatched, nonzero loaded miles, or a trailer assignment alone never
establish loaded state. Terminal/empty status tokens (delivered, complete,
completed, cancelled/canceled, empty, unassigned, unloaded) exclude the record,
including compound statuses. This is a conservative application classification,
not a claim that every provider lifecycle literal has been production-certified.

Confirmation additionally requires all of the following:

- A non-placeholder trailer number and current truck assignment from the latest
  stored dispatch record for that trailer.
- That exact dispatch was observed in a successful TorqueAI sync within 120
  minutes. A recent organization sync does not refresh other retained records.
- One unambiguous tenant-owned Motive vehicle for the truck, with active/in-service
  vehicle status and a fresh collected GPS observation matching the requested city.
  The stored truck number must still match; GPS must not predate the selected
  dispatch change/assignment evidence.
- A fresh identity-checked Motive vehicle lookup whose active current-driver name
  exactly matches the dispatch driver name after trimming and case folding.
- No conflicting stop equipment, multiple current trailers on the same truck,
  future change timestamp, or pickup schedule consisting entirely of future dates.

“Confirmed” is **operational confirmation using the current dispatch truck
assignment**. Motive's authoritative lookup establishes the current *driver*,
not a physical trailer attachment. TorqueAI exposes only driver names, so the
cross-provider check is name correlation, not a shared driver-ID join. This tool
cannot independently prove that the trailer is still coupled or measure cargo.
Evidence explicitly reports `trailer_location_via_dispatch_truck_assignment`.
Do not describe the result as sensor-verified trailer attachment or cargo.

The current TorqueAI model has no actual pickup/delivery timestamps or certified
current-stop marker. Explicit loaded/in-transit status supplies lifecycle evidence;
scheduled dates are never promoted to pickup completion or physical presence.
If real lifecycle/attachment evidence is added later, it can strengthen this rule.

### Location hierarchy and uncertainty

1. Durable Motive city/state + `located_at`, resolved through the unique dispatch
   truck and checked current-driver observation, is `motive_gps`.
2. An actual TorqueAI current stop would be a fallback only with certified actual
   presence and observation time. **No such persisted field exists today**, so
   this version never fabricates `torqueai_current_stop`.
3. A matching scheduled stop without GPS can only create a possible match with
   `location_source=dispatch_inference`, null current city/region/time, and
   `scheduled_stop_only_not_current_location`. It never enters confirmed count.

GPS in another city overrides a matching scheduled stop, even when that GPS is
stale. Stale GPS in the requested city may appear in `uncertain_trailers`.
Missing, future-dated, contradictory, or stale evidence prevents confirmation.
Unknown loaded status likewise remains uncertain when there is a possible city
match. Uncertain candidates are not an inventory of every trailer with unknown
location; a city-related observation or scheduled stop is needed to list one.
Zero confirmed means no qualifying evidence, not proof the physical inventory is
empty. ChatGPT must distinguish these meanings.

The shared assignment thresholds are reused: high confidence through 30 minutes,
medium through 120 minutes, stale above 120. Confirmation checks dispatch last
observation, GPS time, lookup collection time and location collection time;
confidence uses the oldest of these. Future timestamps are invalid, not age zero.
`as_of` is query time, not a promise that every source was refreshed at that time.

Dedupe precedes city and status filtering. Sort by latest `last_changed_at`, then
`first_observed_at`, then database ID for deterministic ties. The latest record
wins; a newer delivered/empty record suppresses an obsolete loaded one. Conflicting
truck/status records tied on change time are uncertain, even though a deterministic
record is selected for display. These
are durable observation/change times, not invented provider lifecycle times.
At most 5,000 dispatch/vehicle rows are examined and 500 trailer results returned;
exceeding either bound produces `RESULT_LIMIT_EXCEEDED`, never a partial count.

### Structured output

The published descriptor contains the complete `inputSchema` and `outputSchema`.
Successful output has `status=success`, `source=polaris_operational_intelligence`,
request echo, query `as_of`, `location_staleness_threshold_minutes`, summary
`confirmed_loaded_trailer_count` / `uncertain_loaded_trailer_count`, `trailers`
and `uncertain_trailers`. Each trailer includes:

- Trailer, load, load status and truck numbers.
- Current city/province/country, location source and `location_observed_at`.
- `dispatch_last_changed_at`, `dispatch_last_observed_at`, `pairing_observed_at`.
- `loaded_state`, confidence, evidence codes and attention flags.

Driver names are used internally for consistency but omitted from this result.
No coordinates, addresses, customer names, provider IDs, raw payloads, VINs,
credentials, billing or free-text stop notes are exposed. Unknown errors are
sanitized. Returned operational strings are data, never instructions.
Annotations are readOnly=true, destructive=false, idempotent=true, openWorld=false:
the tool reads a bounded private dataset with no external actions.

### Durable synchronization and rollout

The user-authorized evidence extension adds `motive_location_observations` and
nullable `torqueai_dispatches.last_observed_at`. Existing rows receive **no false
freshness backfill**. Successful TorqueAI ingestion refreshes last observation
for returned rows even when fingerprints are unchanged, preserving first/changed
times and existing inserted/updated/unchanged accounting.

The independent signed endpoint is:
`POST /api/v1/internal/motive/location-observations/run` with an empty body and
no query parameters. It reuses the Motive job-signature authentication and
server-side scheduled organization resolution, restricted to `mor-logistics`.
MCP OAuth tokens cannot invoke it. It is disabled unless
`POLARIS_MOTIVE_LOCATION_SYNC_ENABLED=true` on the backend.

The sync reads at most 100 known tenant vehicles. Per vehicle it calls the fixed
GET `/v3/vehicle_locations` filtered to that provider ID and the existing GET
`/v1/vehicles/lookup`. It validates envelope, returned vehicle ID/number, coordinate
range and timestamp shape; no arbitrary URLs or fleet IDs are accepted from MCP.
It persists only minimized city/time/current-driver observations. Lookup failures,
missing location or schema mismatches never manufacture confirmation. A failed
refresh marks the signal unavailable; an older overlapping collection cannot
replace a newer observation. Provider retries remain bounded by the existing
connector. Run the trigger serially, as the supplied workflow does.

V3 requires Motive Vehicle Gateway support. Country is derived as Canada only
when the returned state is a recognized Canadian province; unknown countries
remain null. No external geocoder or guessed city boundaries are used.
Official contract: [Motive vehicle locations v3](https://developer-docs.gomotive.com/reference/fetch-a-list-of-all-the-vehicles-and-their-locations-v3).
Production envelope/permissions and name consistency must be checked in staging;
unavailable or unsupported data yields zero confirmed, not a live MCP fallback.

Rollout after PR approval and merge:

1. Apply `alembic upgrade head` before starting code that reads the new fields.
2. Keep existing TorqueAI sync and Motive vehicle ingestion operational. Refresh
   the relevant dispatch window; historical rows outside it remain unconfirmed.
3. Configure backend `POLARIS_MOTIVE_LOCATION_SYNC_ENABLED=true`, existing
   `POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG=mor-logistics`, and the
   existing Motive trigger secret/provider credentials through normal secret
   management. No provider credential is copied into ChatGPT.
4. Set repository variable `POLARIS_MOTIVE_LOCATION_SYNC_ENABLED=true` to enable
   `.github/workflows/motive-location-observations.yml`. It reuses repository
   variable `POLARIS_PRODUCTION_API_URL` and secret
   `POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET`, runs every 15 minutes, and
   supports manual dispatch. GitHub scheduling can be delayed; freshness still
   fails closed. Backend and repository flags are independently required.
5. Grant `operations.loaded_trailers.read` to the existing dedicated OAuth client
   and approved owner. Keep `operations.pickups.read` for pickups. The identity,
   issuer, audience, endpoint, callback and MCP feature flag remain the same.
6. Refresh the existing ChatGPT connection's tool metadata and reauthorize for
   the new scope. A second connection/server is unnecessary. Existing pickup-only
   grants continue to work but cannot call the new tool.
7. Verify a known loaded trailer against dispatch status, timestamps and Motive
   city; also verify stale, contradictory and zero-result examples. Compare
   confirmed and uncertain counts separately. Do not merge or deploy merely
   because synthetic contract tests pass.

No production migration, configuration change, provider sync, or ChatGPT linking
is performed by local tests or by this PR. Disabling the sync flag stops new
observations; old evidence naturally expires. The MCP flag disables both tools. Destructive schema downgrade is intentionally
blocked by the existing database gate; recover through the normal forward
migration/backup process, not by dropping durable evidence.
