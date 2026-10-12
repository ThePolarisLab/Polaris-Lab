"""Add minimized historical update review evidence; no operational changes."""
from alembic import op
from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKeyConstraint, Integer, MetaData, String, Table, UniqueConstraint
revision = "202610110001"
down_revision = "202610070001"
branch_labels = None
depends_on = None

def define_update_table(metadata):
    """Separate minimized proposed evidence; legacy full-bundle images stay distinct."""
    return Table(
        "torqueai_backfill_update_evidence", metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String, nullable=False),
        Column("manifest_id", String(36), nullable=False),
        Column("window_id", String(36), nullable=False),
        Column("attempt_id", String(36), nullable=False),
        Column("identity_evidence_id", String(36), nullable=False),
        Column("dispatch_id", Integer, nullable=False),
        Column("provider_load_number", String(120), nullable=False),
        Column("provider_order_number", String(255), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("evidence", JSON, nullable=False),
        Column("evidence_fingerprint", String(64), nullable=False),
        ForeignKeyConstraint(["identity_evidence_id"], ["torqueai_backfill_identity_evidence.id"]),
        ForeignKeyConstraint(["organization_id", "manifest_id"],
                             ["torqueai_backfill_manifests.organization_id", "torqueai_backfill_manifests.id"]),
        ForeignKeyConstraint(["organization_id", "window_id"],
                             ["torqueai_backfill_windows.organization_id", "torqueai_backfill_windows.id"]),
        ForeignKeyConstraint(["organization_id", "attempt_id", "provider_load_number", "provider_order_number"],
                             ["torqueai_backfill_identity_evidence.organization_id", "torqueai_backfill_identity_evidence.attempt_id",
                              "torqueai_backfill_identity_evidence.provider_load_number", "torqueai_backfill_identity_evidence.provider_order_number"]),
        UniqueConstraint("organization_id", "attempt_id", "dispatch_id", name="uq_tai_bf_update_dispatch"),
        UniqueConstraint("organization_id", "identity_evidence_id", name="uq_tai_bf_update_identity"),
        CheckConstraint("dispatch_id > 0", name="ck_tai_bf_update_dispatch"),
    )



def upgrade():
    metadata = MetaData()
    # Parent stubs resolve frozen FK targets without importing runtime models.
    Table("torqueai_backfill_manifests", metadata, Column("organization_id", String), Column("id", String))
    Table("torqueai_backfill_windows", metadata, Column("organization_id", String), Column("id", String))
    Table("torqueai_backfill_identity_evidence", metadata, Column("id", String), Column("organization_id", String), Column("attempt_id", String), Column("provider_load_number", String), Column("provider_order_number", String))
    define_update_table(metadata).create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Downgrade is unsafe: historical update evidence must be preserved")
