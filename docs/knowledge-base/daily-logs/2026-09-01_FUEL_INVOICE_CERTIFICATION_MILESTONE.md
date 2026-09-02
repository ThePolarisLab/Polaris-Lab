# Polaris Knowledge Base — Fuel Invoice Certification Milestone

**Date:** 2026-09-01

**Certification status corrected:** 2026-09-02

## Final State

Fuel Connector V1 advanced from durable supplier-invoice evidence to trusted Outlook invoice ingestion with controlled production certification for representative BVD, Eco CAD and Eco USD invoices. BVD and Eco CAD invoice paths are production-verified for import plus exact replay. After the Eco USD parser correction was merged and deployment confirmed, the authorized verification established a completed 135-row import and an API idempotent replay. This certifies the representative invoice-ingestion paths, not price reconciliation or unattended operation.

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
- Eco USD invoice `U9165021`: the post-deploy API request returned HTTP 200, `idempotent_replay`, 135 rows and no error. The script stopped because its first-call assertion expected `import_success`; it did not execute its second request. This was an assertion mismatch, not evidence of a failed import.

Reproduction against the exact Eco USD Outlook PDF showed the prior 112-row expectation was incomplete. The corrected parser produces 135 rows: 44 truck fuel, 30 reefer fuel, 29 DEF, 22 Money Code, and 10 OTHER. Offline completeness checks preserve provider Final AMT total `33,588.14` and discounts `2,859.89`; local real-PDF SQLite import/replay completed without duplicates and tenant isolation remained intact.

The subsequent authorized read-only database inspection confirmed Eco USD import run `4` for tenant `org-mor-logistics` was completed at `2026-09-01T20:27:52.611Z`, with no error and `records_read = records_inserted = 135`. Its 135 distinct line numbers span 1–135, with no duplicate or mismatched evidence found for that invoice and source. Outlook message and attachment provenance were populated. The stored source SHA-256 `fbbe150c2f7a504d73535bc3e033bcfc16742a9b5dc0176c31e68c1668fd8a2f` matched the exact PDF inspected locally.

Together, the completed durable import and API replay close the representative Eco USD invoice-ingestion certification gate. The offline supplier-total checks above are not a claim that the stopped API script performed a new import or independently rechecked production totals.

## Roadmap Change / Completed Work

- Trusted BVD invoice Outlook ingestion: merged and production-certified for representative import/replay.
- Trusted Eco CAD invoice Outlook ingestion: merged and production-certified for representative import/replay.
- Eco USD source-contract defect: root-caused and parser correction merged.
- Trusted Eco USD invoice ingestion: representative 135-row completed production import and idempotent replay verified.
- Durable provenance and exact-file replay protections remain intact.
- No quote-vs-invoice reconciliation, Motive matching, invoice scheduling, supplier writes, card controls, or payments were activated.

## Remaining Gates

1. Review the separately authorized read-only supplier price reconciliation preview in PR #277; it does not depend on merging this documentation PR.
2. Require passing exact-head CI and human merge approval before deploying that preview, then certify its GET response separately against stored evidence.
3. Keep quantity/location and Motive vehicle reconciliation outside the current preview scope pending separate review.
4. Keep invoice scheduling and all supplier-side automation outside scope until separately designed and authorized.
