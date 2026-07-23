from uuid import uuid4

from fastapi.testclient import TestClient

from app.events import event_bus
from app.main import app
from app.security.models import Permission, ROLE_PERMISSIONS
from app.security.providers import LocalTokenProvider


client = TestClient(app)


def bootstrap(role: str = "member") -> tuple[dict, dict]:
    suffix = uuid4().hex[:10]
    organization = client.post(
        "/api/v1/organizations",
        json={"slug": f"security-{suffix}", "display_name": "Security Test"},
    ).json()
    identity = client.post(
        "/api/v1/identities",
        json={"email": f"security-{suffix}@example.test", "display_name": "Security Builder"},
    ).json()
    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships",
        json={"identity_id": identity["id"], "role": role},
    )
    assert response.status_code == 201
    return organization, identity


def test_local_login_builds_tenant_bound_principal_and_event():
    organization, identity = bootstrap("owner")
    login = client.post(
        "/api/v1/auth/local/token",
        json={"identity_id": identity["id"], "organization_id": organization["id"]},
    )
    assert login.status_code == 200

    me = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {login.json()['access_token']}",
            "X-Polaris-Organization": organization["id"],
        },
    )
    assert me.status_code == 200
    assert me.json()["identity_id"] == identity["id"]
    assert me.json()["organization_id"] == organization["id"]
    assert "organization.manage" in me.json()["permissions"]

    event = event_bus.recent(limit=1)[0]
    assert event.event_type == "identity.authentication.succeeded.v1"
    assert event.organization_id == organization["id"]


def test_missing_invalid_and_expired_credentials_are_rejected():
    organization, identity = bootstrap()
    missing = client.get(
        "/api/v1/auth/me",
        headers={"X-Polaris-Organization": organization["id"]},
    )
    invalid = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer invalid.token",
            "X-Polaris-Organization": organization["id"],
        },
    )
    expired = LocalTokenProvider().issue(identity["id"], ttl_seconds=-1)
    expired_response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {expired}",
            "X-Polaris-Organization": organization["id"],
        },
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert expired_response.status_code == 401


def test_cross_tenant_access_is_denied():
    first_org, identity = bootstrap()
    second_org, _ = bootstrap()
    token = LocalTokenProvider().issue(identity["id"])

    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Polaris-Organization": second_org["id"],
        },
    )

    assert response.status_code == 403
    assert first_org["id"] != second_org["id"]


def test_role_permissions_are_explicit_and_deny_unknown_roles():
    assert Permission.ORGANIZATION_MANAGE in ROLE_PERMISSIONS["owner"]
    assert Permission.ORGANIZATION_MANAGE not in ROLE_PERMISSIONS["viewer"]
    assert ROLE_PERMISSIONS.get("unknown", frozenset()) == frozenset()
