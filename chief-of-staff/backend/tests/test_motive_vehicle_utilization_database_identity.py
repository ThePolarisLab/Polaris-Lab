"""Database enforcement tests for the Motive vehicle-utilization database identity gate.

Proves:

- a clean Alembic upgrade to head creates
  ``uq_motive_vehicle_util_org_vehicle_request_window`` on
  ``motive_vehicle_utilization`` with the exact certified column order, and
  retains the legacy ``uq_motive_vehicle_util_org_period`` constraint;
- database-level uniqueness enforcement of the certified
  ``organization_id + motive_vehicle_id + request_window_start +
  request_window_end`` identity for fully-populated rows;
- historical/legacy rows with an incomplete (nullable) key remain
  insertable -- the future writer, not this migration, will require a
  complete key;
- the duplicate preflight fails closed: existing duplicate fully-populated
  rows block the migration, the sanitized error carries no provider
  identifiers, no row is deleted or changed, the Alembic version does not
  advance, and the target constraint is not partially created.

This module is purely a database/schema-contract gate. It makes no live
Motive provider calls, enables no writer, and advances no checkpoint.
"""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database.models import register_models
from app.models.motive import MotiveVehicleRecord, MotiveVehicleUtilizationRecord
from app.organizations.models import Organization

register_models()

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONSTRAINT_NAME = "uq_motive_vehicle_util_org_vehicle_request_window"
LEGACY_CONSTRAINT_NAME = "uq_motive_vehicle_util_org_period"
PREVIOUS_REVISION = "202608140001"


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _run_python(
    script: str,
    database_url: str,
    *,
    extra_env: dict[str, str] | None = None,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": database_url,
            "POLARIS_ENV": "test",
            "POLARIS_AUTH_SECRET": "database-identity-test-secret-value",
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


# ---------------------------------------------------------------------------
# Clean upgrade: certified constraint created, legacy constraint retained.
# ---------------------------------------------------------------------------
def test_clean_upgrade_creates_certified_constraint_with_exact_column_order(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "clean-identity.db")
    _run_python(
        """
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect

        command.upgrade(Config('alembic.ini'), 'head')
        engine = create_engine(__import__('os').environ['DATABASE_URL'])
        inspector = inspect(engine)
        constraints = {c['name']: c['column_names'] for c in inspector.get_unique_constraints('motive_vehicle_utilization')}

        assert 'uq_motive_vehicle_util_org_vehicle_request_window' in constraints
        assert constraints['uq_motive_vehicle_util_org_vehicle_request_window'] == [
            'organization_id', 'motive_vehicle_id', 'request_window_start', 'request_window_end',
        ]

        assert 'uq_motive_vehicle_util_org_period' in constraints
        assert constraints['uq_motive_vehicle_util_org_period'] == [
            'organization_id', 'provider_vehicle_id', 'reporting_period_start', 'reporting_period_end',
        ]
        """,
        db_url,
    )


def test_second_upgrade_to_head_is_idempotent_no_op(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "idempotent-identity.db")
    _run_python(
        """
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect

        config = Config('alembic.ini')
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')

        engine = create_engine(__import__('os').environ['DATABASE_URL'])
        inspector = inspect(engine)
        constraint_names = {c['name'] for c in inspector.get_unique_constraints('motive_vehicle_utilization')}
        assert 'uq_motive_vehicle_util_org_vehicle_request_window' in constraint_names
        assert 'uq_motive_vehicle_util_org_period' in constraint_names
        """,
        db_url,
    )


# ---------------------------------------------------------------------------
# Database-level uniqueness enforcement (model metadata).
# ---------------------------------------------------------------------------
@pytest.fixture()
def identity_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'motive-utilization-identity.db').as_posix()}"
    engine = create_engine(database_url)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSession.begin() as session:
        session.add(Organization(id="org-a", slug="org-a", display_name="Org A"))
        session.add(Organization(id="org-b", slug="org-b", display_name="Org B"))
        session.add(MotiveVehicleRecord(id=1, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="veh-a"))
        session.add(MotiveVehicleRecord(id=2, organization_id="org-a", organization_slug="org-a", provider_vehicle_id="veh-b"))
        session.add(MotiveVehicleRecord(id=3, organization_id="org-b", organization_slug="org-b", provider_vehicle_id="veh-a"))
    return TestingSession


def _record(**overrides: object) -> MotiveVehicleUtilizationRecord:
    base: dict[str, object] = dict(
        organization_id="org-a",
        organization_slug="org-a",
        provider_vehicle_id="veh-a",
        motive_vehicle_id=1,
        request_window_start=date(2026, 8, 12),
        request_window_end=date(2026, 8, 13),
    )
    base.update(overrides)
    return MotiveVehicleUtilizationRecord(**base)


def test_first_fully_populated_certified_identity_row_succeeds(identity_db) -> None:
    with identity_db.begin() as session:
        session.add(_record())
    with identity_db() as session:
        assert session.query(MotiveVehicleUtilizationRecord).count() == 1


def test_second_row_with_identical_certified_identity_fails_closed(identity_db) -> None:
    with identity_db.begin() as session:
        session.add(_record())
    with pytest.raises(IntegrityError):
        with identity_db.begin() as session:
            session.add(_record())
    with identity_db() as session:
        assert session.query(MotiveVehicleUtilizationRecord).count() == 1


def test_same_vehicle_different_request_window_start_succeeds(identity_db) -> None:
    with identity_db.begin() as session:
        session.add(_record())
    with identity_db.begin() as session:
        session.add(_record(request_window_start=date(2026, 8, 11)))
    with identity_db() as session:
        assert session.query(MotiveVehicleUtilizationRecord).count() == 2


