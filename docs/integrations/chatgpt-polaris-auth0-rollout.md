# Polaris MCP — Auth0 production rollout

Status: **deployment plan only**. Keep `POLARIS_CHATGPT_MCP_ENABLED=false` until every preflight and acceptance check below passes.

This guide chooses **Auth0 as the first production OAuth issuer** for the private MOR Logistics ChatGPT ↔ Polaris MCP connection. The existing Polaris resource-server implementation remains authoritative and unchanged.

## Why Auth0

Polaris already requires a standards-oriented JWT access token contract:

- RS256 signature and pinned public JWKS;
- JWT header `typ: at+jwt`;
- exact HTTPS issuer and resource audience;
- `sub`, `client_id`, `scope`, integer `iat` and `exp` claims;
- token lifetime no longer than one hour;
- authorization-code login with PKCE handled by the external issuer/client;
- MCP RFC 8707 `resource` semantics.

Auth0's current RFC 9068 access-token profile provides `typ: at+jwt` and the `client_id` claim, and Auth0's Resource Parameter Compatibility Profile supports the MCP `resource` parameter. These match Polaris's existing validation contract without weakening authentication.

References:

- https://auth0.com/docs/secure/tokens/access-tokens/access-token-profiles
- https://auth0.com/ai/docs/mcp/guides/resource-param-compatibility-profile
- https://auth0.com/ai/docs/mcp/get-started/authorization-for-your-mcp-server
- https://developers.openai.com/plugins/build/auth
- https://developers.openai.com/plugins/deploy/connect-chatgpt

## Fixed Polaris resource

Production resource URL / Auth0 API identifier:

```text
https://polaris-executive-api.onrender.com/mcp
```

Do not use the site root, a trailing slash variant, a query string, or another audience. Polaris validates this value exactly.

Required scopes:

```text
operations.pickups.read
operations.loaded_trailers.read
```

No write, connector, financial, admin, or generic proxy scopes belong on this client.

## 1. Create the MOR-owned Auth0 tenant

Use a tenant owned and administered by MOR/Polaris, not a developer's personal tenant. Enable MFA for tenant administrators and keep tenant-administration credentials out of the repository and ChatGPT conversations.

In **Tenant Settings → Advanced**:

1. Enable **Resource Parameter Compatibility Profile**.
2. Use the **IETF / RFC 9068 access-token profile** for the Polaris resource server.
3. Keep signing algorithm **RS256**.

Do not enable opaque access tokens for the Polaris MCP API.

## 2. Register the Polaris MCP API / resource server

Create one Auth0 API whose identifier is exactly:

```text
https://polaris-executive-api.onrender.com/mcp
```

Configure:

- signing algorithm: `RS256`;
- RFC 9068 JWT access-token profile (`at+jwt`);
- access-token lifetime: at most `3600` seconds;
- scopes:
  - `operations.pickups.read`
  - `operations.loaded_trailers.read`

Polaris does not depend on an Auth0 `permissions` claim; the access token must carry the requested OAuth scope string.

## 3. Create a dedicated ChatGPT OAuth application

Create a new application/client only for this connection. Do not reuse MOR's admin, website, Microsoft, or other OAuth clients.

Required behavior:

- authorization-code flow;
- PKCE S256;
- no password grant;
- no client-credentials access to Polaris MCP;
- owner login only for Phase 1;
- requested resource exactly `https://polaris-executive-api.onrender.com/mcp`;
- requested scopes limited to the two Polaris read scopes.

The final callback URI is supplied by ChatGPT when the Polaris connection is created. Add the **exact URI shown by ChatGPT** to Auth0 Allowed Callback URLs. Do not guess or hard-code a callback before that step.

If the client uses a secret, store it only in Auth0 and ChatGPT's connection configuration. Polaris does not need the client secret.

## 4. Validate one Auth0 access token before enabling Polaris

After the client/API are configured, decode a non-production sample access token locally and verify only its public header/claims. Never commit or paste the token itself.

The token must satisfy all of these:

```text
header.alg == RS256
header.typ == at+jwt
header.kid is present
iss == configured Auth0 issuer
aud == https://polaris-executive-api.onrender.com/mcp
sub == the approved owner's stable Auth0 subject
client_id == the dedicated ChatGPT client ID
scope contains operations.pickups.read and/or operations.loaded_trailers.read
exp and iat are integers
0 < exp - iat <= 3600
```

If Auth0 emits `azp` instead of `client_id`, `typ: JWT` instead of `at+jwt`, an opaque token, or another audience, fix Auth0's profile. **Do not loosen Polaris validation to accommodate the wrong token profile.**

## 5. Pin public JWKS

Fetch Auth0's public signing JWKS from the issuer's documented JWKS endpoint in a trusted administrative session. Store only the public RSA JWK set in:

```text
POLARIS_CHATGPT_PUBLIC_JWKS
```

Requirements enforced by Polaris:

