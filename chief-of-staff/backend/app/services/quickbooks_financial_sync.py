"""Synchronize QuickBooks financial data into Polaris-owned storage."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any

from app.connectors.quickbooks import EXPECTED_COMPANY_NAME, QuickBooksConnector
from app.database.database import SessionLocal
from app.models.financial_snapshot import FinancialAccount, FinancialSnapshot, FinancialSyncHistory


class QuickBooksFinancialSyncService:
    def __init__(self, connector: QuickBooksConnector | None = None) -> None:
        self.connector = connector or QuickBooksConnector()
        self.organization_slug = os.getenv("POLARIS_ORGANIZATION_SLUG", "mor-logistics")

    def sync(self, *, start_date: date | None = None, end_date: date | None = None) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        timer = perf_counter()
        with SessionLocal() as session:
            history = FinancialSyncHistory(
                organization_slug=self.organization_slug,
                status="running",
                started_at=started_at,
            )
            session.add(history)
            session.commit()
            session.refresh(history)

        try:
            company = self.connector.company_info()
            company_name = str(company.get("CompanyName") or "")
            if company_name != EXPECTED_COMPANY_NAME:
                raise RuntimeError("QuickBooks company identity does not match the configured organization")

            accounts = self.connector.accounts()
            reports = {
                "profit_loss": self.connector.report("ProfitAndLoss", start_date=start_date, end_date=end_date),
                "balance_sheet": self.connector.report("BalanceSheet", start_date=start_date, end_date=end_date),
                "cash_flow": self.connector.report("CashFlow", start_date=start_date, end_date=end_date),
            }
            now = datetime.now(timezone.utc)

            with SessionLocal.begin() as session:
                for account in accounts:
                    qbo_id = str(account.get("Id") or "")
                    if not qbo_id:
                        continue
                    row = session.query(FinancialAccount).filter_by(
                        organization_slug=self.organization_slug,
                        qbo_id=qbo_id,
                    ).one_or_none()
                    values = {
                        "name": str(account.get("Name") or account.get("FullyQualifiedName") or qbo_id),
                        "fully_qualified_name": account.get("FullyQualifiedName"),
                        "account_type": account.get("AccountType"),
                        "account_subtype": account.get("AccountSubType"),
                        "active": bool(account.get("Active", True)),
                        "current_balance": _number(account.get("CurrentBalance")),
                        "payload": account,
                        "synced_at": now,
                    }
                    if row is None:
                        session.add(FinancialAccount(organization_slug=self.organization_slug, qbo_id=qbo_id, **values))
                    else:
                        for key, value in values.items():
                            setattr(row, key, value)

                session.add(FinancialSnapshot(
                    organization_slug=self.organization_slug,
                    snapshot_type="company",
                    period_start=start_date.isoformat() if start_date else None,
                    period_end=end_date.isoformat() if end_date else None,
                    payload=company,
                    captured_at=now,
                ))
                for snapshot_type, payload in reports.items():
                    header = payload.get("Header") if isinstance(payload, dict) else {}
                    session.add(FinancialSnapshot(
                        organization_slug=self.organization_slug,
                        snapshot_type=snapshot_type,
                        period_start=str((header or {}).get("StartPeriod") or start_date or "") or None,
                        period_end=str((header or {}).get("EndPeriod") or end_date or "") or None,
                        accounting_method=str((header or {}).get("ReportBasis") or "Accrual"),
                        payload=payload,
                        captured_at=now,
                    ))

                history = session.get(FinancialSyncHistory, history.id)
                history.status = "success"
                history.completed_at = now
                history.duration_ms = round((perf_counter() - timer) * 1000)
                history.accounts_imported = len(accounts)
                history.company_name = company_name

            return self.status()
        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            with SessionLocal.begin() as session:
                history = session.get(FinancialSyncHistory, history.id)
                history.status = "failed"
                history.completed_at = completed_at
                history.duration_ms = round((perf_counter() - timer) * 1000)
                history.error_message = str(exc)[:1000]
            raise

    def status(self) -> dict[str, Any]:
        with SessionLocal() as session:
            history = session.query(FinancialSyncHistory).filter_by(
                organization_slug=self.organization_slug
            ).order_by(FinancialSyncHistory.started_at.desc()).first()
            if history is None:
                return {"status": "never_synced", "last_sync": None, "accounts": 0, "snapshots": {}}
            snapshots = {}
            for kind in ("profit_loss", "balance_sheet", "cash_flow"):
                latest = session.query(FinancialSnapshot).filter_by(
                    organization_slug=self.organization_slug,
                    snapshot_type=kind,
                ).order_by(FinancialSnapshot.captured_at.desc()).first()
                snapshots[kind] = latest.captured_at.isoformat() if latest else None
            return {
                "status": history.status,
                "last_sync": history.completed_at.isoformat() if history.completed_at else None,
                "duration_ms": history.duration_ms,
                "accounts": history.accounts_imported,
                "company": history.company_name,
                "error": history.error_message,
                "snapshots": snapshots,
            }


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
