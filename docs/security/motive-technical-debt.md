# Motive Technical Debt and Deferred Scope

## Accepted for Track 4C.1A

| Item | Status | Required Before |
| --- | --- | --- |
| Exact Motive rate-limit contract | Unresolved | Broad sync |
| Complete driver-list endpoint contract | Unresolved | Driver persistence from provider |
| Production API approval and final credential | Pending | Production verification and sync |
| Webhook authentication/signature contract | Deferred | Webhook implementation |
| Checkpoint advancement with durable provider records | Foundation only | Broad sync |

## Rules

- Do not add Motive persistence without `organization_id` and `organization_slug`.
- Do not query Motive tenant-owned data without principal-derived organization filtering.
- Do not log or return API keys.
- Do not infer retry windows for `429`.
- Do not write Motive data into `trucks`, Outlook, or QuickBooks tables.
- Do not add undocumented driver endpoints.
