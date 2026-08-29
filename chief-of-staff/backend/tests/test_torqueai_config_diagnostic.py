from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./polaris-torqueai-config-diagnostic-test.db")
os.environ.setdefault("POLARIS_ENV", "test")
os.environ.setdefault("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_CLIENT_ID", "client-id")
os.environ.setdefault("POLARIS_QBO_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POLARIS_QBO_REDIRECT_URI", "http://localhost:8000/api/v1/connectors/quickbooks/oauth/callback")
os.environ.setdefault("POLARIS_QBO_OAUTH_STATE_SECRET", "quickbooks-state-secret-with-enough-length")
os.environ.setdefault("POLARIS_QBO_TOKEN_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from fastapi.testclient import TestClient

import app.api.internal_torqueai as internal_torqueai
from app.connectors import torqueai
from app.connectors.torqueai import TorqueAIConnector
from app.main import app
from app.security.job_auth import sign_job_request

TRIGGER_SECRET_ENV = "POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET"
TRIGGER_SECRET = "torqueai-config-diagnostic-test-secret"
PATH = "/api/v1/internal/torqueai/config-diagnostic"


@pytest.fixture(autouse=True)
def reset_environment(monkeypatch: pytest.MonkeyPatch):
    for name in (
        TRIGGER_SECRET_ENV,
        torqueai.TORQUEAI_API_TOKEN_ENV,
        torqueai.TORQUEAI_BASE_URL_ENV,
        torqueai.TORQUEAI_ORGANIZATION_SLUG_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client():
    return TestClient(app)


def _signed_headers(*, body: bytes = b"") -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-Polaris-Job-Timestamp": timestamp,
        "X-Polaris-Job-Signature": sign_job_request(
            method="POST",
            path=PATH,
            body=body,
            timestamp=timestamp,
            secret=TRIGGER_SECRET,
        ),
    }


def test_config_diagnostic_is_hmac_only_bodyless_and_zero_provider_or_scheduler_calls(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def provider_must_not_run(*_args, **_kwargs):
        raise AssertionError("provider must not be called by configuration diagnostic")

    def scheduler_must_not_run(*_args, **_kwargs):
        raise AssertionError("scheduler must not be called by configuration diagnostic")

    monkeypatch.setattr(TorqueAIConnector, "fetch_dispatches", provider_must_not_run)
    monkeypatch.setattr(internal_torqueai, "run_scheduled_torqueai_dispatch_sync", scheduler_must_not_run)
    monkeypatch.setenv(TRIGGER_SECRET_ENV, TRIGGER_SECRET)
    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, "tk_clean_secret")
    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, "https://morlogistics.kordovatek.com")

    assert client.post(PATH).status_code == 401

    body = b'{"retry":true}'
    rejected = client.post(PATH, headers=_signed_headers(body=body), content=body)
    assert rejected.status_code == 400
    assert "retry" not in rejected.text

    response = client.post(PATH, headers=_signed_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "ok",
        "provider": "torqueai",
        "token_configured": True,
        "token_has_bearer_prefix": False,
        "token_has_wrapping_quotes": False,
        "token_has_outer_whitespace": False,
        "token_has_line_break": False,
        "base_url_configured": True,
        "base_url_https_origin": True,
        "provider_called": False,
        "scheduler_called": False,
        "dispatch_claimed": False,
        "raw_dispatches_returned": False,
        "secrets_exposed": False,
    }
    assert "tk_clean_secret" not in response.text
    assert "morlogistics.kordovatek.com" not in response.text


def test_config_diagnostic_reports_credential_shape_without_values(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = internal_torqueai._torqueai_configuration_diagnostic()
    assert missing["token_configured"] is False
    assert missing["base_url_configured"] is False
    assert missing["base_url_https_origin"] is False

    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, "Bearer provider-secret")
    bearer = internal_torqueai._torqueai_configuration_diagnostic()
    assert bearer["token_configured"] is True
    assert bearer["token_has_bearer_prefix"] is True
    assert "provider-secret" not in repr(bearer)

    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, '"quoted-provider-secret"')
    quoted = internal_torqueai._torqueai_configuration_diagnostic()
    assert quoted["token_has_wrapping_quotes"] is True
    assert "quoted-provider-secret" not in repr(quoted)

    monkeypatch.setenv(torqueai.TORQUEAI_API_TOKEN_ENV, " provider-secret\r\n")
    whitespace = internal_torqueai._torqueai_configuration_diagnostic()
    assert whitespace["token_has_outer_whitespace"] is True
    assert whitespace["token_has_line_break"] is True
    assert "provider-secret" not in repr(whitespace)

    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, "https://morlogistics.kordovatek.com/")
    valid_base = internal_torqueai._torqueai_configuration_diagnostic()
    assert valid_base["base_url_configured"] is True
    assert valid_base["base_url_https_origin"] is True
    assert "morlogistics.kordovatek.com" not in repr(valid_base)

    monkeypatch.setenv(torqueai.TORQUEAI_BASE_URL_ENV, "https://morlogistics.kordovatek.com/path")
    invalid_base = internal_torqueai._torqueai_configuration_diagnostic()
    assert invalid_base["base_url_https_origin"] is False


def test_config_diagnostic_workflow_is_manual_only_and_cannot_call_provider_or_scheduler() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = (repo_root / ".github" / "workflows" / "torqueai-config-diagnostic.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert PATH in workflow
    assert "/api/v1/internal/torqueai/dispatches/scheduled-sync" not in workflow
    assert "/api/external/dispatches" not in workflow
    assert "POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET" in workflow
    assert "POLARIS_PRODUCTION_API_URL" in workflow
    assert "POLARIS_TORQUEAI_API_TOKEN" not in workflow
    assert "POLARIS_TORQUEAI_BASE_URL" not in workflow
    assert "POLARIS_TORQUEAI_ORGANIZATION_SLUG" not in workflow
    assert "DATABASE_URL" not in workflow
    assert 'payload.get("provider_called") is not False' in workflow
    assert 'payload.get("scheduler_called") is not False' in workflow
    assert 'payload.get("dispatch_claimed") is not False' in workflow
    assert 'payload.get("secrets_exposed") is not False' in workflow
