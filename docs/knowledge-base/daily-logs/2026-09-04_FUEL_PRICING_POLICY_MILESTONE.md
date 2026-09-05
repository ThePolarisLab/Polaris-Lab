# Fuel Pricing Policy Milestone — 2026-09-04

## Final state

Fuel Connector V1 now has an approved supplier-product pricing policy for reefer fuel and DEF in the read-only supplier price-reconciliation preview. PR #279 is merged into `main` and advances the policy contract to `supplier-price-preview-v2`.

## Official decisions

- Eco ULSR and BVD TF remain classified as reefer fuel, but use the supplier's published ULSD rate for the same station/effective-date comparison.
- BVD truck fuel TA continues to map to the published ULSD rate.
- BVD/Eco do not publish DEF rates. Valid DEF invoice lines therefore use the invoice billed price as the approved price basis; supplier-price comparison is `not_applicable` rather than a fabricated match.
- DEF price basis does not certify DEF quantity. Quantity remains pending until both fuel-receipt evidence and the corresponding Motive fuel entry are independently verified.
- Money Code and OTHER remain outside supplier fuel-price comparison.

## Principles reaffirmed

- Preserve the provider/invoice product classification even when business policy selects another published supplier rate for comparison.
- Separate price verification from quantity verification.
- Never infer an unpublished supplier rate.
- Keep station matching strict, tenant-scoped, provenance-backed and fail-closed.
- Reconciliation remains advisory/read-only: no provider, Motive, Outlook, payment, scheduler, accounting or production-data mutation is introduced by this policy.

## Roadmap change

The earlier unresolved reefer-to-ULSD question is closed by an explicit MOR policy rather than a parser heuristic. DEF is also removed from the supplier-rate matching backlog: its price basis is now formally invoice-authored, while its quantity-evidence workflow becomes the remaining gate.

## Engineering decisions

The reconciliation policy is versioned as `supplier-price-preview-v2`. Eco `ULSR` and BVD `TF` select an explicit `ULSD` quote without changing the durable invoice category/product. Valid DEF rows return `not_applicable` with reason `supplier_def_rate_not_published`, identify `invoice_billed_price_by_policy` as the price basis, and expose quantity status `pending_receipt_and_motive` with required evidence classes `fuel_receipt` and `motive_fuel_entry`.

## Verification notes

PR #279 merged after 1,216 full-backend tests and 73 focused fuel import/reconciliation tests passed. It introduced no migration and no production-data mutation.

## Completed work

- Merged PR #279: `feat(fuel): apply approved reefer and DEF pricing policy`.
- Advanced the read-only reconciliation contract to V2.
- Closed the reefer-rate interpretation decision for Eco ULSR and BVD TF.
- Formalized DEF price-basis and quantity-evidence separation.

## Remaining gates

- After deployment, rerun the read-only reconciliation for Eco USD invoice `U9165021` and verify the V2 classifications/results against persisted evidence.
- Do not mark DEF quantity verified until both the fuel receipt and corresponding Motive fuel entry are matched.
- Keep durable financial approval, accounting adjustments, supplier writes/payments, automated reconciliation actions and other Fuel automation outside this gate unless separately designed and authorized.
