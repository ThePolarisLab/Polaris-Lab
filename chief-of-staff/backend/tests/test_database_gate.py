from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_HEAD = "202608060001"


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
            "POLARIS_OUTLOOK_TOKEN_ENCRYPTION_KEY": "uPlZqC60CQaQGFL-kQo-xUOyEE5uNUAyxKmwbzfdiVo=",
            "POLARIS_MOTIVE_TOKEN_ENCRYPTION_KEY": "uPlZqC60CQaQGFL-kQo-xUOyEE5uNUAyxKmwbzfdiVo=",
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
        f"""
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect, text
        from app.database.schema_guard import assert_database_at_head

        command.upgrade(Config('alembic.ini'), 'head')
        assert_database_at_head()
        engine = create_engine(__import__('os').environ['DATABASE_URL'])
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        for table in [
            'organizations',
            'trucks',
            'quickbooks_oauth_credentials',
            'outlook_oauth_credentials',
            'motive_credentials',
            'motive_oauth_states',
            'motive_sync_history',
            'motive_sync_checkpoints',
            'motive_vehicles',
            'motive_drivers',
            'motive_vehicle_utilization',
            'motive_driver_utilization',
            'motive_ifta_summaries',
            'ace_inbond_movements',
            'ace_inbond_events',
            'ace_import_runs',
            'ace_feed_runs',
        ]:
            assert table in tables
        with engine.connect() as connection:
            assert connection.execute(text('SELECT COUNT(*) FROM organizations')).scalar_one() == 0
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '{ALEMBIC_HEAD}'
        motive_credential_columns = {{column['name'] for column in inspector.get_columns('motive_credentials')}}
        assert 'encrypted_access_token' in motive_credential_columns
        assert 'encrypted_refresh_token' in motive_credential_columns
        assert 'expires_at' in motive_credential_columns
        assert 'granted_scopes' in motive_credential_columns
        assert 'provider_company_id' in motive_credential_columns
        assert 'encrypted_api_key' not in motive_credential_columns
        assert 'environment_mode' not in motive_credential_columns
        assert 'key_present' not in motive_credential_columns
        motive_state_columns = {{column['name'] for column in inspector.get_columns('motive_oauth_states')}}
        assert {{'state', 'organization_id', 'identity_id', 'nonce', 'redirect_uri', 'scopes', 'expires_at', 'consumed_at'}}.issubset(motive_state_columns)
        motive_constraints = {{constraint['name'] for constraint in inspector.get_unique_constraints('motive_credentials')}}
        assert 'uq_motive_credential_org_method' in motive_constraints
        vehicle_constraints = {{constraint['name'] for constraint in inspector.get_unique_constraints('motive_vehicles')}}
        assert 'uq_motive_vehicle_org_provider' in vehicle_constraints
        utilization_columns = {{column['name'] for column in inspector.get_columns('motive_vehicle_utilization')}}
        assert {{
            'motive_vehicle_id',
            'request_window_start',
            'request_window_end',
            'idle_time',
            'driving_time',
            'idle_fuel',
            'driving_fuel',
            'metric_units',
            'parser_version',
        }}.issubset(utilization_columns)
        utilization_foreign_keys = {{foreign_key['name'] for foreign_key in inspector.get_foreign_keys('motive_vehicle_utilization')}}
        assert 'fk_motive_vehicle_utilization_motive_vehicle_id' in utilization_foreign_keys
        utilization_constraints = {{constraint['name']: constraint['column_names'] for constraint in inspector.get_unique_constraints('motive_vehicle_utilization')}}
        assert utilization_constraints['uq_motive_vehicle_util_org_vehicle_request_window'] == [
            'organization_id', 'motive_vehicle_id', 'request_window_start', 'request_window_end',
        ]
        assert utilization_constraints['uq_motive_vehicle_util_org_period'] == [
            'organization_id', 'provider_vehicle_id', 'reporting_period_start', 'reporting_period_end',
        ]
        utilization_indexes = {{index['name'] for index in inspector.get_indexes('motive_vehicle_utilization')}}
        assert 'ix_motive_vehicle_utilization_motive_vehicle_id' in utilization_indexes
        assert 'ix_motive_vehicle_utilization_request_window_start' in utilization_indexes
        assert 'ix_motive_vehicle_utilization_request_window_end' in utilization_indexes
        """,
        db_url,
    )


