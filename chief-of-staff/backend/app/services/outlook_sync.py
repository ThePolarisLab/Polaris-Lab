"""Checkpointed read-only Outlook synchronization into Polaris-owned tables."""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.connectors.models import ConnectorStatus, SyncResult
from app.connectors.outlook import OutlookConnector, OutlookConnectorError
from app.database.database import SessionLocal
from app.models.outlook import (
    OutlookAttachment,
    OutlookFolder,
    OutlookFolderCheckpoint,
    OutlookMessage,
    OutlookMessageClassification,
    OutlookSyncHistory,
)
from app.organizations.models import Organization

DEFAULT_FOLDERS = ("Inbox", "Sent Items", "Archive")
EXCLUDED_FOLDERS = {"deleted items", "junk email"}


class OutlookSyncError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass
class OutlookSyncStats:
    folders_scanned: int = 0
    messages_discovered: int = 0
    messages_inserted: int = 0
    messages_updated: int = 0
    messages_unchanged: int = 0
    messages_removed: int = 0
    attachments_indexed: int = 0
    checkpoint_before: dict[str, str | None] = field(default_factory=dict)
    checkpoint_after: dict[str, str | None] = field(default_factory=dict)

    @property
    def records_read(self) -> int:
        return self.messages_discovered + self.attachments_indexed

    @property
    def records_written(self) -> int:
        return self.messages_inserted + self.messages_updated + self.attachments_indexed + self.messages_removed


