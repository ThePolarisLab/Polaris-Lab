"""Exercise the real MCP HTTP transport against isolated durable data and signed JWTs."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import validate
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.chatgpt_mcp import security, server
from app.database.database import Base
from app.identity.models import Identity, OrganizationMembership
from app.models.torqueai import TorqueAIDispatchStop, TorqueAIDispatchSyncState
from app.organizations.models import Organization
from app.security.models import Permission, ROLE_PERMISSIONS
from app.security.service import AuthorizationError
from tests import auth_helpers, test_torqueai_pickup_planning as planning


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid="test-key", alg="RS256", use="sig")
    return private, json.dumps({"keys": [public]})


@pytest.fixture
def setup(tmp_path, monkeypatch, keys):
    engine = create_engine(f"sqlite:///{tmp_path / 'mcp.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    for module in (security, auth_helpers, planning):
        monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setenv("POLARIS_LOCAL_AUTH_SECRET", "test-local-auth-secret-with-enough-length")
    org, identity, local_headers = auth_helpers.seed_principal(security.ROLE)
    with factory.begin() as session:
        session.query(Organization).filter_by(id=org["id"]).update({"slug": "mor-logistics"})
    config = security.MCPSettings(
        resource_url="https://polaris.example.test/mcp", issuer="https://auth.example.test",
        client_id="dedicated-client", subject="approved-owner-subject",
        identity_id=identity["id"], organization_id=org["id"], public_jwks=keys[1],
    )
    app = FastAPI()
    server.install_mcp(app, config)
    with TestClient(app, base_url="https://polaris.example.test") as client:
        yield {"client": client, "config": config, "factory": factory, "engine": engine,
               "private": keys[0], "org": org["id"], "local_headers": local_headers}
    engine.dispose()


def token(setup, **overrides):
    now = int(time.time())
    claims = {"iss": setup["config"].issuer, "aud": setup["config"].resource_url,
              "sub": setup["config"].subject, "client_id": setup["config"].client_id,
              "scope": security.SCOPE, "iat": now, "exp": now + 600}
    claims.update(overrides)
    return jwt.encode(claims, setup["private"], algorithm="RS256", headers={"kid": "test-key", "typ": "at+jwt"})


def rpc(setup, method="tools/call", arguments=None, name="get_pickups", headers=None, params=None):
    request_headers = {"Authorization": "Bearer " + token(setup),
                       "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
    if headers is not None:
        request_headers.update(headers)
    if params is None:
        params = {"name": name, "arguments": arguments if arguments is not None else {"date": planning.TARGET_DATE, "province": "Manitoba"}} if method == "tools/call" else {}
    return setup["client"].post("/mcp", headers=request_headers,
                                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def payload(response):
    assert response.status_code == 200, response.text
    assert "result" in response.json(), response.text
    result = response.json()["result"]["structuredContent"]
    validate(result, server.OUTPUT_SCHEMA)
    return result


def add(setup, load="101", **kwargs):
    values = dict(organization_id=setup["org"], load_number=load, pickup_province="MB", pickup_city="Winnipeg")
    values.update(kwargs)
    planning._add_dispatch(**values)


def test_protocol_initialize_and_registration(setup):
    response = rpc(setup, "initialize", params={"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"]["name"] == "polaris-chatgpt-readonly"
    response = rpc(setup, "tools/list")
    assert response.status_code == 200, response.text
    tools = response.json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["get_pickups"]
    tool = tools[0]
    assert tool["annotations"] == {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    assert tool["inputSchema"]["additionalProperties"] is False
    assert tool["inputSchema"]["required"] == ["date", "province"]
    assert tool["inputSchema"]["properties"]["date"]["format"] == "date"
    assert tool["_meta"]["securitySchemes"] == [{"type": "oauth2", "scopes": [security.SCOPE]}]
    assert tool["outputSchema"]["type"] == "object"


def test_pickups_match_same_stop_date_province_and_city(setup):
    add(setup, "101")
    add(setup, "102", pickup_province="Manitoba", pickup_city="Brandon", driver=None, truck=None, trailer=None)
    add(setup, "103", pickup_date="2026-09-12")
    add(setup, "104", pickup_province="ON")
    add(setup, "105", pickup_job="Drop Off")
    result = payload(rpc(setup))
    assert {load["load_number"] for load in result["loads"]} == {"101", "102"}
    assert result["summary"] == {"pickup_load_count": 2, "attention_required_count": 1, "missing_driver_count": 1, "missing_truck_count": 1}
    missing = next(load for load in result["loads"] if load["load_number"] == "102")
    assert missing["attention_flags"] == ["missing_driver", "missing_truck", "missing_trailer"]
    filtered = payload(rpc(setup, arguments={"date": planning.TARGET_DATE, "province": "mb", "city": " brandon "}))
    assert [load["load_number"] for load in filtered["loads"]] == ["102"]


def test_tenant_rows_children_and_headers_cannot_escape_scope(setup):
    other, _, _ = auth_helpers.seed_principal()
    add(setup, "101")
    add(setup, "SECRET-OTHER", organization_id=other["id"])
    with setup["factory"].begin() as session:
        child = session.query(TorqueAIDispatchStop).filter_by(organization_id=setup["org"], job="Drop Off").one()
        child.organization_id = other["id"]
        child.city = "SECRET-CHILD"
    response = rpc(setup, headers={"X-Polaris-Organization": other["id"]})
    assert payload(response)["summary"]["pickup_load_count"] == 1
    assert "SECRET" not in response.text
    assert payload(response)["loads"][0]["deliveries"] == []
    response = rpc(setup, arguments={"date": planning.TARGET_DATE, "province": "MB", "organization_id": other["id"]})
    assert payload(response)["error"]["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("arguments,code", [
    ({"date": "2026-02-30", "province": "MB"}, "INVALID_DATE"),
    ({"date": "20260911", "province": "MB"}, "INVALID_DATE"),
    ({"date": 123, "province": "MB"}, "INVALID_DATE"),
    ({"province": "MB"}, "INVALID_DATE"),
    ({"date": planning.TARGET_DATE, "province": " "}, "INVALID_PROVINCE"),
    ({"date": planning.TARGET_DATE, "province": "Texas"}, "INVALID_PROVINCE"),
    ({"date": planning.TARGET_DATE, "province": "MB' OR 1=1--"}, "INVALID_PROVINCE"),
    ({"date": planning.TARGET_DATE, "province": "MB", "city": " "}, "INVALID_INPUT"),
])
def test_safe_input_errors(setup, arguments, code):
    response = rpc(setup, arguments=arguments)
    assert payload(response) == {"status": "error", "error": {"code": code}}
    assert response.json()["result"]["isError"] is True


@pytest.mark.parametrize("authorization", ["", "Bearer invalid", "Basic abc"])
def test_authentication_required_for_every_protocol_request(setup, authorization):
    for method in ("initialize", "tools/list", "tools/call"):
        response = rpc(setup, method, headers={"Authorization": authorization})
        assert response.status_code == 401
        assert response.json() == {"error": {"code": "AUTH_REQUIRED"}}
        assert "oauth-protected-resource/mcp" in response.headers["www-authenticate"]


@pytest.mark.parametrize("claims,status", [
    ({"aud": "https://elsewhere.test"}, 401), ({"iss": "https://elsewhere.test"}, 401),
    ({"exp": 1}, 401), ({"iat": 1, "exp": 9999999999}, 401),
    ({"sub": "other-user"}, 403), ({"client_id": "admin-client"}, 403),
    ({"scope": "connector.write"}, 403), ({"scope": [security.SCOPE]}, 403),
])
def test_token_claims_verified(setup, claims, status):
    response = rpc(setup, headers={"Authorization": "Bearer " + token(setup, **claims)})
    assert response.status_code == status


@pytest.mark.parametrize("target,value", [("identity", "disabled"), ("membership", "revoked"), ("organization", "suspended"), ("role", "owner"), ("role", "platform_admin")])
def test_revocation_and_accidental_admin_role_rejected_immediately(setup, target, value):
    assert rpc(setup, "tools/list").status_code == 200
    with setup["factory"].begin() as session:
        if target == "identity":
            session.query(Identity).filter_by(id=setup["config"].identity_id).one().status = value
        elif target == "organization":
            session.query(Organization).filter_by(id=setup["org"]).one().status = value
        else:
            member = session.query(OrganizationMembership).filter_by(identity_id=setup["config"].identity_id).one()
            setattr(member, "role" if target == "role" else "status", value)
    assert rpc(setup, "tools/list").status_code in (401, 403)


def test_no_provider_calls_writes_or_unnecessary_private_fields(setup, monkeypatch):
    add(setup)
    import httpx
    import urllib.request
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected provider/network call")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    from app.connectors.torqueai import TorqueAIConnector
    for name in dir(TorqueAIConnector):
        if not name.startswith("_") and callable(getattr(TorqueAIConnector, name)):
            monkeypatch.setattr(TorqueAIConnector, name, forbidden)
    statements = []
    def record(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(setup["engine"], "before_cursor_execute", record)
    try:
        response = rpc(setup)
    finally:
        event.remove(setup["engine"], "before_cursor_execute", record)
    assert payload(response)["summary"]["pickup_load_count"] == 1
    assert statements and all(s.lstrip().upper().startswith("SELECT ") for s in statements)
    for field in ("dispatcher_name", "total_charge", "address", "zip_code", "fingerprint", "credential", "access_token"):
        assert field not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert ROLE_PERMISSIONS[security.ROLE] == frozenset({Permission.PICKUP_READ})


@pytest.mark.parametrize("sql", ["INSERT INTO identities (id) VALUES ('x')", "UPDATE identities SET status='disabled'", "DELETE FROM identities"])
def test_write_guard_blocks_accidental_service_writes(setup, sql):
    with pytest.raises(AuthorizationError):
        with security.readonly_session() as session:
            session.execute(text(sql))


def test_unknown_tools_and_errors_do_not_leak(setup, monkeypatch):
    assert payload(rpc(setup, name="assign_driver"))["error"]["code"] == "UNKNOWN_TOOL"
    def fail(*args, **kwargs):
        raise RuntimeError("SECRET connection-string password")
    monkeypatch.setattr(server, "query_pickup_plan", fail)
    response = rpc(setup)
    assert payload(response)["error"]["code"] == "INTERNAL_ERROR"
    assert "SECRET" not in response.text


def test_freshness_is_tenant_bound_and_not_fabricated(setup):
    result = payload(rpc(setup))
    assert result["summary"]["pickup_load_count"] == 0
    assert result["as_of"] is None and result["freshness"]["status"] == "unknown"
    when = datetime.now(timezone.utc) - timedelta(hours=3)
    with setup["factory"].begin() as session:
        session.add(TorqueAIDispatchSyncState(
            organization_id=setup["org"], last_successful_completed_at=when,
            last_successful_window_start=date(2026, 9, 1), last_successful_window_end=date(2026, 9, 10),
            last_successful_run_id="test-run",
        ))
    result = payload(rpc(setup))
    assert result["as_of"] == when.isoformat()
    assert result["freshness"]["status"] == "stale"


def test_metadata_and_disabled_route(setup, monkeypatch):
    assert setup["client"].post("/mcp", json={}).status_code == 401
    response = setup["client"].get("/.well-known/oauth-protected-resource/mcp")
    assert response.json()["resource"] == setup["config"].resource_url
    monkeypatch.delenv("POLARIS_CHATGPT_MCP_ENABLED", raising=False)
    app = FastAPI()
    assert server.install_mcp(app) is None
    assert TestClient(app).post("/mcp").status_code == 404


def test_stateless_transport_delete_has_no_write_action(setup):
    response = setup["client"].delete("/mcp", headers={"Authorization": "Bearer " + token(setup)})
    assert response.status_code == 405


def test_wrong_host_origin_and_admin_tokens_rejected(setup):
    assert rpc(setup, headers={"Host": "evil.test"}).status_code == 421
    assert rpc(setup, headers={"Origin": "https://evil.test"}).status_code == 403
    assert rpc(setup, headers={"Authorization": setup["local_headers"]["Authorization"]}).status_code == 401


def test_configuration_rejects_private_keys_and_insecure_urls(setup):
    for changes in ({"resource_url": "http://polaris.example.test/mcp"}, {"resource_url": "https://polaris.example.test/other"}, {"public_jwks": '{"keys":[{"kty":"oct","k":"secret"}]}'}):
        with pytest.raises(ValueError):
            replace(setup["config"], **changes)


def test_forged_token_and_id_token_rejected(setup):
    claims = jwt.decode(token(setup), options={"verify_signature": False})
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for key, headers in ((other_key, {"kid": "test-key", "typ": "at+jwt"}),
                         (setup["private"], {"kid": "unknown-key", "typ": "at+jwt"}),
                         (setup["private"], {"kid": "test-key", "typ": "JWT"})):
        credential = jwt.encode(claims, key, algorithm="RS256", headers=headers)
        assert rpc(setup, headers={"Authorization": "Bearer " + credential}).status_code == 401


def test_missing_membership_and_wrong_organization_rejected(setup):
    with setup["factory"].begin() as session:
        org = session.query(Organization).filter_by(id=setup["org"]).one()
        org.slug = "another-organization"
    assert rpc(setup).status_code == 403
    with setup["factory"].begin() as session:
        session.query(Organization).filter_by(id=setup["org"]).one().slug = "mor-logistics"
        session.query(OrganizationMembership).filter_by(identity_id=setup["config"].identity_id).delete()
    assert rpc(setup).status_code == 403


def test_secrets_in_excluded_fields_never_leave_tool(setup):
    from app.models.torqueai import TorqueAIDispatch
    add(setup)
    with setup["factory"].begin() as session:
        row = session.query(TorqueAIDispatch).filter_by(organization_id=setup["org"]).one()
        row.dispatcher_name = "SECRET-DISPATCHER"
        for stop in row.operational_stops:
            stop.notes = "SECRET-API-KEY"
            stop.address = "PRIVATE-ADDRESS"
    response = rpc(setup)
    assert payload(response)["summary"]["pickup_load_count"] == 1
    assert "SECRET" not in response.text and "PRIVATE-ADDRESS" not in response.text


def test_result_limit_never_reports_partial_success(setup, monkeypatch):
    add(setup, "101")
    add(setup, "102")
    monkeypatch.setattr(server, "MAX_LOADS", 1)
    assert payload(rpc(setup)) == {"status": "error", "error": {"code": "RESULT_LIMIT_EXCEEDED"}}


def test_city_filter_is_bound_and_multiple_stops_preserved(setup):
    add(setup)
    with setup["factory"].begin() as session:
        stop = session.query(TorqueAIDispatchStop).filter_by(organization_id=setup["org"], job="Pick Up").one()
        session.add(TorqueAIDispatchStop(
            organization_id=setup["org"], dispatch_id=stop.dispatch_id, stop_index=3,
            job="Pick Up", city="Brandon", province="Manitoba",
            scheduled_pickup_date_text=planning.TARGET_DATE, source_fingerprint="s" * 64,
            first_observed_at=planning.NOW, last_changed_at=planning.NOW,
        ))
    assert len(payload(rpc(setup))["loads"][0]["pickups"]) == 2
    result = payload(rpc(setup, arguments={"date": planning.TARGET_DATE, "province": "MB", "city": "' OR 1=1 --"}))
    assert result["summary"]["pickup_load_count"] == 0
