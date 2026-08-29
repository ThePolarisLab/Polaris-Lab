# TorqueAI Durable Dispatch Ingestion Design Gate

Status: design gate only. This document authorizes no live TorqueAI request, database migration, database write, scheduler, frontend behavior, or production ingestion by itself.

## Goal

Define the first durable TorqueAI ingestion gate for Polaris after successful live certification of the read-only external dispatch API.

The next implementation should let an explicitly authorized Polaris operator fetch a small, bounded dispatch window from TorqueAI, validate every provider page, and persist a minimized operational dispatch record set to PostgreSQL/Neon with deterministic tenant isolation and idempotent update behavior.

The implementation must remain intentionally narrow:

- backend only;
- read-only toward TorqueAI;
- explicit operator invocation only;
- bounded provider-call volume;
- no automatic retry;
- no scheduler or polling;
- no historical backfill engine;
- no raw provider payload storage;
- no billing/charge persistence;
- no stop/address persistence;
- no frontend dispatch view yet;
- no Daily Brief or KPI interpretation yet.

## Certified production evidence

The controlled production certification against the deployed Polaris backend completed successfully on August 28, 2026.

Sanitized evidence observed:

- Polaris certification endpoint returned HTTP `200`.
- `status = certified_response_observed`.
- `provider = torqueai`.
- `response_contract_valid = true`.
- `tenant_scope_validated = true`.
- `secrets_exposed = false`.
- `raw_dispatches_returned = false`.
- explicit request date was `2026-08-27`.
- page was `1` with limit `100`.
- `total_count = 9` and `rows_returned = 9`.
- pagination was not required for that one-day sample.

The live response exposed field types only, not values. Observed field names/types included:

- `loadNumber`: number;
- `orderNumber`: string;
- `status`: string;
- `orderDate`: string;
- `shipDate`: string;
- `deliveryDate`: string;
- `invoiceDate`: null in the sampled record;
- `customerName`: string;
- `dispatcherName`: string;
- `driverName`: string;
- `carrierName`: string;
- `truckNumber`: string;
- `trailerNumber`: string;
- `loadedMiles`: number;
- `currency`: string;
- `totalCharge`: number;
- `stops`: array;
- `billing`: object.

This certification proves connectivity and the response envelope for one real page. It does **not** prove global identity uniqueness, historical completeness, immutability of any provider field, or finality of a dispatch after its first observation.

## Existing provider contract remains authoritative

The underlying certified provider operation remains:

`GET {configured_base_url}/api/external/dispatches`

with Bearer authentication sourced only from `POLARIS_TORQUEAI_API_TOKEN` in the deployment secret store.

The implementation must continue to enforce the earlier connector design gate:

- HTTPS configured origin only;
- exact `/api/external/dispatches` path only;
- GET only;
- explicit date bounds;
- tenant binding to `POLARIS_TORQUEAI_ORGANIZATION_SLUG`;
- no browser-to-TorqueAI access;
- sanitized provider errors;
- no retry on `429` or other provider failures.

## First persistence scope

### Persisted operational fields

The first durable dispatch table may persist only the following provider-derived operational fields:

- normalized provider load number;
- normalized provider order number;
- status;
- order date text;
- ship date text;
- delivery date text;
- customer name;
- dispatcher name;
- driver name;
- carrier name;
- truck number;
- trailer number;
- loaded miles;
- a deterministic fingerprint of only these approved fields.

Polaris-managed provenance fields should also be stored:

- internal row ID;
- organization ID;
- first observed timestamp;
- last changed timestamp;
- creation/update timestamps as required by the existing ORM convention.

### Explicitly excluded from the first durable table

Do **not** persist these TorqueAI fields in the first gate:

- `billing` object;
- `totalCharge`;
- billing rate/subtotal/total/tax;
- billing line items;
- detention charges;
- deductions;
- `currency` when used only as financial context;
- nested `stops`;
- stop addresses;
- coordinates;
- actual/scheduled stop timing details;
- raw provider JSON;
- raw HTTP response bodies;
- Authorization headers;
- API token values.

These exclusions are deliberate data-minimization boundaries, not parser limitations. Financial ingestion and stop/location ingestion require separate design gates because they increase privacy and business-risk exposure.

## Proposed durable dispatch schema

Use an ORM/migration shape equivalent to a `torqueai_dispatches` table.

Minimum logical columns:

