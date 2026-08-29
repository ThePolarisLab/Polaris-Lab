# TorqueAI Automatic Dispatch Sync — Design Gate

Status: **design only**

This document defines the next controlled TorqueAI gate after the certified durable-ingestion, durable-read API, and Dispatch dashboard work. It does **not** enable a scheduler, add a provider call, change production configuration, or alter the Dispatch UI.

## 1. Goal

Automatically reconcile a small recent window of TorqueAI dispatches into Polaris durable storage without requiring a browser user to run the manual ingestion endpoint.

The automatic path must preserve the guarantees already certified for the manual path:

- tenant isolation;
- provider access only from the Polaris backend;
- explicit bounded date windows;
- sequential bounded pagination;
- no TorqueAI provider retries;
- validate all pages before dispatch-row mutation;
- tenant-scoped idempotent insert/update/unchanged behavior;
- provider omission is never interpreted as deletion;
- no raw provider payload persistence;
- no billing, total charge, stops, addresses, coordinates, or other deferred fields;
- no browser-to-TorqueAI access;
- sanitized logs and responses only.

This gate is about **safe automation of the already-approved ingestion contract**, not expansion of the TorqueAI data contract.

## 2. Why GitHub Actions is the scheduler

Polaris development infrastructure remains free-tier oriented:

- GitHub: source, CI, and scheduled trigger authority;
- Render Free Web Service: FastAPI execution surface;
- Neon Free: PostgreSQL durable state.

A Render Free web process must not own an in-process timer, daemon loop, APScheduler instance, or background thread for this job. Free web instances can sleep/restart and do not provide a reliable singleton scheduling guarantee.

Therefore the scheduled architecture is:

`GitHub Actions -> signed internal Polaris endpoint -> TorqueAI connector -> validated ingestion -> Neon`

GitHub Actions only wakes the backend. It never receives the TorqueAI provider token, TorqueAI base URL, database URL, or any dispatch records.

## 3. Staged rollout: cron is NOT enabled in the first implementation PR

Automatic sync is deliberately split into two implementation stages.

### Stage 1 — certified trigger path, no cron

The first implementation PR may add:

1. a narrow machine-authenticated internal TorqueAI scheduled-sync endpoint;
2. durable duplicate-trigger claiming;
3. a GitHub Actions workflow containing `workflow_dispatch` only;
4. focused backend, migration, security, and workflow tests.

It must **not** add a `schedule:`/cron event.

After merge and exact-merge CI success, the operator configures/verifies the trigger secret and runs the workflow manually exactly once. The result is certified using only sanitized aggregate metadata and a durable database read.

### Stage 2 — enable hourly schedule

Only after Stage 1 production certification may a separate, very small PR add the GitHub Actions `schedule:` stanza.

Proposed production cadence:

```yaml
schedule:
  - cron: "17 * * * *"
```

GitHub scheduled workflows may start later than their nominal minute; correctness must never depend on exact minute execution.

The Stage 2 PR retains `workflow_dispatch` for controlled operator testing and uses workflow concurrency:

```yaml
concurrency:
  group: torqueai-dispatch-sync-production
  cancel-in-progress: false
```

No cadence faster than hourly is approved by this design.

## 4. Internal endpoint

Proposed route:

`POST /api/v1/internal/torqueai/dispatches/scheduled-sync`

Properties:

- machine-only; no browser/user session authentication;
- empty request body;
- no caller-supplied organization;
- no caller-supplied date window;
- no caller-supplied pagination controls;
- resolves one configured active Polaris organization server-side;
- derives the approved rolling window server-side;
- returns only sanitized aggregate execution metadata.

The route must be registered separately from user-facing TorqueAI routes.

The existing browser/manual endpoint remains unchanged and continues to require `CONNECTOR_WRITE`.

## 5. Reuse Polaris machine-authentication convention

TorqueAI must reuse `app.security.job_auth.verify_job_signature` rather than introduce a second job-auth scheme.

Required headers:

- `X-Polaris-Job-Timestamp`
- `X-Polaris-Job-Signature`

The existing canonical signature contract is:

`METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + SHA256(BODY)`

with HMAC-SHA256 over that canonical string.

The existing helper already provides:

- required server-side secret;
- integer timestamp validation;
- five-minute default clock-skew tolerance;
- 64-character hexadecimal signature validation;
- constant-time `hmac.compare_digest` verification;
- body-digest binding.

TorqueAI scheduled sync must use a dedicated secret environment variable:

`POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET`

The same secret value is configured independently as:

- a Render environment secret for the backend; and
- a GitHub Actions repository secret for the trigger workflow.

The secret value must never be printed, returned, committed, or logged.

A missing, stale, malformed, or incorrect signature returns a generic machine-authentication failure before organization lookup, database claim, or provider access.

## 6. Server-owned tenant resolution

The scheduled caller cannot choose a tenant.

Use a dedicated scheduled-organization setting:

`POLARIS_TORQUEAI_SCHEDULED_ORGANIZATION_SLUG`

The backend resolves exactly one active Polaris organization by that slug.

The resolved slug must also match the already-required TorqueAI connector configuration `POLARIS_TORQUEAI_ORGANIZATION_SLUG`; a mismatch fails closed before provider access.

This preserves the existing connector rule that a company-specific TorqueAI token cannot be used on behalf of another Polaris tenant.

GitHub Actions is never given the organization slug as an input that can select a different tenant.

## 7. Disabled-by-default production switch

Add an explicit backend feature switch:

`POLARIS_TORQUEAI_SCHEDULED_SYNC_ENABLED`

Default: false/unset.

When disabled, an otherwise valid signed trigger returns a sanitized `disabled` result and performs:

- zero provider calls;
- zero dispatch writes;
- zero sync-state advancement.

Stage 1 must be deployed with no cron. The operator may enable the switch only when the Render and GitHub trigger-secret presence has been verified and the one controlled `workflow_dispatch` certification is ready.

## 8. Scheduled window

Each scheduled execution reconciles a rolling seven-provider-date window:

- `to = current UTC date`
- `from = to - 6 days`

The values are sent explicitly to TorqueAI; provider defaults are not used.

This intentionally reuses the already-approved manual ingestion maximum of seven inclusive days.

Important semantics: TorqueAI's provider query date is **not** treated as the persisted `ship_date`. The certified Aug. 27 provider query returned dispatches with multiple later ship dates. The scheduled window therefore means "recent provider query dates," not "shipments whose ship date is in the last seven days."

A rolling window is used because recent dispatch status/equipment/assignment details can change after first observation. Idempotent fingerprints make unchanged rows cheap at the database layer.

This design does **not** claim that records outside the seven-provider-date hot window remain current forever. Historical backfill and long-tail reconciliation remain separate gates.

## 9. Provider-call bounds

Scheduled sync reuses the certified ingestion constants unless a later design explicitly changes them:

- page size: 100;
- maximum pages: 10;
- maximum provider rows: 1,000;
- maximum inclusive date range: 7 days;
- pages fetched sequentially;
- zero application-level provider retries.

If page 1 declares more than 1,000 rows or more than 10 pages, the run fails closed.

If pagination metadata changes across pages, a duplicate provisional identity is returned, approved field types are malformed, or validated row count differs from `totalCount`, the run fails closed and performs zero dispatch-row mutation.

A provider `429` is recorded as a sanitized failed run. Polaris does not immediately retry TorqueAI. The next valid scheduled slot is the next opportunity to reconcile.

## 10. Durable trigger claim before provider access

This is the central retry-safety requirement.

Render Free may be cold when GitHub calls it. The trigger workflow may therefore retry the **HTTP wake-up request**, but it must never cause the same scheduled slot to fetch TorqueAI twice.

Before page 1 provider access, the backend must atomically create and commit a durable scheduled-run claim.

### 10.1 Trigger slot

The scheduled trigger slot is the authenticated request timestamp rounded down to the UTC hour, rendered canonically, for example:

`2026-08-29T05:00:00Z`

It is derived from the already-verified `X-Polaris-Job-Timestamp`; it is not supplied in a body/query parameter.

### 10.2 Sync-run schema extension

