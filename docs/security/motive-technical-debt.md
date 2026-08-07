# Motive Technical Debt and Deferred Scope

## Accepted for Track 4C.1E

| Item | Status | Required Before |
| --- | --- | --- |
| Company API Key production auth for Mor Logistics | Selected | Deploy verification |
| API key source | Secure backend env `MOTIVE_API_KEY` | Any live provider call |
| Exact Motive numeric rate-limit quotas/windows | Not provided | Do not invent; broad sync must remain bounded |
| `Retry-After` handling | Confirmed required | Any retryable 429 handling |
| Users pagination | Confirmed | User/driver sync design |
| Driver role filtering | Deferred until real provider role fields are observed or documented | Driver persistence from provider |
| Token revocation endpoint contract | OAuth-only/deferred | Future OAuth architecture |
| Webhook authentication/signature contract | Deferred | Webhook implementation |
| Checkpoint advancement with durable provider records | Foundation only | Broad sync |

## Rules

- Do not add Motive persistence without `organization_id` and `organization_slug`.
- Do not query Motive tenant-owned data without principal-derived organization filtering.
- Do not log or return `MOTIVE_API_KEY`, `X-API-Key` values, request header dictionaries containing secrets, authorization headers, client secrets, authorization codes, access tokens, refresh tokens, or OAuth state values.
- Do not infer Motive numeric quotas or reset windows.
- Honor `Retry-After` when present and use bounded exponential backoff with jitter for retryable 429/5xx/transport failures.
- Do not retry 401 or 403 as transient failures.
- Do not write Motive data into `trucks`, Outlook, or QuickBooks tables.
- Do not invent driver role names.
- Do not reactivate OAuth production behavior without a new architecture decision.
- Do not implement broad sync, webhooks, or executive KPIs in the API-key foundation PR.
