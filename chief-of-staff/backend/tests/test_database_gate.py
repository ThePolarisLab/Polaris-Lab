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
        from sqlalchemy import create_engine, inspect, text
        from app.database.schema_guard import assert_database_at_head

        command.upgrade(Config('alembic.ini'), 'head')
        assert_database_at_head()
        engine = create_engine(__import__('os').environ['DATABASE_URL'])
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert 'organizations' in tables
        assert 'trucks' in tables
        assert 'quickbooks_oauth_credentials' in tables
        with engine.connect() as connection:
            assert connection.execute(text('SELECT COUNT(*) FROM organizations')).scalar_one() == 0
            assert connection.execute(text('SELECT COUNT(*) FROM memory_entries')).scalar_one() == 0
        columns = {column['name']: column for column in inspector.get_columns('trucks')}
        assert 'organization_id' in columns
        assert columns['organization_id']['nullable'] is False
        indexes = {index['name'] for index in inspector.get_indexes('trucks')}
        assert 'ix_trucks_organization_id' in indexes
        unique_constraints = {constraint['name'] for constraint in inspector.get_unique_constraints('trucks')}
        assert 'uq_truck_organization_unit_number' in unique_constraints
        foreign_keys = inspector.get_foreign_keys('trucks')
        assert any(fk['referred_table'] == 'organizations' for fk in foreign_keys)
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


def test_tenant_table_inventories_are_complete() -> None:
    db_url = "sqlite:///:memory:"
    _run_python(
        """
        import importlib
        from app.database.validate_schema import TENANT_TABLES as validator_tables

        add_columns = importlib.import_module('migrations.versions.202607290002_add_nullable_tenant_columns')
        backfill = importlib.import_module('migrations.versions.202607290003_backfill_and_require_tenant_ownership')
        expected = {
            'companies',
            'trucks',
            'memory_entries',
            'knowledge_relationships',
            'missions',
            'mission_workflows',
            'mission_tasks',
            'team_notes',
            'financial_accounts',
            'financial_snapshots',
            'financial_sync_history',
            'quickbooks_oauth_credentials',
            'quickbooks_oauth_states',
        }
        assert set(add_columns.TENANT_TABLES) == expected
        assert set(backfill.TENANT_TABLES) == expected
        assert set(validator_tables) == expected
        """,
        db_url,
    )