def test_same_vehicle_different_request_window_end_succeeds(identity_db) -> None:
    with identity_db.begin() as session:
        session.add(_record())
    with identity_db.begin() as session:
        session.add(_record(request_window_end=date(2026, 8, 14)))
    with identity_db() as session:
        assert session.query(MotiveVehicleUtilizationRecord).count() == 2


def test_different_motive_vehicle_id_same_org_and_window_succeeds(identity_db) -> None:
    with identity_db.begin() as session:
        session.add(_record())
    with identity_db.begin() as session:
        session.add(_record(motive_vehicle_id=2, provider_vehicle_id="veh-b"))
    with identity_db() as session:
        assert session.query(MotiveVehicleUtilizationRecord).count() == 2


def test_different_organization_equivalent_request_window_succeeds(identity_db) -> None:
    with identity_db.begin() as session:
        session.add(_record())
    with identity_db.begin() as session:
        session.add(_record(organization_id="org-b", organization_slug="org-b", motive_vehicle_id=3))
    with identity_db() as session:
        assert session.query(MotiveVehicleUtilizationRecord).count() == 2


# ---------------------------------------------------------------------------
# Legacy nullable-key rows remain possible (intentional backward compatibility).
# ---------------------------------------------------------------------------
def test_multiple_rows_with_null_motive_vehicle_id_and_window_are_not_rejected(identity_db) -> None:
    with identity_db.begin() as session:
        session.add(
            _record(
                provider_vehicle_id="legacy-a",
                motive_vehicle_id=None,
                request_window_start=None,
                request_window_end=None,
            )
        )
        session.add(
            _record(
                provider_vehicle_id="legacy-b",
                motive_vehicle_id=None,
                request_window_start=None,
                request_window_end=None,
            )
        )
    with identity_db() as session:
        assert session.query(MotiveVehicleUtilizationRecord).count() == 2


def test_multiple_rows_with_null_request_window_only_are_not_rejected(identity_db) -> None:
    with identity_db.begin() as session:
        session.add(_record(provider_vehicle_id="veh-a", motive_vehicle_id=1, request_window_start=None, request_window_end=None))
        session.add(_record(provider_vehicle_id="veh-b", motive_vehicle_id=2, request_window_start=None, request_window_end=None))
    with identity_db() as session:
        assert session.query(MotiveVehicleUtilizationRecord).count() == 2


# ---------------------------------------------------------------------------
# Duplicate preflight fails closed before any schema mutation.
# ---------------------------------------------------------------------------
def test_duplicate_preflight_fails_closed_before_head(tmp_path: Path) -> None:
    db_url = _sqlite_url(tmp_path / "duplicate-preflight.db")

    _run_python(
        f"""
        import sqlite3
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config('alembic.ini'), '{PREVIOUS_REVISION}')

        path = __import__('os').environ['DATABASE_URL'].removeprefix('sqlite:///')
        connection = sqlite3.connect(path)
        connection.execute(
            "INSERT INTO organizations (id, slug, display_name, legal_name, status, created_at, updated_at) "
            "VALUES ('org-a', 'org-a', 'Org A', NULL, 'active', '2026-01-01', '2026-01-01')"
        )
        connection.execute(
            "INSERT INTO motive_vehicles (id, organization_id, organization_slug, provider, provider_vehicle_id, "
            "source_endpoint, created_at, updated_at) VALUES "
            "(1, 'org-a', 'org-a', 'motive', 'veh-a', '/v1/vehicles', '2026-01-01', '2026-01-01')"
        )
        for row_id in (10, 11):
            connection.execute(
                "INSERT INTO motive_vehicle_utilization (id, organization_id, organization_slug, provider, "
                "provider_vehicle_id, motive_vehicle_id, source_endpoint, request_window_start, request_window_end, "
                "created_at, updated_at) VALUES (?, 'org-a', 'org-a', 'motive', 'veh-a', 1, "
                "'/v1/vehicle_utilization', '2026-08-12', '2026-08-12', '2026-01-01', '2026-01-01')",
                (row_id,),
            )
        connection.commit()
        connection.close()
        """,
        db_url,
    )

    result = _run_python(
        """
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config('alembic.ini'), 'head')
        """,
        db_url,
        expect_success=False,
    )
    assert "duplicates" in result.stderr
    assert "cannot proceed safely" in result.stderr
    # Sanitized: no provider vehicle identifiers, VINs, unit numbers, or raw payloads leaked.
    assert "veh-a" not in result.stderr
    assert "vin" not in result.stderr.lower()

    _run_python(
        f"""
        import sqlite3
        from sqlalchemy import create_engine, inspect

        path = __import__('os').environ['DATABASE_URL'].removeprefix('sqlite:///')
        connection = sqlite3.connect(path)
        count = connection.execute('SELECT COUNT(*) FROM motive_vehicle_utilization').fetchone()[0]
        assert count == 2, f'expected the two pre-existing rows to remain untouched, got {{count}}'
        version = connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        assert version == '{PREVIOUS_REVISION}', f'alembic version unexpectedly advanced to {{version}}'
        connection.close()

        engine = create_engine(__import__('os').environ['DATABASE_URL'])
        inspector = inspect(engine)
        constraint_names = {{c['name'] for c in inspector.get_unique_constraints('motive_vehicle_utilization')}}
        assert 'uq_motive_vehicle_util_org_vehicle_request_window' not in constraint_names
        """,
        db_url,
    )
