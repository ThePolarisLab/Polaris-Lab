"""Authenticated Outlook connector APIs."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.connectors.models import SyncResult
from app.connectors.outlook import OutlookConnector, OutlookConnectorError
from app.connectors.outlook_credentials import OutlookCredentialStore
from app.connectors.outlook_oauth import OutlookOAuthError, OutlookOAuthService
from app.database.database import SessionLocal
from app.models.outlook import OutlookFolder, OutlookMessage, OutlookSyncHistory
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/outlook", tags=["outlook"])


def _db() -> Session:
    with SessionLocal() as session:
        yield session


def _connector(organization_id: str) -> OutlookConnector:
    return OutlookConnector(credential_store=OutlookCredentialStore(organization_id))


def _frontend_url() -> str:
    return os.getenv("POLARIS_FRONTEND_URL", "http://localhost:5173").rstrip("/")


@router.get("/status")
def outlook_status(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ))) -> dict[str, Any]:
    """Return safe, tenant-bound Outlook connector status."""
    connector = _connector(principal.organization_id)
    health = connector.health()
    return {"health": health.model_dump(mode="json"), "status": connector.safe_status()}


@router.get("/connect")
def outlook_connect(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE))) -> dict[str, str]:
    """Return a Microsoft authorization URL after Polaris auth and org checks pass."""
    try:
        url = OutlookOAuthService().authorization_url(
            organization_id=principal.organization_id,
            identity_id=principal.identity_id,
        )
    except OutlookOAuthError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"authorization_url": url}


@router.get("/callback")
def outlook_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Public Microsoft callback protected by signed, one-use OAuth state."""
    if error:
        return RedirectResponse(f"{_frontend_url()}/executive/connectors?outlook=denied", status_code=status.HTTP_303_SEE_OTHER)
    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outlook callback is missing required parameters")
    try:
        OutlookOAuthService().complete_authorization(code=code, state=state)
    except OutlookOAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RedirectResponse(f"{_frontend_url()}/executive/connectors?outlook=connected", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/sync", response_model=SyncResult)
def outlook_sync(
    mode: str = Query(default="incremental", pattern="^(initial|full|incremental)$"),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
) -> SyncResult:
    """Run a read-only Outlook synchronization for the active organization."""
    result = _connector(principal.organization_id).sync() if mode == "incremental" else _run_sync(principal.organization_id, mode)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.model_dump(mode="json"))
    return result


@router.post("/disconnect")
def outlook_disconnect(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE))) -> dict[str, bool | str]:
    """Disconnect the active organization's Outlook credential without touching the mailbox."""
    try:
        _connector(principal.organization_id).disconnect()
    except OutlookConnectorError:
        OutlookCredentialStore(principal.organization_id).delete()
    return {"disconnected": True, "organization_id": principal.organization_id}


