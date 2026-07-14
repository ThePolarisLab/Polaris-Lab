import os
from pathlib import Path

TEST_DB = Path(__file__).parent / "test_polaris.db"
os.environ["POLARIS_DATABASE_PATH"] = str(TEST_DB)

import pytest
from fastapi.testclient import TestClient

from app.core.database import initialize_database
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    if TEST_DB.exists():
        TEST_DB.unlink()
    initialize_database()
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
