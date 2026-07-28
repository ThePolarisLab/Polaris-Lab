import importlib

import app.database.database as database_module


def test_database_url_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    module = importlib.reload(database_module)

    assert module.DATABASE_URL == "sqlite:///./polaris.db"
    assert module.engine.url.drivername == "sqlite"


def test_database_url_normalizes_render_postgres_scheme(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://polaris:secret@example.internal/polaris",
    )

    module = importlib.reload(database_module)

    assert module.DATABASE_URL == (
        "postgresql+psycopg://polaris:secret@example.internal/polaris"
    )
    assert module.engine.url.drivername == "postgresql+psycopg"

    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(database_module)
