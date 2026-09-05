# Fuel invoice review preview

## Purpose

This is the smallest read-only presentation layer on top of the certified
`supplier-price-preview-v3` reconciliation response. It helps a human reviewer
see what needs attention, why, the analytical amount involved, and the stored
supplier quote evidence without changing the underlying reconciliation policy.

The screen is observer-only. It does not import evidence, contact Outlook,
Motive or a supplier, create accounting entries, approve an invoice, make a
payment, or write a reconciliation decision.

## Production evidence used for this slice

On 2026-09-05 the user validated the hosted GET preview for Eco invoice
`U9165021`, Polaris invoice run `4`, covering 2026-08-23 through 2026-08-29 in
USD. The response was HTTP 200, `supplier-price-preview-v3`, `read_only: true`,
and contained 135 lines.

Observed status coverage:

- ULSD: 38 `price_difference`, 6 `match`.
- ULSR: 27 `price_difference`, 3 `match`.
- DEFD: 29 `not_applicable` under the approved DEF price policy.
- MC: 22 `not_applicable`.
- CADV: 10 `not_applicable`.
- Total: 65 price differences, 9 matches, 61 not applicable, zero unresolved.

The completed 65-line difference review produced these signed analytical sums:

- ULSD truck fuel: 38 lines, -0.37269 USD.
- ULSR reefer fuel: 27 lines, +1.66573 USD.
- Combined: 65 lines, +1.29304 USD.

These are analytical comparisons only. They are not confirmed supplier
overcharges, losses, refunds, liabilities, accounting adjustments or payment
approvals.

## Line 66 investigation

Line 66 is the clear exception in the observed invoice. The hosted preview
returned:

- transaction date: 2026-08-26
- product: ULSR
- invoice billed rate: 5.5790 USD/gallon
- applicable supplier ULSD quote: 5.4155 USD/gallon
- rate difference: +0.1635 USD/gallon
- quantity: 10.4 gallons
- analytical impact: +1.70040 USD
- quote date: 2026-08-26
- fallback days: 0

The source invoice independently shows the same TA MORIARTY, NM stop for unit
2218 with ULSD billed at 5.4160 for 71.2 gallons and ULSR billed at 5.5790 for
10.4 gallons. Under MOR's approved policy, Eco ULSR remains reefer fuel but is
compared with the published ULSD supplier rate for the same station/date.
Therefore line 66 belongs in the investigation queue rather than the
precision-sized review group.

A separate receipt for this transaction was not identified in the available
workspace-file search performed for this slice. Do not infer that no receipt
exists. The supplier quote value above remains grounded in the certified hosted
preview and persisted quote provenance returned by that API; the matching
2026-08-26 rate-sheet PDF was not independently reopened from the file Library
in this work session.

## Possible precision-sized differences

The other 64 price differences are each within 0.0005 per gallon in absolute
rate difference and together total -0.40736 USD analytical impact. Both positive
and negative 0.0005 differences occur. No supplier rounding rule has been
certified.

The frontend therefore uses `0.0005` only as an **observed display cue** for a
"possible precision" review group. It is not a reconciliation tolerance and it
does not change `price_difference` or `fallback_difference` status. No line is
auto-approved or silently reclassified.

The review model keeps source decimal strings intact and uses integer-scaled
BigInt arithmetic for its displayed aggregate so the frontend does not
introduce binary floating-point drift into the review total.

## Review screen behavior

The Executive workspace exposes `Fuel Review`. A reviewer supplies an existing
Polaris invoice run ID (or uses `#executive/fuel-review?invoice=<id>`). The page
calls only the existing tenant-scoped GET endpoint:

`/api/v1/fuel/invoices/{invoice_run_id}/price-reconciliation`

The screen presents:

1. **Investigate first** — price/fallback differences outside the observed
   precision-sized band, sorted by absolute analytical impact.
2. **Possible precision differences** — exact nonzero differences at or below
   0.0005 per unit. Backend status is preserved and the UI explicitly says no
   rounding rule or tolerance is assumed.
3. **DEF quantity verification** — DEF remains supplier-price
   `not_applicable`; quantity remains `pending_receipt_and_motive` and displays
   the two required evidence classes: fuel receipt plus Motive fuel entry.
4. **Unresolved evidence** — if a future preview returns unresolved lines, they
   remain a separate evidence queue and are not guessed into another state.
5. Quote evidence identifiers, quote source filename/hash prefix, effective date,
   billed rate, quote rate, quantity, exact rate difference and analytical impact.

This slice intentionally does not add invoice discovery/listing, receipt upload,
Motive matching, supplier actions, persistence of review decisions, or a new
backend status.

## Safety invariants retained

- Supplier matching remains exact and source-backed; no fuzzy matching is added.
- Same-date quote preference and seven-day prior fallback policy are unchanged.
- Future quotes remain prohibited.
- Backend Decimal zero-tolerance comparison is unchanged.
- DEF pricing and quantity policy is unchanged.
- No automated write, payment, provider call, ingestion, Motive reconciliation,
  rounding tolerance or auto-approval is introduced.

## Next evidence gate

Before expanding the workflow beyond this presentation slice, verify the UI
against the hosted run 4 response and inspect line 66 with any available fuel
receipt and corresponding Motive transaction. A supplier rounding convention,
if later obtained from authoritative evidence, requires an explicit policy
change and tests; it must not be inferred from these 64 small differences.
