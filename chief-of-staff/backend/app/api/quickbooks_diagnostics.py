"""Read-only QuickBooks report-shape diagnostics.

These endpoints exist only to inspect provider-authored report structure. They do not
calculate accounting metrics, mutate QuickBooks, or expose raw transaction payloads.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.quickbooks_financials import _connector, _safe_call
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/qbo/diagnostics", tags=["quickbooks-diagnostics"])


def _decimal_text(value: Any) -> str | None:
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _group_summaries(payload: dict[str, Any]) -> list[dict[str, str | None]]:
    """Return provider group names and summary amounts without raw transaction rows."""
    summaries: list[dict[str, str | None]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            group = str(node.get("group") or "").strip()
            if group:
                summary = node.get("Summary")
                columns = summary.get("ColData") if isinstance(summary, dict) else None
                label: str | None = None
                amount: str | None = None
                if isinstance(columns, list) and columns:
                    label = str((columns[0] or {}).get("value") or "").strip() or None
                    for column in reversed(columns[1:]):
                        amount = _decimal_text((column or {}).get("value"))
                        if amount is not None:
                            break
                summaries.append({"group": group, "label": label, "value": amount})
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload.get("Rows", {}))
    return summaries


def _provider_report(
    organization_id: str,
    report_name: str,
    start_date: date | None,
    end_date: date | None,
    accounting_method: Literal["Accrual", "Cash"],
) -> dict[str, Any]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not exceed end_date")

    params: dict[str, str] = {"accounting_method": accounting_method}
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()

    connector = _connector(organization_id)
    return _safe_call(
        lambda: connector._get(  # noqa: SLF001 - intentionally narrow provider diagnostic
            f"reports/{report_name}",
            operation=f"{report_name} diagnostic report",
            params=params,
        )
    )


@router.get("/profit-loss-detail-structure")
def profit_loss_detail_structure(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    accounting_method: Literal["Accrual", "Cash"] = Query(default="Accrual"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.FINANCIAL_READ)),
) -> dict[str, Any]:
    """Inspect provider-authored ProfitAndLossDetail groups without exposing transactions."""
    payload = _provider_report(
        principal.organization_id,
        "ProfitAndLossDetail",
        start_date,
        end_date,
        accounting_method,
    )
    header = payload.get("Header", {}) if isinstance(payload, dict) else {}
    return {
        "report_name": header.get("ReportName") or "ProfitAndLossDetail",
        "period": {
            "start": header.get("StartPeriod") or (start_date.isoformat() if start_date else None),
            "end": header.get("EndPeriod") or (end_date.isoformat() if end_date else None),
            "basis": header.get("ReportBasis") or accounting_method,
        },
        "currency": header.get("Currency"),
        "group_summaries": _group_summaries(payload),
    }
