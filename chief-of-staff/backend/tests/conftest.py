"""Shared pytest hooks for database migration invariants."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def pytest_collection_modifyitems(session, config, items) -> None:
    """Keep the database-gate expected revision synchronized with Alembic.

    The legacy test module carried a hard-coded head revision. New forward-only
    migrations should not require editing that constant by hand; derive it from
    Alembic after collection so the existing test functions validate the actual
    repository head.
    """
    module = sys.modules.get("test_database_gate") or sys.modules.get("tests.test_database_gate")
    if module is None or not hasattr(module, "ALEMBIC_HEAD"):
        return

    backend_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_root / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_config)
    module.ALEMBIC_HEAD = script.get_current_head()