def test_current_seeded_database_upgrade_preserves_tenant_rows(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "current-seeded.db")
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
        CREATE TABLE companies (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, name TEXT, description TEXT, website TEXT, industry TEXT, location TEXT, mission TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE trucks (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, unit_number TEXT, make TEXT, model TEXT, year INTEGER, vin TEXT, license_plate TEXT, status TEXT, notes TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE memory_entries (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, category TEXT, title TEXT, details TEXT, importance INTEGER, source TEXT, created_at TEXT);
        CREATE TABLE knowledge_relationships (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, source TEXT, target TEXT, relation TEXT, created_at TEXT);
        CREATE TABLE missions (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, code TEXT, title TEXT, description TEXT, status TEXT, priority TEXT, owner TEXT, company TEXT, progress INTEGER, created_at TEXT, started_at TEXT, due_at TEXT, completed_at TEXT);
        CREATE TABLE mission_workflows (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, mission_id INTEGER, title TEXT, status TEXT, progress INTEGER, position INTEGER);
        CREATE TABLE mission_tasks (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, workflow_id INTEGER, title TEXT, status TEXT, position INTEGER, system TEXT, capability TEXT, notes TEXT, completed_at TEXT);
        CREATE TABLE team_notes (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, author TEXT, note_type TEXT, status TEXT, title TEXT, details TEXT, target_entity TEXT, assigned_to TEXT, due_at TEXT, created_at TEXT, updated_at TEXT, resolved_at TEXT);
        CREATE TABLE financial_accounts (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, qbo_id TEXT, name TEXT, fully_qualified_name TEXT, account_type TEXT, account_subtype TEXT, active INTEGER, current_balance REAL, payload TEXT, synced_at TEXT);
        CREATE TABLE financial_snapshots (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, snapshot_type TEXT, period_start TEXT, period_end TEXT, accounting_method TEXT, payload TEXT, captured_at TEXT);
        CREATE TABLE financial_sync_history (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, status TEXT, started_at TEXT, completed_at TEXT, duration_ms INTEGER, accounts_imported INTEGER, company_name TEXT, error_message TEXT);
        CREATE TABLE quickbooks_oauth_credentials (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, realm_id TEXT, encrypted_refresh_token TEXT, scopes TEXT, connected_at TEXT, updated_at TEXT);
        CREATE TABLE quickbooks_oauth_states (state TEXT PRIMARY KEY, organization_id TEXT NOT NULL, identity_id TEXT, created_at TEXT, expires_at TEXT, consumed_at TEXT);
        INSERT INTO organizations VALUES ('org-a', 'org-a', 'Org A', NULL, 'active', '2026-01-01', '2026-01-01');
        INSERT INTO memory_entries VALUES (1, 'org-a', 'ops', 'Seeded memory', 'preserve me', 3, 'test', '2026-01-02');
        ''')
        connection.commit()
        connection.close()

        command.stamp(Config('alembic.ini'), '202607290001')
        command.upgrade(Config('alembic.ini'), 'head')

        connection = sqlite3.connect(path)
        assert connection.execute('SELECT organization_id, details FROM memory_entries WHERE id = 1').fetchone() == ('org-a', 'preserve me')
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '202607290003'
        """,
        db_url,
    )


def test_legacy_single_organization_backfills_and_preserves_sensitive_rows(tmp_path: Path) -> None:
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
        INSERT INTO organizations VALUES ('org-a', 'org-a', 'Org A', NULL, 'active', '2026-01-01T00:00:00', '2026-01-01T00:00:00');
        INSERT INTO memory_entries VALUES (1, 'ops', 'Legacy memory', 'preserve me', 3, 'test', '2026-01-02T03:04:05');
        INSERT INTO quickbooks_oauth_credentials VALUES (7, 'realm-1', 'encrypted-refresh-token-value', 'scope-a scope-b', '2026-01-03T00:00:00', '2026-01-04T00:00:00');
        ''')
        connection.commit()
        connection.close()

        from app.database.validate_schema import validate_schema
        result = validate_schema()
        assert result.status == 'legacy-pre-tenant-compatible'
        command.stamp(Config('alembic.ini'), '202607290001')
        command.upgrade(Config('alembic.ini'), 'head')

        connection = sqlite3.connect(path)
        organization_id, details, created_at = connection.execute('SELECT organization_id, details, created_at FROM memory_entries WHERE id = 1').fetchone()
        assert organization_id == 'org-a'
        assert details == 'preserve me'
        assert created_at == '2026-01-02T03:04:05'
        credential = connection.execute('SELECT id, organization_id, realm_id, encrypted_refresh_token, connected_at, updated_at FROM quickbooks_oauth_credentials WHERE id = 7').fetchone()
        assert credential == (7, 'org-a', 'realm-1', 'encrypted-refresh-token-value', '2026-01-03T00:00:00', '2026-01-04T00:00:00')
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


def test_invalid_explicit_backfill_organization_id_is_rejected(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "legacy-invalid-explicit.db")
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
        INSERT INTO memory_entries VALUES (1, 'ops', 'Legacy memory', 'preserve me', 3, 'test', '2026-01-01');
        ''')
        connection.commit()
        connection.close()

        command.stamp(Config('alembic.ini'), '202607290001')
        command.upgrade(Config('alembic.ini'), 'head')
        """,
        db_url,
        extra_env={"POLARIS_TENANT_BACKFILL_ORGANIZATION_ID": "org-missing"},
        expect_success=False,
    )
    assert "does not match an existing organization" in result.stderr or "does not match an existing organization" in result.stdout


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


def test_no_organization_legacy_rows_can_be_backfilled_only_with_explicit_bootstrap(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "legacy-no-org-explicit.db")
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
        CREATE TABLE memory_entries (id INTEGER PRIMARY KEY, category TEXT, title TEXT, details TEXT, importance INTEGER, source TEXT, created_at TEXT);
        INSERT INTO memory_entries VALUES (1, 'ops', 'Legacy memory', 'preserve me', 3, 'test', '2026-01-01');
        ''')
        connection.commit()
        connection.close()

        command.stamp(Config('alembic.ini'), '202607290001')
        command.upgrade(Config('alembic.ini'), 'head')

        connection = sqlite3.connect(path)
        assert connection.execute('SELECT id, slug, display_name FROM organizations').fetchone() == ('org-mor', 'mor-logistics', 'MOR Logistics Manitoba Limited')
        assert connection.execute('SELECT organization_id, details FROM memory_entries WHERE id = 1').fetchone() == ('org-mor', 'preserve me')
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '202607290003'
        """,
        db_url,
        extra_env={
            "POLARIS_TENANT_BACKFILL_ORGANIZATION_ID": "org-mor",
            "POLARIS_TENANT_BACKFILL_ORGANIZATION_SLUG": "mor-logistics",
            "POLARIS_TENANT_BACKFILL_ORGANIZATION_NAME": "MOR Logistics Manitoba Limited",
        },
    )


def test_partial_schema_is_rejected_by_adoption_validator(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "partial.db")
    _run_python(
        """
        import os
        import sqlite3
        path = os.environ['DATABASE_URL'].removeprefix('sqlite:///')
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE organizations (id TEXT PRIMARY KEY, slug TEXT, display_name TEXT, legal_name TEXT, status TEXT, created_at TEXT, updated_at TEXT)')
        connection.commit()
        connection.close()
        from app.database.validate_schema import validate_schema
        result = validate_schema()
        assert result.status == 'partial'
        assert result.stamp_revision is None
        """,
        db_url,
    )


def test_unknown_schema_is_rejected_by_adoption_validator(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "unknown-schema.db")
    _run_python(
        """
        import os
        import sqlite3
        path = os.environ['DATABASE_URL'].removeprefix('sqlite:///')
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE unexpected_table (id INTEGER PRIMARY KEY)')
        connection.commit()
        connection.close()
        from app.database.validate_schema import validate_schema
        result = validate_schema()
        assert result.status == 'unknown'
        assert result.stamp_revision is None
        """,
        db_url,
    )


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


def test_production_startup_rejects_unknown_revision(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "unknown-revision.db")
    _run_python(
        """
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine
        import os

        command.upgrade(Config('alembic.ini'), 'head')
        engine = create_engine(os.environ['DATABASE_URL'])
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num = 'unknown_revision'")
        """,
        db_url,
    )
    _run_python(
        """
        try:
            import app.main  # noqa: F401
        except Exception as exc:
            assert 'unknown_revision' in str(exc) or 'Alembic head' in str(exc)
        else:
            raise AssertionError('production startup accepted an unknown revision')
        """,
        db_url,
        extra_env={"POLARIS_ENV": "production", "POLARIS_AUTO_CREATE_SCHEMA": "false"},
    )


def test_production_startup_rejects_stale_revision(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "stale-revision.db")
    _run_python(
        """
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine
        import os

        command.upgrade(Config('alembic.ini'), 'head')
        engine = create_engine(os.environ['DATABASE_URL'])
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num = '202607290002'")
        """,
        db_url,
    )
    _run_python(
        """
        try:
            import app.main  # noqa: F401
        except Exception as exc:
            assert '202607290002' in str(exc) or 'Alembic head' in str(exc)
        else:
            raise AssertionError('production startup accepted a stale revision')
        """,
        db_url,
        extra_env={"POLARIS_ENV": "production", "POLARIS_AUTO_CREATE_SCHEMA": "false"},
    )
