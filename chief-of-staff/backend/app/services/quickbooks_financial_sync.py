"""Synchronize QuickBooks financial data into Polaris-owned storage."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any, Literal

from app.connectors.quickbooks import (
    REPORT_NAMES,
    RESOURCE_ENTITY,
    QuickBooksConnector,
    QuickBooksConnectorError,
    decimal_string,
)
from app.connectors.quickbooks_credentials import QuickBooksCredentialStore
from app.database.database import SessionLocal
from app.models.financial_snapshot import FinancialAccount, FinancialSnapshot, FinancialSyncHistory


class QuickBooksFinancialSyncService:
    def __init__(self, organization_id: str, connector: QuickBooksConnector | None = None) -> None:
        self.organization_id = organization_id
        self.store = QuickBooksCredentialStore(organization_id)
        self.connector = connector or QuickBooksConnector(credential_store=self.store)

    def sync(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        mode: Literal["full", "incremental"] = "full",
    ) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        timer = perf_counter()
        checkpoint_before = self._last_checkpoint() if mode == "incremental" else None
        history_id = self._start_history(started_at, mode, checkpoint_before)

        try:
            with self.connector.organization_sync_lock():
                verification = self.connector.verify_company_identity()
                changed_since = checkpoint_before if mode == "incremental" else None
                now = datetime.now(timezone.utc)
                resource_counts: dict[str, int] = {"company": 1}
                report_availability: dict[str, bool] = {}
                latest_observed_at = checkpoint_before

                accounts = self.connector.list_all_resource("accounts", changed_since=changed_since)
                resource_counts["accounts"] = len(accounts)
                resources: dict[str, list[dict[str, Any]]] = {"accounts": accounts}
                for resource in RESOURCE_ENTITY:
                    if resource == "accounts":
                        continue
                    rows = self.connector.list_all_resource(resource, changed_since=changed_since)
                    resources[resource] = rows
                    resource_counts[resource] = len(rows)
                    latest_observed_at = _latest_timestamp(rows, latest_observed_at)

                reports: dict[str, dict[str, Any]] = {}
                for report_key in REPORT_NAMES:
                    reports[report_key] = self.connector.report(report_key, start_date=start_date, end_date=end_date)
                    report_availability[report_key] = True

                company = self.connector.company_info()
                with SessionLocal.begin() as session:
                    self._upsert_accounts(session, accounts, now)
                    self._snapshot(session, "company", company, now, start_date, end_date)
                    for resource, rows in resources.items():
                        self._snapshot(
                            session,
                            f"resource_{resource}",
                            {"records": rows, "count": len(rows), "mode": mode},
                            now,
                            start_date,
                            end_date,
                        )
                    for snapshot_type, payload in reports.items():
                        header = payload.get("Header") if isinstance(payload, dict) else {}
                        self._snapshot(
                            session,
                            snapshot_type,
                            payload,
                            now,
                            date.fromisoformat(str((header or {}).get("StartPeriod"))) if (header or {}).get("StartPeriod") else start_date,
                            date.fromisoformat(str((header or {}).get("EndPeriod"))) if (header or {}).get("EndPeriod") else end_date,
                            str((header or {}).get("ReportBasis") or "Accrual"),
                        )
                    checkpoint_after = latest_observed_at or now.isoformat()
                    history = session.get(FinancialSyncHistory, history_id)
                    history.status = "success"
                    history.completed_at = now
                    history.duration_ms = round((perf_counter() - timer) * 1000)
                    history.accounts_imported = len(accounts)
                    history.company_name = str(verification["verified_company_name"])
                    history.resource_counts = resource_counts
                    history.report_availability = report_availability
                    history.checkpoint_after = checkpoint_after
                    history.verification_status = str(verification["identity_verification_status"])
                self.store.record_sync_success()
                return self.status()
        except Exception as exc:
            safe_message = str(exc)[:1000]
            completed_at = datetime.now(timezone.utc)
            with SessionLocal.begin() as session:
                history = session.get(FinancialSyncHistory, history_id)
                history.status = "failed"
                history.completed_at = completed_at
                history.duration_ms = round((perf_counter() - timer) * 1000)
                history.error_message = safe_message
            if isinstance(exc, QuickBooksConnectorError):
                self.store.record_sync_failure(safe_message, status=exc.status.value)
            else:
                self.store.record_sync_failure("QuickBooks synchronization failed")
            raise

    def verification(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        return self.connector.production_verification(
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            max_pages_per_resource=25,
        )

    def status(self) -> dict[str, Any]:
        with SessionLocal() as session:
            history = (
                session.query(FinancialSyncHistory)
                .filter_by(organization_id=self.organization_id)
                .order_by(FinancialSyncHistory.started_at.desc())
                .first()
            )
            snapshots = {}
            for kind in (*REPORT_NAMES.keys(), *(f"resource_{resource}" for resource in RESOURCE_ENTITY)):
                latest = (
                    session.query(FinancialSnapshot)
                    .filter_by(organization_id=self.organization_id, snapshot_type=kind)
                    .order_by(FinancialSnapshot.captured_at.desc())
                    .first()
                )
                snapshots[kind] = latest.captured_at.isoformat() if latest else None
            credential_status = self.store.metadata()
            if history is None:
                return {
                    "status": "never_synced",
                    "last_sync": None,
                    "accounts": 0,
                    "resource_counts": {},
                    "report_availability": {},
                    "checkpoint": None,
                    "snapshots": snapshots,
                    "quickbooks": credential_status,
                }
            return {
                "status": history.status,
                "last_sync": history.completed_at.isoformat() if history.completed_at else None,
                "duration_ms": history.duration_ms,
                "accounts": history.accounts_imported,
                "company": history.company_name,
                "error": history.error_message,
                "sync_mode": history.sync_mode,
                "resource_counts": history.resource_counts or {},
                "report_availability": history.report_availability or {},
                "checkpoint": history.checkpoint_after,
                "snapshots": snapshots,
                "quickbooks": credential_status,
            }

    def _start_history(self, started_at: datetime, mode: str, checkpoint_before: str | None) -> int:
        with SessionLocal() as session:
            history = FinancialSyncHistory(
                organization_id=self.organization_id,
                status="running",
                started_at=started_at,
                sync_mode=mode,
                checkpoint_before=checkpoint_before,
                resource_counts={},
                report_availability={},
            )
            session.add(history)
            session.commit()
            session.refresh(history)
            return int(history.id)

    def _last_checkpoint(self) -> str | None:
        with SessionLocal() as session:
            history = (
                session.query(FinancialSyncHistory)
                .filter_by(organization_id=self.organization_id, status="success")
                .order_by(FinancialSyncHistory.completed_at.desc())
                .first()
            )
            return history.checkpoint_after if history else None

    def _upsert_accounts(self, session, accounts: list[dict[str, Any]], synced_at: datetime) -> None:
        for account in accounts:
            qbo_id = str(account.get("Id") or "")
            if not qbo_id:
                continue
            row = session.query(FinancialAccount).filter_by(organization_id=self.organization_id, qbo_id=qbo_id).one_or_none()
            values = {
                "name": str(account.get("Name") or account.get("FullyQualifiedName") or qbo_id),
                "fully_qualified_name": account.get("FullyQualifiedName"),
                "account_type": account.get("AccountType"),
                "account_subtype": account.get("AccountSubType"),
                "active": bool(account.get("Active", True)),
                "current_balance": decimal_string(account.get("CurrentBalance")),
                "payload": account,
                "synced_at": synced_at,
            }
            if row is None:
                session.add(FinancialAccount(organization_id=self.organization_id, qbo_id=qbo_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)

    def _snapshot(
        self,
        session,
        snapshot_type: str,
        payload: dict[str, Any],
        captured_at: datetime,
        period_start: date | None,
        period_end: date | None,
        accounting_method: str = "Accrual",
    ) -> None:
        session.add(
            FinancialSnapshot(
                organization_id=self.organization_id,
                snapshot_type=snapshot_type,
                period_start=period_start.isoformat() if period_start else None,
                period_end=period_end.isoformat() if period_end else None,
                accounting_method=accounting_method,
                payload=payload,
                captured_at=captured_at,
            )
        )


def _latest_timestamp(records: list[dict[str, Any]], current: str | None) -> str | None:
    latest = current
    for record in records:
        metadata = record.get("MetaData") if isinstance(record, dict) else None
        value = metadata.get("LastUpdatedTime") if isinstance(metadata, dict) else None
        if isinstance(value, str) and (latest is None or value > latest):
            latest = value
    return latest


def checkpoint_json(value: str | None) -> str | None:
    if value is None:
        return None
    return json.dumps({"changed_since": value})
