"""Read-only QuickBooks financial API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from app.connectors.quickbooks import QuickBooksConnector, QuickBooksConnectorError

router = APIRouter(prefix="/api/v1/qbo", tags=["quickbooks-financials"])


def _connector() -> QuickBooksConnector:
    return QuickBooksConnector()


def _safe_call(operation):
    try:
        return operation()
    except QuickBooksConnectorError as exc:
        message = str(exc)
        status_code = 503 if "not configured" in message.lower() or "not been authorized" in message.lower() else 502
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.get("/company")
def get_company() -> dict[str, Any]:
    """Return metadata for the verified QuickBooks company."""
    return _safe_call(lambda: _connector().company_info())


@router.get("/accounts")
def get_accounts() -> dict[str, Any]:
    """Return the active QuickBooks Chart of Accounts."""
    accounts = _safe_call(lambda: _connector().accounts())
    return {"count": len(accounts), "accounts": accounts}


def _get_report(
    report_name: str,
    start_date: date | None,
    end_date: date | None,
    accounting_method: Literal["Accrual", "Cash"],
) -> dict[str, Any]:
    return _safe_call(
        lambda: _connector().report(
            report_name,
            start_date=start_date,
            end_date=end_date,
            accounting_method=accounting_method,
        )
    )


@router.get("/reports/profit-loss")
def get_profit_and_loss(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
) -> dict[str, Any]:
    """Return a Profit and Loss report for an optional date range."""
    return _get_report("ProfitAndLoss", start_date, end_date, accounting_method)


@router.get("/reports/balance-sheet")
def get_balance_sheet(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
) -> dict[str, Any]:
    """Return a Balance Sheet report for an optional date range."""
    return _get_report("BalanceSheet", start_date, end_date, accounting_method)


@router.get("/reports/cash-flow")
def get_cash_flow(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
) -> dict[str, Any]:
    """Return a Statement of Cash Flows for an optional date range."""
    return _get_report("CashFlow", start_date, end_date, accounting_method)
