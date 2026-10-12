# TorqueAI historical backfill control plane

This release stores control/evidence records only. It does not execute historical
backfill, mutate dispatches/stops, expose an operator write command, or apply
rollback. The existing `torqueai_history_preview` command remains read-only and
does not create manifests. PR #333 originally exposed no caller for the internal
library. The disabled-by-default signed certification bridge described below
adds one preview-only API caller; no MCP tool, scheduler task or startup hook
calls the library.

## Coverage semantics and evidence

Provider coverage means `Dispatch.date` in the provider documentation and observed
`orderDate` in responses. It is not a claim that order date is an immutable
creation timestamp. Business analysis may use `shipDate`; retrieval and analytical
date/lane coverage are distinct. Ship, delivery, invoice and stop dates may be
outside a requested provider interval.

Evidence reviewed 2026-10-07 at runtime/main
`dbaa6bd818a7a70f8ee1410044b8d21606d27b86`:

| Provider interval, inclusive | Records | Order dates inside | Ship-date range | Ship dates outside |
| --- | ---: | ---: | --- | ---: |
| 2026-08-25–2026-08-31 | 29 | 29 | 2026-08-25–2026-09-06 | 6 |
| 2026-09-01–2026-09-07 | 22 | 22 | 2026-08-31–2026-09-11 | 6 |

The owner-run sanitized diagnostic reported zero adjacent exact identity overlap,
unchanged database snapshots/checkpoints/claims, and no provider writes. All six
expected September ship-date Manitoba-to-Texas workbook identities appeared in
the August provider interval: their order dates were August 26–27. Workbook
values were reconciliation evidence, never imported as provider truth.

Provenance: provider-supplied `DispatchAPI.pdf`, page 1 (`Dispatch.date` filter)
and page 3 (order/ship/delivery fields), SHA-256
`29cec80453facbff86dbc24031837ed0a279782f309ce520e3b26fb00b5e909c`;
owner-run `torqueai_date_semantics_diagnostic.py` sanitized output. The original
workbook SHA-256 is
`0bf1228499eb33b99393b05df68441db3bd6128da9e6a9bd2b34a52b3846d178`.
These source artifacts remain external historical evidence, not public payloads.

No fixed overlap is justified. Plans accept adjacent inclusive intervals (next
start = previous end + one day), reject overlaps/duplicates, and limit every
window to seven days. Historical completeness remains uncertified. Date moves,
source revisions, endpoint exclusions and unproven earliest provider coverage
could still cause omissions; these tests do not prove multi-page completeness.

## Durable model

Migration `202610070001`, parent `202609120002`, added the original four tables.
The update-review extension adds only `torqueai_backfill_update_evidence` through
forward-only migration `202610110001` (parent `202610070001`). No production
migration or preview is performed while preparing the update-review PR.

- `torqueai_backfill_manifests`: immutable tenant/request-key plan, operator,
  exact code SHA, created timestamp, `dispatch_order_date` semantics and
  database-constrained `preview_only` mode. Status is the per-window ledger;
  manifests do not carry a second potentially contradictory status field.
- `torqueai_backfill_windows`: exact inclusive source interval, state, created,
  preview-start/completion and approval timestamps, reviewer, active preview
  attempt and lease. Exact tenant intervals are database-unique across manifests;
  the planner rejects all tenant interval overlaps under the tenant row lock.
  Repeated previews use the existing window's attempt ledger.
- `torqueai_backfill_attempts`: immutable completed preview evidence, retry key,
  initiator, SHA, start/completion, pagination totals/pages, provider/validated
  counts, projected insert/update/unchanged/conflict counts, missing-stop counts,
  ship-date range and sanitized failure codes. Actual inserted/updated are zero.
  Evidence is content-hashed. Failed/retried attempts remain historical records.
- `torqueai_backfill_identity_evidence`: exact tenant/load/order per attempt,
  classification, quarantine and conflicting order literals, optional complete
  before/after durable bundles with independent integrity fingerprints.

