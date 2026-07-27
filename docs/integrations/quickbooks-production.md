# QuickBooks Online production adapter

The Hermes QuickBooks connector can use `IntuitQuickBooksApiClient` for read-only production synchronization. The client refreshes OAuth access tokens, verifies the exact QuickBooks company identity, paginates entity queries, reads financial reports, retries transient failures, and exposes a secret-free verification status.

## Security boundary

No Intuit client secret, access token, refresh token, or realm ID may be committed to source control, written to logs, included in Hermes evidence, or returned by an API response. Polaris receives only a credential reference such as:

```text
secret://polaris/quickbooks/mor-logistics-production
```

The application must provide a `QuickBooksCredentialResolver` backed by the deployment secret manager. The resolved object contains `clientId`, `clientSecret`, `refreshToken`, and `realmId` in memory only.

## Required deployment configuration

Configure these values in the deployment secret manager, not in GitHub variables containing plaintext secrets:

- Intuit OAuth client ID
- Intuit OAuth client secret
- Current refresh token
- QuickBooks realm/company ID
- Credential reference used by the connector
- Expected company name: `MOR LOGISTICS MANITOBA LIMITED`

Non-secret runtime configuration may include:

- API base URL, default `https://quickbooks.api.intuit.com`
- OAuth token URL, default `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`
- QuickBooks minor version, default `75`
- retry attempt and backoff settings

## Intuit operator setup

1. Configure the production redirect URI in the Intuit developer application.
2. Complete initial authorization using an administrator of the correct QuickBooks company.
3. Store the returned refresh token and realm ID in the secret manager.
4. Configure Polaris with the credential reference only.
5. Start the connector and confirm that authentication resolves exactly to `MOR LOGISTICS MANITOBA LIMITED`.
6. Run a read-only smoke synchronization for company information, accounts, open invoices, and the Profit and Loss report.
7. Confirm System Health reports the connected company without showing any credential material.

## Supported resources

- company information
- customers
- vendors
- accounts
- invoices
- payments
- bills
- purchases
- journal entries

Incremental entity reads use `MetaData.LastUpdatedTime` and Hermes checkpoints. Query pages use Intuit `STARTPOSITION` and `MAXRESULTS` semantics.

## Supported reports

- Profit and Loss
- Balance Sheet
- Cash Flow
- Aged Receivables
- Aged Payables

## Verification status

`getVerificationStatus()` intentionally returns only:

- whether an in-memory authenticated session exists
- verified company name
- last successful request time
- a constant assertion that secrets are not exposed

It never returns credential values, OAuth tokens, or the realm ID.

## Production smoke test rules

Production verification must remain read-only. Unit and integration tests must use mocked HTTP responses or an Intuit sandbox. Do not create, update, void, or delete QuickBooks records as part of connector verification.

## Rotation and disconnect

Intuit may rotate refresh tokens. The resolver's durable secret storage must be updated by the deployment integration whenever a newly issued refresh token is persisted. Calling `disconnect()` clears all credential and token material held by the client process. Remote revocation remains an explicit operator action until a secret-manager persistence/revocation service is wired into the deployment runtime.
