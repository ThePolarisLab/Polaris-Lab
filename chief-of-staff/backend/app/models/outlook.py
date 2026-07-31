"""Tenant-owned Outlook synchronization, evidence, and attention models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutlookFolder(Base):
    __tablename__ = "outlook_folders"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider_folder_id", name="uq_outlook_folder_org_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_folder_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    parent_folder_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    well_known_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    child_folder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_item_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unread_item_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    organization = relationship("Organization")


class OutlookFolderCheckpoint(Base):
    __tablename__ = "outlook_folder_checkpoints"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider_folder_id", name="uq_outlook_checkpoint_org_folder"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_folder_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    delta_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checkpoint_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_started", index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    organization = relationship("Organization")


class OutlookMessage(Base):
    __tablename__ = "outlook_messages"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider_message_id", name="uq_outlook_message_org_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_message_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    immutable_provider_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    internet_message_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    folder_provider_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender: Mapped[dict] = mapped_column(JSON, default=dict)
    reply_to: Mapped[list] = mapped_column(JSON, default=list)
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    cc_recipients: Mapped[list] = mapped_column(JSON, default=list)
    bcc_recipients: Mapped[list] = mapped_column(JSON, default=list)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    importance: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    flag: Mapped[dict] = mapped_column(JSON, default=dict)
    is_read: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_draft: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    body_content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_web_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_sync_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    organization = relationship("Organization")
    attachments = relationship("OutlookAttachment", cascade="all, delete-orphan", back_populates="message")
    classifications = relationship("OutlookMessageClassification", cascade="all, delete-orphan", back_populates="message")


class OutlookAttachment(Base):
    __tablename__ = "outlook_attachments"
    __table_args__ = (
        UniqueConstraint("organization_id", "message_id", "provider_attachment_id", name="uq_outlook_attachment_org_message_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("outlook_messages.id"), nullable=False, index=True)
    provider_attachment_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    filename: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_inline: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    content_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attachment_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    organization = relationship("Organization")
    message = relationship("OutlookMessage", back_populates="attachments")


class OutlookMessageClassification(Base):
    __tablename__ = "outlook_message_classifications"
    __table_args__ = (
        UniqueConstraint("organization_id", "message_id", "category", "rule", name="uq_outlook_classification_org_message_category_rule"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("outlook_messages.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    confidence: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    rule: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    organization = relationship("Organization")
    message = relationship("OutlookMessage", back_populates="classifications")


class OutlookSyncHistory(Base):
    __tablename__ = "outlook_sync_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    organization_slug: Mapped[str] = mapped_column(String, nullable=False, index=True)
    connector: Mapped[str] = mapped_column(String(60), nullable=False, default="outlook", index=True)
    sync_mode: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    folders_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attachments_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_before: Mapped[dict] = mapped_column(JSON, default=dict)
    checkpoint_after: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization = relationship("Organization")
