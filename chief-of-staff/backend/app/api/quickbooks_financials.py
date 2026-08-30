"""QuickBooks financial reads, durable synchronization, and executive summary."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.connectors.quickbooks import REPORT_NAMES, RESOURCE_ENTITY, QuickBooksConnector, QuickBooksConnectorError
from app.connectors.quickbooks_credentials import QuickBooksCredentialStore
from app.database.database import SessionLocal
from app.models.financial_snapshot import FinancialSnapshot
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission
from app.services.quickbooks_financial_sync import QuickBooksFinancialSyncService, QuickBooksSyncStageError

router = APIRouter(prefix="/api/v1/qbo", tags=["quickbooks-financials"])
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportMetric:
    label: str
    normalized_label: str
    value: str


def _connector(organization_id: str) -> QuickBooksConnector:
    return QuickBooksConnector(credential_store=QuickBooksCredentialStore(organization_id))


def _safe_call(operation):
    try:
        return operation()
    except QuickBooksConnectorError as exc:
        message = str(exc)
        status_code = 503 if exc.status.value in {"not_configured", "authorization_required", "reauthorization_required"} else 502
        raise HTTPException(status_code=status_code, detail=message) from exc
    except QuickBooksSyncStageError as exc:
        raise HTTPException(status_code=500, detail=exc.payload()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="QuickBooks operation failed") from exc


@router.get("/company")
def get_company(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ))) -> dict[str, Any]:
    return _safe_call(lambda: _connector(principal.organization_id).company_info())


@router.get("/accounts")
def get_accounts(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ))) -> dict[str, Any]:
    accounts = _safe_call(lambda: _connector(principal.organization_id).accounts())
    return {"count": len(accounts), "accounts": accounts}


@router.get("/resources/{resource}")
def get_resource(
    resource: Literal["customers", "vendors", "accounts", "items", "invoices", "payments", "bills", "purchases", "journal_entries"],
    changed_since: str | None = Query(default=None),
    cursor: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    rows, next_cursor = _safe_call(
        lambda: _connector(principal.organization_id).list_resource_page(
            resource,
            changed_since=changed_since,
            cursor=cursor,
            limit=limit,
        )
    )
    return {"resource": resource, "count": len(rows), "records": rows, "next_cursor": next_cursor}


def _get_report(organization_id: str, report_name: str, start_date: date | None, end_date: date | None, accounting_method: Literal["Accrual", "Cash"]) -> dict[str, Any]:
    return _safe_call(lambda: _connector(organization_id).report(report_name, start_date=start_date, end_date=end_date, accounting_method=accounting_method))


@router.get("/reports/profit-loss")
def get_profit_and_loss(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    return _get_report(principal.organization_id, "profit_loss", start_date, end_date, accounting_method)


@router.get("/reports/balance-sheet")
def get_balance_sheet(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    return _get_report(principal.organization_id, "balance_sheet", start_date, end_date, accounting_method)


@router.get("/reports/cash-flow")
def get_cash_flow(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    return _get_report(principal.organization_id, "cash_flow", start_date, end_date, accounting_method)


@router.get("/reports/aged-receivables")
def get_aged_receivables(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    return _get_report(principal.organization_id, "aged_receivables", start_date, end_date, accounting_method)


@router.get("/reports/aged-payables")
def get_aged_payables(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    return _get_report(principal.organization_id, "aged_payables", start_date, end_date, accounting_method)


@router.post("/sync")
def synchronize_financials(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    mode: Literal["full", "incremental"] = Query(default="full"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_WRITE)),
) -> dict[str, Any]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not exceed end_date")
    try:
        return QuickBooksFinancialSyncService(principal.organization_id).sync(start_date=start_date, end_date=end_date, mode=mode)
    except QuickBooksSyncStageError as exc:
        logger.exception(
            "QuickBooks sync endpoint failed",
            extra={
                "organization_id": principal.organization_id,
                "identity_id": principal.identity_id,
                "company_id": exc.company_id,
                "sync_mode": mode,
                "sync_stage": exc.stage,
            },
        )
        detail = exc.payload()
        detail["identity_id"] = principal.identity_id
        raise HTTPException(status_code=500, detail=detail) from exc


@router.get("/sync/status")
def synchronization_status(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ))) -> dict[str, Any]:
    return QuickBooksFinancialSyncService(principal.organization_id).status()


@router.get("/verification")
def verification_status(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ))) -> dict[str, Any]:
    return _connector(principal.organization_id).safe_status(include_resources=True)


@router.post("/verification")
def run_verification(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page_size: int = Query(default=100, ge=1, le=1000),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
) -> dict[str, Any]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not exceed end_date")
    return _safe_call(lambda: QuickBooksFinancialSyncService(principal.organization_id).verification(start_date=start_date, end_date=end_date, page_size=page_size))


@router.get("/executive-summary")
def executive_summary(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ))) -> dict[str, Any]:
    with SessionLocal() as session:
        profit_loss = _latest_snapshot(session, principal.organization_id, "profit_loss")
        balance_sheet = _latest_snapshot(session, principal.organization_id, "balance_sheet")
    status = QuickBooksFinancialSyncService(principal.organization_id).status()
    if profit_loss is None or balance_sheet is None:
        return {**status, "currency": "CAD", "period": None, "metrics": None}

    pl_values = _report_values(profit_loss.payload)
    pl_metrics = _report_metrics(profit_loss.payload)
    bs_values = _report_values(balance_sheet.payload)
    bs_metrics = _report_metrics(balance_sheet.payload)
    header = profit_loss.payload.get("Header", {})
    revenue = _first(pl_values, "total income", "total revenue", "income")
    gross_profit_metric = get_profit_loss_gross_profit_metric(profit_loss.payload)
    gross_profit = _metric_value(gross_profit_metric)
    expenses = _first(pl_values, "total expenses", "expenses")
    net_income = _first(pl_values, "net income", "net operating income", "profit")
    cash = _first(bs_values, "total bank accounts", "total cash and cash equivalent", "cash and cash equivalents", "bank accounts")
    cash_metric = _first_report_metric(bs_metrics, "total bank accounts", "total cash and cash equivalent", "cash and cash equivalents", "bank accounts")
    accounts_receivable_metric = get_balance_sheet_metric(balance_sheet.payload, "Accounts Receivable")
    accounts_payable_metric = get_balance_sheet_metric(balance_sheet.payload, "Accounts Payable")
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
            "cash": cash,
            "accounts_receivable": _metric_value(accounts_receivable_metric),
            "accounts_payable": _metric_value(accounts_payable_metric),
        },
        "metrics_metadata": {
            "revenue": _metric_metadata(_first_report_metric(pl_metrics, "total income", "total revenue", "income"), profit_loss, "ProfitAndLoss"),
            "expenses": _metric_metadata(_first_report_metric(pl_metrics, "total expenses", "expenses"), profit_loss, "ProfitAndLoss"),
            "gross_profit": _metric_metadata(gross_profit_metric, profit_loss, "ProfitAndLoss"),
            "net_income": _metric_metadata(_first_report_metric(pl_metrics, "net income", "net operating income", "profit"), profit_loss, "ProfitAndLoss"),
            "cash": _metric_metadata(cash_metric, balance_sheet, "BalanceSheet", value_override=cash),
            "accounts_receivable": _metric_metadata(accounts_receivable_metric, balance_sheet, "BalanceSheet"),
            "accounts_payable": _metric_metadata(accounts_payable_metric, balance_sheet, "BalanceSheet"),
        },
    }


def _latest_snapshot(session, organization_id: str, snapshot_type: str) -> FinancialSnapshot | None:
    return session.query(FinancialSnapshot).filter_by(organization_id=organization_id, snapshot_type=snapshot_type).order_by(FinancialSnapshot.captured_at.desc()).first()


def get_balance_sheet_metric(report_payload: dict[str, Any], label: str) -> ReportMetric | None:
    """Return the QuickBooks consolidated Balance Sheet total for a metric label."""
    target = _metric_total_key(label)
    for metric in reversed(_report_metrics(report_payload)):
        if _metric_total_key(metric.label) == target and metric.normalized_label.startswith("total "):
            return metric
    return None


def get_profit_loss_gross_profit_metric(report_payload: dict[str, Any]) -> ReportMetric | None:
    """Return QuickBooks-authored Gross Profit without recalculating it in Polaris."""
    metric = _first_report_metric(_report_metrics(report_payload), "gross profit")
    if metric is not None:
        return metric
    return _report_group_metric(report_payload, "GrossProfit")


def _report_values(payload: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for metric in _report_metrics(payload):
        values[metric.normalized_label] = metric.value
    return values


def _report_metrics(payload: dict[str, Any]) -> list[ReportMetric]:
    metrics: list[ReportMetric] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            columns = node.get("ColData") or (node.get("Summary") or {}).get("ColData")
            if isinstance(columns, list) and columns:
                raw_label = str((columns[0] or {}).get("value") or "").strip()
                label = raw_label.lower()
                for column in reversed(columns[1:]):
                    amount = _decimal_text((column or {}).get("value"))
                    if amount is not None:
                        metrics.append(ReportMetric(label=raw_label, normalized_label=label, value=amount))
                        break
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload.get("Rows", {}))
    return metrics


def _first(values: dict[str, str], *names: str) -> str | None:
    for name in names:
        if name in values:
            return values[name]
    return None


def _first_report_metric(metrics: list[ReportMetric], *names: str) -> ReportMetric | None:
    for name in names:
        for metric in reversed(metrics):
            if metric.normalized_label == name:
                return metric
    return None


def _report_group_metric(payload: dict[str, Any], group: str) -> ReportMetric | None:
    target = _normalize_report_group(group)
    found: ReportMetric | None = None

    def visit(node: Any) -> None:
        nonlocal found
        if found is not None:
            return
        if isinstance(node, dict):
            if _normalize_report_group(node.get("group")) == target:
                summary = node.get("Summary")
                summary_columns = summary.get("ColData") if isinstance(summary, dict) else None
                columns = summary_columns or node.get("ColData")
                if isinstance(columns, list) and columns:
                    raw_label = str((columns[0] or {}).get("value") or "").strip() or group
                    for column in reversed(columns[1:]):
                        amount = _decimal_text((column or {}).get("value"))
                        if amount is not None:
                            found = ReportMetric(label=raw_label, normalized_label=raw_label.lower(), value=amount)
                            return
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload.get("Rows", {}))
    return found


def _normalize_report_group(value: Any) -> str:
    return "".join(character for character in str(value or "").lower() if character.isalnum())


def _metric_value(metric: ReportMetric | None) -> str | None:
    return metric.value if metric is not None else None


def _metric_metadata(
    metric: ReportMetric | None,
    snapshot: FinancialSnapshot,
    report_name: str,
    *,
    value_override: str | None = None,
) -> dict[str, Any]:
    header = snapshot.payload.get("Header", {}) if isinstance(snapshot.payload, dict) else {}
    captured_at = snapshot.captured_at.isoformat() if snapshot.captured_at else None
    return {
        "value": value_override if value_override is not None else _metric_value(metric),
        "report_name": report_name,
        "report_label": metric.label if metric is not None else None,
        "snapshot_id": snapshot.id,
        "captured_at": captured_at,
        "period_end": header.get("EndPeriod") or snapshot.period_end,
        "accounting_basis": header.get("ReportBasis") or snapshot.accounting_method,
        "currency": header.get("Currency") or "CAD",
        "organization_slug": snapshot.organization_slug,
    }


def _metric_total_key(label: str) -> str:
    normalized = " ".join(str(label).strip().lower().split())
    if normalized.startswith("total "):
        normalized = normalized[6:]
    normalized = normalized.replace("(a/r)", "").replace("(a/p)", "")
    return "total " + " ".join(normalized.split())


def _decimal_text(value: Any) -> str | None:
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None
