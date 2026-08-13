# ACE GitHub Scheduled Trigger Foundation

Polaris ACE automatic ingestion uses the same Outlook report importer that powers the manual `Import Latest ACE Report` action. Because the Render Blueprint cron service requires billing information, the no-additional-cost scheduling foundation is:

```text
GitHub Actions schedule
-> HMAC-authenticated Polaris backend endpoint
-> configured active organization
-> existing ACE Outlook importer
-> existing ACE reconciliation
-> ace_feed_runs
```

GitHub is only the scheduler and wakeup mechanism. It does not receive production database credentials, Outlook tokens, Microsoft Graph credentials, organization slugs, or shipment data.

## Endpoint

The scheduled workflow calls:

```text
POST /api/v1/internal/ace/daily-feed/run
```

This is a machine-only endpoint. It does not accept organization IDs, organization slugs, job names, shipment values, Outlook credentials, or user session credentials. The backend resolves the target organization from `POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG`.

## HMAC Signature

The endpoint requires:

```text
X-Polaris-Job-Timestamp
X-Polaris-Job-Signature
```

The signature is lowercase hex HMAC-SHA256 using `POLARIS_ACE_CRON_TRIGGER_SECRET`.

Canonical signed value:

```text
HTTP_METHOD_UPPERCASE
REQUEST_PATH
UNIX_TIMESTAMP_SECONDS
SHA256_HEX_OF_REQUEST_BODY
```

The body is empty for the scheduled workflow, so the body digest is the SHA256 digest of empty bytes. The backend rejects missing configuration, missing headers, malformed timestamps, stale/future timestamps outside the five-minute tolerance, malformed signatures, and mismatched signatures.

## Schedule

The GitHub Actions workflow runs daily at:

```text
17 13 * * *
```

GitHub scheduled workflows use cron scheduling on the default branch and run in UTC by default. The non-zero minute intentionally avoids the top-of-hour load window.

Approximate local times:

- Eastern daylight time: 9:17 AM
- Eastern standard time: 8:17 AM
- Central/Winnipeg daylight time: 8:17 AM
- Central/Winnipeg standard time: 7:17 AM

## Render Free Cold Start

The existing Render web service remains the execution environment. Render Free web services can spin down after idle periods and wake on inbound HTTP requests. The GitHub workflow uses a long request timeout and one controlled retry for transient connection or 5xx failures. Duplicate retry remains safe because ACE import idempotency is keyed by `organization_id + source_message_id`.

## Tenant Targeting

The backend fails closed unless `POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG` resolves to exactly one active Polaris organization. The slug is supplied through Render environment configuration and is not committed to source.

## Source And Idempotency

The scheduled trigger reuses the PR #141 source contract:

- subject: `MOR ACE Daily In-Bond Report`
- attachment: `.xlsx`
- worksheet: `Report 1`
- header row: 4
- blank column A allowed
- Penalty Indicator absent and unreported

The existing identities remain authoritative:

- import replay: `organization_id + source_message_id`
- movement replay: `organization_id + inbond_number + bill_of_lading_number`

## Security

Outlook remains delegated read-only `Mail.Read`. The scheduled trigger does not request or require `Mail.ReadWrite` or `Mail.Send`, and it does not move, delete, mark, modify, send, forward, or reply to email.

The workflow does not contain `DATABASE_URL`, Outlook credentials, Microsoft Graph secrets, source organization values, provider message IDs, or shipment data. The backend response contains only safe counts/status.

The job does not store raw email bodies, raw attachments, Graph tokens, provider message IDs in public responses, shipment values in logs, or workbook row dumps.

## Observability

`ace_import_runs` remains the source-message reconciliation record. `ace_feed_runs` records safe feed-check outcomes, including scheduled/manual mode, status category, source-found flag, replay flag, row counts, exception count, and completion time.

## Production Activation

Activation remains incomplete until all of the following are configured after review, merge, and deployment:

- Render backend env: `POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG`
- Render backend env: `POLARIS_ACE_CRON_TRIGGER_SECRET`
- GitHub Actions secret: `POLARIS_ACE_CRON_TRIGGER_SECRET`
- GitHub repository/environment variable: `POLARIS_PRODUCTION_API_URL`

The manual `Import Latest ACE Report` action remains the controlled fallback. Standalone Manifest ingestion, CBP automation, automatic Unauthorized classification, and broader Daily Brief feed-staleness alerts remain deferred.
