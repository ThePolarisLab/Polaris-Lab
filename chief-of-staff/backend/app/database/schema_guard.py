"""Runtime database lifecycle checks for Polaris."""

from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.core.config import settings
from app.database.database import Base, engine
from app.database.models import register_models

MANAGED_ENVIRONMENTS = {"production", "staging"}
DEV_TEST_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


class DatabaseSchemaError(RuntimeError):
    """Raised when the database schema is unsafe for application startup."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    config = Config(str(_backend_root() / "alembic.ini"))
    return config


def _alembic_head() -> str:
    script = ScriptDirectory.from_config(_alembic_config())
    head = script.get_current_head()
    if head is None:
        raise DatabaseSchemaError("Alembic has no head revision configured")
    return head


def _database_revision() -> str | None:
    inspector = inspect(engine)
    if "alembic_version" not in inspector.get_table_names():
        return None
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def assert_database_at_head() -> None:
    """Fail if the database is not managed by Alembic at the latest revision."""

    current = _database_revision()
    head = _alembic_head()
    if current != head:
        raise DatabaseSchemaError(
            "Database schema is not at Alembic head. Run `alembic upgrade head` "
            f"before starting Polaris. current={current or 'unversioned'} head={head}"
        )


def prepare_database_for_runtime() -> None:
    """Prepare or validate the database before the FastAPI app serves requests."""

    register_models()
    environment = settings.environment.lower()
    auto_create = os.getenv("POLARIS_AUTO_CREATE_SCHEMA")

    if environment in MANAGED_ENVIRONMENTS:
        assert_database_at_head()
        return

    if auto_create is None:
        auto_create_enabled = environment in DEV_TEST_ENVIRONMENTS
    else:
        auto_create_enabled = auto_create.strip().lower() in {"1", "true", "yes", "on"}

    if auto_create_enabled:
        Base.metadata.create_all(bind=engine)
        return

    assert_database_at_head()


def health_database_status() -> str:
    """Return a coarse health state without exposing schema internals."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "connected"
    except Exception:
        return "unavailable"
