# TorqueAI Operational Dispatch Enrichment

Status: implementation in progress; nested stop/location schema remains an explicit certification gate.

## Business goal

Expand durable TorqueAI dispatch data so Polaris can support daily dispatch planning, truck positioning, lane planning, equipment planning, revenue context, change detection, and future empty-mile reduction.

The target business question is eventually: **“Show all loads picking up in Manitoba tomorrow.”** This PR does not build the future AI load-matching engine.

## Live-certified provider evidence

A controlled live certification on 2026-08-28 observed these provider fields/types on `GET /api/external/dispatches` without retaining values:

- `loadNumber`: number
- `orderNumber`: string
- `status`: string
- `orderDate`: string
- `shipDate`: string
- `deliveryDate`: string
- `invoiceDate`: null in sampled record
- `customerName`: string
- `dispatcherName`: string
- `driverName`: string
- `carrierName`: string
- `truckNumber`: string
- `trailerNumber`: string
- `loadedMiles`: number
- `currency`: string
- `totalCharge`: number
- `stops`: array
- `billing`: object

The original durable ingestion gate intentionally persisted only the minimized operational subset through `loadedMiles`. `currency`, `totalCharge`, nested `stops`, addresses/timing, and `billing` were deliberately excluded at that stage.

## Fields added in this PR from already-certified evidence

This PR now whitelists and durably exposes only three additional facts that are already supported by live provider evidence:

- `currency` -> `currency` (nullable text)
- `totalCharge` -> `total_charge` (nullable exact decimal)
- `stops` array -> `stop_count` (nullable integer derived only from array length)

The nested contents of `stops` are **not** persisted. The raw `billing` object is **not** persisted.

These fields live in a one-to-one `torqueai_dispatch_operational` table keyed to the existing durable dispatch. This preserves the original `torqueai_dispatches` contract and gives future certified location/equipment fields a clean extension surface.

## Ingestion and change detection

Manual and scheduled ingestion both pass through the operational enrichment layer while reusing the same existing TorqueAI provider page calls. Enrichment does not make a second provider request.

The original dispatch fingerprint remains unchanged and continues to represent the original certified persisted field set. The operational enrichment has its own deterministic SHA-256 fingerprint covering only:

- currency;
- total charge;
- stop count.

When only one of those operational fields changes, Polaris updates the enrichment record, advances the parent dispatch `last_changed_at`, and counts the dispatch as updated rather than unchanged for that sync run.

All provider-derived enrichment fields are nullable for backward compatibility with existing stored dispatch records and provider omission.

## Durable read API additions

`GET /api/v1/torqueai/dispatches` remains authenticated, tenant-scoped, and database-only. It never contacts TorqueAI.

The response now adds:

- `currency`
- `total_charge`
- `stop_count`

The read API also adds case-insensitive filters for already-certified durable fields:

- `driver`
- `truck`
- `carrier`
- `trailer`
- `currency`

Existing filters for ship date (`from` / `to`), status, customer, and dispatcher remain backward-compatible.

## Nested schema observer

The certification metadata now has a recursive schema-only observer. It reports JSON key paths and JSON types across the observed provider page, including nested arrays/objects, while returning no provider values.

Examples of output shape are key paths only, such as `stops[]`, `stops[].<provider-key>`, or `billing.<provider-key>`.

Security properties:

- no provider values returned;
- no raw payload returned;
- no token or Authorization header returned;
- authenticated tenant scope retained;
- provider operation remains GET-only;
- certification performs no database mutation.

## Fields intentionally not implemented yet

The 2026-08-28 live evidence proved that `stops` is an array but did **not** certify its nested field names/types. Therefore this PR does not guess or persist any of the following yet:

- pickup/shipper facility name;
- pickup address/city/province-state/postal-country;
- pickup appointment date/time/window;
- consignee/delivery address/city/province-state/postal-country;
- delivery appointment date/time/window;
- stop type or ordered stop sequence fields;
- commodity, weight, pieces/pallets;
- equipment type or reefer/dry-van indicator;
- temperature/set point/range;
- empty/deadhead miles or total miles;
- special instructions.

Some of these may exist in TorqueAI, but they are treated as unavailable to Polaris until their exact provider names and types are certified. `billing` is known to exist as an object but remains excluded from persistence in this PR beyond the already-certified top-level `totalCharge` and `currency` fields.

## Next certification gate

Run the enhanced certification endpoint against the deployed backend, where the TorqueAI token is already stored. Record only `observed_schema_paths` and JSON types; do not retain raw provider values.

If the real nested stop schema proves the requested pickup/delivery fields, add only those exact fields to the operational enrichment model, migration, fingerprint, serialization, filters, tests, and this document before considering the location portion complete.

Until that evidence exists, the query **“Show all loads picking up in Manitoba tomorrow”** remains intentionally unsupported. Polaris must not substitute `shipDate` for pickup location or infer Manitoba from unrelated fields.

## Phase 2 direction

After location/appointment/equipment fields are certified and durable, a separate optimization phase can combine:

`Motive truck location + available hours + trailer/equipment + TorqueAI pickup + appointment + destination + miles + revenue`

to rank feasible load assignments and reduce empty miles. That optimization is explicitly outside this PR.
