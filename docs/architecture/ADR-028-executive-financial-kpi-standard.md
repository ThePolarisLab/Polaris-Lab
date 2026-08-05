# ADR-028: Executive Financial KPI Standard

Status: Accepted  
Date: 2026-08-05  
Owner: Polaris Lab  
Standard: PES-001

## Context

RC-1 financial trust audits for Accounts Receivable and Accounts Payable found that the executive dashboard was reading child Balance Sheet account rows such as `Accounts Receivable (A/R)` and `Accounts Payable (A/P)`. In multi-currency QuickBooks companies, QuickBooks may also report sibling foreign-currency accounts and consolidated `Total ...` rows after applying QuickBooks-owned accounting rules and currency conversion.

Polaris must not reproduce QuickBooks accounting logic. Polaris must preserve QuickBooks as the Financial System of Record and display the report values QuickBooks has already calculated.

Follow-up RC-1 production evidence found QuickBooks report labels that differ by report/company shape while still representing consolidated QuickBooks-authored totals. The Profit and Loss footer may be labelled `Profit`, and the Balance Sheet consolidated cash line may be labelled `Total Cash and Cash Equivalent`.

## Decision

Executive Dashboard financial KPIs sourced from the Balance Sheet must display consolidated Balance Sheet totals exactly as reported by QuickBooks.

Polaris will:

- read QuickBooks report payloads through the production Python FastAPI QuickBooks connector;
- store report payloads in tenant-owned `financial_snapshots` records;
- parse executive Balance Sheet KPIs from QuickBooks `Total ...` rows;
- accept QuickBooks-authored Profit and Loss footer labels, including `Profit`, when mapping Net Income;
- accept QuickBooks-authored consolidated Balance Sheet cash labels, including `Total Cash and Cash Equivalent`, when mapping Cash Position;
- expose audit metadata with each backend KPI response;
- avoid exchange-rate calculation, currency aggregation, or accounting derivation inside Polaris.

QuickBooks owns:

- exchange rates;
- currency conversion;
- accounting basis;
- account hierarchy;
- consolidated Balance Sheet totals;
- Profit and Loss footer totals.

Polaris owns:

- secure connector operation;
- tenant isolation;
- durable snapshots;
- API exposure;
- executive presentation;
- audit metadata and diagnostics.

## Consequences

- Accounts Receivable must use the QuickBooks Balance Sheet `Total Accounts Receivable ...` row.
- Accounts Payable must use the QuickBooks Balance Sheet `Total Accounts Payable ...` row.
- Net Income may use the QuickBooks Profit and Loss `Profit` footer label when that is the consolidated bottom-line label returned by QuickBooks.
- Cash Position may use the QuickBooks Balance Sheet `Total Cash and Cash Equivalent` label when that is the consolidated cash label returned by QuickBooks.
- Revenue and expense KPIs remain sourced from Profit and Loss report totals and are unchanged by this ADR.
- Missing authoritative total rows fail gracefully by returning no value. Polaris does not silently fall back to child rows without a future explicit architecture decision.
- Aged Receivables and Aged Payables remain reconciliation/subledger evidence, not the executive dashboard source of truth for the consolidated Balance Sheet KPI.

## Verification

Regression tests must cover:

- single-currency Balance Sheet totals;
- multi-currency Balance Sheet totals;
- child rows that must not be selected;
- nested QuickBooks report structures;
- missing total rows;
- Profit and Loss `Profit` footer mapping to Net Income;
- Balance Sheet `Total Cash and Cash Equivalent` mapping to Cash Position;
- missing/null executive KPI display.

## Non-Goals

This ADR does not authorize:

- manual exchange-rate calculation;
- summing foreign-currency account rows;
- accounting adjustments inside Polaris;
- QuickBooks write operations;
- deriving Gross Profit from revenue minus expenses or income minus cost of goods sold;
- changing Revenue, Expenses, Accounts Receivable, Accounts Payable, or Gross Profit behavior beyond the explicitly documented labels.