Extend `torqueai_dispatch_sync_runs` with nullable scheduler metadata rather than introducing a second source of run truth:

- `trigger_mode` — nullable bounded text; scheduled value `scheduled`;
- `trigger_slot` — nullable bounded UTC-hour text.

Add a uniqueness rule covering scheduled slots:

`(organization_id, trigger_mode, trigger_slot)`

Manual historic/current runs keep both columns null. PostgreSQL and SQLite both permit multiple rows containing nulls under a normal unique constraint, so the existing manual path remains compatible.

The migration must be forward-only under the repository's destructive-downgrade policy and pass both SQLite and PostgreSQL migration gates.

### 10.3 Claim transaction

For a scheduled request:

1. verify HMAC and timestamp;
2. verify scheduled-sync feature flag;
3. resolve and validate the configured organization;
4. derive UTC trigger slot and seven-day provider window;
5. attempt to insert a `TorqueAIDispatchSyncRun` row with status `claimed`, scheduled trigger metadata, requested dates, zero counts, and a generated run ID;
6. commit that claim transaction;
7. **only then** instantiate/use the provider connector and fetch page 1.

If the unique scheduled slot already exists, return sanitized `already_claimed` metadata and make zero provider calls.

A uniqueness race is handled as an already-claimed result after rollback/re-read, not as permission to fetch the provider.

### 10.4 Existing ingestion service refactor

The current ingestion service creates its own run ID and inserts its final run evidence. Scheduled execution therefore requires a narrow refactor so the shared ingestion logic can operate against a pre-created claimed run.

The approved direction is:

- manual path behavior remains externally unchanged;
- shared provider-fetch/validate/upsert logic remains one implementation;
- scheduled wrapper pre-creates/commits the claim;
- shared ingestion accepts the pre-created run identity and updates that row to `success` or `failed` rather than inserting a second run row;
- successful dispatch mutations + successful run metadata + sync-state advancement remain in one atomic transaction after all provider pages validate;
- provider/contract failures update only sanitized run evidence and make zero dispatch-row writes;
- database persistence failure never causes an automatic provider retry.

Tests must prove the manual endpoint's existing contract has not regressed.

## 11. Crash semantics

Once a scheduled slot is claimed, that slot is consumed even if the process crashes before or during provider work.

This is intentional fail-safe behavior: avoiding duplicate provider calls is more important than retrying the same hour automatically.

A retry of the same signed slot returns `already_claimed` and makes zero provider calls.

The next hourly slot reconciles the same rolling seven-day window and can recover missed durable changes.

No automatic claim reset/requeue/stale-claim recovery is approved in this gate.

## 12. GitHub Actions workflow — Stage 1

Proposed file:

`.github/workflows/torqueai-dispatch-sync.yml`

Stage 1 triggers:

```yaml
on:
  workflow_dispatch:
```

No `schedule:` entry is present.

The workflow:

1. verifies the trigger secret is non-empty without printing it;
2. creates one Unix timestamp;
3. signs the empty-body POST using the same canonical format as `job_auth.py`;
4. calls the fixed Render endpoint;
5. prints only the sanitized backend response;
6. fails the workflow on non-successful/invalid execution results;
7. uses a bounded timeout.

GitHub stores only `POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET` for this workflow.

GitHub must not receive:

- `POLARIS_TORQUEAI_API_TOKEN`;
- `POLARIS_TORQUEAI_BASE_URL`;
- `POLARIS_TORQUEAI_ORGANIZATION_SLUG`;
- `DATABASE_URL`;
- any customer, driver, carrier, equipment, billing, stop, or dispatch values.

## 13. Trigger-level HTTP retry versus provider retry

These are distinct.

The workflow may use a very small HTTP retry allowance solely to tolerate a sleeping Render Free service, e.g. a maximum of two retry attempts with a short delay.

That is safe only because the durable trigger claim is committed before provider access. A duplicate HTTP request for the same signed timestamp/hour must receive `already_claimed` and make zero TorqueAI calls.

The Polaris TorqueAI connector itself continues to have **zero provider retries**.

