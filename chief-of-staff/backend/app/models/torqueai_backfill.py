"""Control-plane evidence only; no relationship/cascade to operational records."""
from datetime import datetime, timezone

from sqlalchemy import (JSON, CheckConstraint, Column, Date, DateTime, ForeignKeyConstraint,
                        Integer, MetaData, String, Table, UniqueConstraint)

from app.database.database import Base

STATES = "'planned','previewed','approved','running','completed','failed','blocked'"
SEMANTICS = "dispatch_order_date"
CLAIM_NAMESPACE = "torqueai_historical_preview"


def define_tables(metadata: MetaData):
    """Shared runtime schema; Alembic carries its own frozen copy."""
    manifest = Table(
        "torqueai_backfill_manifests", metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String, nullable=False),
        Column("request_key", String(120), nullable=False),
        Column("operator", String(120), nullable=False),
        Column("code_sha", String(40), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("window_semantics", String(40), nullable=False),
        Column("execution_mode", String(30), nullable=False),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "id", name="uq_tai_bf_manifest_tenant_id"),
        UniqueConstraint("organization_id", "request_key", name="uq_tai_bf_manifest_request"),
        CheckConstraint("window_semantics = 'dispatch_order_date'", name="ck_tai_bf_semantics"),
        CheckConstraint("execution_mode = 'preview_only'", name="ck_tai_bf_execution_mode"),
    )
    window = Table(
        "torqueai_backfill_windows", metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String, nullable=False),
        Column("manifest_id", String(36), nullable=False),
        Column("date_from", Date, nullable=False),
        Column("date_to", Date, nullable=False),
        Column("status", String(20), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("started_at", DateTime(timezone=True)),
        Column("completed_at", DateTime(timezone=True)),
        Column("approved_at", DateTime(timezone=True)),
        Column("approved_by", String(120)),
        Column("active_attempt_id", String(36)),
        Column("lease_until", DateTime(timezone=True)),
        ForeignKeyConstraint(["organization_id", "manifest_id"],
                             ["torqueai_backfill_manifests.organization_id", "torqueai_backfill_manifests.id"]),
        UniqueConstraint("organization_id", "id", name="uq_tai_bf_window_tenant_id"),
        UniqueConstraint("organization_id", "date_from", "date_to", name="uq_tai_bf_window_interval"),
        CheckConstraint("date_to >= date_from", name="ck_tai_bf_window_order"),
        CheckConstraint("date_to - date_from <= 6", name="ck_tai_bf_window_seven_days").ddl_if(dialect="postgresql"),
        CheckConstraint("julianday(date_to) - julianday(date_from) <= 6", name="ck_tai_bf_window_seven_days_sqlite").ddl_if(dialect="sqlite"),
        CheckConstraint(f"status IN ({STATES})", name="ck_tai_bf_window_status"),
    )
    attempt = Table(
        "torqueai_backfill_attempts", metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String, nullable=False),
        Column("window_id", String(36), nullable=False),
        Column("request_key", String(120), nullable=False),
        Column("operator", String(120), nullable=False),
        Column("code_sha", String(40), nullable=False),
        Column("claim_namespace", String(40), nullable=False),
        Column("started_at", DateTime(timezone=True), nullable=False),
        Column("completed_at", DateTime(timezone=True)),
        Column("status", String(20), nullable=False),
        Column("evidence", JSON),
        Column("evidence_fingerprint", String(64)),
        ForeignKeyConstraint(["organization_id", "window_id"],
                             ["torqueai_backfill_windows.organization_id", "torqueai_backfill_windows.id"]),
        UniqueConstraint("organization_id", "id", name="uq_tai_bf_attempt_tenant_id"),
        UniqueConstraint("organization_id", "window_id", "request_key", name="uq_tai_bf_attempt_request"),
        CheckConstraint("claim_namespace = 'torqueai_historical_preview'", name="ck_tai_bf_claim_namespace"),
        CheckConstraint("status IN ('previewing','previewed','failed','blocked')", name="ck_tai_bf_attempt_status"),
    )
    identity = Table(
        "torqueai_backfill_identity_evidence", metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String, nullable=False),
        Column("attempt_id", String(36), nullable=False),
        Column("provider_load_number", String(120), nullable=False),
        Column("provider_order_number", String(255), nullable=False),
        Column("classification", String(30), nullable=False),
        Column("quarantined", Integer, nullable=False),
        Column("conflicting_order_numbers", JSON, nullable=False),
        Column("before_image", JSON(none_as_null=True)),
        Column("before_fingerprint", String(64)),
        Column("after_image", JSON(none_as_null=True)),
        Column("after_fingerprint", String(64)),
        ForeignKeyConstraint(["organization_id", "attempt_id"],
                             ["torqueai_backfill_attempts.organization_id", "torqueai_backfill_attempts.id"]),
        UniqueConstraint("organization_id", "attempt_id", "provider_load_number", "provider_order_number",
                         name="uq_tai_bf_evidence_identity"),
        CheckConstraint("classification IN ('would_insert','would_update','unchanged','identity_conflict')",
                        name="ck_tai_bf_evidence_classification"),
        CheckConstraint("(classification = 'identity_conflict' AND quarantined = 1) OR "
                        "(classification <> 'identity_conflict' AND quarantined = 0)", name="ck_tai_bf_quarantine"),
        CheckConstraint("(before_image IS NULL AND before_fingerprint IS NULL) OR "
                        "(before_image IS NOT NULL AND before_fingerprint IS NOT NULL)", name="ck_tai_bf_before_pair"),
        CheckConstraint("(after_image IS NULL AND after_fingerprint IS NULL) OR "
                        "(after_image IS NOT NULL AND after_fingerprint IS NOT NULL)", name="ck_tai_bf_after_pair"),
    )
    return manifest, window, attempt, identity


MANIFEST, WINDOW, ATTEMPT, IDENTITY = define_tables(Base.metadata)


def utcnow():
    return datetime.now(timezone.utc)