- `id`: Polaris internal primary key;
- `organization_id`: required FK / tenant key;
- `provider_load_number`: required normalized text;
- `provider_order_number`: required normalized text;
- `status`: nullable bounded text;
- `order_date_text`: nullable bounded text;
- `ship_date_text`: nullable bounded text;
- `delivery_date_text`: nullable bounded text;
- `customer_name`: nullable bounded text;
- `dispatcher_name`: nullable bounded text;
- `driver_name`: nullable bounded text;
- `carrier_name`: nullable bounded text;
- `truck_number`: nullable bounded text;
- `trailer_number`: nullable bounded text;
- `loaded_miles`: nullable non-negative decimal;
- `source_fingerprint`: required SHA-256 hex digest of the canonical approved-field representation;
- `first_observed_at`: required timestamp;
- `last_changed_at`: required timestamp.

Indexes should support at minimum:

- tenant-scoped provider identity lookup;
- tenant + ship-date-text filtering if useful without implying parsed-date semantics;
- tenant + status lookup only if justified by current query plans.

Do not add speculative indexes for future dashboards before query behavior exists.

## Provider identity strategy

TorqueAI does not expose a certified immutable provider dispatch ID in the observed contract.

The first durable gate therefore uses a **provisional tenant-scoped composite provider identity**:

`(organization_id, provider_load_number, provider_order_number)`

Normalization rules:

- `loadNumber` must be a JSON integer value, not boolean, float, null, array, or object;
- convert the integer deterministically to canonical decimal text before persistence;
- `orderNumber` must be a non-empty bounded string after trimming outer whitespace;
- do not case-fold or otherwise rewrite the provider order number unless a later certification proves that behavior safe.

The database should enforce uniqueness across the composite identity.

This strategy intentionally does **not** claim that `loadNumber` alone is globally unique or that `orderNumber` alone is globally unique.

### Identity fail-closed rules

Before any dispatch writes occur, the ingestion run must fail closed if:

- either identity component is missing or malformed;
- the same composite key appears more than once in the fetched window;
- two duplicate composite keys carry different approved-field content;
- the provider starts returning `loadNumber` with a type different from the certified integer shape;
- an identity collision is detected against existing tenant data in a way that cannot be represented as a normal update.

Do not invent an identity fallback from customer, driver, dates, truck, trailer, or billing fields.

If future evidence shows that either provider identity component can legitimately change for the same dispatch, stop and open a new identity/reconciliation design gate before attempting automatic record merging.

## Date-field handling

The live certification proved that `orderDate`, `shipDate`, and `deliveryDate` are strings, but it intentionally did not expose their values. Therefore the first persistence gate must not silently assume a date/time format that has not been certified.

Persist these as bounded normalized text fields in the first gate.

Rules:

- null/omitted provider value remains null;
- string values are trimmed only at their outer boundaries;
- reject values above the configured maximum length;
- do not manufacture a date or zero value from omission;
- do not parse into UTC or another timezone yet.

A later schema-normalization gate may add typed date/time columns after real value formats and timezone semantics are safely certified.

## Numeric handling

`loadedMiles` was observed as a JSON number.

Rules:

- must be finite;
- must be non-negative;
- boolean is invalid even though some runtimes treat it as numeric;
- null/omitted means unknown and persists as null;
- no missing value becomes zero;
- convert through a deterministic decimal representation rather than binary floating-point arithmetic before database persistence.

Financial numeric fields remain excluded from this gate.

## Source fingerprint

For each validated provider dispatch, build a canonical representation containing only the approved persisted provider fields in a fixed field order and deterministic null/string/decimal encoding.

Store:

`source_fingerprint = sha256(canonical_approved_fields)`

The fingerprint must exclude:

- token/header data;
- raw JSON;
- billing/charge fields;
- stops/addresses;
- Polaris timestamps;
- sync-run metadata.

The fingerprint exists only to decide whether an already-known dispatch changed within the approved persisted field set. It is not a security signature and must not be treated as provider identity.

## Idempotent upsert semantics

For each validated composite provider key:

1. No existing row:
   - insert one row;
   - set `first_observed_at` and `last_changed_at` to the current ingestion observation time.

2. Existing row with identical `source_fingerprint`:
   - do not rewrite the dispatch row;
   - count it as unchanged;
   - successful sync-run history is sufficient evidence that the record was observed again.

3. Existing row with a different `source_fingerprint`:
   - update only the approved persisted provider fields and fingerprint;
   - preserve `first_observed_at`;
   - advance `last_changed_at`.

4. Existing database row omitted from a later provider result:
   - do not delete it;
   - do not mark it cancelled/closed/missing;
   - do not infer provider deletion;
   - provider omission remains unknown until a later reconciliation design explicitly defines semantics.

## Manual ingestion API gate

The first persistence implementation should expose one explicit, authenticated operator action rather than a scheduler.

Proposed shape:

`POST /api/v1/connectors/torqueai/dispatches/ingest`

The exact final route name may follow existing Polaris conventions, but its semantics must remain explicit and write-capable.

