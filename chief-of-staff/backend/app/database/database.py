"""Database configuration for local development and hosted environments."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _database_url() -> str:
    """Return a SQLAlchemy-compatible database URL.

    Local development keeps the existing SQLite default. Hosted environments can
    provide DATABASE_URL (for example, Render Postgres). Some providers still
    return the legacy ``postgres://`` scheme, which SQLAlchemy does not accept.
    """

    value = os.getenv("DATABASE_URL", "sqlite:///./polaris.db").strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


DATABASE_URL = _database_url()

engine_options: dict[str, object] = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()
