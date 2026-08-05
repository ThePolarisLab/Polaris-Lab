# Financial Trust Documentation

Status date: 2026-08-05  
Scope: RC-1 Executive Financial KPI Standardization

## Standard

QuickBooks is the Financial System of Record for executive financial KPIs. Polaris does not calculate exchange rates, aggregate currencies, or derive accounting totals. Polaris reads, stores, and displays QuickBooks-owned report totals.

For Balance Sheet executive KPIs, Polaris uses consolidated QuickBooks Balance Sheet total rows. Aged Receivables and Aged Payables reports remain reconciliation evidence and subledger diagnostics, not the executive dashboard source for consolidated Balance Sheet KPIs.

## Executive KPI Sources

| KPI | QuickBooks authoritative source | Polaris behavior |
|---|---|---|
| Revenue | Profit and Loss report | Unchanged |
| Expenses | Profit and Loss report | Unchanged |
| Gross Profit | Profit and Loss report | Unchanged |
| Net Income | Profit and Loss report | Unchanged |
| Cash Position | Balance Sheet report | Existing Balance Sheet parsing retained |
| Accounts Receivable | Balance Sheet `Total Accounts Receivable ...` row | Display QuickBooks total exactly |
| Accounts Payable | Balance Sheet `Total Accounts Payable ...` row | Display QuickBooks total exactly |

## Audit Metadata

The backend exposes metadata for executive KPI diagnostics, including value, report name, report label, snapshot ID, capture time, report period end, accounting basis, currency, and organization slug. The current frontend is not required to display this metadata.

## RC-1 Status

The approved RC-1 principle is: QuickBooks owns accounting; Polaris owns executive intelligence. Certification evidence should compare Polaris dashboard KPIs to the corresponding QuickBooks authoritative report rows, not to child account rows or manually aggregated currency balances.
