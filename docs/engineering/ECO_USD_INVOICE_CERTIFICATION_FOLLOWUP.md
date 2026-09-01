# Eco USD invoice certification follow-up

## Status: production certification remains blocked

The user-approved production run after PRs #273/#274 produced:

| Source | Invoice | First call | Repeat call |
| --- | --- | --- | --- |
| BVD CAD | 992481 | import_success, 30 rows | idempotent_replay |
| Eco CAD | C9193095 | import_success, 4 rows | idempotent_replay |
| Eco USD | unavailable on failed result | import_failed, zero rows | import_failed, zero rows |

All six HTTP responses were 200. HTTP success alone is not an import success.
The console runner incorrectly continued after an application-level failure.
Future certification must stop unless the initial status is import_success
(or an explicitly reviewed pre-existing idempotent_replay) and each repeat is
idempotent_replay with replayed=true and the same invoice/currency/count.
records_inserted on replay describes the original run, not new inserts.

## Reproduced source and root cause

Read-only Outlook retrieval found the August 30 email from
Billing@ecopetroleum.ca, subject Fuel Invoice; 08-23_08-29_USD, with one PDF:
Mor Logistics Manitoba Limited_08-23_08-29_USD.pdf.
The PDF identifies MOR Logistics and invoice U9165021.

Using the pinned pypdf 5.9.0 against the actual PDF reproduces the rejection:

- 22 money-code rows omit both location cells.
- Three of those rows also omit the driver name.
- One DEF transaction has its upper half on page 9 and lower half on page 10,
  separated by repeated table headers.

The old parser rejected blank location rows and would silently skip missing-driver
rows and the trailing split transaction. This is a parser/source-contract defect;
the successful BVD/CAD results do not indicate a deployment or general auth failure.

## Narrow correction and local evidence

Recognize only the observed USD MC absent-driver/absent-location forms, retaining
NULL values rather than invented locations or names. Preserve all monetary fields
and existing categories. Join transaction halves across pages after removing only
recognized table headers. Reject malformed masked-card rows and unfinished rows,
instead of omitting them.

The corrected local parse contains 135 transactions:

| Category | Rows |
| --- | ---: |
| TRUCK_FUEL | 44 |
| REEFER_FUEL | 30 |
| DEF | 29 |
| MONEY_CODE | 22 |
| OTHER | 10 |

As a local completeness check only, summing the preserved Final AMT fields gives
33,588.14, matching the supplier's Due Amount; discounts sum to 2,859.89,
matching Total Discount. No accounting or reconciliation calculation is added
to production code. The original expectation of 112 transactions was incomplete.

Regression tests cover absent cells, cross-page continuation, malformed rows,
missing financial/location fields, persistence of NULLs and idempotent replay.
Real provider PDFs and personal transaction details are not committed.

## Next gate

After review, exact-head CI and a human merge, verify deployment and obtain
approval for an Eco USD-only import and exact replay. Expect invoice U9165021
and 135 rows only if that exact source remains the newest selected PDF.
Do not repeat already successful BVD/CAD imports unless their code/source needs
separate verification. No production certification is claimed by local tests.
No scheduler, auth, tenant isolation, provider writes, payments or reconciliation
changes are part of this correction.
