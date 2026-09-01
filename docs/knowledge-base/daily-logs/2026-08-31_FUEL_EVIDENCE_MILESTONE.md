# Polaris Knowledge Base — Fuel Evidence Milestone

**Milestone date:** 2026-08-31  
**Status updated:** 2026-09-01

## Final State

Polaris crossed a meaningful Pre-Track 4D / Fuel Connector V1 milestone. BVD and Eco quoted-price evidence and supplier-invoice evidence now have durable, tenant-scoped ingestion foundations and trusted read-only Outlook source paths. BVD CAD/USD and Eco CAD/USD quoted-price imports have been production-certified with exact-file replay. Trusted weekly BVD and Eco invoice ingestion was merged in PR #274. The system remains evidence-first and read-only; reconciliation judgments and supplier actions are not enabled.

## Official Decisions

- Provider-authored fuel values are preserved as evidence; Polaris does not reverse-engineer supplier totals at ingestion time.
- BVD transaction API evidence and BVD PCN quoted-price evidence remain separate source contracts behind one normalized fuel evidence boundary.
- Eco CAD and USD price reports share the fuel-price evidence store, while supplier-specific source fields remain explicit.
- Quote evidence and invoice evidence remain separate until a reviewed reconciliation contract is implemented.
- Raw PDF bytes are not persisted; durable provenance and SHA-256 replay identity are retained.
- Fuel V1 remains Observer/Advisory and read-only: no supplier writes, card controls, payments, route optimization, or automated fueling instructions.

## Principles Reaffirmed

- Certify real provider evidence before broad automation.
- Fail closed when provider layouts or identities do not match the certified contract.
- Preserve exact provider-authored decimal text rather than silently recalculating accounting facts.
- Keep tenant ownership and replay protection at every durable evidence boundary.
- Treat production activation as a separate gate from implementation merge.

## Current Roadmap State

- BVD PCN contract definition: complete.
- Durable BVD CAD/USD PCN price evidence ingestion: merged and production-certified.
- Trusted BVD Outlook quoted-price import: merged and production-certified.
- BVD daily scheduler foundation: merged but remains gated for controlled activation.
- Eco CAD/USD price evidence foundation: merged.
- Trusted Eco Outlook quoted-price import: merged and production-certified for CAD and USD.
- Supplier invoice evidence foundation for BVD and Eco: merged.
- Trusted BVD/Eco weekly invoice ingestion from Outlook: merged in PR #274.
- Production certification of invoice ingestion: pending.
- Quote-vs-invoice and Motive reconciliation: not implemented.

## Engineering Decisions

BVD CAD and USD are treated as distinct certified provider layouts rather than forcing one schema interpretation. The certified USD layout contains 605 ULSD station rows and preserves provider `Your Price` as the comparison price. The certified CAD layout contains 92 station rows.

Eco uses the shared fuel-price evidence model. For USD, provider `Your Price` is the comparison field. For CAD, provider `Total Price` is the comparison field while `Price` and `GST/HST` remain separately preserved evidence. Production certification imported 350 Eco USD rows and 67 Eco CAD rows with idempotent replay.

The BVD scheduler uses a dedicated machine-auth secret and dual default-off gates. GitHub Actions supplies redundant wake-up opportunities; exact provider-file replay remains idempotent through tenant + supplier + SHA-256 identity. Production scheduling must not be assumed enabled without explicit configuration verification.

Supplier invoice evidence has dedicated import-run and line-evidence persistence. BVD fuel invoices distinguish Truck Fuel, Reefer Fuel and DEF. Express-Codes-only documents are skipped during Outlook selection and are not persisted as fuel invoices. Eco invoice evidence preserves provider product, quantity, retail/unit/billed price, taxes, discounts, fees, amounts and unit identity. Only the approved optional leading-`M` truck normalization is applied.

PR #274 added authenticated manual Outlook import routes for the newest trusted BVD fuel invoice and separate Eco CAD/USD weekly invoices. Outlook message ID, attachment ID, filename and received timestamp are preserved. Outlook remains read-only, and no scheduler, supplier API, Motive call or reconciliation calculation was added.

## Research / Verification Notes

- BVD CAD quoted-price evidence: 92 station rows, production import and exact replay certified.
- BVD USD quoted-price evidence: 605 ULSD station rows, production import and exact replay certified.
- Eco CAD quoted-price evidence: 67 rows, production import and exact replay certified.
- Eco USD quoted-price evidence: 350 rows, production import and exact replay certified.
- Eco CAD production cross-check showed invoice Unit price `1.8520` / Billed price `2.0928` aligning with rate-sheet Price `1.852` / Total Price `2.0928`.
- Real invoice evidence includes BVD fuel invoice 988495, newer BVD Express-only invoice 988488, Eco USD invoice U9165021 with 112 transaction rows, and Eco CAD invoice C9193095 with 4 transaction rows.
- Live Outlook evidence confirmed BVD invoice sender `applications@bvdpetroleum.com` and Eco invoice sender `Billing@ecopetroleum.ca`.

## Completed Work

- Merged PR #264 — BVD Fuel Connector V1 contract.
- Merged PR #265 — durable BVD PCN price evidence ingestion.
- Merged PR #266 — trusted manual BVD Outlook quoted-price import.
- Merged PR #267 — certified BVD USD PCN layout correction.
- Merged PR #268 — gated BVD PCN daily scheduler foundation.
- Merged PR #269 — Eco price evidence foundation.
- Merged PR #271 — trusted Eco Outlook quoted-price import.
- Merged PR #272 — durable BVD + Eco supplier invoice evidence foundation.
- Merged PR #274 — trusted BVD + Eco weekly invoice ingestion from Outlook.

## Remaining Gates

1. Production-certify BVD fuel-invoice import and exact replay.
2. Production-certify Eco CAD invoice import and exact replay.
3. Production-certify Eco USD invoice import and exact replay.
4. Verify production deployment and database migration state before certification.
5. Keep the BVD scheduler disabled unless its backend secret, organization slug, backend flag and repository variable are explicitly configured and a manual dispatch succeeds.
6. Define and review supplier quote ↔ supplier invoice price reconciliation as a separate PR.
7. Define Motive ↔ invoice truck, quantity and location reconciliation as a later separate PR.
8. Keep Money Code/EFS reconciliation, supplier writes, payments, card control and broader fuel automation deferred until explicitly designed and authorized.
