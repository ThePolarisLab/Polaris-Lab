# ACE Render Cron Foundation

Polaris ACE automatic ingestion uses the same Outlook report importer that powers the manual `Import Latest ACE Report` action. The scheduling foundation is a Render Cron Job that executes a direct Python command:

```bash
python -m app.jobs.ace_daily_import
```

The cron job is a separate Render service, not an in-process web scheduler. Render cron expressions are evaluated in UTC, so the Blueprint schedule is configured as UTC and should be adjusted operationally if the expected report delivery time changes.

## Tenant Targeting

The job fails closed unless `POLARIS_ACE_DAILY_IMPORT_ORGANIZATION_SLUG` resolves to exactly one active Polaris organization. The organization is supplied through Render environment configuration, not hard-coded in business logic and not supplied by a public request.

## Source And Idempotency

The job reuses the PR #141 source contract:

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

Outlook remains delegated read-only `Mail.Read`. The cron job does not request or require `Mail.ReadWrite` or `Mail.Send`, and it does not move, delete, mark, modify, send, forward, or reply to email.

The job does not store raw email bodies, raw attachments, Graph tokens, provider message IDs in public responses, shipment values in logs, or workbook row dumps.

## Observability

`ace_import_runs` remains the source-message reconciliation record. `ace_feed_runs` records safe feed-check outcomes, including automatic/manual mode, status category, source-found flag, replay flag, row counts, exception count, and completion time. This allows Polaris to distinguish:

- successful import
- idempotent replay
- no new report yet
- source contract failure
- import failure

Full scheduler UI, Daily Brief feed-staleness alerts, and broader System Health rules remain deferred until the cron foundation is reviewed and deployed.