class OutlookSyncService:
    """Synchronize Outlook folders/messages with tenant isolation and durable checkpoints."""

    def __init__(self, *, connector: OutlookConnector, organization_id: str) -> None:
        self.connector = connector
        self.organization_id = organization_id

    def sync(self, *, mode: str = "incremental") -> SyncResult:
        if mode not in {"initial", "full", "incremental"}:
            raise OutlookSyncError("validate_mode", "Outlook sync mode must be initial, full, or incremental")
        run_id = f"outlook-{uuid4()}"
        started_at = datetime.now(timezone.utc)
        stats = OutlookSyncStats()
        history_id: int | None = None

        with self.connector.organization_sync_lock():
            try:
                with SessionLocal.begin() as session:
                    organization = _organization(session, self.organization_id)
                    history = OutlookSyncHistory(
                        organization_id=organization.id,
                        organization_slug=organization.slug,
                        connector="outlook",
                        sync_mode=mode,
                        status="running",
                        run_id=run_id,
                        started_at=started_at,
                        checkpoint_before={},
                        checkpoint_after={},
                    )
                    session.add(history)
                    session.flush()
                    history_id = history.id

                self.connector.authenticate()
                mailbox = self.connector.mailbox_identity()
                folders = self._discover_folders(run_id)
                active_folders = [folder for folder in folders if _folder_allowed(folder.display_name)]
                stats.folders_scanned = len(active_folders)

                for folder in active_folders:
                    self._sync_folder(folder, mode=mode, run_id=run_id, stats=stats)

                with SessionLocal.begin() as session:
                    history = session.get(OutlookSyncHistory, history_id)
                    if history is not None:
                        completed_at = datetime.now(timezone.utc)
                        history.status = "success"
                        history.completed_at = completed_at
                        history.duration_ms = int((completed_at - started_at).total_seconds() * 1000)
                        history.folders_scanned = stats.folders_scanned
                        history.messages_discovered = stats.messages_discovered
                        history.messages_inserted = stats.messages_inserted
                        history.messages_updated = stats.messages_updated
                        history.messages_unchanged = stats.messages_unchanged
                        history.messages_removed = stats.messages_removed
                        history.attachments_indexed = stats.attachments_indexed
                        history.checkpoint_before = stats.checkpoint_before
                        history.checkpoint_after = stats.checkpoint_after
                self.connector._store().record_sync_success()
                completed_at = datetime.now(timezone.utc)
                return SyncResult(
                    connector="outlook",
                    started_at=started_at,
                    completed_at=completed_at,
                    records_read=stats.records_read,
                    records_written=stats.records_written,
                    events_published=stats.messages_inserted + stats.messages_updated,
                    success=True,
                )
            except Exception as exc:
                safe_message = _safe_error(exc)
                status_value = getattr(getattr(exc, "status", None), "value", None) or ConnectorStatus.SYNCHRONIZATION_FAILED.value
                with SessionLocal.begin() as session:
                    if history_id is not None:
                        history = session.get(OutlookSyncHistory, history_id)
                        if history is not None:
                            completed_at = datetime.now(timezone.utc)
                            history.status = "failed"
                            history.completed_at = completed_at
                            history.duration_ms = int((completed_at - started_at).total_seconds() * 1000)
                            history.error_category = getattr(exc, "stage", "sync_failed")
                            history.error_message = safe_message
                            history.checkpoint_before = stats.checkpoint_before
                            history.checkpoint_after = {}
                self.connector._store().record_sync_failure(safe_message, status=status_value)
                completed_at = datetime.now(timezone.utc)
                return SyncResult(
                    connector="outlook",
                    started_at=started_at,
                    completed_at=completed_at,
                    records_read=stats.records_read,
                    records_written=stats.records_written,
                    success=False,
                    errors=[safe_message],
                )

    def _discover_folders(self, run_id: str) -> list[OutlookFolder]:
        org_slug = self._organization_slug()
        folders: list[dict] = []
        queue: list[tuple[str | None, dict | None]] = [(None, None)]
        seen: set[str] = set()
        while queue:
            parent_id, marker = queue.pop(0)
            if marker and marker.get("next"):
                payload = self.connector.list_child_folders(parent_id or "", url=marker["next"])
            elif parent_id:
                payload = self.connector.list_child_folders(parent_id)
            else:
                payload = self.connector.list_folders()
            page = payload.get("value") or []
            if not isinstance(page, list):
                raise OutlookSyncError("fetch_folders", "Outlook folder response was malformed")
            for item in page:
                if not isinstance(item, dict):
                    continue
                folder_id = str(item.get("id") or "")
                if not folder_id or folder_id in seen:
                    continue
                seen.add(folder_id)
                folders.append(item)
                if int(item.get("childFolderCount") or 0) > 0:
                    queue.append((folder_id, None))
            next_link = payload.get("@odata.nextLink")
            if isinstance(next_link, str) and next_link:
                queue.append((parent_id, {"next": next_link}))

        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            stored: list[OutlookFolder] = []
            for item in folders:
                folder_id = str(item.get("id") or "")
                name = str(item.get("displayName") or "")
                enabled = _folder_allowed(name)
                row = session.query(OutlookFolder).filter_by(organization_id=self.organization_id, provider_folder_id=folder_id).one_or_none()
                values = {
                    "organization_slug": org_slug,
                    "display_name": name,
                    "parent_folder_id": item.get("parentFolderId"),
                    "well_known_name": _well_known_name(name),
                    "child_folder_count": item.get("childFolderCount"),
                    "total_item_count": item.get("totalItemCount"),
                    "unread_item_count": item.get("unreadItemCount"),
                    "is_sync_enabled": enabled,
                    "synced_at": now,
                }
                if row is None:
                    row = OutlookFolder(
                        organization_id=self.organization_id,
                        provider_folder_id=folder_id,
                        **values,
                    )
                    session.add(row)
                    session.flush()
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
                if enabled:
                    stored.append(row)
            session.flush()
            return [
                OutlookFolder(
                    id=row.id,
                    organization_id=row.organization_id,
                    organization_slug=row.organization_slug,
                    provider_folder_id=row.provider_folder_id,
                    display_name=row.display_name,
                    is_sync_enabled=row.is_sync_enabled,
                )
                for row in stored
            ]

    def _sync_folder(self, folder: OutlookFolder, *, mode: str, run_id: str, stats: OutlookSyncStats) -> None:
        checkpoint_before = self._checkpoint(folder.provider_folder_id)
        stats.checkpoint_before[folder.provider_folder_id] = checkpoint_before
        delta_after: str | None = None
        next_url: str | None = None
        first = True
        while True:
            if mode == "incremental" and checkpoint_before and first:
                payload = self.connector.delta_messages(folder.provider_folder_id, delta_link=checkpoint_before)
            elif mode == "incremental":
                payload = self.connector.delta_messages(folder.provider_folder_id) if first else self.connector.delta_messages(folder.provider_folder_id, delta_link=next_url)
            else:
                since = (datetime.now(timezone.utc) - timedelta(days=_initial_lookback_days())).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                payload = self.connector.list_messages(folder.provider_folder_id, url=next_url, since_iso=since if first else None)
            first = False
            messages = payload.get("value") or []
            if not isinstance(messages, list):
                raise OutlookSyncError("fetch_messages", "Outlook message response was malformed")
            stats.messages_discovered += len(messages)
            self._persist_messages(folder, messages, run_id=run_id, stats=stats)
            next_link = payload.get("@odata.nextLink")
            delta_link = payload.get("@odata.deltaLink")
            if isinstance(delta_link, str) and delta_link:
                delta_after = delta_link
            if isinstance(next_link, str) and next_link:
                next_url = next_link
                continue
            break
        if delta_after:
            self._save_checkpoint(folder.provider_folder_id, delta_after)
            stats.checkpoint_after[folder.provider_folder_id] = delta_after

    def _persist_messages(self, folder: OutlookFolder, messages: list[dict], *, run_id: str, stats: OutlookSyncStats) -> None:
        org_slug = self._organization_slug()
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            for message in messages:
                provider_id = str(message.get("id") or "")
                if not provider_id:
                    continue
                if "@removed" in message:
                    existing = session.query(OutlookMessage).filter_by(organization_id=self.organization_id, provider_message_id=provider_id).one_or_none()
                    if existing and existing.removed_at is None:
                        existing.removed_at = now
                        existing.last_seen_at = now
                        stats.messages_removed += 1
                    continue
                normalized = _normalize_message(message, organization_id=self.organization_id, organization_slug=org_slug, folder_id=folder.provider_folder_id, run_id=run_id, observed_at=now)
                existing = session.query(OutlookMessage).filter_by(organization_id=self.organization_id, provider_message_id=provider_id).one_or_none()
                if existing is None:
                    existing = OutlookMessage(**normalized)
                    session.add(existing)
                    session.flush()
                    stats.messages_inserted += 1
                else:
                    if _message_changed(existing, normalized):
                        for key, value in normalized.items():
                            setattr(existing, key, value)
                        stats.messages_updated += 1
                    else:
                        existing.last_seen_at = now
                        stats.messages_unchanged += 1
                _replace_classifications(session, existing, org_slug=org_slug, classifications=classify_message(existing))
                if bool(message.get("hasAttachments")):
                    stats.attachments_indexed += self._persist_attachments(session, existing, org_slug=org_slug)

    def _persist_attachments(self, session: Session, message: OutlookMessage, *, org_slug: str) -> int:
        payload = self.connector.list_attachments(message.provider_message_id)
        attachments = payload.get("value") or []
        if not isinstance(attachments, list):
            raise OutlookSyncError("fetch_attachments", "Outlook attachment response was malformed")
        count = 0
        for item in attachments:
            if not isinstance(item, dict):
                continue
            attachment_id = str(item.get("id") or "")
            if not attachment_id:
                continue
            row = session.query(OutlookAttachment).filter_by(
                organization_id=self.organization_id,
                message_id=message.id,
                provider_attachment_id=attachment_id,
            ).one_or_none()
            values = {
                "organization_slug": org_slug,
                "filename": item.get("name"),
                "mime_type": item.get("contentType"),
                "size": item.get("size"),
                "is_inline": item.get("isInline"),
                "content_id": item.get("contentId"),
                "attachment_type": str(item.get("@odata.type") or "attachment"),
                "synced_at": datetime.now(timezone.utc),
            }
            if row is None:
                session.add(
                    OutlookAttachment(
                        organization_id=self.organization_id,
                        message_id=message.id,
                        provider_attachment_id=attachment_id,
                        **values,
                    )
                )
                count += 1
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        return count

    def _checkpoint(self, folder_id: str) -> str | None:
        with SessionLocal() as session:
            row = session.query(OutlookFolderCheckpoint).filter_by(organization_id=self.organization_id, provider_folder_id=folder_id).one_or_none()
            return row.delta_link if row else None

    def _save_checkpoint(self, folder_id: str, delta_link: str) -> None:
        org_slug = self._organization_slug()
        now = datetime.now(timezone.utc)
        with SessionLocal.begin() as session:
            row = session.query(OutlookFolderCheckpoint).filter_by(organization_id=self.organization_id, provider_folder_id=folder_id).one_or_none()
            if row is None:
                session.add(
                    OutlookFolderCheckpoint(
                        organization_id=self.organization_id,
                        organization_slug=org_slug,
                        provider_folder_id=folder_id,
                        delta_link=delta_link,
                        last_successful_sync_at=now,
                        checkpoint_status="healthy",
                        updated_at=now,
                    )
                )
            else:
                row.organization_slug = org_slug
                row.delta_link = delta_link
                row.last_successful_sync_at = now
                row.checkpoint_status = "healthy"
                row.updated_at = now

    def _organization_slug(self) -> str:
        with SessionLocal() as session:
            organization = _organization(session, self.organization_id)
            return organization.slug


