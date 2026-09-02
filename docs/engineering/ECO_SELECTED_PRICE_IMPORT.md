# Selected historical Eco price import

## Purpose

Invoice U9165021 covers August 23–29, 2026. Read-only inspection found only an
August 30 Eco USD price run stored; the preview correctly refused future prices.
Outlook search found pricing emails for all seven transaction dates. Those PDFs
have not yet been validated or imported as part of this enhancement.

## API

`POST /api/v1/fuel/eco/prices/import-outlook-selected`

JSON body: `message_id` (exact Outlook message ID), `currency` (`CAD` or `USD`),
`effective_date` (`YYYY-MM-DD`). One explicitly selected source per request.
Requires existing bearer/organization authentication and ORGANIZATION_WRITE.
Tenant credentials and company come from the authenticated organization, never
from caller-supplied company or tenant fields.

Dates must be today or within the previous 90 calendar days (UTC). No latest
fallback, range loop, scheduler or mailbox write is provided. Existing latest
import behavior is unchanged.

## Source safety

The message must belong to a configured Eco source folder in the authenticated
mailbox. Existing trusted sender, company, currency and attachment-name checks
apply. Exactly one matching non-inline PDF is required; incomplete attachment
pagination fails closed. Received timestamp must exist. Subject, filename and
PDF effective date must agree with the requested date; PDF currency and company
must agree too. Validation occurs before the existing durable importer runs,
including before replay lookup. Errors are sanitized.

The existing importer preserves supplier strings, SHA-256, message/attachment
IDs, received timestamp and tenant-scoped exact-file replay protection. An import
adds evidence; it is not a read-only database operation. Outlook itself remains
read-only. Failed prevalidation does not create evidence. Application status and
error_category must be checked even when HTTP status is 200.

## Controlled production procedure after review and deployment

1. Validate the seven USD pricing attachments for August 23–29 against their
   subjects, filenames and source contents. Do not substitute August 30.
2. Use the explicitly approved message ID and date for each individual request.
   Stop on any unexpected response; do not blindly retry a partially completed run.
3. Verify stored row counts, source provenance and replay behavior. No invoice
   re-import or direct SQL evidence insertion is required.
4. Rerun the read-only invoice price preview. Missing station/product matches
   and arithmetic anomalies remain unresolved; importing dates is not proof of
   full price reconciliation or a confirmed overcharge.

No production imports are executed by this PR. Human merge approval and deployed
endpoint verification remain required before the approved historical import.
