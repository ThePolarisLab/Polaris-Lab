# Fuel Review discrepancy treatment

## Decision

Polaris separates technical reconciliation results from human review disposition and from accounting treatment.

A detected `price_difference` remains a `price_difference` even when a reviewer accepts it. Manual approval is a review decision only; it does not rewrite supplier evidence, change the supplier quote, alter analytical impact, create an accounting entry, approve payment, or establish supplier liability.

## Review dispositions

- `not_reviewed`
- `approved_no_action`
- `evidence_required`
- `supplier_inquiry_required`
- `confirmed_overcharge`
- `confirmed_undercharge`
- `credit_requested`
- `credit_received`
- `accounting_posted`
- `reopened`

This implementation slice adds the bounded `approved_no_action` and `reopened` workflow only. Financial-claim dispositions remain future work and must not be inferred from analytical differences.

## Manual approval

A reviewer with organization write permission may approve an individual price discrepancy.

Approval records an append-only review event with:

- organization
- invoice run and invoice line
- action/disposition
- reviewer identity and role
- UTC timestamp
- optional reason
- immutable snapshot of technical status, billed rate, supplier quote, rate difference, analytical impact, and policy version at approval time

For differences within the observed `0.0005` per-unit presentation band, a reason may be omitted. This is convenience only and does not certify a supplier rounding policy.

For differences outside that band, a short reason is required before `approved_no_action` can be recorded.

## Bulk precision approval

The Fuel Review screen may offer **Approve all precision discrepancies**. It applies only to currently unapproved, non-zero `price_difference`/`fallback_difference` lines whose absolute rate difference is `<= 0.0005` per unit.

Bulk approval records one append-only event per line. It does not create a tolerance rule and does not convert those lines to matches.

## Reopen

An approved discrepancy may be reopened. Reopening adds another audit event; it never deletes or edits the prior approval. The current review state is derived from the latest event for the line.

## Accounting boundary

Analytical impact, confirmed discrepancy, and recovered/credited amount are distinct concepts.

This review workflow does not post QuickBooks entries, modify AP, change supplier balances, request credits, contact suppliers, reconcile Motive, or authorize payment.