def _organization(session: Session, organization_id: str) -> Organization:
    organization = session.get(Organization, organization_id)
    if organization is None or not organization.slug or not organization.slug.strip():
        raise OutlookSyncError("organization_context", "Outlook synchronization requires a valid organization")
    return organization


def _folder_allowed(name: str) -> bool:
    normalized = _norm(name)
    if normalized in EXCLUDED_FOLDERS:
        return False
    allowed = {_norm(value) for value in os.getenv("POLARIS_OUTLOOK_SYNC_FOLDERS", ",".join(DEFAULT_FOLDERS)).split(",") if value.strip()}
    return normalized in allowed


def _well_known_name(name: str) -> str | None:
    normalized = _norm(name)
    return normalized.replace(" ", "_") if normalized in {_norm(value) for value in DEFAULT_FOLDERS} else None


def _initial_lookback_days() -> int:
    return max(1, min(int(os.getenv("POLARIS_OUTLOOK_INITIAL_LOOKBACK_DAYS", "14")), 365))


def _max_body_bytes() -> int:
    return max(0, int(os.getenv("POLARIS_OUTLOOK_MAX_BODY_BYTES", "12000")))


def _normalize_message(message: dict, *, organization_id: str, organization_slug: str, folder_id: str, run_id: str, observed_at: datetime) -> dict:
    body = message.get("body") if isinstance(message.get("body"), dict) else {}
    body_text, truncated = _safe_body(str(body.get("content") or ""))
    provider_folder_id = str(message.get("parentFolderId") or folder_id)
    return {
        "organization_id": organization_id,
        "organization_slug": organization_slug,
        "provider_message_id": str(message.get("id") or ""),
        "immutable_provider_id": message.get("immutableId"),
        "conversation_id": message.get("conversationId"),
        "internet_message_id": message.get("internetMessageId"),
        "folder_provider_id": provider_folder_id,
        "subject": _safe_subject(message.get("subject")),
        "sender": _email_identity(message.get("sender")),
        "reply_to": _email_list(message.get("replyTo")),
        "recipients": _email_list(message.get("toRecipients")),
        "cc_recipients": _email_list(message.get("ccRecipients")),
        "bcc_recipients": _email_list(message.get("bccRecipients")),
        "received_at": _parse_dt(message.get("receivedDateTime")),
        "sent_at": _parse_dt(message.get("sentDateTime")),
        "created_at": _parse_dt(message.get("createdDateTime")),
        "modified_at": _parse_dt(message.get("lastModifiedDateTime")),
        "importance": message.get("importance"),
        "categories": message.get("categories") if isinstance(message.get("categories"), list) else [],
        "flag": message.get("flag") if isinstance(message.get("flag"), dict) else {},
        "is_read": message.get("isRead"),
        "is_draft": message.get("isDraft"),
        "has_attachments": bool(message.get("hasAttachments")),
        "body_content_type": body.get("contentType"),
        "body_text": body_text,
        "body_truncated": truncated,
        "source_web_link": message.get("webLink"),
        "evidence": {
            "connector": "outlook",
            "provider": "microsoft_graph",
            "provider_message_id": str(message.get("id") or ""),
            "folder_provider_id": provider_folder_id,
            "observed_at": observed_at.isoformat(),
            "sync_run_id": run_id,
        },
        "observed_at": observed_at,
        "last_seen_at": observed_at,
        "removed_at": None,
        "last_sync_run_id": run_id,
        "synced_at": observed_at,
    }