Tenant-qualified foreign keys prevent cross-tenant parent linkage. The service
requires the active MOR organization; no caller-supplied alternative slug exists.
Customer names are not identity keys. Internal separators in order identifiers
are preserved; no aliasing, normalization or resolution is introduced.

## State and retry rules

Window states are `planned`, `previewed`, `approved`, `running`, `completed`,
`failed`, `blocked`. This release can reach only planned, previewed, approved,
failed or blocked; running/completed are reserved for a separately approved
executor and cannot be entered through this library.

Preview attempts are `previewing`, `previewed`, `failed`, `blocked`. While a
preview is active, its window stays planned with an active attempt/30-minute
lease. A successful conflict-free result becomes previewed; conflicts block the
window, and failed validation records failed evidence. Approval requires a
successful result and no quarantined conflict from any prior attempt on that
window; a later preview cannot silently clear historical conflicts. Approval
records human review only; it enables no
execution. Approved windows cannot be re-previewed in this release.

Manifest request-key retries return the original plan only if operator, SHA and
intervals match. Completed preview retries return their evidence without another
provider call. An in-progress retry cannot refetch. A new attempt key is required
after failure. A live claim blocks other attempts; expired attempts are marked
failed and retained. Expired/superseded owners cannot finish a later attempt.
PostgreSQL tenant/window row locks and unique keys serialize claims and plan
creation. There are no automatic retries or scheduled backfill tasks.

## Structural isolation

The service owns SQLAlchemy Core transactions, not a caller ORM session. An SQL
boundary allows INSERT/UPDATE only to the original four control tables, INSERT
only to the new update-review table, and rejects raw SQL
and DELETE. It has no operational persistence callback. Claims are window-local
with namespace `torqueai_historical_preview`; normal scheduled-sync claim and
checkpoint tables are neither read for coordination nor updated.

Provider reads reuse the existing preview validator unchanged: existing auth,
100 rows/page, 10 pages, 1,000 rows/window, echoed interval/pagination validation,
exact identities and normalized stop validation. Its database reads keep their
own SELECT-only/read-only transaction. Ledger writes occur separately after
preview; partial failures cannot publish completed evidence.

## Before-images and conditional rollback

Image recording is an internal evidence-only primitive. It accepts complete
whitelisted durable dispatch/operational/stops bundles, checks tenant and exact
identity linkage, and rejects arbitrary fields/raw payloads. Values must already
be JSON scalars (dates, decimals and timestamps need stable canonical string
representations). Stops must have unique ordered indices. Updates require a
before-image; inserts require prior absence. Conflict/unchanged identities cannot
stage images. Once staged, images/fingerprints are immutable through the service.

These hashes are full-bundle integrity hashes, distinct from existing source
fingerprints. Rollback eligibility requires valid before/after hashes and an
exact full current bundle match to the after-image, including timestamps and
stops. Any later change refuses rollback. Insert eligibility would permit a
future conditional deletion only while the inserted bundle remains unchanged;
update eligibility would permit restoring the intact before-image. No restoration
or deletion implementation exists here. Staged images do not prove a mutation
occurred or authorize rollback.

A future executor must capture before-images and changes atomically, record
actual applied outcomes separately from projected counts, lock/recheck current
images during rollback, fence claims, quarantine same-load/different-order cases,
and preserve source-system authority. Evidence-library checks are not database
permissions against arbitrary administrator SQL.

## Remaining release gates

- Review/merge and additive migration rollout approval remain separate steps.
  Existing database startup gates will require the new Alembic head after rollout.
- Validate migrations and concurrent lease behavior on isolated PostgreSQL before
  any production executor; SQLite regressions and PostgreSQL SQL compilation are
  not a substitute for that drill.
- Strengthen backup/restore evidence before operational updates: the previously
  recorded six-hour recovery window, no snapshots/backup schedule, and unverified
  restore drill remain material risks. Before-images complement backups.
- Confirm complete historical provider intervals, pagination and unresolved
  order revisions. No workbook import or automatic conflict resolution is allowed.