Authorization requirements:

- authenticated Polaris principal;
- tenant header/context required;
- `CONNECTOR_WRITE` permission because the operation both calls a provider and mutates the Polaris database;
- database organization slug must match configured `POLARIS_TORQUEAI_ORGANIZATION_SLUG` before any provider request.

Request body should contain explicit:

- `from` date;
- `to` date.

No caller-supplied provider URL, token, page size, arbitrary endpoint, or organization slug is allowed.

## Initial ingestion bounds

Polaris should intentionally use bounds smaller than TorqueAI's vendor maximum for the first durable gate.

Initial fixed implementation limits:

- maximum inclusive date window: **7 days**;
- provider page size: **100**;
- maximum pages per invocation: **10**;
- maximum provider rows per invocation: **1,000**;
- no automatic retry;
- one monotonically increasing page sequence only.

After receiving and validating page 1, calculate the required page count from `totalCount` and `itemsPerPage`.

If required pages exceed 10 or total rows exceed 1,000:

- fail closed;
- do not request page 2;
- do not write dispatch rows;
- return a sanitized `ingestion_bound_exceeded` error.

These limits can be revisited in a separate volume-certification gate after real usage evidence exists.

## Multi-page retrieval algorithm

For an approved request window:

1. Validate tenant, permission, date order, and 7-day maximum locally.
2. Request page 1 with limit 100.
3. Validate the full response envelope using the certified connector parser.
4. Calculate required page count.
5. Fail before requesting another page if row/page bounds would be exceeded.
6. Request pages 2..N sequentially with no retry.
7. Validate each page independently.
8. Require response date range and page number to match the request.
9. Collect only approved fields into minimized normalized in-memory records.
10. Reject duplicate provisional provider identities across all pages before database mutation.
11. Only after **all** required provider pages are successfully fetched and validated may dispatch persistence begin.

Do not make provider page calls in parallel in the first gate. Sequential calls keep rate behavior deterministic and make the no-retry contract auditable.

## Transaction and partial-failure behavior

### Provider phase

No dispatch database rows should be inserted or updated while provider pagination is still in progress.

If any provider page fails or is malformed:

- stop immediately;
- make no further provider call;
- write no dispatch rows;
- do not advance successful sync state.

A sanitized failed sync-history record may be persisted in a short independent database transaction if implementation tests prove it contains no provider payload or secret material.

### Persistence phase

After every required page is validated and normalized:

- perform dispatch inserts/updates plus successful sync-state mutation in one database transaction;
- if the transaction fails, roll it back completely;
- do not report success or advance state when the dispatch transaction did not commit.

## Sync-run history

Add a minimized tenant-scoped sync-run table equivalent to `torqueai_dispatch_sync_runs`.

Allowed logical fields:

- internal run ID;
- organization ID;
- requested `from` / `to` dates;
- fixed page size;
- status: started/success/failed according to existing Polaris enum conventions;
- pages fetched;
- provider total row count when known;
- rows validated;
- rows inserted;
- rows updated;
- rows unchanged;
- stable sanitized error code when failed;
- started/completed timestamps.

Forbidden history content:

- token;
- Authorization header;
- raw dispatch payload;
- customer/driver/address values;
- provider response body;
- stack trace containing provider data.

## Sync state / checkpoint semantics

Add one tenant-scoped state row equivalent to `torqueai_dispatch_sync_state`.

It may record:

- organization ID;
- last successful requested window start;
- last successful requested window end;
- last successful run ID;
- last successful completion timestamp.

Important: this state is **operational evidence only**, not proof of provider completeness or finality.

Do not call the window end a final `completed_through` business checkpoint in the first TorqueAI gate because dispatches may change after their ship/order date and the API contract does not certify immutable historical snapshots.

The future scheduler/reconciliation gate must separately decide how much trailing history to re-read for status/equipment changes.

## Sanitized ingestion response

The operator-facing Polaris response should contain aggregate metadata only, for example:

- `status`;
- `provider = torqueai`;
- requested from/to;
- pages fetched;
- provider total count;
- rows validated;
- inserted count;
- updated count;
- unchanged count;
- `tenant_scope_validated = true`;
- `raw_dispatches_returned = false`;
- `secrets_exposed = false`.

It must not return persisted dispatch rows from the write endpoint.

A separate future read API can expose purpose-specific minimized dispatch data under `CONNECTOR_READ` after its own review.

## Logging rules

Allowed logs:

- stable run ID;
- organization ID or safe internal tenant identifier according to existing Polaris logging policy;
- bounded from/to dates;
- page number;
- HTTP status category;
- aggregate row counts;
- stable sanitized error code.

