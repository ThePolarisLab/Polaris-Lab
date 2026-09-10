# TorqueAI Operational Dispatch Enrichment

Status: production nested schema certified on 2026-09-10; durable stop implementation in progress.

## Business goal

Expand durable TorqueAI dispatch data so Polaris can support daily dispatch planning, truck positioning, lane planning, reefer context, revenue context, change detection, and future empty-mile reduction. The target question is **“Show all loads picking up in Manitoba tomorrow.”** This PR does not build the future AI load-matching engine.

## Production certification evidence

The machine-authenticated production certification ran against `GET /api/external/dispatches` for 2026-09-09 and returned HTTP 200 with two dispatches. It exposed schema paths and JSON types only: `schema_values_returned=false`, `raw_dispatches_returned=false`, and `secrets_exposed=false`.

Certified top-level operational fields include `currency` (string), `totalCharge` (number), `billing` (object), and `stops` (array). Certified billing paths include `billing.currency`, `billing.rate`, `billing.subTotal`, `billing.taxAmount`, and `billing.total`.

Certified stop paths include:

- identity/order: `stops[].sequence`, `stops[].stopNo`, `stops[].job`;
- location: `name`, `address`, `city`, `province`, `country`, `zipCode`, `latitude`, `longitude`;
- load context: `commodity`, `weight`, `weightUnit`, `notes`;
- assignment: `driverName`, `coDriverName`, `carrierName`, `truckNumber`, `trailerNumber`;
- scheduling: `scheduled.isWindow`, `scheduled.pickupDate`, `pickupDate2`, `pickupTime`, `pickupTime2`;
- temperature: `temperature`, `temperatureUnit`.

`stops[].temperature` was observed as a mixed JSON type, so Polaris stores only a bounded normalized scalar text representation rather than assuming number or string. `stops[].pallets` and `stops[].pieces` were observed only as null in the certified sample and are intentionally not typed or persisted yet. `stops[].actual.*` fields were likewise observed only as null and remain deferred until useful non-null types are certified.

## Durable model

The original `torqueai_dispatches` table remains unchanged. Certified top-level enrichment is stored one-to-one in `torqueai_dispatch_operational`. Certified nested stops are normalized into `torqueai_dispatch_stops`, tenant-scoped by organization and keyed by dispatch plus provider array position (`stop_index`).

All provider-derived enrichment fields are nullable. Raw TorqueAI payloads are never stored. Exact nested date/time formats were not exposed by the type-only certification, so scheduled date/time values remain bounded text rather than being silently interpreted as SQL dates or times.

Billing persistence is limited to the certified scalar whitelist: currency, rate, subtotal, tax amount and total. `billing.lineItems` and `billing.deductions` are arrays but their nested contracts were not certified and are not persisted.

## Ingestion and fingerprints

Manual and scheduled ingestion use the same existing bounded TorqueAI provider calls. The enrichment layer does not make a second provider request.

The original base dispatch fingerprint remains unchanged. Operational enrichment has a separate deterministic fingerprint covering certified top-level billing fields plus deterministic stop fingerprints. A stop-only change therefore advances the parent dispatch change time and is classified as an updated dispatch rather than unchanged.

When a dispatch's certified operational snapshot changes, its normalized stop set is replaced transactionally from the new whitelisted snapshot. Failed base ingestion must not persist partial enrichment.

## Durable read API

`GET /api/v1/torqueai/dispatches` remains authenticated, tenant-scoped, database-only, and provider-free. It exposes normalized billing and stop objects and supports case-insensitive filters for the existing dispatch fields plus:

- `currency`
- `stop_job`
- `stop_city`
- `stop_province`
- `stop_country`

Multiple stop filters are applied to the same matching stop through an `EXISTS` relationship predicate, avoiding false matches across different stops and avoiding duplicate dispatch rows.

## Pickup/delivery role gate

Production certification proves that `stops[].job` is a string, but by design it did **not** expose provider values. Neither the repository nor public TorqueAI material currently certifies which exact `job` value means pickup versus delivery.

Therefore Polaris persists and filters the exact `job` string but does not invent mappings such as `PICKUP`, `PU`, `SHIPPER`, first-stop-is-pickup, or last-stop-is-delivery. A final narrow categorical certification of the distinct `stops[].job` values is required before adding a semantic `pickup_*` or `delivery_*` API filter.

The durable foundation needed for the Manitoba question is now present. Once the real pickup job value is certified, the query can be expressed safely as the existing ship-date window plus `stop_job=<certified pickup value>` and `stop_province=MB` (or corresponding country/city filters), without another database redesign.

## Explicitly deferred fields

Not currently certified strongly enough for typed persistence or not present in the production schema sample:

- pallets and pieces beyond observed null;
- actual arrived/departed/pickedUp/delivered beyond observed null;
- equipment/reefer-dry indicator (not observed in the production dispatch schema);
- empty/deadhead miles or total miles (not observed);
- nested billing deductions/line item structure;
- semantic pickup/delivery role mapping until job values are certified.

## Phase 2

After the stop-role enum is certified, a separate optimization phase can combine:

`Motive truck location + available hours + trailer/equipment + TorqueAI stop location + appointment + destination + loaded miles + revenue`

to rank feasible assignments and reduce empty miles. Human approval remains required for operational actions.
