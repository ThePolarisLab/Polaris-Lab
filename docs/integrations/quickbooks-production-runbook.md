# QuickBooks Production Runbook

Target company: `MOR LOGISTICS MANITOBA LIMITED`  
Scope: read-only production verification for Issue #61 / Phase 3A.

## Safety Rules

- Do not commit Intuit credentials, OAuth tokens, authorization codes, realm IDs, or production screenshots containing sensitive financial details.
- Do not run production smoke tests from GitHub Actions.
- Do not create, update, void, delete, or post QuickBooks transactions in this phase.
- Use only authenticated Polaris routes for connector status, verification, sync, and disconnect.
- Public health routes must not expose company identity, realm ID, financial data, or connector configuration.
- Confirm production `DATABASE_URL` points to persistent Render PostgreSQL before OAuth or sync. Do not use `sqlite:////tmp/polaris.db` for live QuickBooks credentials or financial cache.

## Required Render Environment Variables

Set these on the Render web service, not in source control:

```text
POLARIS_ENV=production
DATABASE_URL=<Render PostgreSQL Internal Database URL>
POLARIS_FRONTEND_URL=<deployed Polaris frontend URL>
POLARIS_QBO_ENVIRONMENT=production
POLARIS_QBO_CLIENT_ID=<Intuit production client id>
POLARIS_QBO_CLIENT_SECRET=<Intuit production client secret>
POLARIS_QBO_REDIRECT_URI=https://polaris-executive-api.onrender.com/api/v1/connectors/quickbooks/oauth/callback
POLARIS_QBO_OAUTH_STATE_SECRET=<random 32+ byte secret>
POLARIS_QBO_TOKEN_ENCRYPTION_KEY=<Fernet key>
POLARIS_QBO_EXPECTED_COMPANY_NAME=MOR LOGISTICS MANITOBA LIMITED
POLARIS_QBO_MINOR_VERSION=75
POLARIS_QBO_REQUEST_TIMEOUT_SECONDS=20
POLARIS_QBO_MAX_ATTEMPTS=3
POLARIS_QBO_RETRY_BASE_SECONDS=0.25
```

Also confirm the normal Phase 1 and Phase 2 variables are present: auth secrets, CORS origins, and any deployment-specific allowed origins.

## Intuit Configuration

1. Open the Intuit developer app used by Mor Logistics.
2. Confirm it is a production QuickBooks Online app, not a sandbox-only app.
3. Confirm the redirect URI exactly matches `POLARIS_QBO_REDIRECT_URI`.
4. Confirm accounting read scopes are available.
5. Do not copy production client secrets into GitHub, CI logs, issue comments, or pull request text.

## Preflight Deployment Procedure

1. Confirm the Render service is connected to persistent PostgreSQL with the internal database URL.
2. Confirm the Render start command runs migrations before Uvicorn, or run the equivalent protected migration job before startup:

```bash
python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

3. Confirm `/health` returns `200` with only generic public status.
4. Confirm detailed system and connector health routes require authentication.
5. Confirm `alembic current` reports the repository head revision.
6. Redeploy once and confirm the database state persists.

## Smoke Test Procedure

1. Confirm Render deploy is live, `/health` returns 200, `DATABASE_URL` is persistent PostgreSQL, and migrations are at head.
2. Sign in to Polaris with an identity that has `connector.write`, `connector.read`, `financial.write`, and `financial.read` in the active Mor Logistics organization.
3. Open Connector Center and choose `Connect` for QuickBooks.
4. Complete Intuit OAuth using an authorized user for `MOR LOGISTICS MANITOBA LIMITED`.
5. Confirm Polaris returns to the frontend with `quickbooks=connected`.
6. Open Connector Center again and confirm:
   - authorization status is authorized;
   - verified company is `MOR LOGISTICS MANITOBA LIMITED`;
   - realm status is present without showing the realm ID;
   - no token, client secret, OAuth code, or raw state is visible.
7. Choose `Verify` to run the read-only verification endpoint.
8. Confirm the verification response/status includes safe counts for:
   - CompanyInfo;
   - Customers;
   - Vendors;
   - Accounts;
   - Invoices;
   - Payments;
   - Bills;
   - Purchases;
   - Journal Entries.
9. Confirm report availability for:
   - Profit and Loss;
   - Balance Sheet;
   - Cash Flow;
   - Aged Receivables;
   - Aged Payables.
10. Run one controlled full sync: `POST /api/v1/qbo/sync?mode=full` through the authenticated UI or API client.
11. Run one incremental sync: `POST /api/v1/qbo/sync?mode=incremental`.
12. Confirm the executive financial dashboard shows the latest sync and metrics without raw provider payloads or secrets.
13. Inspect Render logs and confirm no access token, refresh token, authorization code, client secret, full OAuth state, or realm ID appears.
14. Redeploy the service and confirm QuickBooks authorization status, verification metadata, sync history, and Alembic state survive restart.
15. Record evidence in Issue #61, but only check production boxes that were actually verified against the live company.

## Failure Modes

| State | Meaning | Operator action |
|---|---|---|
| `not_configured` | Required QuickBooks environment variables are absent or invalid. | Set Render environment variables and redeploy. |
| `authorization_required` | No tenant-bound credential exists. | Complete OAuth from an authorized Polaris session. |
| `connected_unverified` | Credential exists but company verification has not succeeded. | Run verification. |
| `company_mismatch` | Intuit CompanyInfo did not match the expected Mor Logistics name. | Disconnect immediately, verify Intuit account/company, and reauthorize only with the correct company. |
| `rate_limited` | Intuit returned 429. | Wait and retry later; do not bypass rate limits. |
| `synchronization_failed` | A read-only sync failed after credential and company verification. | Inspect safe error summary and retry after the root cause is resolved. |
| `reauthorization_required` | Refresh token is revoked/expired or cannot refresh. | Disconnect/reconnect through OAuth. |

## Rollback or Disable Procedure

1. Do not attempt to downgrade production data in place.
2. Disable QuickBooks by disconnecting the connector from an authenticated organization administrator account.
3. If app startup or schema compatibility is affected, follow the Database Gate restore-from-verified-backup procedure.
4. If Intuit credentials are suspected compromised, rotate/revoke them in Intuit first, then remove Render environment variables.

## Issue #61 Evidence Checklist

Implementation/CI evidence can be attached from the Phase 3A PR. Production operator evidence must be recorded separately:

- [ ] OAuth app credentials configured outside GitHub
- [ ] Redirect URI confirmed
- [ ] Realm/company ID stored securely by Polaris OAuth credential storage
- [ ] Initial authorization completed
- [ ] Token refresh verified
- [ ] Company identity verified
- [ ] Read-only resource sync verified
- [ ] Financial reports verified
- [ ] Connector health visible in Polaris System Health

Do not close Issue #61 until every checked item has evidence.
