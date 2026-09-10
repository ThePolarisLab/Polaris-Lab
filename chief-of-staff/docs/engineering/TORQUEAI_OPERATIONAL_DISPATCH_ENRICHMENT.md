# TorqueAI Operational Dispatch Enrichment

Status: evidence gate in progress.

## Business goal

Expand durable TorqueAI dispatch data so Polaris can support operational questions such as loads picking up in Manitoba on a given date, future truck/load positioning, lane planning, equipment planning, and empty-mile reduction.

This gate does not build an AI load-matching engine.

## Existing live-certified top-level provider fields

A controlled live certification on 2026-08-28 observed these provider fields/types on `/api/external/dispatches` without retaining values:

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

The first durable ingestion gate intentionally persisted only the minimized operational subset and excluded `currency`, `totalCharge`, `stops`, addresses, timing details, and billing.

## Evidence still required before location persistence

The live certification proved that `stops` is an array, but it did not certify nested stop field names or types. Polaris must not guess pickup/delivery/address/appointment field names.

This branch therefore extends the existing certification metadata with a recursive schema-only observer. The observer returns JSON key paths and JSON types across the observed page, including nested arrays/objects, while returning no provider values.

Examples of output shape are key paths only, such as `stops[]`, `stops[].<provider-key>`, or `billing.<provider-key>`.

Security properties:

- no provider values returned;
- no raw payload returned;
- no token/header returned;
- existing authenticated tenant scope retained;
- provider operation remains GET-only;
- no database mutation performed by certification.

## Implementation rule after live nested certification

Only provider fields actually observed in the live schema report may be normalized and persisted. New database columns must be nullable unless the provider contract proves they are required. Existing public fields remain backward-compatible.

Once nested stop fields are certified, the same feature branch can add the validated pickup/delivery/location/appointment fields, source fingerprint coverage, migration, durable read serialization and filtering, tests, and documentation required by the operational enrichment scope.
