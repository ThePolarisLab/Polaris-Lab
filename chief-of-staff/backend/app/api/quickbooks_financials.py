"""QuickBooks financial reads, durable synchronization, and executive summary."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.connectors.quickbooks import QuickBooksConnector, QuickBooksConnectorError
from app.database.database import SessionLocal
from app.models.financial_snapshot import FinancialSnapshot
from app.security.dependencies import require_permission
from app.security.models import Permission
from app.services.quickbooks_financial_sync import QuickBooksFinancialSyncService

router = APIRouter(prefix="/api/v1/qbo", tags=["quickbooks-financials"])

connector_read = Depends(require_permission(Permission.CONNECTOR_READ))
connector_manage = Depends(require_permission(Permission.CONNECTOR_MANAGE))
executive_read = Depends(require_permission(Permission.EXECUTIVE_READ))


def _connector() -> QuickBooksConnector:
    return QuickBooksConnector()


def _safe_call(operation):
    try:
        return operation()
    except QuickBooksConnectorError as exc:
        message = str(exc)
        status_code = 503 if "not configured" in message.lower() or "not been authorized" in message.lower() else 502
        raise HTTPException(status_code=status_code, detail=message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="QuickBooks operation failed") from exc


@router.get("/company", dependencies=[connector_read])
def get_company() -> dict[str, Any]:
    return _safe_call(lambda: _connector().company_info())


@router.get("/accounts", dependencies=[connector_read])
def get_accounts() -> dict[str, Any]:
    accounts = _safe_call(lambda: _connector().accounts())
    return {"count": len(accounts), "accounts": accounts}


def _get_report(report_name: str, start_date: date | None, end_date: date | None, accounting_method: Literal["Accrual", "Cash"]) -> dict[str, Any]:
    return _safe_call(lambda: _connector().report(report_name, start_date=start_date, end_date=end_date, accounting_method=accounting_method))


@router.get("/reports/profit-loss", dependencies=[connector_read])
def get_profit_and_loss(start_date: date | None = Query(default=None), end_date: date | None = Query(default=None), accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual")) -> dict[str, Any]:
    return _get_report("ProfitAndLoss", start_date, end_date, accounting_method)


@router.get("/reports/balance-sheet", dependencies=[connector_read])
def get_balance_sheet(start_date: date | None = Query(default=None), end_date: date | None = Query(default=None), accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual")) -> dict[str, Any]:
    return _get_report("BalanceSheet", start_date, end_date, accounting_method)


@router.get("/reports/cash-flow", dependencies=[connector_read])
def get_cash_flow(start_date: date | None = Query(default=None), end_date: date | None = Query(default=None), accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual")) -> dict[str, Any]:
    return _get_report("CashFlow", start_date, end_date, accounting_method)


@router.post("/sync", dependencies=[connector_manage])
def synchronize_financials(start_date: date | None = Query(default=None), end_date: date | None = Query(default=None)) -> dict[str, Any]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not exceed end_date")
    return _safe_call(lambda: QuickBooksFinancialSyncService().sync(start_date=start_date, end_date=end_date))


@router.get("/sync/status", dependencies=[connector_read])
def synchronization_status() -> dict[str, Any]:
    return QuickBooksFinancialSyncService().status()


@router.get("/executive-summary", dependencies=[executive_read])
def executive_summary() -> dict[str, Any]:
    organization_slug = os.getenv("POLARIS_ORGANIZATION_SLUG", "mor-logistics")
    with SessionLocal() as session:
        profit_loss = _latest_snapshot(session, organization_slug, "profit_loss")
        balance_sheet = _latest_snapshot(session, organization_slug, "balance_sheet")
    status = QuickBooksFinancialSyncService().status()
    if profit_loss is None or balance_sheet is None:
        return {**status, "currency": "CAD", "period": None, "metrics": None}

    pl_values = _report_values(profit_loss.payload)
    bs_values = _report_values(balance_sheet.payload)
    header = profit_loss.payload.get("Header", {})
    revenue = _first(pl_values, "total income", "total revenue", "income")
    gross_profit = _first(pl_values, "gross profit")
    expenses = _first(pl_values, "total expenses", "expenses")
    net_income = _first(pl_values, "net income", "net operating income")
    return {
        **status,
        "currency": str(header.get("Currency") or "CAD"),
        "period": {
            "start": header.get("StartPeriod") or profit_loss.period_start,
            "end": header.get("EndPeriod") or balance_sheet.period_end,
            "basis": header.get("ReportBasis") or profit_loss.accounting_method,
        },
        "metrics": {
            "revenue": revenue,
            "expenses": expenses,
            "gross_profit": gross_profit,
            "net_income": net_income,
            "cash": _first(bs_values, "total bank accounts", "cash and cash equivalents", "bank accounts"),
            "accounts_receivable": _first(bs_values, "accounts receivable (a/r)", "accounts receivable"),
            "accounts_payable": _first(bs_values, "accounts payable (a/p)", "accounts payable"),
        },
    }


def _latest_snapshot(session, organization_slug: str, snapshot_type: str) -> FinancialSnapshot | None:
    return session.query(FinancialSnapshot).filter_by(
        organization_slug=organization_slug,
        snapshot_type=snapshot_type,
    ).order_by(FinancialSnapshot.captured_at.desc()).first()


def _report_values(payload: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            columns = node.get("ColData") or (node.get("Summary") or {}).get("ColData")
            if isinstance(columns, list) and columns:
                label = str((columns[0] or {}).get("value") or "").strip().lower()
                for column in reversed(columns[1:]):
                    try:
                        values[label] = float((column or {}).get("value"))
                        break
                    except (TypeError, ValueError):
                        continue
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload.get("Rows", {}))
    return values


def _first(values: dict[str, float], *names: str) -> float | None:
    for name in names:
        if name in values:
            return values[name]
    return None
