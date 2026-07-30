from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _run_python(script: str, database_url: str, *, extra_env: dict[str, str] | None = None, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": database_url,
            "POLARIS_ENV": "test",
            "POLARIS_AUTH_SECRET": "database-gate-test-secret-value",
            "POLARIS_QBO_TOKEN_ENCRYPTION_KEY": "uPlZqC60CQaQGFL-kQo-xUOyEE5uNUAyxKmwbzfdiVo=",
            "POLARIS_AUTO_CREATE_SCHEMA": "false",
        }
    )
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(f"subprocess failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    if not expect_success and result.returncode == 0:
        raise AssertionError(f"subprocess unexpectedly succeeded\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def test_clean_sqlite_upgrade_head_starts_and_has_expected_schema(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "clean.db")
    _run_python(
        """
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect
        from app.database.schema_guard import assert_database_at_head

        command.upgrade(Config('alembic.ini'), 'head')
        assert_database_at_head()
        inspector = inspect(create_engine(__import__('os').environ['DATABASE_URL']))
        tables = set(inspector.get_table_names())
        assert 'organizations' in tables
        assert 'trucks' in tables
        assert 'quickbooks_oauth_credentials' in tables
        columns = {column['name'] for column in inspector.get_columns('trucks')}
        assert 'organization_id' in columns
        indexes = {index['name'] for index in inspector.get_indexes('trucks')}
        assert 'ix_trucks_organization_id' in indexes
        """,
        db_url,
    )


def test_upgrade_head_is_idempotent(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "idempotent.db")
    _run_python(
        """
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect

        config = Config('alembic.ini')
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')
        version = create_engine(__import__('os').environ['DATABASE_URL']).connect().exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()
        assert version == '202607290003'
        assert 'organizations' in inspect(create_engine(__import__('os').environ['DATABASE_URL'])).get_table_names()
        """,
        db_url,
    )


def test_legacy_single_organization_backfills_tenant_rows(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "legacy-single.db")
    _run_python(
        """
        import os
        import sqlite3
        from alembic import command
        from alembic.config import Config

        path = os.environ['DATABASE_URL'].removeprefix('sqlite:///')
        connection = sqlite3.connect(path)
        connection.executescript('''
        CREATE TABLE organizations (id TEXT PRIMARY KEY, slug TEXT, display_name TEXT, legal_name TEXT, status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE identities (id TEXT PRIMARY KEY, email TEXT, display_name TEXT, status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE organization_memberships (id INTEGER PRIMARY KEY, organization_id TEXT, identity_id TEXT, role TEXT, status TEXT, created_at TEXT);
        CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT, description TEXT, website TEXT, industry TEXT, location TEXT, mission TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE trucks (id INTEGER PRIMARY KEY, unit_number TEXT, make TEXT, model TEXT, year INTEGER, vin TEXT, license_plate TEXT, status TEXT, notes TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE memory_entries (id INTEGER PRIMARY KEY, category TEXT, title TEXT, details TEXT, importance INTEGER, source TEXT, created_at TEXT);
        CREATE TABLE knowledge_relationships (id INTEGER PRIMARY KEY, source TEXT, target TEXT, relation TEXT, created_at TEXT);
        CREATE TABLE missions (id INTEGER PRIMARY KEY, code TEXT, title TEXT, description TEXT, status TEXT, priority TEXT, owner TEXT, company TEXT, progress INTEGER, created_at TEXT, started_at TEXT, due_at TEXT, completed_at TEXT);
        CREATE TABLE mission_workflows (id INTEGER PRIMARY KEY, mission_id INTEGER, title TEXT, status TEXT, progress INTEGER, position INTEGER);
        CREATE TABLE mission_tasks (id INTEGER PRIMARY KEY, workflow_id INTEGER, title TEXT, status TEXT, position INTEGER, system TEXT, capability TEXT, notes TEXT, completed_at TEXT);
        CREATE TABLE team_notes (id INTEGER PRIMARY KEY, author TEXT, note_type TEXT, status TEXT, title TEXT, details TEXT, target_entity TEXT, assigned_to TEXT, due_at TEXT, created_at TEXT, updated_at TEXT, resolved_at TEXT);
        CREATE TABLE financial_accounts (id INTEGER PRIMARY KEY, qbo_id TEXT, name TEXT, fully_qualified_name TEXT, account_type TEXT, account_subtype TEXT, active INTEGER, current_balance REAL, payload TEXT, synced_at TEXT);
        CREATE TABLE financial_snapshots (id INTEGER PRIMARY KEY, snapshot_type TEXT, period_start TEXT, period_end TEXT, accounting_method TEXT, payload TEXT, captured_at TEXT);
        CREATE TABLE financial_sync_history (id INTEGER PRIMARY KEY, status TEXT, started_at TEXT, completed_at TEXT, duration_ms INTEGER, accounts_imported INTEGER, company_name TEXT, error_message TEXT);
        CREATE TABLE quickbooks_oauth_credentials (id INTEGER PRIMARY KEY, realm_id TEXT, encrypted_refresh_token TEXT, scopes TEXT, connected_at TEXT, updated_at TEXT);
        CREATE TABLE quickbooks_oauth_states (state TEXT PRIMARY KEY, identity_id TEXT, created_at TEXT, expires_at TEXT, consumed_at TEXT);
        INSERT INTO organizations VALUES ('org-a', 'org-a', 'Org A', NULL, 'active', '2026-01-01', '2026-01-01');
        INSERT INTO memory_entries VALUES (1, 'ops', 'Legacy memory', 'preserve me', 3, 'test', '2026-01-01');
        ''')
        connection.commit()
        connection.close()

        from app.database.validate_schema import validate_schema
        result = validate_schema()
        assert result.status == 'legacy-pre-tenant-compatible'
        command.stamp(Config('alembic.ini'), '202607290001')
        command.upgrade(Config('alembic.ini'), 'head')

        connection = sqlite3.connect(path)
        organization_id, details = connection.execute('SELECT organization_id, details FROM memory_entries WHERE id = 1').fetchone()
        assert organization_id == 'org-a'
        assert details == 'preserve me'
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '202607290003'
        """,
        db_url,
    )


def test_legacy_multi_organization_backfill_requires_operator_mapping(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "legacy-multi.db")
    result = _run_python(
        """
        import os
        import sqlite3
        from alembic import command
        from alembic.config import Config

        path = os.environ['DATABASE_URL'].removeprefix('sqlite:///')
        connection = sqlite3.connect(path)
        connection.executescript('''
        CREATE TABLE organizations (id TEXT PRIMARY KEY, slug TEXT, display_name TEXT, legal_name TEXT, status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE memory_entries (id INTEGER PRIMARY KEY, category TEXT, title TEXT, details TEXT, importance INTEGER, source TEXT, created_at TEXT);
        INSERT INTO organizations VALUES ('org-a', 'org-a', 'Org A', NULL, 'active', '2026-01-01', '2026-01-01');
        INSERT INTO organizations VALUES ('org-b', 'org-b', 'Org B', NULL, 'active', '2026-01-01', '2026-01-01');
        INSERT INTO memory_entries VALUES (1, 'ops', 'Legacy memory', 'preserve me', 3, 'test', '2026-01-01');
        ''')
        connection.commit()
        connection.close()

        command.stamp(Config('alembic.ini'), '202607290001')
        command.upgrade(Config('alembic.ini'), 'head')
        """,
        db_url,
        expect_success=False,
    )
    assert "multiple organizations" in result.stderr or "multiple organizations" in result.stdout


def test_legacy_rows_without_organization_fail_safely(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "legacy-no-org.db")
    result = _run_python(
        """
        import os
        import sqlite3
        from alembic import command
        from alembic.config import Config

        path = os.environ['DATABASE_URL'].removeprefix('sqlite:///')
        connection = sqlite3.connect(path)
        connection.executescript('''
        CREATE TABLE organizations (id TEXT PRIMARY KEY, slug TEXT, display_name TEXT, legal_name TEXT, status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE memory_entries (id INTEGER PRIMARY KEY, category TEXT, title TEXT, details TEXT, importance INTEGER, source TEXT, created_at TEXT);
        INSERT INTO memory_entries VALUES (1, 'ops', 'Legacy memory', 'preserve me', 3, 'test', '2026-01-01');
        ''')
        connection.commit()
        connection.close()

        command.stamp(Config('alembic.ini'), '202607290001')
        command.upgrade(Config('alembic.ini'), 'head')
        """,
        db_url,
        expect_success=False,
    )
    assert "no organizations" in result.stderr or "no organizations" in result.stdout


def test_downgrade_fails_explicitly(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "downgrade.db")
    result = _run_python(
        """
        from alembic import command
        from alembic.config import Config

        config = Config('alembic.ini')
        command.upgrade(config, 'head')
        command.downgrade(config, '-1')
        """,
        db_url,
        expect_success=False,
    )
    assert "unsafe" in result.stderr or "unsafe" in result.stdout


def test_production_startup_rejects_unversioned_schema(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "stale.db")
    _run_python(
        """
        from app.database.database import Base, engine
        from app.database.models import register_models

        register_models()
        Base.metadata.create_all(bind=engine)
        """,
        db_url,
        extra_env={"POLARIS_ENV": "test", "POLARIS_AUTO_CREATE_SCHEMA": "true"},
    )
    _run_python(
        """
        try:
            import app.main  # noqa: F401
        except Exception as exc:
            assert 'Alembic head' in str(exc) or 'unversioned' in str(exc)
        else:
            raise AssertionError('production startup accepted an unversioned schema')
        """,
        db_url,
        extra_env={"POLARIS_ENV": "production", "POLARIS_AUTO_CREATE_SCHEMA": "false"},
    )
