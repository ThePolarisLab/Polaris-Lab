# Polaris Knowledge Base — QuickBooks Financial Reconciliation Milestone

**Date:** 2026-08-30

## Final State

Polaris restored the read-only QuickBooks financial overview in the Executive Workspace and closed the final known KPI reconciliation gap in the underlying executive-summary mapping.

Production reconciliation for **2026-01-01 through 2026-08-30**, **Accrual**, **CAD** confirmed that Revenue, Total Expenses, Net Income, Cash Position, Accounts Receivable, and Accounts Payable match QuickBooks exactly. Gross Profit was verified in QuickBooks at **$3,578,117.10**; Polaris had returned `null` because the provider report exposed the value through the QuickBooks-authored `GrossProfit` group rather than the visible summary-label path. Merged PR #256 adds that provider-authored group as a fallback while preserving the existing visible-label lookup first.

## Official Decisions and Principles

- QuickBooks remains authoritative for financial KPI values; Polaris does not independently calculate Gross Profit.
- Financial presentation is read-only, tenant-scoped, and backed by durable Polaris snapshots.
- Provider synchronization remains in the governed Connectors surface; the Financial page exposes no sync/write action.
- Exact cents, accounting basis, currency, reporting period, synchronization time, and report provenance remain visible for reconciliation.
- Financial mappings fail closed when the required QuickBooks-authored value is unavailable.

## Roadmap / Architecture Change

Merged PR #255 restores a dedicated `Financial` executive route displaying seven QuickBooks-backed KPIs: Revenue, Total Expenses, Gross Profit, Net Income, Cash Position, Accounts Receivable, and Accounts Payable.

Merged PR #256 closes the remaining Gross Profit mapping defect without adding accounting aggregation, FX logic, provider writes, schema changes, permissions changes, or additional provider calls.

## Engineering Decisions

Gross Profit resolution preserves the existing visible `Gross Profit` label lookup. Only when that label is unavailable does Polaris read the QuickBooks-authored `GrossProfit` report group summary. If neither source supplies a value, the metric remains unavailable rather than being reconstructed inside Polaris.

The Executive Financial page continues to consume only `/api/v1/qbo/executive-summary`; it does not trigger a QuickBooks synchronization.

## Research / Verification Notes

Production reconciliation established exact QuickBooks agreement for six of seven displayed KPIs and identified the seventh discrepancy as a report-shape interpretation issue rather than an accounting-value disagreement. The verified QuickBooks Gross Profit for the reconciliation period is **$3,578,117.10**.

Focused regression coverage now includes the normal visible Gross Profit label, the `GrossProfit` group fallback, and fail-closed behavior when neither provider-authored source exists.

## Completed Work

- Merged PR #255: restored the read-only QuickBooks Financial executive surface.
- Reconciled the seven Financial KPIs against matching QuickBooks reports for the 2026-01-01 through 2026-08-30 Accrual/CAD period.
- Isolated the Gross Profit null to the provider report-group shape.
- Merged PR #256: added the QuickBooks `GrossProfit` group fallback while preserving existing governance and safety boundaries.

## Remaining Gates

After deployment of the merged Gross Profit fix, refresh the existing Financial page **without triggering a new QuickBooks sync** and confirm that Gross Profit resolves from the already-stored snapshot to the verified **$3,578,117.10** value. If that production display check passes, no known seven-KPI reconciliation gap remains for this certified period.

Any future accounting metric, foreign-exchange treatment, write capability, automated interpretation, alerting, or cross-connector financial intelligence remains a separate reviewed gate.