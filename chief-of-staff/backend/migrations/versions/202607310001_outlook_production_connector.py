"""Outlook production connector persistence.

Revision ID: 202607310001
Revises: 202607300004
Create Date: 2026-07-31 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "202607310001"
down_revision = "202607300004"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    existing = _tables()

    if "outlook_oauth_credentials" not in existing:
        op.create_table(
            "outlook_oauth_credentials",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("microsoft_tenant_id", sa.String(length=120), nullable=False),
            sa.Column("mailbox_user_id", sa.String(length=255), nullable=False),
            sa.Column("mailbox_address", sa.String(length=320), nullable=False),
            sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
            sa.Column("scopes", sa.Text(), nullable=False),
            sa.Column("connector_health_status", sa.String(length=60), nullable=False, server_default="connected_unverified"),
            sa.Column("reauthorization_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_error_summary", sa.Text(), nullable=True),
            sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_refresh_status", sa.String(length=40), nullable=True),
            sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", name="uq_outlook_oauth_credentials_organization_id"),
        )
        _create_index_if_missing("ix_outlook_oauth_credentials_organization_id", "outlook_oauth_credentials", ["organization_id"], unique=True)
        _create_index_if_missing("ix_outlook_oauth_credentials_organization_slug", "outlook_oauth_credentials", ["organization_slug"])
        _create_index_if_missing("ix_outlook_oauth_credentials_microsoft_tenant_id", "outlook_oauth_credentials", ["microsoft_tenant_id"])
        _create_index_if_missing("ix_outlook_oauth_credentials_mailbox_user_id", "outlook_oauth_credentials", ["mailbox_user_id"])
        _create_index_if_missing("ix_outlook_oauth_credentials_mailbox_address", "outlook_oauth_credentials", ["mailbox_address"])

    if "outlook_oauth_states" not in existing:
        op.create_table(
            "outlook_oauth_states",
            sa.Column("state", sa.String(length=255), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("identity_id", sa.String(), nullable=False),
            sa.Column("nonce", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["identity_id"], ["identities.id"]),
            sa.PrimaryKeyConstraint("state"),
        )
        _create_index_if_missing("ix_outlook_oauth_states_organization_id", "outlook_oauth_states", ["organization_id"])
        _create_index_if_missing("ix_outlook_oauth_states_identity_id", "outlook_oauth_states", ["identity_id"])
        _create_index_if_missing("ix_outlook_oauth_states_nonce", "outlook_oauth_states", ["nonce"])
        _create_index_if_missing("ix_outlook_oauth_states_expires_at", "outlook_oauth_states", ["expires_at"])
        _create_index_if_missing("ix_outlook_oauth_states_consumed_at", "outlook_oauth_states", ["consumed_at"])

    if "outlook_folders" not in existing:
        op.create_table(
            "outlook_folders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider_folder_id", sa.String(length=512), nullable=False),
            sa.Column("display_name", sa.String(length=500), nullable=False),
            sa.Column("parent_folder_id", sa.String(length=512), nullable=True),
            sa.Column("well_known_name", sa.String(length=120), nullable=True),
            sa.Column("child_folder_count", sa.Integer(), nullable=True),
            sa.Column("total_item_count", sa.Integer(), nullable=True),
            sa.Column("unread_item_count", sa.Integer(), nullable=True),
            sa.Column("is_sync_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_folder_id", name="uq_outlook_folder_org_provider"),
        )
        _create_index_if_missing("ix_outlook_folders_organization_id", "outlook_folders", ["organization_id"])
        _create_index_if_missing("ix_outlook_folders_provider_folder_id", "outlook_folders", ["provider_folder_id"])
        _create_index_if_missing("ix_outlook_folders_is_sync_enabled", "outlook_folders", ["is_sync_enabled"])

    if "outlook_folder_checkpoints" not in existing:
        op.create_table(
            "outlook_folder_checkpoints",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider_folder_id", sa.String(length=512), nullable=False),
            sa.Column("delta_link", sa.Text(), nullable=True),
            sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("checkpoint_status", sa.String(length=60), nullable=False, server_default="not_started"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_folder_id", name="uq_outlook_checkpoint_org_folder"),
        )
        _create_index_if_missing("ix_outlook_folder_checkpoints_organization_id", "outlook_folder_checkpoints", ["organization_id"])
        _create_index_if_missing("ix_outlook_folder_checkpoints_provider_folder_id", "outlook_folder_checkpoints", ["provider_folder_id"])

    if "outlook_messages" not in existing:
        op.create_table(
            "outlook_messages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("provider_message_id", sa.String(length=512), nullable=False),
            sa.Column("immutable_provider_id", sa.String(length=512), nullable=True),
            sa.Column("conversation_id", sa.String(length=512), nullable=True),
            sa.Column("internet_message_id", sa.String(length=512), nullable=True),
            sa.Column("folder_provider_id", sa.String(length=512), nullable=True),
            sa.Column("subject", sa.Text(), nullable=True),
            sa.Column("sender", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("reply_to", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("recipients", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("cc_recipients", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("bcc_recipients", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("importance", sa.String(length=40), nullable=True),
            sa.Column("categories", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("flag", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("is_read", sa.Boolean(), nullable=True),
            sa.Column("is_draft", sa.Boolean(), nullable=True),
            sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("body_content_type", sa.String(length=40), nullable=True),
            sa.Column("body_text", sa.Text(), nullable=True),
            sa.Column("body_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source_web_link", sa.Text(), nullable=True),
            sa.Column("evidence", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_sync_run_id", sa.String(length=120), nullable=True),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "provider_message_id", name="uq_outlook_message_org_provider"),
        )
        _create_index_if_missing("ix_outlook_messages_organization_id", "outlook_messages", ["organization_id"])
        _create_index_if_missing("ix_outlook_messages_provider_message_id", "outlook_messages", ["provider_message_id"])
        _create_index_if_missing("ix_outlook_messages_conversation_id", "outlook_messages", ["conversation_id"])
        _create_index_if_missing("ix_outlook_messages_received_at", "outlook_messages", ["received_at"])
        _create_index_if_missing("ix_outlook_messages_has_attachments", "outlook_messages", ["has_attachments"])

    if "outlook_attachments" not in existing:
        op.create_table(
            "outlook_attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("provider_attachment_id", sa.String(length=512), nullable=False),
            sa.Column("filename", sa.String(length=1000), nullable=True),
            sa.Column("mime_type", sa.String(length=255), nullable=True),
            sa.Column("size", sa.Integer(), nullable=True),
            sa.Column("is_inline", sa.Boolean(), nullable=True),
            sa.Column("content_id", sa.String(length=512), nullable=True),
            sa.Column("attachment_type", sa.String(length=120), nullable=True),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["message_id"], ["outlook_messages.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "message_id", "provider_attachment_id", name="uq_outlook_attachment_org_message_provider"),
        )
        _create_index_if_missing("ix_outlook_attachments_organization_id", "outlook_attachments", ["organization_id"])
        _create_index_if_missing("ix_outlook_attachments_message_id", "outlook_attachments", ["message_id"])

    if "outlook_message_classifications" not in existing:
        op.create_table(
            "outlook_message_classifications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=120), nullable=False),
            sa.Column("confidence", sa.String(length=40), nullable=False, server_default="medium"),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("rule", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["message_id"], ["outlook_messages.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "message_id", "category", "rule", name="uq_outlook_classification_org_message_category_rule"),
        )
        _create_index_if_missing("ix_outlook_message_classifications_organization_id", "outlook_message_classifications", ["organization_id"])
        _create_index_if_missing("ix_outlook_message_classifications_message_id", "outlook_message_classifications", ["message_id"])
        _create_index_if_missing("ix_outlook_message_classifications_category", "outlook_message_classifications", ["category"])

    if "outlook_sync_history" not in existing:
        op.create_table(
            "outlook_sync_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("organization_slug", sa.String(), nullable=False),
            sa.Column("connector", sa.String(length=60), nullable=False, server_default="outlook"),
            sa.Column("sync_mode", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("run_id", sa.String(length=120), nullable=False),
            sa.Column("folders_scanned", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("messages_discovered", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("messages_inserted", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("messages_updated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("messages_unchanged", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("messages_removed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("attachments_indexed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("checkpoint_before", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("checkpoint_after", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_category", sa.String(length=120), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", name="uq_outlook_sync_history_run_id"),
        )
        _create_index_if_missing("ix_outlook_sync_history_organization_id", "outlook_sync_history", ["organization_id"])
        _create_index_if_missing("ix_outlook_sync_history_run_id", "outlook_sync_history", ["run_id"], unique=True)
        _create_index_if_missing("ix_outlook_sync_history_status", "outlook_sync_history", ["status"])


def downgrade() -> None:
    for table_name in (
        "outlook_sync_history",
        "outlook_message_classifications",
        "outlook_attachments",
        "outlook_messages",
        "outlook_folder_checkpoints",
        "outlook_folders",
        "outlook_oauth_states",
        "outlook_oauth_credentials",
    ):
        if table_name in _tables():
            op.drop_table(table_name)
