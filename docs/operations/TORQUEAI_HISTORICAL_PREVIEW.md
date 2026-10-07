# TorqueAI historical coverage preview

This operator-only command previews one explicit historical window against current
durable MOR data. It does not backfill data or certify historical completeness.
There is no HTTP/MCP endpoint, scheduler integration, write mode, manifest, claim,
retry mechanism, workbook input, or customer alias input.

## Execution boundary

From `chief-of-staff/backend`, an authorized operator with the existing backend
database and TorqueAI credentials can run:

```sh
python -m app.connectors.torqueai_history_preview --from 2025-06-01 --to 2025-06-07
```

This is an example, not approval to execute against production. Production preview
execution requires a separately approved window. Keep identity-bearing output in
private operational evidence, not public GitHub comments. No new credentials,
Auth0 scopes, grants, configuration values, or permission changes are needed.
Only the configured `mor-logistics` provider and active MOR database tenant are
accepted; the caller cannot select another tenant.

The existing connector performs authenticated GET requests and validates each
response. Preview reuses ingestion window, identity/field and operational/stop
validators. Limits remain seven inclusive days, 100 rows/page, 10 pages and 1,000
rows/window. Changed pagination totals, duplicate composite identities and invalid
provider contracts fail closed. Failures return sanitized codes, never raw payloads
or provider exception messages. No failures are persisted.

## Structural isolation

Preview never calls ingestion persistence, installs enrichment callbacks, creates
an ORM session, or accesses sync-run/claim/checkpoint tables. It owns separate
database connections and transactions, selects scalar columns and always rolls
back. PostgreSQL transactions use REPEATABLE READ / READ ONLY; a connection-level
guard permits only SQLAlchemy SELECT statements. It does not mutate a caller's
pending session or rely on a `dry_run` flag in the write-enabled ingestion path.

Provider calls finish before the reconciliation database snapshot opens. Counts
describe that snapshot, not a reservation or promise of a future write outcome.
Normal scheduled ingestion remains unchanged. This preview creates no durable
backfill progress or rollback evidence and cannot authorize later backfill writes.

## Response contract

- `status`: `success` or `failed`; `mode`: `historical_preview`.
- `request`: exact inclusive `from` / `to` provider request window.
- `provider_records_received`: rows received from successfully parsed pages.
- `validated_records`: complete base and operational validation count; a later
  total-count failure can still report validated rows, but no classifications.
- `would_insert`, `would_update`, `unchanged`: mutually exclusive nonconflicting
  identity counts. Update includes changed base or operational/stop fingerprints,
  or missing durable enrichment. Unchanged excludes observation timestamps that
  normal ingestion would refresh.
- `identity_conflicts`: number of returned identities whose load number has more
  than one order number across current MOR data and this provider response.
  Conflicts take precedence over all other classifications; nothing is merged.
- `identities`: exact provider load/order strings, classification, exact identity
  presence, conflicting order numbers, and missing usable lane-stop indicator.
- `missing_usable_lane_stops`: returned records lacking both literal `Pick Up` and
  `Drop Off` roles with nonblank city, province and country. This is a conservative
  completeness indicator, not proof of a particular lane. No aliases are inferred.
- `pagination`: request page size, pages fetched, provider total, and per-page
  page number, received row count, total and advertised page size.
- `returned_ship_dates`: minimum/maximum parseable ISO ship dates, count outside
  the requested window, and missing/invalid date count.
- `validation_failures`: sanitized error codes; a failed preview is not actionable.
- Explicit false indicators for database/provider writes, checkpoint/claim changes
  and raw provider payload return.

Existing ingestion trims outer order whitespace. Preview instead rejects such
identifiers with `identity_not_exact`, so it never silently presents a normalized
identity as an exact historical match. Internal order text, including VOID prefixes,
punctuation and tabs, remains distinct. Customer names are not identity keys.

## Date semantics and future gates

An echoed provider request window does not establish which business date TorqueAI
filters. Out-of-window ship dates remain in the preview and are counted; missing
or malformed dates remain unknown. Synthetic regression fixtures demonstrate this
reporting only. They establish no live provider selection semantics, historical
coverage, or completeness.

Before any future write-enabled backfill: verify provider date semantics, resolve
identity conflicts, approve exact windows, implement a separate durable progress
ledger and conditional before-image rollback, and demonstrate backup/restore.
Workbook records are reconciliation evidence and must never replace provider truth.