Forbidden logs:

- token/header;
- raw dispatch JSON;
- customer name;
- driver name;
- carrier name;
- truck/trailer values;
- order/load identifiers if not already permitted by the existing production log policy;
- addresses;
- financial values.

## Migration safety

The implementation must use a forward-only Alembic migration consistent with current Polaris migration policy.

Requirements:

- fresh install succeeds;
- upgrade from current `main` succeeds;
- repeated `alembic upgrade head` is safe;
- destructive downgrade remains blocked if that is the repository policy;
- tenant FK and composite unique constraint are explicit;
- no default demo/provider records are inserted by the migration.

## Implementation test requirements

The persistence implementation must prove at minimum:

1. only the certified GET endpoint is called;
2. authenticated tenant + `CONNECTOR_WRITE` is required;
3. organization mismatch fails before provider access;
4. request window over 7 days fails before provider access;
5. page size is fixed at 100;
6. page 1 total requiring >10 pages or >1,000 rows fails before page 2;
7. pagination is sequential and stops exactly at the validated total;
8. there is no automatic retry on 429 or any provider failure;
9. malformed page N causes zero dispatch writes;
10. missing/malformed provisional identity causes zero dispatch writes;
11. duplicate composite provider identity across pages fails closed;
12. first observation inserts exactly one row;
13. identical rerun creates no duplicate and does not rewrite unchanged dispatch rows;
14. changed approved fields update the existing composite-key row;
15. omission from a later window does not delete or mutate the old row;
16. loaded-miles null remains null, zero remains a legitimate zero, negative/non-finite fails;
17. provider date strings are stored without invented timezone/date interpretation;
18. billing, totalCharge, currency-as-financial-context, stops, addresses, and raw JSON are absent from durable dispatch storage;
19. source fingerprint changes only when approved persisted provider fields change;
20. transaction failure rolls back all dispatch writes and does not mark sync success;
21. failed sync history is sanitized;
22. successful response contains aggregate metadata only;
23. token/header never appear in database rows, logs captured by tests, exceptions, or API responses;
24. tenant A can never read/update tenant B's dispatch rows through ingestion internals;
25. migration gate succeeds on a fresh schema and repeated upgrade.

## Controlled durable-ingestion production certification

After the implementation PR is merged and all workflows that actually register on its exact head and merge SHA are successful, perform one operator-approved live durable-ingestion run.

Use the already certified completed date `2026-08-27` first because the earlier sanitized certification observed 9 dispatch rows and no pagination for that date.

Expected certification evidence should be aggregate only:

- provider call succeeds;
- one page is sufficient if provider data has not materially changed;
- rows validate;
- durable rows are inserted/updated/unchanged as appropriate;
- no financial/stop/raw payload fields are stored;
- tenant isolation holds;
- no token exposure;
- rerunning is **not** part of the first production certification unless a separate idempotency verification is deliberately approved.

Do not assume the provider count must still equal 9; TorqueAI data may legitimately change after the earlier certification. A changed count is evidence to inspect, not an automatic failure.

## Temporary certification endpoint cleanup

The route `/api/v1/connectors/torqueai/certification` has completed its original purpose.

The durable-ingestion implementation or an immediately adjacent focused cleanup PR should remove that temporary provider-call route after the durable connector path is certified, so ordinary `CONNECTOR_READ` users do not retain an unnecessary endpoint that can trigger provider calls.

Do not remove it in this documentation-only design PR.

## Deferred gates

Still deferred after this design:

- automatic scheduler/cron;
- trailing-window reconciliation policy;
- large historical backfill;
- >7-day runs;
- >1,000 rows per invocation;
- automatic retries/rate-limit backoff;
- stop/address/location persistence;
- financial/billing persistence;
- typed normalization of provider date strings;
- dispatch read API/UI;
- Daily Brief integration;
- load exception/attention logic;
- revenue/margin analysis;
- dispatcher/driver/customer performance metrics;
- joining TorqueAI to Motive, QuickBooks, fuel, ACE, or other provider records;
- provider identity redesign if future evidence invalidates the provisional composite key.

Each deferred item changes provider-call volume, persistence exposure, reconciliation semantics, or business interpretation and therefore requires a separate reviewed gate.

## Acceptance criteria for this design PR

This design gate is complete when:

- only this documentation file changes;
- branch is based on the exact verified production-certified `main` SHA;
- no TorqueAI request is made as part of the PR;
- no Neon/database write occurs;
- no migration/code/frontend/Render setting changes occur;
- the existing Render token remains secret;
- exact-head workflows that actually register finish successfully;
- reviews/review threads are checked before marking ready;
- the next implementation is constrained to the manual bounded durable-ingestion behavior defined above.