No code may loop around `fetch_dispatches()` after 429, timeout, 5xx, contract failure, or any other provider error.

## 14. Sanitized endpoint response

The internal endpoint may return only scheduler/run metadata such as:

```json
{
  "status": "executed",
  "provider": "torqueai",
  "trigger_mode": "scheduled",
  "trigger_slot": "2026-08-29T05:00:00Z",
  "request": {"from": "2026-08-23", "to": "2026-08-29"},
  "dispatch_claimed": true,
  "pages_fetched": 1,
  "provider_total_count": 9,
  "rows_validated": 9,
  "rows_inserted": 0,
  "rows_updated": 2,
  "rows_unchanged": 7,
  "tenant_scope_validated": true,
  "raw_dispatches_returned": false,
  "secrets_exposed": false
}
```

Other allowed statuses include:

- `disabled`;
- `already_claimed`;
- `failed`.

Failure responses expose a bounded internal `error_code`, not provider bodies or dispatch values.

The sample numbers above are illustrative only and are not a production expectation.

## 15. Logging and observability

Allowed structured log/evidence fields:

- generated run ID;
- internal organization ID;
- trigger mode;
- trigger slot;
- requested provider dates;
- pages fetched;
- provider total count;
- rows validated/inserted/updated/unchanged;
- sanitized status/error code;
- timestamps.

Never log:

- HMAC secret/signature;
- TorqueAI bearer token;
- provider base URL if it may contain tenant-specific information beyond already-controlled configuration;
- raw provider body;
- load/order numbers;
- customer/dispatcher/driver/carrier names;
- truck/trailer values;
- billing/charge/stops/addresses/coordinates.

## 16. Dashboard behavior remains read-only

The Dispatch dashboard remains a durable-database reader.

This design does **not** add:

- a browser `Sync now` button;
- browser access to the internal machine endpoint;
- polling of TorqueAI from the frontend;
- provider-call counters based on client-side assumptions;
- ingestion controls for ordinary users.

After scheduled sync is enabled, the dashboard continues to call only `GET /api/v1/torqueai/dispatches`.

## 17. Failure behavior

| Failure | Required behavior |
| --- | --- |
| Missing/invalid HMAC | 401 generic machine-auth failure; zero provider calls |
| Timestamp outside tolerance | 401; zero provider calls |
| Feature flag disabled | sanitized disabled result; zero provider calls |
| Scheduled org missing/inactive | fail closed; zero provider calls |
| Scheduled org/provider org mismatch | fail closed; zero provider calls |
| Duplicate hourly trigger slot | `already_claimed`; zero provider calls |
| Claim database failure | fail closed; zero provider calls |
| TorqueAI 401/403 | sanitized failed run; zero dispatch writes |
| TorqueAI 429 | sanitized failed run; no TorqueAI retry |
| TorqueAI 5xx/timeout | sanitized failed run; no TorqueAI retry |
| Pagination/contract failure | sanitized failed run; zero dispatch writes |
| >10 pages or >1000 rows | fail closed; zero dispatch writes |
| Dispatch DB mutation failure | rollback mutation transaction; no automatic provider retry |
| Process crash after claim | slot remains consumed; next hourly slot reconciles rolling window |

## 18. Tests required before Stage 1 can be Ready

### Machine-auth tests

- valid signature accepted;
- missing secret rejected;
- missing timestamp/signature rejected;
- stale/future timestamp rejected;
- malformed signature rejected;
- wrong method/path/body signature rejected;
- secret/signature never included in response/log assertions.

### Claim tests

- claim commits before provider access;
- first slot can enter provider path;
- duplicate same-org/same-slot makes zero provider calls;
- concurrent uniqueness race fails safe as already claimed;
- a later UTC-hour slot is independently claimable;
- manual rows with null scheduler metadata remain allowed.

### Scheduler tests

- disabled flag makes zero provider calls;
- organization is server-selected only;
- missing/inactive org fails before provider;
- provider org mismatch fails before provider;
- rolling window is exactly seven inclusive UTC dates;
- no request body/date/org overrides are accepted.

### Ingestion regression tests

