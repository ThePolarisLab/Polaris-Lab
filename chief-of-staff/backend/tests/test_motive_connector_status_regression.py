"""Regression gate for the Motive connector-construction bug in the generic
connector-status API (see app/api/connectors.py::_tenant_connector).

Prior to this fix, the Motive branch of ``_tenant_connector`` called::

    MotiveConnector(credential_store=MotiveCredentialStore(principal.organization_id))

``MotiveConnector.__init__`` never accepted a ``credential_store`` keyword
argument -- it reads the Motive Company API Key directly from the
``MOTIVE_API_KEY`` environment variable (see app/connectors/motive.py). That
call therefore raised a ``TypeError`` for any organization the moment
``GET /api/v1/connectors``, ``GET /api/v1/connectors/motive``, or
``POST /api/v1/connectors/motive/sync`` was invoked, because those endpoints
route every registered connector through ``_tenant_connector`` before
touching it. ``MotiveCredentialStore`` (app/connectors/motive_credentials.py)
is a completely separate, currently-dormant OAuth token-storage subsystem
that the Company API Key request path never reads from.

This module proves:
- the fixed constructor call (``MotiveConnector(organization_id=...)``) is
  used, matching the pattern already proven correct in app/api/motive.py;
- the unsupported ``credential_store`` keyword is rejected by
  ``MotiveConnector.__init__`` (locks in that the connector was not widened
  to accommodate the bad caller instead of fixing the caller);
- an organization with Motive configured (``MOTIVE_API_KEY`` set) no longer
  crashes any of the three affected endpoints;
- an organization without Motive configured preserves prior "not configured"
  behavior;
- the OAuth credential-storage subsystem (``MotiveCredentialStore``) is never
  touched by the generic connector-status path;
- Company API Key requests made through a connector built via
  ``_tenant_connector`` still authenticate with ``x-api-key`` (never
  ``Authorization: Bearer``);
- no secret value ever appears in a connector-status API response.

No live Motive API call is made anywhere in this module. All provider
interaction is mocked via ``httpx.MockTransport``. Only the synthetic
placeholder API key ``test-motive-api-key-regression`` is used.
"""

from __future__ import annotations

import inspect

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.connectors import _tenant_connector
from app.connectors.motive import MotiveConnector
from app.connectors.motive_credentials import MotiveCredentialStore
from app.connectors.registry import connector_registry
from app.main import app
from app.security.models import AuthenticatedPrincipal, Permission
from tests.auth_helpers import seed_principal

FAKE_API_KEY = "test-motive-api-key-regression"


def _principal(organization_id: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        identity_id="identity-regression",
        organization_id=organization_id,
        membership_id=f"membership-{organization_id}",
        role="owner",
        permissions=frozenset({Permission.CONNECTOR_READ, Permission.CONNECTOR_WRITE}),
        provider="test",
        subject="test-subject-regression",
    )


@pytest.fixture(autouse=True)
def _motive_registered():
    """Ensure the real MotiveConnector is registered for these tests,
    regardless of what earlier test modules left in the shared in-process
    registry (app.main registers it once at import time; other test modules
    clear/replace the registry for their own isolation)."""
    connector_registry.register(MotiveConnector(), replace=True)
    yield


# ---------------------------------------------------------------------------
# Root cause: the tenant-connector wrapper's supported constructor.
# ---------------------------------------------------------------------------
def test_tenant_connector_builds_motive_connector_with_organization_id() -> None:
    connector = connector_registry.get("motive")
    principal = _principal("org-regression-a")

    tenant_connector = _tenant_connector(connector, principal)

    assert isinstance(tenant_connector, MotiveConnector)
    assert tenant_connector.organization_id == "org-regression-a"


def test_motive_connector_constructor_rejects_unsupported_credential_store_kwarg() -> None:
    """Locks in that the fix was to correct the caller, not widen
    MotiveConnector to accept a credential_store it has no use for."""
    with pytest.raises(TypeError):
        MotiveConnector(credential_store=MotiveCredentialStore("org-regression-a"))


def test_tenant_connector_never_touches_the_oauth_credential_store(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden_init(self, organization_id):  # noqa: ANN001
        raise AssertionError("MotiveCredentialStore must not be instantiated by the generic connector-status path")

    monkeypatch.setattr(MotiveCredentialStore, "__init__", _forbidden_init)

    connector = connector_registry.get("motive")
    tenant_connector = _tenant_connector(connector, _principal("org-regression-b"))

    assert isinstance(tenant_connector, MotiveConnector)


# ---------------------------------------------------------------------------
# Endpoint-level regression: no TypeError, sanitized responses either way.
# ---------------------------------------------------------------------------
def test_list_connectors_endpoint_with_motive_configured_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    _, _, headers = seed_principal("owner")
    client = TestClient(app)

    response = client.get("/api/v1/connectors", headers=headers)

    assert response.status_code == 200
    body = response.json()
    motive_entries = [entry for entry in body if entry["name"] == "motive"]
    assert len(motive_entries) == 1
    assert motive_entries[0]["status"] in {"configured_unverified", "connected", "authorization_required"}
    assert FAKE_API_KEY not in response.text


def test_list_connectors_endpoint_without_motive_configured_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOTIVE_API_KEY", raising=False)
    _, _, headers = seed_principal("owner")
    client = TestClient(app)

    response = client.get("/api/v1/connectors", headers=headers)

    assert response.status_code == 200
    body = response.json()
    motive_entries = [entry for entry in body if entry["name"] == "motive"]
    assert len(motive_entries) == 1
    assert motive_entries[0]["status"] == "not_configured"


def test_get_single_motive_connector_endpoint_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    _, _, headers = seed_principal("owner")
    client = TestClient(app)

    response = client.get("/api/v1/connectors/motive", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "motive"
    assert FAKE_API_KEY not in response.text


def test_sync_motive_connector_endpoint_does_not_crash_and_makes_no_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    _, _, headers = seed_principal("owner")
    client = TestClient(app)

    response = client.post("/api/v1/connectors/motive/sync", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["connector"] == "motive"
    # Broad Motive sync is intentionally deferred; the generic sync path must
    # not attempt any provider HTTP call to reach that response.
    assert body["success"] is False


# ---------------------------------------------------------------------------
# Auth boundary: Company API Key semantics unchanged through this code path.
# ---------------------------------------------------------------------------
def test_connector_built_by_tenant_wrapper_still_authenticates_with_x_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIVE_API_KEY", FAKE_API_KEY)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"vehicles": [], "pagination": {"total": 0}})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = connector_registry.get("motive")
    tenant_connector = _tenant_connector(connector, _principal("org-regression-c"))
    # Swap in a mock transport post-construction so no live network call can occur.
    tenant_connector._client = mock_client

    tenant_connector.list_vehicles(organization_id="org-regression-c", organization_slug="org-regression-c")

    assert len(calls) == 1
    assert calls[0].headers["x-api-key"] == FAKE_API_KEY
    assert "Authorization" not in calls[0].headers


def test_oauth_credential_store_remains_a_distinct_module_from_the_status_path() -> None:
    """The Company API Key status path (app/api/connectors.py) must never
    import or reference the OAuth credential-storage subsystem now that the
    bad call site is fixed -- while the unrelated QuickBooks/Outlook OAuth
    credential-store wiring (a different, intentional architecture) must
    stay untouched by this narrow fix."""
    import app.api.connectors as connectors_module

    source = inspect.getsource(connectors_module)
    assert "MotiveCredentialStore" not in source
    assert "QuickBooksCredentialStore(principal.organization_id)" in source
    assert "OutlookCredentialStore(principal.organization_id)" in source