- No Auth0/MCP, lane analytics, normal hourly ingestion, provider limits or
  production configuration changes are part of this release.
- Planned intervals remain reserved even after failure. Splitting/replacing an
  existing interval, resolving quarantine, reopening approval or enabling execution
  requires a separately reviewed evidence-preserving transition; none is exposed
  in this foundation. Initial intervals should be sized using read-only preview.
# Signed production preview certification bridge

Render Free has no shell or one-off jobs, and operator/GitHub environments do not
hold the TorqueAI or database credentials. A manual GitHub Actions workflow may
therefore trigger one bounded preview through
`POST /api/v1/internal/torqueai/historical-preview-certification`.
This is a preview-only bridge to `BackfillControl`, not a historical write executor.

The bridge reuses `verify_job_signature` and
`POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET`. GitHub Actions is only the signed trigger
authority; Render retains the provider and database credentials. The request
contains only `date_from` and `date_to`. MOR is resolved on the server; pagination
remains 100/page, ten pages, 1,000 records and seven inclusive days per interval.
The server records `RENDER_GIT_COMMIT`; missing deployment identity fails closed.

`POLARIS_TORQUEAI_HISTORICAL_PREVIEW_CERTIFICATION_ENABLED` is unset/false by
default. An operator must manually set it to `true` on Render for controlled
certification, then disable it afterward. This PR does not enable it. Existing
GitHub `POLARIS_PRODUCTION_API_URL` and HMAC secret configuration is reused; no
TorqueAI/database credentials belong in Actions. There is no automatic schedule.

The first live certification used **2026-08-25 through 2026-08-31**. That interval
is now reserved and must not be dispatched again through the certification bridge.
Provider retrieval means
`Dispatch.date` / observed `orderDate`, not `shipDate`; September ship dates can
appear in the August response. An order date is not certified as an immutable
creation timestamp. No overlap, source cleanup, aliases or workbook imports are
introduced. Retrieval coverage and analytical ship-date/lane coverage stay distinct.

The certification uses a separate database pool with a SQL guard permitting only
SELECT and compiled INSERT/UPDATE against the original four control ledger tables,
plus INSERT-only proposed update evidence. It
does not share normal scheduled sessions or claims. A before/after snapshot
streams tenant rows into hashes and returns only aggregate counts/fingerprints
and normal sync-run identifiers/timestamps. The returned `database_writes=false`
means **no operational database writes**; expected control-ledger inserts/updates
are reported separately. No approval, running/completed execution transition,
historical dispatch/stop write or rollback is authorized or implemented here.

A signed duplicate or overlapping interval is refused without another provider
fetch. Stable per-interval request keys and existing tenant reservations serialize
concurrent duplicates; there is no retry. Conflict-free previews remain `previewed`,
quarantined conflicts remain `blocked`, and provider-validation failures remain
`failed`. Unexpected interruption may preserve a partial ledger/30-minute lease;
operators must inspect that evidence before separately authorizing recovery.

If normal state changes during the preview, sync-run hashes and latest run
identifiers/timestamps expose concurrent activity. The isolated SQL boundary proves
this path cannot write those tables, but the bridge conservatively returns
`inconclusive` / non-2xx rather than asserting that another writer explains every
change. Concurrent ledger activity also invalidates exact expected count deltas.
The workflow fails these cases and never retries. No operational mutation is
repaired automatically.

The manual workflow `.github/workflows/torqueai-historical-preview-certification.yml`
signs the exact JSON body, refuses redirects, uses a fixed endpoint and bounded
timeout, and prints only type-checked counts, dates, statuses and safety flags.
Disabled/authentication/request failures do not echo inputs or secrets. No raw
provider/business records or load/order/customer identities are returned.

**Live certification remains incomplete until the merged workflow passes in
production. Historical completeness and write-enabled backfill remain uncertified.**


## Proposed update review evidence (not execution authorization)

