import os
from pathlib import Path
TEST_DB=Path(__file__).parent/"test_polaris.db"; os.environ["POLARIS_DATABASE_PATH"]=str(TEST_DB)
import pytest
from fastapi.testclient import TestClient
from app.core.database import initialize_database
from app.main import app
@pytest.fixture(autouse=True)
def clean_database():
    TEST_DB.unlink(missing_ok=True); initialize_database(); yield; TEST_DB.unlink(missing_ok=True)
@pytest.fixture
def client():
    with TestClient(app) as c: yield c
