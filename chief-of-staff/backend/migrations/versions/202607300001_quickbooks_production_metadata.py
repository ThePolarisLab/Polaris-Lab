"""QuickBooks production adapter metadata.

Revision ID: 202607300001
Revises: 202607290003
Create Date: 2026-07-30 00:01:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202607300001"
down_revision = "202607290003"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in set(_inspector().get_table_names())


def _columns(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_table(table_name):
        return
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("verified_company_name", sa.String(length=255), nullable=True))
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("company_verified_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("verification_status", sa.String(length=40), nullable=False, server_default="unverified"))
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("connector_health_status", sa.String(length=60), nullable=False, server_default="authorization_required"))
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("reauthorization_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("last_error_summary", sa.Text(), nullable=True))
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("quickbooks_oauth_credentials", sa.Column("last_refresh_status", sa.String(length=40), nullable=True))

    _add_column_if_missing("financial_sync_history", sa.Column("sync_mode", sa.String(length=40), nullable=False, server_default="full"))
    _add_column_if_missing("financial_sync_history", sa.Column("resource_counts", sa.JSON(), nullable=False, server_default="{}"))
    _add_column_if_missing("financial_sync_history", sa.Column("report_availability", sa.JSON(), nullable=False, server_default="{}"))
    _add_column_if_missing("financial_sync_history", sa.Column("checkpoint_before", sa.Text(), nullable=True))
    _add_column_if_missing("financial_sync_history", sa.Column("checkpoint_after", sa.Text(), nullable=True))
    _add_column_if_missing("financial_sync_history", sa.Column("verification_status", sa.String(length=60), nullable=True))

    if not _has_table("financial_accounts") or "current_balance" not in _columns("financial_accounts"):
        return

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("financial_accounts") as batch_op:
            batch_op.alter_column("current_balance", existing_type=sa.Float(), type_=sa.String(length=80), existing_nullable=True)
    else:
        op.alter_column(
            "financial_accounts",
            "current_balance",
            existing_type=sa.Float(),
            type_=sa.String(length=80),
            existing_nullable=True,
            postgresql_using="current_balance::text",
        )


def downgrade() -> None:
    raise RuntimeError(
        "unsafe downgrade blocked: downgrading QuickBooks production metadata can discard "
        "verification and sync evidence. Restore from a verified backup if rollback is required."
    )