def _message_changed(row: OutlookMessage, values: dict) -> bool:
    for key in ("subject", "modified_at", "folder_provider_id", "importance", "body_text", "has_attachments", "is_read", "is_draft"):
        if getattr(row, key) != values.get(key):
            return True
    return False


def _replace_classifications(session: Session, message: OutlookMessage, *, org_slug: str, classifications: list[dict]) -> None:
    session.query(OutlookMessageClassification).filter_by(organization_id=message.organization_id, message_id=message.id).delete()
    for item in classifications:
        session.add(
            OutlookMessageClassification(
                organization_id=message.organization_id,
                organization_slug=org_slug,
                message_id=message.id,
                category=item["category"],
                confidence=item["confidence"],
                reason=item["reason"],
                rule=item["rule"],
            )
        )


def classify_message(message: OutlookMessage) -> list[dict]:
    text = " ".join([message.subject or "", message.body_text or "", str((message.sender or {}).get("address") or "")]).lower()
    rules = [
        ("Invoice", ("invoice", "statement", "remittance"), "finance_invoice_terms"),
        ("Payment", ("payment", "paid", "eft", "wire"), "finance_payment_terms"),
        ("Collections", ("overdue", "past due", "collection"), "finance_collections_terms"),
        ("Accounts Receivable", ("accounts receivable", "a/r", "ar "), "finance_ar_terms"),
        ("Accounts Payable", ("accounts payable", "a/p", "ap "), "finance_ap_terms"),
        ("Dispatch", ("dispatch", "load", "pickup", "delivery"), "operations_dispatch_terms"),
        ("Driver", ("driver", "driver pay", "driver issue"), "operations_driver_terms"),
        ("Border", ("border", "crossing", "port of entry"), "operations_border_terms"),
        ("Customs", ("customs", "pars", "ace", "clearance"), "operations_customs_terms"),
        ("Safety", ("safety", "incident", "accident", "violation"), "operations_safety_terms"),
        ("Maintenance", ("maintenance", "repair", "service"), "operations_maintenance_terms"),
        ("Rate Request", ("rate request", "quote", "lane rate"), "customer_rate_terms"),
        ("Load Tender", ("tender", "load confirmation"), "customer_tender_terms"),
        ("Complaint", ("complaint", "unhappy", "escalation"), "customer_complaint_terms"),
        ("POD", ("pod", "proof of delivery"), "customer_pod_terms"),
        ("Claim", ("claim", "damage", "shortage"), "customer_claim_terms"),
        ("Legal", ("legal", "lawyer", "court"), "management_legal_terms"),
        ("HR", ("hr", "human resources", "employment"), "management_hr_terms"),
        ("Insurance", ("insurance", "policy", "certificate"), "management_insurance_terms"),
        ("Compliance", ("compliance", "audit", "certificate"), "management_compliance_terms"),
        ("Government", ("government", "cra", "cbsa", "dot", "fmcsa"), "management_government_terms"),
    ]
    matches = [
        {"category": category, "confidence": "medium", "reason": f"Matched deterministic {rule} rule", "rule": rule}
        for category, needles, rule in rules
        if any(needle in text for needle in needles)
    ]
    if message.importance == "high":
        matches.append({"category": "High Importance", "confidence": "high", "reason": "Source message importance is high", "rule": "source_high_importance"})
    return matches or [{"category": "unclassified", "confidence": "low", "reason": "No deterministic rule matched", "rule": "unclassified_fallback"}]


def _safe_body(value: str) -> tuple[str, bool]:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    text = re.sub(r"\s+", " ", text).strip()
    max_bytes = _max_body_bytes()
    if max_bytes <= 0:
        return "", bool(text)
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


def _safe_subject(value) -> str | None:
    if value is None:
        return None
    return str(value)[:1000]


def _email_identity(value) -> dict:
    if not isinstance(value, dict):
        return {}
    address = value.get("emailAddress") if isinstance(value.get("emailAddress"), dict) else {}
    return {"name": address.get("name"), "address": str(address.get("address") or "").lower()}


def _email_list(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [_email_identity(item) for item in value if isinstance(item, dict)]


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _safe_error(exc: Exception) -> str:
    value = str(exc) or exc.__class__.__name__
    for marker in ("access_token", "refresh_token", "client_secret", "authorization", "code", "state"):
        value = value.replace(marker + "=", marker + "=[REDACTED]")
    return value[:500]
