"""Production authentication bootstrap and sessions.

Revision ID: 202607300002
Revises: 202607300001
Create Date: 2026-07-30 22:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202607300002"
down_revision = "202607300001"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _columns(table_name: str) -> dict[str, dict[str, object]]:
    if table_name not in _tables():
        return {}
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def _align_membership_id_type() -> None:
    if "organization_memberships" not in _tables() or "id" not in _columns("organization_memberships"):
        return
    column_type = _columns("organization_memberships")["id"]["type"]
    if isinstance(column_type, sa.String):
        return
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("organization_memberships") as batch_op:
            batch_op.alter_column("id", existing_type=column_type, type_=sa.String(), existing_nullable=False)
    else:
        op.alter_column(
            "organization_memberships",
            "id",
            existing_type=column_type,
            type_=sa.String(),
            existing_nullable=False,
            postgresql_using="id::text",
        )


def upgrade() -> None:
    _align_membership_id_type()
    existing = _tables()

    if "production_password_credentials" not in existing:
        op.create_table(
            "production_password_credentials",
            sa.Column("identity_id", sa.String(), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("algorithm", sa.String(length=40), nullable=False, server_default="bcrypt"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["identity_id"], ["identities.id"]),
            sa.PrimaryKeyConstraint("identity_id"),
        )

    if "production_auth_sessions" not in existing:
        op.create_table(
            "production_auth_sessions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("identity_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("refresh_token_hash", sa.String(length=128), nullable=False),
            sa.Column("rotated_from_session_id", sa.String(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("ip_address", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoke_reason", sa.String(length=120), nullable=True),
            sa.ForeignKeyConstraint(["identity_id"], ["identities.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("refresh_token_hash", name="uq_production_auth_sessions_refresh_token_hash"),
        )
        _create_index_if_missing("ix_production_auth_sessions_id", "production_auth_sessions", ["id"])
        _create_index_if_missing("ix_production_auth_sessions_identity_id", "production_auth_sessions", ["identity_id"])
        _create_index_if_missing("ix_production_auth_sessions_organization_id", "production_auth_sessions", ["organization_id"])
        _create_index_if_missing("ix_production_auth_sessions_refresh_token_hash", "production_auth_sessions", ["refresh_token_hash"], unique=True)

    if "production_auth_bootstrap_state" not in existing:
        op.create_table(
            "production_auth_bootstrap_state",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("identity_id", sa.String(), nullable=False),
            sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["identity_id"], ["identities.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "production_login_attempts" not in existing:
        op.create_table(
            "production_login_attempts",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("ip_address", sa.String(length=120), nullable=True),
            sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("failure_reason", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("id", name="uq_production_login_attempt_id"),
        )
        _create_index_if_missing("ix_production_login_attempts_email", "production_login_attempts", ["email"])
        _create_index_if_missing("ix_production_login_attempts_ip_address", "production_login_attempts", ["ip_address"])
        _create_index_if_missing("ix_production_login_attempts_created_at", "production_login_attempts", ["created_at"])


def downgrade() -> None:
    for table_name in (
        "production_login_attempts",
        "production_auth_bootstrap_state",
        "production_auth_sessions",
        "production_password_credentials",
    ):
        if table_name in _tables():
            op.drop_table(table_name)
    if "organization_memberships" in _tables() and isinstance(_columns("organization_memberships").get("id", {}).get("type"), sa.String):
        raise RuntimeError(
            "unsafe downgrade blocked: organization_memberships.id was widened to string for ORM compatibility. "
            "Restore from a verified backup if rollback is required."
        )