- RSA keys only;
- unique `kid`;
- RS256 signing use;
- minimum 2048-bit RSA key;
- no private key parameters.

Plan key rotation deliberately: publish the new public key to Polaris before Auth0 begins signing tokens with it, and remove retired keys after old access tokens have expired.

## 6. Provision the restricted Polaris service identity

Provision exactly one active Polaris identity/membership for this integration using the trusted backend administrative procedure already documented in `chatgpt-polaris-mcp.md`.

Required role:

```text
polaris_chatgpt_readonly
```

That role must remain exactly:

```text
operations.pickups.read
operations.loaded_trailers.read
```

Do not give the identity a password, local login token, owner/admin role, connector permission, financial permission, or write permission.

Record the resulting identity ID and existing MOR organization ID in the deployment secret/configuration store, not in Git.

## 7. Configure Render with the feature still OFF

Set these production environment values first:

```text
POLARIS_CHATGPT_MCP_ENABLED=false
POLARIS_CHATGPT_RESOURCE_URL=https://polaris-executive-api.onrender.com/mcp
POLARIS_CHATGPT_ISSUER=<exact Auth0 HTTPS issuer>
POLARIS_CHATGPT_CLIENT_ID=<dedicated ChatGPT OAuth client ID>
POLARIS_CHATGPT_SUBJECT=<approved owner's stable Auth0 sub>
POLARIS_CHATGPT_IDENTITY_ID=<restricted Polaris identity ID>
POLARIS_CHATGPT_ORGANIZATION_ID=<existing MOR organization ID>
POLARIS_CHATGPT_PUBLIC_JWKS=<public RSA JWKS JSON>
```

Do not place an Auth0 client secret or refresh token in Render for this resource server.

## 8. Pre-enable acceptance checks

With the feature flag still false:

- production normal API remains healthy;
- Motive and TorqueAI scheduled ingestion remain unchanged;
- existing backend/security/database CI is green;
- service identity has exactly the restricted role;
- Auth0 access token matches the contract above;
- resource identifier and audience match exactly;
- public JWKS contains the token's signing `kid`;
- no provider/API credentials are exposed to ChatGPT.

Then enable `POLARIS_CHATGPT_MCP_ENABLED=true` in a controlled deployment.

Immediately verify:

1. `GET /.well-known/oauth-protected-resource/mcp` returns the Polaris resource and Auth0 issuer.
2. Unauthenticated `/mcp` returns 401 with a resource-metadata challenge.
3. Wrong issuer/audience/client/subject fails closed.
4. Pickup-only scope cannot call loaded trailers and vice versa.
5. `tools/list` exposes only `get_pickups` and `get_loaded_trailers`.
6. No write/assignment tool exists.

## 9. Connect ChatGPT

In ChatGPT's current Plugins/connector management UI, create a private Polaris connection using:

```text
https://polaris-executive-api.onrender.com/mcp
```

Use OAuth and the dedicated Auth0 client. Copy the exact callback URI that ChatGPT displays into Auth0 before completing sign-in.

First acceptance questions:

```text
Check tomorrow's pickups in Manitoba.
How many loaded trailers are in Winnipeg right now?
Which loaded trailers in Winnipeg have uncertain or stale location evidence?
```

For loaded trailers, compare the tool output against Polaris evidence rules:

- scheduled destination alone never proves current city;
- fresh Motive GPS for the assigned truck is authoritative over a scheduled stop;
- stale/unavailable GPS is surfaced as uncertainty;
- delivered/empty/terminal trailer assignments do not count;
- explicit loaded/in-transit status is required for confirmation;
- confirmation means operational evidence, not a cargo sensor or physical inspection.

## 10. Rollback

If any authentication, tenant isolation, evidence, or schema issue appears:

1. Set `POLARIS_CHATGPT_MCP_ENABLED=false`.
2. Revoke/disable the dedicated Auth0 client or owner grant if necessary.
3. Disable the restricted Polaris service membership if immediate revocation is required.
4. Leave TorqueAI/Motive ingestion and ordinary Polaris APIs untouched.
5. Diagnose before re-enabling; do not replace OAuth with a static bearer/admin token.

## Production gate

MCP may be enabled only after all of these are true:

- [ ] Post-PR #321 Motive location sync is production-certified.
- [ ] Loaded-trailer intelligence tests are green and evidence semantics reviewed.
- [ ] Auth0 resource profile emits RFC 9068 RS256 `at+jwt` access tokens.
- [ ] RFC 8707 Resource Parameter Compatibility is enabled.
- [ ] Dedicated ChatGPT client exists and is owner-restricted.
- [ ] Restricted Polaris service identity exists with exact read-only permissions.
- [ ] Render environment values are configured with public JWKS only.
- [ ] Unauthorized and wrong-scope tests fail closed in production/staging.
- [ ] ChatGPT connection acceptance tests pass.

Until every box is checked, keep the feature flag OFF.