@router.get("/folders")
def outlook_folders(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    rows = (
        session.query(OutlookFolder)
        .filter(OutlookFolder.organization_id == principal.organization_id)
        .order_by(OutlookFolder.display_name.asc())
        .all()
    )
    return {
        "count": len(rows),
        "folders": [
            {
                "id": row.id,
                "provider_folder_id": row.provider_folder_id,
                "display_name": row.display_name,
                "parent_folder_id": row.parent_folder_id,
                "well_known_name": row.well_known_name,
                "total_item_count": row.total_item_count,
                "unread_item_count": row.unread_item_count,
                "is_sync_enabled": row.is_sync_enabled,
                "synced_at": _iso(row.synced_at),
            }
            for row in rows
        ],
    }


@router.get("/messages")
def outlook_messages(
    folder_id: str | None = Query(default=None),
    classification: str | None = Query(default=None),
    attention: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    query = _message_query(session, principal.organization_id)
    if folder_id:
        query = query.filter(OutlookMessage.folder_provider_id == folder_id)
    if classification:
        query = query.join(OutlookMessage.classifications).filter_by(category=classification)
    if attention:
        ids = {item["message_id"] for item in _attention_items(session, principal.organization_id, limit=500)}
        query = query.filter(OutlookMessage.id.in_(ids or {-1}))
    total = query.count()
    rows = query.order_by(desc(OutlookMessage.received_at), desc(OutlookMessage.synced_at)).offset(offset).limit(limit).all()
    return {"count": len(rows), "total": total, "messages": [_message_payload(row, include_body=False) for row in rows]}


@router.get("/messages/{message_id}")
def outlook_message(
    message_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    row = _message_query(session, principal.organization_id).filter(OutlookMessage.id == message_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlook message not found")
    return _message_payload(row, include_body=True)


@router.get("/attention")
def outlook_attention(
    limit: int = Query(default=25, ge=1, le=100),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    return {"count": 0, "items": []} if not _mailbox_address(principal.organization_id) else {"count": len(_attention_items(session, principal.organization_id, limit=limit)), "items": _attention_items(session, principal.organization_id, limit=limit)}


@router.get("/sync-history")
def outlook_sync_history(
    limit: int = Query(default=25, ge=1, le=100),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    rows = (
        session.query(OutlookSyncHistory)
        .filter(OutlookSyncHistory.organization_id == principal.organization_id)
        .order_by(desc(OutlookSyncHistory.started_at))
        .limit(limit)
        .all()
    )
    return {
        "count": len(rows),
        "history": [
            {
                "run_id": row.run_id,
                "sync_mode": row.sync_mode,
                "status": row.status,
                "folders_scanned": row.folders_scanned,
                "messages_discovered": row.messages_discovered,
                "messages_inserted": row.messages_inserted,
                "messages_updated": row.messages_updated,
                "messages_unchanged": row.messages_unchanged,
                "messages_removed": row.messages_removed,
                "attachments_indexed": row.attachments_indexed,
                "started_at": _iso(row.started_at),
                "completed_at": _iso(row.completed_at),
                "duration_ms": row.duration_ms,
                "error_category": row.error_category,
                "error_message": row.error_message,
            }
            for row in rows
        ],
    }


def _run_sync(organization_id: str, mode: str) -> SyncResult:
    from app.services.outlook_sync import OutlookSyncService

    return OutlookSyncService(connector=_connector(organization_id), organization_id=organization_id).sync(mode=mode)


def _message_query(session: Session, organization_id: str):
    return (
        session.query(OutlookMessage)
        .options(joinedload(OutlookMessage.classifications), joinedload(OutlookMessage.attachments))
        .filter(OutlookMessage.organization_id == organization_id, OutlookMessage.removed_at.is_(None))
    )


def _message_payload(row: OutlookMessage, *, include_body: bool) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "internet_message_id": row.internet_message_id,
        "folder_provider_id": row.folder_provider_id,
        "subject": row.subject,
        "sender": row.sender,
        "recipients": row.recipients,
        "cc_recipients": row.cc_recipients,
        "received_at": _iso(row.received_at),
        "sent_at": _iso(row.sent_at),
        "importance": row.importance,
        "categories": row.categories,
        "is_read": row.is_read,
        "is_draft": row.is_draft,
        "has_attachments": row.has_attachments,
        "body_truncated": row.body_truncated,
        "classifications": [
            {"category": item.category, "confidence": item.confidence, "reason": item.reason, "rule": item.rule}
            for item in row.classifications
        ],
        "attachments": [
            {
                "filename": item.filename,
                "mime_type": item.mime_type,
                "size": item.size,
                "is_inline": item.is_inline,
                "attachment_type": item.attachment_type,
            }
            for item in row.attachments
        ],
        "evidence": row.evidence,
        "observed_at": _iso(row.observed_at),
        "last_seen_at": _iso(row.last_seen_at),
    }
    if include_body:
        payload["body_text"] = row.body_text
    return payload


def _attention_items(session: Session, organization_id: str, *, limit: int) -> list[dict[str, Any]]:
    mailbox = _mailbox_address(organization_id)
    threshold = datetime.now(timezone.utc) - timedelta(hours=_followup_threshold_hours())
    rows = (
        _message_query(session, organization_id)
        .filter(OutlookMessage.is_draft.is_(False), OutlookMessage.received_at <= threshold)
        .order_by(desc(OutlookMessage.importance == "high"), desc(OutlookMessage.received_at))
        .limit(500)
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        sender = str((row.sender or {}).get("address") or "").casefold()
        if sender == mailbox:
            continue
        if _has_later_outbound_response(session, organization_id, mailbox, row):
            continue
        classifications = [item for item in row.classifications if item.category != "unclassified"]
        if not classifications and row.importance != "high":
            continue
        category = classifications[0].category if classifications else "High Importance"
        items.append(
            {
                "message_id": row.id,
                "subject": row.subject,
                "sender": row.sender,
                "received_at": _iso(row.received_at),
                "category": category,
                "reason": f"Possible follow-up: inbound {category} communication has no later sent response in this conversation.",
                "confidence": "medium" if classifications else "low",
                "evidence": row.evidence,
            }
        )
        if len(items) >= limit:
            break
    return items


def _has_later_outbound_response(session: Session, organization_id: str, mailbox: str, row: OutlookMessage) -> bool:
    if not row.conversation_id or not row.received_at:
        return False
    candidate = (
        session.query(OutlookMessage)
        .filter(
            OutlookMessage.organization_id == organization_id,
            OutlookMessage.conversation_id == row.conversation_id,
            OutlookMessage.sent_at > row.received_at,
            OutlookMessage.removed_at.is_(None),
        )
        .all()
    )
    return any(str((item.sender or {}).get("address") or "").casefold() == mailbox for item in candidate)


def _mailbox_address(organization_id: str) -> str:
    try:
        metadata = OutlookCredentialStore(organization_id).metadata()
    except Exception:
        return ""
    return str(metadata.get("mailbox_address") or "").casefold()


def _followup_threshold_hours() -> int:
    return max(1, int(os.getenv("POLARIS_OUTLOOK_FOLLOWUP_THRESHOLD_HOURS", "24")))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
