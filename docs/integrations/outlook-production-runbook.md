# Outlook Production Activation Runbook

Status: Track 4B implementation complete pending operator verification

This runbook connects Microsoft 365 Outlook to Polaris as a read-only, tenant-bound connector. It must not be used to enable sending, replying, forwarding, deleting, moving, marking read, editing flags, editing categories, creating drafts, rules, calendar, contacts, or Teams actions.

## Architecture Boundary

Python FastAPI owns:

- OAuth initiation and callback handling;
- one-use signed OAuth state;
- token encryption and refresh-token rotation;
- Microsoft Graph HTTPS calls;
- synchronization orchestration;
- provider-owned Outlook persistence;
- deterministic classification;
- executive attention read models;
- authenticated API exposure.

Hermes and frontend code consume normalized API results. They do not own live Microsoft credentials or refresh-token rotation.

## Microsoft Entra App Registration

1. Create or select the Microsoft Entra app for Polaris.
2. Configure a web redirect URI:

```text
https://polaris-executive-api.onrender.com/api/v1/outlook/callback
```

3. Add delegated Microsoft Graph permission:

```text
Mail.Read
```

4. Include OpenID Connect/offline scopes in the authorization request:

```text
openid profile email offline_access https://graph.microsoft.com/Mail.Read
```

5. Do not grant `Mail.ReadWrite`, `Mail.Send`, calendar, contacts, Teams, mailbox rule, or application-wide mailbox access in Track 4B.

## Render Environment Variables

Set these on `polaris-executive-api` only. Do not place real values in GitHub.

```text
POLARIS_OUTLOOK_CLIENT_ID=<Microsoft application client ID>
POLARIS_OUTLOOK_CLIENT_SECRET=<Microsoft client secret>
POLARIS_OUTLOOK_REDIRECT_URI=https://polaris-executive-api.onrender.com/api/v1/outlook/callback
POLARIS_OUTLOOK_OAUTH_STATE_SECRET=<random value, at least 32 characters>
POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY=<Fernet key>
POLARIS_OUTLOOK_TENANT=organizations
POLARIS_OUTLOOK_SCOPES=openid profile email offline_access https://graph.microsoft.com/Mail.Read
POLARIS_OUTLOOK_SYNC_FOLDERS=Inbox,Sent Items,Archive
POLARIS_OUTLOOK_INITIAL_LOOKBACK_DAYS=14
POLARIS_OUTLOOK_MAX_BODY_BYTES=12000
POLARIS_OUTLOOK_PAGE_SIZE=50
POLARIS_OUTLOOK_REQUEST_TIMEOUT_SECONDS=20
POLARIS_OUTLOOK_MAX_ATTEMPTS=3
POLARIS_OUTLOOK_RETRY_BASE_SECONDS=0.25
POLARIS_OUTLOOK_FOLLOWUP_THRESHOLD_HOURS=24
```

## Deployment Order

1. Confirm PostgreSQL is persistent and backed up.
2. Deploy the backend with the Outlook migration.
3. Run:

```bash
python -m alembic upgrade head
```

4. Start the API.
5. Confirm `/health` returns `{"status":"ok"}`.
6. Confirm authenticated `/api/v1/outlook/status` returns safe status and no secrets.

## Operator Verification

1. Log into Polaris as the Mor Logistics owner.
2. Open Connector Center.
3. Click Outlook Connect.
4. Complete Microsoft OAuth using the approved mailbox.
5. Confirm `/api/v1/outlook/status` shows:
   - authorized;
   - read-only scopes;
   - connected mailbox;
   - no token values.
6. Run initial sync:

```http
POST /api/v1/outlook/sync?mode=initial
```

7. Verify folders were discovered and only approved folders are sync-enabled.
8. Verify message rows contain evidence fields, classifications, and no raw access/refresh tokens.
9. Run incremental sync:

```http
POST /api/v1/outlook/sync?mode=incremental
```

10. Confirm the folder checkpoint advances only after a successful run.
11. Repeat incremental sync and verify idempotent counts.
12. Review `/api/v1/outlook/attention` for conservative possible follow-up signals.
13. Confirm no send/reply/delete/move/mark-read controls appear in the UI.
14. Confirm logs do not include email bodies, access tokens, refresh tokens, authorization codes, client secrets, or raw Graph responses.

## Privacy and Retention

Track 4B minimizes data by default:

- only `Inbox`, `Sent Items`, and `Archive` are synchronized unless explicitly configured otherwise;
- initial sync uses a bounded lookback window;
- body text is sanitized and capped by `POLARIS_OUTLOOK_MAX_BODY_BYTES`;
- binary attachments are not downloaded or stored;
- attachment metadata only is stored;
- operational logs use organization IDs, counts, status, and safe errors rather than message bodies;
- source removals are recorded without silently destroying prior observations.

Formal retention/deletion policy remains a production governance decision before broader rollout.

## Failure Recovery

- Authorization failure: re-run the Connect flow.
- Refresh failure: connector enters reauthorization-required state; do not delete message evidence automatically.
- Expired checkpoint: run `mode=initial` or `mode=full` only after operator approval and backup.
- Throttling: retry/backoff is bounded by runtime settings; repeated 429s leave checkpoint unchanged.
- Sync failure: inspect `outlook_sync_history`; failed runs do not advance checkpoints.

## Rollback

Application rollback should restore the previously deployed backend/frontend version. Database rollback for Outlook tables is destructive and should not be used in production unless restoring from a verified backup is part of the rollback plan.

Recommended production recovery for data-risk events:

1. stop sync actions;
2. preserve logs and database backup;
3. restore from verified backup if data integrity is affected;
4. redeploy known-good application version;
5. verify `/health`, `/api/v1/outlook/status`, and tenant-scoped reads.

## Production Evidence Checklist

- [ ] Microsoft Entra app configured with read-only delegated permissions.
- [ ] Redirect URI confirmed.
- [ ] Render Outlook variables configured without secrets in source.
- [ ] OAuth connection completed for approved mailbox.
- [ ] Microsoft mailbox identity verified.
- [ ] Initial sync completed.
- [ ] Incremental sync completed.
- [ ] Repeated sync is idempotent.
- [ ] Executive classifications populated.
- [ ] Executive attention view populated.
- [ ] No mail mutation controls or permissions are present.
- [ ] Logs and API responses contain no secrets.
- [ ] Human review approves production activation evidence.
