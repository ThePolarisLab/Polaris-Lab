from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_exposes_runtime_context():
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "Polaris Chief of Staff API"
    assert payload["environment"]
    assert payload["organization"]


def test_health_reports_api_and_database_readiness():
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"] == {
        "api": "ready",
        "database": "connected",
    }