- existing manual ingestion remains successful;
- scheduled path preserves 100/page, 10-page, 1,000-row bounds;
- scheduled path still fetches all pages before dispatch mutation;
- success updates the pre-claimed run rather than creating a second run;
- failure updates sanitized pre-claimed evidence only;
- provider 429/timeout/5xx is not retried by backend;
- idempotent unchanged/update behavior remains intact;
- no deferred fields become persisted.

### Workflow tests/static checks

- Stage 1 workflow contains `workflow_dispatch`;
- Stage 1 workflow contains **no `schedule:`**;
- workflow has concurrency protection and timeout;
- only the dedicated HMAC secret is referenced;
- provider token/database secret names do not appear in the workflow;
- endpoint URL/path is fixed;
- signature canonicalization matches backend helper.

## 19. Stage 1 production certification

After the Stage 1 implementation PR is manually merged:

1. verify exact merge SHA on `main`;
2. wait for every push workflow that actually registered on that exact SHA to finish successfully;
3. verify Render deployment is healthy;
4. verify presence (not values) of:
   - Render `POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET`;
   - Render `POLARIS_TORQUEAI_SCHEDULED_SYNC_ENABLED`;
   - Render `POLARIS_TORQUEAI_SCHEDULED_ORGANIZATION_SLUG`;
   - GitHub Actions `POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET`;
5. verify scheduled-org/provider-org equality without exposing the slug value if it is treated as configuration-sensitive;
6. enable the backend scheduled-sync switch;
7. run `workflow_dispatch` exactly once;
8. require workflow success and a sanitized backend `executed` result;
9. perform a read-only durable dispatch API check to confirm rows remain tenant-scoped and no duplicate identities were created;
10. optionally re-dispatch the same job only in a dedicated duplicate-claim certification scenario if the workflow can preserve the exact signed trigger slot; otherwise duplicate behavior remains test-certified, not production-probed.

No cron is enabled during this certification.

If provider contract, pagination, identity, or persistence behavior differs from the approved contract, stop and fix that gate before enabling Stage 2.

## 20. Stage 2 schedule enablement gate

After Stage 1 certification, a separate PR may add only the hourly schedule and any minimal documentation required for it.

Stage 2 readiness requires:

- exact branch based on the certified Stage 1 `main`;
- no TorqueAI schema/data-contract expansion;
- no provider retry logic;
- no dashboard write controls;
- exact-head CI green;
- manual merge;
- exact-merge push CI green.

The first scheduled run is then observed through sanitized GitHub/backend evidence and a read-only durable API check.

## 21. Explicitly deferred

This automatic-sync gate does not approve:

- historical backfill beyond the rolling seven provider dates;
- daily/monthly bulk reconciliation;
- deletion/tombstoning because a dispatch disappears from a provider response;
- billing, `totalCharge`, stops, addresses, coordinates, or raw JSON persistence;
- financial analytics or QuickBooks joins;
- Motive/TorqueAI cross-provider matching;
- Daily Brief interpretation;
- alerts, recommendations, driver scoring, customer scoring, or status thresholds;
- user-configurable scheduling;
- multiple TorqueAI organizations/tokens;
- stale-claim replay/reset logic;
- provider retries;
- Render in-process timers/workers.

Each requires a separate reviewed design gate.

## 22. Acceptance criteria

This design gate is satisfied when reviewers agree that the future implementation:

1. uses GitHub Actions only as a signed wake-up authority;
2. keeps provider credentials and data inside Render/Neon;
3. reuses Polaris `job_auth` HMAC verification;
4. resolves exactly one tenant server-side;
5. is disabled by default;
6. derives a fixed rolling seven-day UTC provider window;
7. commits a durable unique hourly claim before any provider access;
8. guarantees duplicate trigger requests make zero duplicate TorqueAI calls;
9. reuses the certified ingestion validation/upsert contract;
10. has zero backend provider retries;
11. keeps the Dispatch UI durable-read-only;
12. ships Stage 1 with `workflow_dispatch` only and **no cron**;
13. requires one controlled production workflow certification before a separate Stage 2 hourly schedule PR.
