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


def test_builder_system_health_exposes_timestamped_readiness():
    response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"] == {
        "api": "ready",
        "database": "connected",
    }
    assert payload["checked_at"]


def test_builder_system_info_exposes_non_secret_runtime_metadata():
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "Polaris Chief of Staff API"
    assert payload["environment"]
    assert payload["organization"]
    assert payload["started_at"]
    assert payload["uptime_seconds"] >= 0
    assert payload["git_commit"]


def test_builder_system_version_exposes_build_identity():
    response = client.get("/api/v1/system/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"]
    assert payload["git_commit"]