The October 8, 2026 live run [37721893570](https://github.com/ThePolarisLab/Polaris-Lab/actions/runs/37721893570)
at `5bd7a2c21768c7aa4b8942069c9af8e677c2d38d` safely previewed 29 records:
27 projected updates and two quarantined conflicts. Both window and attempt
remain blocked. Attempt `4909d0e9-4ee8-4770-a795-8ad1934b21d1` remains immutable;
this extension does not populate it retroactively. Its 27 updates were
identity-safe but lacked durable field-level before/after review evidence.
The unresolved identities `4813 / VOID - ATL-29017` and
`4824 / VOID - 31461-64338` remain quarantined pending authoritative evidence.
No VOID stripping, aliases, load-only matching or status/date heuristics are allowed.

There are four distinct gates:

1. **Identity certification:** one exact tenant/load/order match and no competing
   order pairing for the same load. The existing conflict rule is unchanged.
2. **Proposed update evidence:** a separate insert-only review record for each
   deterministic `would_update`, linked to its manifest, window, attempt, identity
   evidence and durable dispatch row. A completed attempt binds the sorted review
   fingerprints; retries cannot replace them. Conflicts, unchanged records and
   proposed inserts receive no update-review images.
3. **Execution authorization:** no historical writer, scheduler or new approval
   path is provided. Review evidence is not permission to apply a change.
4. **Rollback eligibility:** future design must verify the live row still matches
   the certified applied image, tenant and exact row identity, and recheck under
   a lock. A proposal is not an applied image. No restore/delete function exists.

### Approved minimized image fields

Images contain only these already-persisted dispatch fields:
`provider_load_number`, `provider_order_number`, `status`, `order_date_text`,
`ship_date_text`, `delivery_date_text`, `customer_name`, `dispatcher_name`,
`driver_name`, `carrier_name`, `truck_number`, `trailer_number`, `loaded_miles`.
Decimal miles use the existing ingestion canonical string representation.
The deterministic sorted changed-field list compares normalized before/proposed
values; unchanged fields are excluded. These business values remain in the
restricted durable review ledger, never the certification response or Actions logs.

Separate metadata retains current/proposed dispatch source fingerprints and
current/proposed operational source fingerprints. Operational enrichment changes
are **hash-only**: no billing, total charge, address, coordinate, note, raw provider
payload or deferred field is copied into review images. An operational-only change
can therefore have zero dispatch changed fields but different operational hashes.
This is not full field-level certification or rollback readiness for enrichment
or stops. Those changes require separately approved review design before writes.

Each record has a creation timestamp, code SHA and explicit nonquarantined
`would_update` classification. SHA-256 hashes cover each image and the complete
metadata envelope; the attempt fingerprint binds the review hashes. Validation
rejects altered images, diffs, hashes, tenant/row/attempt linkage and extra fields.
A read-only precondition decision compares the current normalized dispatch image,
row ID, tenant, exact pairing and both source fingerprints with the certified
before state. This excludes observation timestamps, which scheduled sync may
advance without changing normalized business state. It is not a writer.

The SQL application boundaries deny UPDATE/DELETE of the new review table.
Administrator SQL is outside those boundaries; integrity validation detects
out-of-band tampering. Hashes are integrity checks, not signed attestations against
an administrator able to rewrite every related hash and ledger record.

Certification adds only `update_evidence_count`,
`update_evidence_integrity_valid`, `changed_field_count_total`, and
`rollback_preconditions_recorded`. The last flag means the minimized dispatch
precondition evidence is present, not that rollback or execution is authorized.
The manual-only workflow fails closed if evidence is missing or invalid and
prints only type-checked aggregate metadata. Normal ingestion, checkpoint/claim
namespace, scopes, credentials and provider pagination/retry behavior are unchanged.

After merge, additive migration rollout and one separately approved bounded live
certification remain required. Use an unreserved interval; never overwrite the
old blocked attempt. Source/provider truth remains authoritative. Retrieval
coverage remains Dispatch.date/orderDate; analytical ship-date coverage and
historical completeness remain separate and uncertified. Strengthening production
backup/restore evidence remains a prerequisite to operational writes.