def test_upgrade_head_is_idempotent(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "idempotent.db")
    _run_python(
        f"""
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect

        config = Config('alembic.ini')
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')
        engine = create_engine(__import__('os').environ['DATABASE_URL'])
        version = engine.connect().exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()
        assert version == '{ALEMBIC_HEAD}'
        assert 'motive_credentials' in inspect(engine).get_table_names()
        """,
        db_url,
    )


def test_tenant_table_inventories_are_complete() -> None:
    db_url = "sqlite:///:memory:"
    _run_python(
        """
        import importlib
        from app.database.validate_schema import ACE_TENANT_TABLES, LEGACY_OPTIONAL_TABLES, MOTIVE_TENANT_TABLES, TENANT_TABLES as validator_tables

        add_columns = importlib.import_module('migrations.versions.202607290002_add_nullable_tenant_columns')
        backfill = importlib.import_module('migrations.versions.202607290003_backfill_and_require_tenant_ownership')
        phase1_expected = {
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
        post_baseline_tenant_tables = {
            'production_auth_sessions',
            'production_auth_bootstrap_state',
            'outlook_oauth_credentials',
            'outlook_oauth_states',
            'outlook_folders',
            'outlook_folder_checkpoints',
            'outlook_messages',
            'outlook_attachments',
            'outlook_message_classifications',
            'outlook_sync_history',
        }
        motive_expected = {
            'motive_credentials',
            'motive_oauth_states',
            'motive_sync_history',
            'motive_sync_checkpoints',
            'motive_vehicles',
            'motive_drivers',
            'motive_vehicle_utilization',
            'motive_driver_utilization',
            'motive_ifta_summaries',
        }
        ace_expected = {
            'ace_inbond_movements',
            'ace_inbond_events',
            'ace_import_runs',
            'ace_feed_runs',
        }
        assert set(add_columns.TENANT_TABLES) == phase1_expected
        assert set(backfill.TENANT_TABLES) == phase1_expected
        assert set(MOTIVE_TENANT_TABLES) == motive_expected
        assert set(ACE_TENANT_TABLES) == ace_expected
        assert set(validator_tables) == phase1_expected | post_baseline_tenant_tables | motive_expected | ace_expected
        assert (post_baseline_tenant_tables | motive_expected | ace_expected).issubset(set(LEGACY_OPTIONAL_TABLES))
        """,
        db_url,
    )


def test_current_seeded_database_upgrade_preserves_tenant_rows(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "current-seeded.db")
    _run_python(
        f"""
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
        CREATE TABLE financial_accounts (id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL, name TEXT, fully_qualified_name TEXT, account_type TEXT, account_subtype TEXT, active INTEGER, current_balance REAL, payload TEXT, synced_at TEXT);
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
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '{ALEMBIC_HEAD}'
        """,
        db_url,
    )


def test_partial_and_unknown_schemas_are_rejected_by_adoption_validator(tmp_path: Path) -> None:
    partial_url = _sqlite_url(tmp_path / "partial.db")
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
        partial_url,
    )
    unknown_url = _sqlite_url(tmp_path / "unknown-schema.db")
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
        unknown_url,
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


def test_production_startup_rejects_unversioned_unknown_and_stale_schema(tmp_path: Path) -> None:
    stale_url = _sqlite_url(tmp_path / "stale.db")
    _run_python(
        """
        from app.database.database import Base, engine
        from app.database.models import register_models

        register_models()
        Base.metadata.create_all(bind=engine)
        """,
        stale_url,
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
        stale_url,
        extra_env={"POLARIS_ENV": "production", "POLARIS_AUTO_CREATE_SCHEMA": "false"},
    )

    unknown_url = _sqlite_url(tmp_path / "unknown-revision.db")
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
        unknown_url,
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
        unknown_url,
        extra_env={"POLARIS_ENV": "production", "POLARIS_AUTO_CREATE_SCHEMA": "false"},
    )

    stale_revision_url = _sqlite_url(tmp_path / "stale-revision.db")
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
        stale_revision_url,
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
        stale_revision_url,
        extra_env={"POLARIS_ENV": "production", "POLARIS_AUTO_CREATE_SCHEMA": "false"},
    )
