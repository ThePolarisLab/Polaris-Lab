# Phase 3B Production Authentication Bootstrap

Status: Draft PR scope  
Runtime target: Render PostgreSQL-backed production/staging

## Purpose

Phase 3B adds the minimum secure production authentication path needed for the internal Polaris launch. It does not re-enable `/api/v1/auth/local/token` in production and does not start QuickBooks OAuth automatically.

## Fixed Bootstrap Target

The one-time bootstrap creates exactly one founding tenant and owner identity:

| Field | Value |
|---|---|
| Organization ID | `org-mor-logistics` |
| Organization slug | `mor-logistics` |
| Organization display name | `MOR Logistics` |
| Organization legal name | `MOR LOGISTICS MANITOBA LIMITED` |
| Identity ID | `mor-admin` |
| Membership role | `owner` |

The administrator email is not committed. It must come from `POLARIS_BOOTSTRAP_ADMIN_EMAIL`.

## Required Render Variables

Set these on `polaris-executive-api` before deployment:

```text
POLARIS_ENV=production
DATABASE_URL=<Render PostgreSQL internal database URL>
POLARIS_FRONTEND_URL=https://polaris-executive.onrender.com
POLARIS_CORS_ORIGINS=https://polaris-executive.onrender.com
POLARIS_SESSION_SECRET=<minimum 32 random characters>
POLARIS_ACCESS_TOKEN_TTL_SECONDS=900
POLARIS_REFRESH_TOKEN_TTL_SECONDS=1209600
POLARIS_BOOTSTRAP_ADMIN_EMAIL=<admin email address>
POLARIS_BOOTSTRAP_SECRET=<one-time random value, minimum 32 characters>
```

Keep existing QuickBooks values configured, but do not begin live QuickBooks OAuth until the production admin can sign in.

## Deployment Order

1. Confirm PostgreSQL backup/recovery posture.
2. Deploy this PR branch to a preview or merge-approved environment only after review.
3. Run migrations before start:

```bash
python -m alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

4. Confirm public health:

```bash
curl https://polaris-executive-api.onrender.com/health
```

Expected response:

```json
{"status":"ok"}
```

## One-Time Bootstrap Procedure

From the deployed frontend:

1. Open `https://polaris-executive.onrender.com`.
2. If bootstrap is available, the login page shows `First administrator bootstrap`.
3. Enter the one-time `POLARIS_BOOTSTRAP_SECRET` from Render.
4. Enter a strong administrator password.
5. Submit `Create First Admin`.
6. Remove `POLARIS_BOOTSTRAP_SECRET` from Render immediately after success.
7. Redeploy/restart the backend so the removed secret is no longer present in runtime environment.

The bootstrap endpoint is idempotent for schema/data safety but rejects any second completed bootstrap attempt. It does not expose the secret in responses or logs.

## Login Procedure

1. Sign in with the email from `POLARIS_BOOTSTRAP_ADMIN_EMAIL` and the password created during bootstrap.
2. The frontend receives a short-lived bearer access token plus a rotated refresh token.
3. The frontend sends:

```text
Authorization: Bearer <access-token>
X-Polaris-Organization: org-mor-logistics
```

4. Confirm:

```bash
curl -H "Authorization: Bearer <token>" \
  -H "X-Polaris-Organization: org-mor-logistics" \
  https://polaris-executive-api.onrender.com/api/v1/auth/me
```

The owner role must include connector and financial permissions required to continue QuickBooks verification.

## Session Behavior

- Access tokens are signed with `POLARIS_SESSION_SECRET`.
- Access tokens are short-lived; default TTL is 900 seconds.
- Refresh tokens are random, stored only as SHA-256 hashes, and rotate on refresh.
- Logout revokes the current server-side session.
- Reused refresh tokens are rejected after rotation.
- Login failures are recorded and rate-limited.

## Security Notes

- `/api/v1/auth/local/token` remains disabled in production/staging.
- Passwords are stored only as bcrypt hashes.
- No bootstrap secret, password, access token, or refresh token is returned except the session tokens from successful login/refresh.
- Static frontend bundles must not embed `VITE_POLARIS_ACCESS_TOKEN` or other bearer credentials.
- This is an internal-launch auth mechanism. External identity provider integration remains later release work.

## QuickBooks Gate

Proceed to live QuickBooks verification only after:

- `/health` is green;
- bootstrap has completed;
- `POLARIS_BOOTSTRAP_SECRET` has been removed;
- admin login succeeds through the deployed frontend;
- `/api/v1/auth/me` confirms `identity_id=mor-admin`, `organization_id=org-mor-logistics`, and owner permissions.
