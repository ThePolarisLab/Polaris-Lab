# QuickBooks Production API

Scope: Phase 3A read-only QuickBooks Online adapter.

All protected routes require:

```text
Authorization: Bearer <polaris-token>
X-Polaris-Organization: <organization-id>
```

The organization header must match the authenticated membership. QuickBooks credentials, financial cache rows, and sync history are keyed by the authenticated `organization_id`.

## OAuth

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/api/v1/connectors/quickbooks/oauth/authorize-url` | `connector.write` | Returns an Intuit authorization URL after Polaris auth headers are validated. |
| `GET` | `/api/v1/connectors/quickbooks/oauth/authorize` | `connector.write` | Redirect variant for non-browser tooling that can attach auth headers. |
| `GET` | `/api/v1/connectors/quickbooks/oauth/callback` | Public HTTP callback | Protected by signed, persisted, expiring, single-use OAuth state. |
| `DELETE` | `/api/v1/connectors/quickbooks/oauth/connection` | `connector.write` | Attempts provider revocation and deletes only the active organization's credential. |

## Reads

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/api/v1/qbo/company` | `financial.read` | Returns CompanyInfo only after tenant-bound credential refresh. |
| `GET` | `/api/v1/qbo/accounts` | `financial.read` | Returns accounts. |
| `GET` | `/api/v1/qbo/resources/{resource}` | `financial.read` | `customers`, `vendors`, `accounts`, `invoices`, `payments`, `bills`, `purchases`, `journal_entries`. Supports `changed_since`, `cursor`, and `limit`. |
| `GET` | `/api/v1/qbo/reports/profit-loss` | `financial.read` | Supports date range and accounting method. |
| `GET` | `/api/v1/qbo/reports/balance-sheet` | `financial.read` | Supports date range and accounting method. |
| `GET` | `/api/v1/qbo/reports/cash-flow` | `financial.read` | Supports date range and accounting method. |
| `GET` | `/api/v1/qbo/reports/aged-receivables` | `financial.read` | Supports date range and accounting method. |
| `GET` | `/api/v1/qbo/reports/aged-payables` | `financial.read` | Supports date range and accounting method. |

## Sync And Verification

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/api/v1/qbo/sync/status` | `financial.read` | Returns safe tenant-bound sync status and checkpoint metadata. |
| `POST` | `/api/v1/qbo/sync?mode=full` | `financial.write` | Full read-only sync into Polaris financial cache. Writes zero records to QuickBooks. |
| `POST` | `/api/v1/qbo/sync?mode=incremental` | `financial.write` | Incremental read-only sync from the last successful checkpoint where supported. |
| `GET` | `/api/v1/qbo/verification` | `connector.read` | Returns safe connector verification metadata. |
| `POST` | `/api/v1/qbo/verification` | `connector.write` | Actively verifies refresh, CompanyInfo, resource reads, and report reads. |
| `GET` | `/api/v1/qbo/executive-summary` | `financial.read` | Returns dashboard-safe metrics parsed from stored financial snapshots. |

## Response Safety

Responses must not include:

- Intuit access tokens;
- refresh tokens;
- client secrets;
- OAuth authorization codes;
- raw OAuth state;
- token encryption keys;
- full realm IDs;
- raw internal exception traces.

Provider payloads returned by direct financial read routes may contain business financial data and therefore require `financial.read` plus tenant organization context.
