# Release Note: RC-1 Executive Financial KPI Standardization

Date: 2026-08-05  
Branch: `rc1/executive-financial-kpi-standardization`  
Status: Draft PR for CTO review

## Summary

Implements PES-001 for executive financial KPIs sourced from QuickBooks Balance Sheet reports.

Executive dashboard Accounts Receivable and Accounts Payable now use consolidated QuickBooks Balance Sheet total rows instead of child account rows. Polaris continues to display QuickBooks-owned accounting results and does not calculate exchange rates, aggregate currencies, or perform accounting transformations.

## Scope

- Revenue behavior unchanged.
- Expense behavior unchanged.
- Accounts Receivable now maps to QuickBooks Balance Sheet `Total Accounts Receivable ...`.
- Accounts Payable now maps to QuickBooks Balance Sheet `Total Accounts Payable ...`.
- Backend KPI metadata added for diagnostics and audit.
- Frontend labels updated to `Total accounts receivable` and `Total accounts payable`.
- Regression tests added for single currency, multi-currency, child rows, nested rows, and missing total rows.

## RC-1 Milestone Status

This change standardizes the Balance Sheet source rule for AR/AP. Final RC-1 certification still requires CI completion, CTO review, deployment, and production evidence that the dashboard values match QuickBooks Balance Sheet consolidated total rows for Mor Logistics.

## Risk

The parser intentionally does not fall back to child AR/AP account rows when a consolidated total row is missing. This is fail-closed behavior aligned with ADR-028.
