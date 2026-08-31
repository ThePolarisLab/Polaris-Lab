# BVD Fuel Connector V1 Contract

Status: Proposed implementation contract for human review
Date: 2026-08-30
Owner: Polaris Lab / MOR Logistics
Base main SHA: `e40cbe7d39e48df8950ac7772507a7f43e2849a1`

## Purpose

Define the first provider-specific contract for Pre-Track 4D Gate 2 - Fuel Connector V1 without guessing provider capabilities, credentials, or unsupported fields.

This document does not authorize provider writes, payment actions, fuel-card controls, route optimization, or automatic supplier reconciliation adjustments.

## Provider evidence available

BVD Petroleum has confirmed to MOR Logistics that a REST API is available to pull fuel transactions and supplied its transaction API documentation.

BVD also stated that fields which are not present in the transaction API response - specifically including invoice/statement number and transaction status such as reversals or adjustments - cannot be supplied or pushed through that API.

As of 2026-08-30, production API credentials, the final authentication method, account identifier, rate-limit details, sandbox availability, historical-retention limits, and other certification details are still pending from BVD IT/support.

Separately, BVD already sends MOR Logistics official PCN price-change notices by Outlook email from `application@bvdpetroleum.com`. The observed CAD PCN attachment is a PDF addressed to MOR Logistics Manitoba Limited and contains an effective-date range plus a station-price table.

Eco Petroleum has not yet supplied an API/feed contract and is outside the implementation scope of this provider contract.

## V1 source boundaries

### Source A - BVD transaction REST API

Purpose:
- actual fuel purchases;
- actual purchased quantity;
- actual transaction amount;
- truck/card/driver/location references where BVD returns them;
- later transaction-to-price and transaction-to-invoice reconciliation.

State:
- provider capability confirmed;
- documentation supplied;
- credentials/authentication certification pending;
- no production API code should be enabled until credentials and the exact response contract are verified.

### Source B - BVD PCN station-price notices

Purpose:
- provider-authored station pricing evidence;
- effective-dated MOR contracted/net price comparison;
- later actual-versus-expected price reconciliation.

Observed Outlook source:
- sender: `application@bvdpetroleum.com`;
- subject pattern includes `BVD PCN`, attachment filename and `EFFECTIVE YYYY-MM-DD`;
- one non-inline PDF attachment for the observed CAD message;
- email body itself carries only the notice/effective-date statement; station rows are in the attachment.

Observed CAD PCN table fields:
- Site;
- Name;
- City;
- Prov;
- Cost;
- Freight;
- Base Price;
- FET;
- PFT;
- PCT;
- Local;
- Fuel Price;
- SalesTax;
- InTax Price;
- QST;
- Retail Price;
- Your Price;
- Savings.

The observed document also contains:
- Effective Date range;
- Company Name: MOR LOGISTICS MANITOBA LIMITED.

Provider-authored values must be stored as evidence; Polaris must not reverse-engineer or recompute BVD pricing components when a provider-authored total/value is available.

## Proposed normalized evidence model

The implementation should keep provider-specific raw field interpretation behind a BVD adapter and expose normalized tenant-scoped records to later Track 4D logic.

### FuelPriceEvidence

Required identity/provenance:
- `organization_id`;
- `provider` = `bvd`;
- `source_type` = `pcn_outlook_pdf`;
- source Outlook message ID;
- source attachment ID or stable attachment fingerprint;
- source filename;
- source received timestamp;
- effective start date;
- effective end date when provider supplies it;
- currency;
- provider location/site ID;
- provider location name;
- city;
- province/state;
- captured timestamp.

Observed price facts, nullable where provider does not supply them:
- cost;
- freight;
- base price;
- federal excise/fuel-tax component;
- provincial fuel-tax component;
- provincial carbon-tax component;
- local-tax component;
- fuel price;
- sales tax;
- in-tax price;
- QST;
- retail price;
- MOR contracted/provider `Your Price`;
- savings.

The first implementation must preserve provider decimal precision and currency provenance. No cross-currency conversion belongs in the provider adapter.

### FuelTransaction

Normalized target fields for the REST API adapter, only when returned authoritatively by BVD:
- `organization_id`;
- provider transaction ID;
- transaction timestamp;
- station/provider location ID and location text;
- quantity;
- quantity unit;
- product/grade;
- unit price if supplied;
- gross amount if supplied;
- discounts/rebates if supplied;
- taxes/fees if supplied;
- net/total amount;
- currency;
- truck/unit reference if supplied;
- card reference, masked where appropriate;
- driver reference if supplied;
- odometer if supplied;
- authorization/reference number if supplied;
- invoice/statement reference only if supplied by the API;
- reversal/adjustment/status only if supplied by the API;
- provider/source capture timestamp.

