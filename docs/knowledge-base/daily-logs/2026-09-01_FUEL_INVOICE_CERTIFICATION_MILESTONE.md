# Polaris Knowledge Base — Fuel Invoice Certification Milestone

**Date:** 2026-09-01

## Final State

Fuel Connector V1 advanced from durable supplier-invoice evidence to trusted Outlook invoice ingestion with partial controlled production certification. BVD and Eco CAD invoice paths are production-verified for import plus exact replay. Eco USD parsing was corrected after production evidence exposed legitimate blank cells and transaction continuation across PDF page boundaries; the corrected contract is merged, but Eco USD remains pending a separately authorized post-deploy production import/replay.

## Official Decisions and Principles

- Outlook remains read-only (`Mail.Read`) and supplier invoice ingestion remains manual; no scheduler or automatic polling is authorized for invoices.
- Provider-authored invoice values and provenance remain evidence. Polaris does not recalculate supplier totals or begin quote/invoice reconciliation in this milestone.
- Malformed or ambiguous provider documents fail closed rather than being silently skipped or normalized into invented values.
- Legitimately absent Eco USD fields such as Money Code driver/city/state are preserved as NULL.
- PDF page boundaries are presentation artifacts, not transaction boundaries; transaction halves may be joined only under the certified structural contract after repeated headers are removed.
- Application-level import status is authoritative. Certification tooling must not treat HTTP 200 alone as success when the payload reports `import_failed`.

## Engineering Decisions

PR #274 connected the existing durable BVD/Eco invoice evidence layer to trusted Outlook sources. BVD selection skips newer Express-only invoices and continues to the newest valid Fuel Card Transactions invoice. Eco selection strictly separates CAD and USD weekly invoice messages. Existing tenant isolation and tenant + supplier + SHA-256 replay protection are preserved.

PR #275 corrected the Eco USD parser without weakening authentication, tenant isolation, supplier-value preservation, Outlook access, or scheduling boundaries. It preserves legitimate blanks, joins valid page-continuation transaction halves, and rejects malformed or unfinished masked-card rows.

## Research / Verification Notes

Controlled production certification established:

- BVD invoice `992481`: 30 rows imported successfully and exact replay succeeded.
- Eco CAD invoice `C9193095`: 4 rows imported successfully and exact replay succeeded.
- Eco USD initially failed closed with `source_contract_error`.

Reproduction against the exact Eco USD Outlook PDF showed the prior 112-row expectation was incomplete. The corrected parser produces 135 rows: 44 truck fuel, 30 reefer fuel, 29 DEF, 22 Money Code, and 10 OTHER. Offline completeness checks preserve provider Final AMT total `33,588.14` and discounts `2,859.89`; local real-PDF SQLite import/replay completed without duplicates and tenant isolation remained intact.

The Eco USD production path is **not yet production-certified** after the parser correction.

## Roadmap Change / Completed Work

- Trusted BVD invoice Outlook ingestion: merged and production-certified for representative import/replay.
- Trusted Eco CAD invoice Outlook ingestion: merged and production-certified for representative import/replay.
- Eco USD source-contract defect: root-caused and parser correction merged.
- Durable provenance and exact-file replay protections remain intact.
- No quote-vs-invoice reconciliation, Motive matching, invoice scheduling, supplier writes, card controls, or payments were activated.

## Remaining Gates

1. Deploy the merged Eco USD parser correction.
2. Obtain approval for an Eco USD-only controlled production import and exact replay.
3. Verify application-level `import_success` / replay status, 135-row completeness, preserved supplier totals, and no duplicate durable evidence.
4. Only after Eco USD certification passes, separately review quote-vs-invoice, quantity/location, applicable-price, and Motive vehicle reconciliation.
5. Keep invoice scheduling and all supplier-side automation outside scope until separately designed and authorized.
