# ADR-028: Executive Financial KPI Standard

Status: Accepted  
Date: 2026-08-05  
Owner: Polaris Lab  
Standard: PES-001

## Context

RC-1 financial trust audits for Accounts Receivable and Accounts Payable found that the executive dashboard was reading child Balance Sheet account rows such as `Accounts Receivable (A/R)` and `Accounts Payable (A/P)`. In multi-currency QuickBooks companies, QuickBooks may also report sibling foreign-currency accounts and consolidated `Total ...` rows after applying QuickBooks-owned accounting rules and currency conversion.

Polaris must not reproduce QuickBooks accounting logic. Polaris must preserve QuickBooks as the Financial System of Record and display the report values QuickBooks has already calculated.

## Decision

Executive Dashboard financial KPIs sourced from the Balance Sheet must display consolidated Balance Sheet totals exactly as reported by QuickBooks.

Polaris will:

- read QuickBooks report payloads through the production Python FastAPI QuickBooks connector;
- store report payloads in tenant-owned `financial_snapshots` records;
- parse executive Balance Sheet KPIs from QuickBooks `Total ...` rows;
- expose audit metadata with each backend KPI response;
- avoid exchange-rate calculation, currency aggregation, or accounting derivation inside Polaris.

QuickBooks owns:

- exchange rates;
- currency conversion;
- accounting basis;
- account hierarchy;
- consolidated Balance Sheet totals.

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
- Revenue and expense KPIs remain sourced from Profit and Loss report totals and are unchanged by this ADR.
- Missing Balance Sheet total rows fail gracefully by returning no value. Polaris does not silently fall back to child rows without a future explicit architecture decision.
- Aged Receivables and Aged Payables remain reconciliation/subledger evidence, not the executive dashboard source of truth for the consolidated Balance Sheet KPI.

## Verification

Regression tests must cover:

- single-currency Balance Sheet totals;
- multi-currency Balance Sheet totals;
- child rows that must not be selected;
- nested QuickBooks report structures;
- missing total rows.

## Non-Goals

This ADR does not authorize:

- manual exchange-rate calculation;
- summing foreign-currency account rows;
- accounting adjustments inside Polaris;
- QuickBooks write operations;
- changing Profit and Loss KPI behavior.
