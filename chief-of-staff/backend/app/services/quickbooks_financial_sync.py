"""Synchronize QuickBooks financial data into Polaris-owned storage."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any, Callable, Literal

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

logger = logging.getLogger(__name__)


class QuickBooksSyncStageError(RuntimeError):
    """Safe sync-stage failure used by the API to return actionable diagnostics."""

    def __init__(
        self,
        *,
        stage: str,
        organization_id: str,
        mode: str,
        message: str,
        exception_type: str,
        company_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.organization_id = organization_id
        self.mode = mode
        self.message = message
        self.exception_type = exception_type
        self.company_id = company_id

    def payload(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "message": self.message,
            "exception": self.exception_type,
            "organization_id": self.organization_id,
            "company_id": self.company_id,
            "sync_mode": self.mode,
        }


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
        stage = "initialize_sync"
        checkpoint_before = self._last_checkpoint() if mode == "incremental" else None
        history_id = self._start_history(started_at, mode, checkpoint_before)

        def run_stage(name: str, operation: Callable[[], Any]) -> Any:
            nonlocal stage
            stage = name
            try:
                return operation()
            except QuickBooksSyncStageError:
                raise
            except Exception as exc:
                raise self._stage_error(name, mode, exc) from exc

        try:
            lock_context = run_stage("acquire_sync_lock", lambda: self.connector.organization_sync_lock())
            with lock_context:
                run_stage("load_stored_oauth_tokens", self.store.load_credential)
                run_stage("refresh_intuit_token_if_needed", self.connector.authenticate)
                run_stage("build_quickbooks_client", self.connector._http)

                company = run_stage("fetch_company_info", self.connector.company_info)
                verification = run_stage("verify_company_identity", self.connector.verify_company_identity)
                changed_since = checkpoint_before if mode == "incremental" else None
                now = datetime.now(timezone.utc)
                resource_counts: dict[str, int] = {"company": 1}
                report_availability: dict[str, bool] = {}
                latest_observed_at = checkpoint_before

                accounts = run_stage(
                    "fetch_accounts",
                    lambda: self.connector.list_all_resource("accounts", changed_since=changed_since),
                )
                resource_counts["accounts"] = len(accounts)
                resources: dict[str, list[dict[str, Any]]] = {"accounts": accounts}
                for resource in RESOURCE_ENTITY:
                    if resource == "accounts":
                        continue
                    rows = run_stage(
                        f"fetch_{resource}",
                        lambda resource=resource: self.connector.list_all_resource(resource, changed_since=changed_since),
                    )
                    resources[resource] = rows
                    resource_counts[resource] = len(rows)
                    latest_observed_at = _latest_timestamp(rows, latest_observed_at)

                reports: dict[str, dict[str, Any]] = {}
                for report_key in REPORT_NAMES:
                    reports[report_key] = run_stage(
                        f"fetch_report_{report_key}",
                        lambda report_key=report_key: self.connector.report(report_key, start_date=start_date, end_date=end_date),
                    )
                    report_availability[report_key] = True

                checkpoint_after = latest_observed_at or now.isoformat()
                db_session = run_stage("open_database_session", SessionLocal)
                try:
                    run_stage(
                        "write_to_database",
                        lambda: self._write_sync_payload(
                            db_session,
                            accounts,
                            company,
                            resources,
                            reports,
                            now,
                            start_date,
                            end_date,
                            mode,
                        ),
                    )
                    run_stage(
                        "update_last_sync",
                        lambda: self._mark_history_success(
                            db_session,
                            history_id,
                            now,
                            timer,
                            accounts,
                            verification,
                            resource_counts,
                            report_availability,
                            checkpoint_after,
                        ),
                    )
                    run_stage("commit_transaction", db_session.commit)
                except Exception:
                    db_session.rollback()
                    raise
                finally:
                    db_session.close()
                self.store.record_sync_success()
                return self.status()
        except Exception as exc:
            sync_error = exc if isinstance(exc, QuickBooksSyncStageError) else self._stage_error(stage, mode, exc)
            logger.exception(
                "QuickBooks financial sync failed",
                extra={
                    "organization_id": self.organization_id,
                    "company_id": sync_error.company_id,
                    "sync_mode": mode,
                    "sync_stage": sync_error.stage,
                },
            )
            safe_message = sync_error.message[:1000]
            self._record_failure(history_id, timer, safe_message, sync_error)
            if isinstance(exc, QuickBooksConnectorError):
                self.store.record_sync_failure(safe_message, status=exc.status.value)
            else:
                self.store.record_sync_failure(f"{sync_error.stage}: {safe_message}")
            raise sync_error from exc

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

    def _stage_error(self, stage: str, mode: str, exc: Exception) -> QuickBooksSyncStageError:
        return QuickBooksSyncStageError(
            stage=stage,
            organization_id=self.organization_id,
            mode=mode,
            message=str(exc)[:1000] or "QuickBooks sync stage failed",
            exception_type=exc.__class__.__name__,
            company_id=self._company_id(),
        )

    def _company_id(self) -> str | None:
        realm_id = getattr(self.connector, "_realm_id", None)
        if realm_id:
            return str(realm_id)
        try:
            return self.store.load_credential().realm_id
        except Exception:
            return None

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

    def _record_failure(
        self,
        history_id: int,
        timer: float,
        safe_message: str,
        sync_error: QuickBooksSyncStageError,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            history = session.get(FinancialSyncHistory, history_id)
            if history is None:
                return
            history.status = "failed"
            history.completed_at = completed_at
            history.duration_ms = round((perf_counter() - timer) * 1000)
            history.error_message = f"{sync_error.stage}: {safe_message}"

    def _last_checkpoint(self) -> str | None:
        with SessionLocal() as session:
            history = (
                session.query(FinancialSyncHistory)
                .filter_by(organization_id=self.organization_id, status="success")
                .order_by(FinancialSyncHistory.completed_at.desc())
                .first()
            )
            return history.checkpoint_after if history else None

    def _write_sync_payload(
        self,
        session,
        accounts: list[dict[str, Any]],
        company: dict[str, Any],
        resources: dict[str, list[dict[str, Any]]],
        reports: dict[str, dict[str, Any]],
        captured_at: datetime,
        start_date: date | None,
        end_date: date | None,
        mode: str,
    ) -> None:
        self._upsert_accounts(session, accounts, captured_at)
        self._snapshot(session, "company", company, captured_at, start_date, end_date)
        for resource, rows in resources.items():
            self._snapshot(
                session,
                f"resource_{resource}",
                {"records": rows, "count": len(rows), "mode": mode},
                captured_at,
                start_date,
                end_date,
            )
        for snapshot_type, payload in reports.items():
            header = payload.get("Header") if isinstance(payload, dict) else {}
            self._snapshot(
                session,
                snapshot_type,
                payload,
                captured_at,
                date.fromisoformat(str((header or {}).get("StartPeriod"))) if (header or {}).get("StartPeriod") else start_date,
                date.fromisoformat(str((header or {}).get("EndPeriod"))) if (header or {}).get("EndPeriod") else end_date,
                str((header or {}).get("ReportBasis") or "Accrual"),
            )

    def _mark_history_success(
        self,
        session,
        history_id: int,
        completed_at: datetime,
        timer: float,
        accounts: list[dict[str, Any]],
        verification: dict[str, Any],
        resource_counts: dict[str, int],
        report_availability: dict[str, bool],
        checkpoint_after: str,
    ) -> None:
        history = session.get(FinancialSyncHistory, history_id)
        if history is None:
            raise RuntimeError("QuickBooks sync history row was not found")
        history.status = "success"
        history.completed_at = completed_at
        history.duration_ms = round((perf_counter() - timer) * 1000)
        history.accounts_imported = len(accounts)
        history.company_name = str(verification["verified_company_name"])
        history.resource_counts = resource_counts
        history.report_availability = report_availability
        history.checkpoint_after = checkpoint_after
        history.verification_status = str(verification["identity_verification_status"])

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
