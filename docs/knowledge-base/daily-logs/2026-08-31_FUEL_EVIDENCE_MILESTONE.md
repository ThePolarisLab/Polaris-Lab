# Polaris Knowledge Base — Fuel Evidence Milestone

**Date:** 2026-08-31

## Final State

Polaris crossed a meaningful Pre-Track 4D / Fuel Connector V1 milestone: BVD and Eco provider-authored fuel price evidence now have durable, tenant-scoped ingestion foundations, trusted read-only Outlook source paths, and the first supplier-invoice evidence model. The system remains evidence-first and read-only; reconciliation judgments and supplier actions are not yet enabled.

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

## Roadmap Changes

- BVD PCN contract definition: complete.
- Durable BVD CAD/USD PCN price evidence ingestion: merged.
- Trusted BVD Outlook import path: merged.
- BVD daily scheduler foundation: merged but remains gated for controlled activation.
- Eco CAD/USD price evidence foundation: merged.
- Trusted Eco Outlook import path: merged; production CAD/USD certification remains the next activation gate.
- Supplier invoice evidence foundation for BVD and Eco: merged.
- Quote-vs-invoice/Motive reconciliation: not yet implemented.

## Engineering Decisions

BVD CAD and USD are treated as distinct certified provider layouts rather than forcing one schema interpretation. The USD contract was corrected from production evidence after the first controlled attempt failed closed; the certified USD layout contains 605 ULSD station rows and preserves provider `Your Price` as the comparison price.

Eco uses the shared fuel-price evidence model. For USD, provider `Your Price` is the cross-provider contracted-price field. For CAD, provider `Total Price` is the comparison field while `Price` and `GST/HST` remain separately preserved evidence.

The BVD scheduler uses a dedicated machine-auth secret and dual default-off gates. GitHub Actions supplies redundant wake-up opportunities; exact provider-file replay remains idempotent through tenant + supplier + SHA-256 identity.

Supplier invoice evidence now has dedicated import-run and line-evidence persistence. BVD fuel invoices distinguish Truck Fuel, Reefer Fuel and DEF and reject Express-Codes-only invoices as `non_fuel_invoice`. Eco invoice evidence preserves provider product, quantity, retail/unit/billed price, taxes, discounts, fees, amounts and unit identity. Only the approved optional leading-`M` truck normalization is applied.

## Research / Verification Notes

- Real BVD CAD PCN evidence certified a 92-station provider layout.
- Controlled BVD USD evidence exposed a different official 15-column layout with 605 ULSD station rows; the parser was corrected rather than weakening validation.
- Real Eco USD price evidence contains 350 ULSD site rows; real Eco CAD price evidence contains 67 ULSD site rows.
- Eco CAD production cross-check showed invoice Unit price `1.8520` / Billed price `2.0928` aligning with prior applicable rate-sheet Price `1.852` / Total Price `2.0928`, supporting the provider-authored Total Price comparison contract.
- Real invoice evidence inspected includes a BVD fuel invoice, a BVD Express-Codes-only invoice that must not be treated as fuel, an Eco weekly USD invoice with 112 transaction rows, and an Eco weekly CAD invoice with 4 transaction rows.

## Completed Work

- Merged PR #264 — BVD Fuel Connector V1 contract.
- Merged PR #265 — durable BVD PCN price evidence ingestion.
- Merged PR #266 — trusted manual BVD Outlook import path.
- Merged PR #267 — certified BVD USD PCN layout correction.
- Merged PR #268 — gated BVD PCN daily scheduler foundation.
- Merged PR #269 — Eco price evidence foundation.
- Merged PR #271 — trusted Eco Outlook price import path.
- Merged PR #272 — durable BVD + Eco supplier invoice evidence foundation.

## Remaining Gates

1. Complete controlled production certification/replay for the latest BVD USD path if not already verified after deployment.
2. Configure the BVD scheduler backend secret, organization slug and backend flag; perform one manual workflow dispatch before enabling the scheduled repository variable.
3. Production-certify Eco CAD import + exact replay, then Eco USD import + exact replay before considering Eco scheduling.
4. Wire trusted BVD/Eco weekly invoice emails from Outlook into the merged invoice parsers and certify representative invoice imports + replay.
5. Define and review quote-vs-invoice reconciliation, quantity/location matching, applicable-price fallback, and Motive vehicle evidence as separate gates.
6. Keep Money Code/EFS reconciliation, supplier writes, payment/card control, and broader fuel automation deferred until explicitly designed and authorized.