Polaris must not fabricate invoice identifiers or infer reversal status from amount signs unless a separate reviewed accounting rule explicitly authorizes that behavior.

### FuelSyncHistory / checkpoint state

Each provider/source path should record tenant-scoped durable execution evidence including:
- provider;
- resource/source type;
- mode;
- started/completed timestamps;
- success/failure state;
- bounded record counts;
- last safe error category/code;
- source/cursor/checkpoint position where applicable;
- replay/idempotency evidence;
- secrets exposed = false.

No process-local checkpoint should be treated as durable production state.

## Idempotency and source validation

PCN price ingestion should fail closed when the source contract is ambiguous.

Minimum candidate rules:
- configured Outlook folder(s) only;
- exact approved sender/domain;
- subject pattern must match the BVD PCN contract;
- exactly one approved, non-inline attachment for the selected price notice;
- attachment company identity must match MOR Logistics Manitoba Limited;
- effective date must be present;
- expected table headers must match the reviewed contract;
- source message/attachment identity must prevent duplicate imports;
- changed provider documents for the same effective date must remain auditable rather than silently overwriting provenance.

REST transaction ingestion should use the provider transaction ID plus organization/provider identity as the principal idempotency boundary where the certified API contract supports it.

## Read-only and security boundary

Fuel Connector V1 is Observer/Advisory only.

Allowed:
- read approved provider evidence;
- normalize and persist tenant-scoped records;
- calculate explicitly reviewed comparison/difference metrics from stored provider facts;
- surface price/quantity exceptions and provenance;
- provide operator recovery guidance.

Not allowed:
- change BVD/Eco account settings;
- authorize or block fuel cards;
- modify supplier transactions;
- create supplier invoices or payments;
- send supplier messages automatically;
- perform route optimization or automatic fueling instructions in this gate;
- expose credentials, raw tokens or uncontrolled raw provider payloads.

## Reconciliation boundary

Gate 2 V1 should first establish trusted evidence, then reconcile.

Initial comparison targets:
1. actual transaction location + timestamp against the effective provider price evidence;
2. actual purchased quantity against provider transaction quantity/invoice facts where available;
3. actual charged unit/total amount against provider-authored pricing components where the source contracts make the comparison valid;
4. supplier invoice/reference facts only where a provider source supplies them authoritatively.

Any derived variance must preserve both source values and explain the comparison basis. A variance must never overwrite provider-authored facts.

## Implementation sequence

### Stage 1 - provider contract and fixture certification
- approve this contract;
- obtain at least one reviewed CAD and one reviewed USD PCN fixture;
- decide the supported PDF extraction dependency or obtain a machine-readable PCN feed from BVD;
- lock expected headers/company/effective-date behavior with parser tests.

### Stage 2 - BVD PCN durable price ingestion
- add tenant-scoped fuel price tables and sync/import history;
- add strict BVD PCN parser;
- add bounded manual Outlook import first;
- prove replay/idempotency and provenance;
- expose passive status/read API;
- only then consider scheduled ingestion using existing governed Outlook patterns.

### Stage 3 - BVD transaction API certification
- obtain credentials and exact authentication method from BVD;
- verify company/account identity;
- capture a sanitized sample response/schema;
- certify pagination/date filters/rate limits and historical range;
- implement read-only durable transaction ingestion and checkpoints;
- do not persist uncontrolled raw payloads as the Track 4D contract.

### Stage 4 - price/quantity reconciliation
- compare trusted BVD price evidence and transaction evidence;
- surface explainable mismatches;
- retain source provenance;
- no supplier mutation or accounting entry.

### Stage 5 - Eco provider adapter
- begin only after Eco supplies an official supported API/feed/file contract;
- map Eco into the same normalized FuelPriceEvidence / FuelTransaction boundary without weakening provider-specific validation.

## Gate 2 V1 acceptance outcome

Fuel Connector V1 is ready for cross-connector use only when Polaris can independently answer:

> Where did MOR fuel, how much did it buy, what provider-authored price was effective, what was MOR charged, and is there a source-supported price or quantity discrepancy?

Every answer must be tenant-scoped, durable, source-traceable and read-only.
