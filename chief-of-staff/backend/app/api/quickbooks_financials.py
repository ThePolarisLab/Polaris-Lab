"""QuickBooks financial reads, durable synchronization, and executive summary."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.connectors.quickbooks import QuickBooksConnector, QuickBooksConnectorError
from app.connectors.quickbooks_credentials import QuickBooksCredentialStore
from app.database.database import SessionLocal
from app.models.financial_snapshot import FinancialSnapshot
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission
from app.services.quickbooks_financial_sync import QuickBooksFinancialSyncService

router = APIRouter(prefix="/api/v1/qbo", tags=["quickbooks-financials"])


def _connector(organization_id: str) -> QuickBooksConnector:
    return QuickBooksConnector(credential_store=QuickBooksCredentialStore(organization_id))


def _safe_call(operation):
    try:
        return operation()
    except QuickBooksConnectorError as exc:
        message = str(exc)
        status_code = 503 if "not configured" in message.lower() or "not been authorized" in message.lower() else 502
        raise HTTPException(status_code=status_code, detail=message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="QuickBooks operation failed") from exc


@router.get("/company")
def get_company(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ))) -> dict[str, Any]:
    return _safe_call(lambda: _connector(principal.organization_id).company_info())


@router.get("/accounts")
def get_accounts(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ))) -> dict[str, Any]:
    accounts = _safe_call(lambda: _connector(principal.organization_id).accounts())
    return {"count": len(accounts), "accounts": accounts}


def _get_report(organization_id: str, report_name: str, start_date: date | None, end_date: date | None, accounting_method: Literal["Accrual", "Cash"]) -> dict[str, Any]:
    return _safe_call(lambda: _connector(organization_id).report(report_name, start_date=start_date, end_date=end_date, accounting_method=accounting_method))


@router.get("/reports/profit-loss")
def get_profit_and_loss(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    return _get_report(principal.organization_id, "ProfitAndLoss", start_date, end_date, accounting_method)


@router.get("/reports/balance-sheet")
def get_balance_sheet(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    return _get_report(principal.organization_id, "BalanceSheet", start_date, end_date, accounting_method)


@router.get("/reports/cash-flow")
def get_cash_flow(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    return _get_report(principal.organization_id, "CashFlow", start_date, end_date, accounting_method)


@router.post("/sync")
def synchronize_financials(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_WRITE)),
) -> dict[str, Any]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not exceed end_date")
    return _safe_call(lambda: QuickBooksFinancialSyncService(principal.organization_id).sync(start_date=start_date, end_date=end_date))


@router.get("/sync/status")
def synchronization_status(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ))) -> dict[str, Any]:
    return QuickBooksFinancialSyncService(principal.organization_id).status()


@router.get("/executive-summary")
def executive_summary(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ))) -> dict[str, Any]:
    with SessionLocal() as session:
        profit_loss = _latest_snapshot(session, principal.organization_id, "profit_loss")
        balance_sheet = _latest_snapshot(session, principal.organization_id, "balance_sheet")
    status = QuickBooksFinancialSyncService(principal.organization_id).status()
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
            "end": header.get("EndPeriod") or profit_loss.period_end,
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


def _latest_snapshot(session, organization_id: str, snapshot_type: str) -> FinancialSnapshot | None:
    return session.query(FinancialSnapshot).filter_by(organization_id=organization_id, snapshot_type=snapshot_type).order_by(FinancialSnapshot.captured_at.desc()).first()


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
