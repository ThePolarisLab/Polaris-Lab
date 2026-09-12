"""Dedicated OAuth resource-server boundary; never accepts Polaris admin tokens."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from urllib.parse import urlsplit

import jwt
from sqlalchemy import event, text

from app.database.database import SessionLocal
from app.organizations.models import Organization
from app.security.models import AuthenticationResult, Permission
from app.security.service import AuthenticationError, AuthorizationError, SecurityService

ROLE = "polaris_chatgpt_readonly"
SCOPE = Permission.PICKUP_READ.value


@dataclass(frozen=True)
class MCPSettings:
    resource_url: str
    issuer: str
    client_id: str
    subject: str
    identity_id: str
    organization_id: str
    public_jwks: str

    @classmethod
    def from_env(cls):
        values = {
            field: os.environ.get("POLARIS_CHATGPT_" + field.upper(), "").strip()
            for field in cls.__dataclass_fields__
        }
        if not all(values.values()):
            raise ValueError("Incomplete Polaris ChatGPT MCP configuration")
        return cls(**values)

    def __post_init__(self):
        for value in (self.resource_url, self.issuer):
            url = urlsplit(value)
            if (url.scheme != "https" or not url.hostname or url.username or url.password
                    or url.query or url.fragment or any(c.isspace() for c in value)):
                raise ValueError("MCP resource and issuer must be canonical HTTPS URLs")
        if urlsplit(self.resource_url).path != "/mcp":
            raise ValueError("MCP resource URL must end in /mcp")
        try:
            keys = json.loads(self.public_jwks)["keys"]
            if not keys or any(
                key.get("kty") != "RSA" or not key.get("kid")
                or key.get("alg", "RS256") != "RS256"
                or key.get("use", "sig") != "sig"
                or any(name in key for name in ("d", "p", "q", "dp", "dq", "qi", "k"))
                for key in keys
            ) or len({key["kid"] for key in keys}) != len(keys):
                raise ValueError
            parsed = jwt.PyJWKSet.from_json(self.public_jwks)
            if any(key.key.key_size < 2048 for key in parsed.keys):
                raise ValueError
        except (ValueError, KeyError, TypeError, jwt.PyJWTError):
            raise ValueError("MCP requires public RS256 verification keys with unique key IDs") from None

    @property
    def metadata_url(self):
        url = urlsplit(self.resource_url)
        return f"{url.scheme}://{url.netloc}/.well-known/oauth-protected-resource/mcp"

    @property
    def challenge(self):
        return f'Bearer resource_metadata="{self.metadata_url}", scope="{SCOPE}"'


@contextmanager
def readonly_session():
    """Fail closed on SQL writes, including future accidental service changes."""
    with SessionLocal() as session:
        connection = session.connection()
        if connection.dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION READ ONLY"))

        def only_select(conn, cursor, statement, parameters, context, executemany):
            if not statement.lstrip().upper().startswith("SELECT "):
                raise AuthorizationError("read-only query required")

        event.listen(connection, "before_cursor_execute", only_select)
        try:
            yield session
        finally:
            session.rollback()
            event.remove(connection, "before_cursor_execute", only_select)


class MCPTokenProvider:
    name = "polaris-chatgpt-oauth"

    def __init__(self, config: MCPSettings):
        self.config = config
        self.keys = jwt.PyJWKSet.from_json(config.public_jwks)

    def validate(self, credential: str) -> AuthenticationResult:
        try:
            if len(credential) > 16384:
                raise ValueError
            header = jwt.get_unverified_header(credential)
            if header.get("alg") != "RS256" or header.get("typ") != "at+jwt":
                raise ValueError
            key = self.keys[header["kid"]]
            claims = jwt.decode(
                credential, key.key, algorithms=["RS256"],
                audience=self.config.resource_url, issuer=self.config.issuer,
                options={"require": ["exp", "iat", "sub", "aud", "iss", "client_id", "scope"]},
            )
            if (type(claims["exp"]) is not int or type(claims["iat"]) is not int
                    or not 0 < claims["exp"] - claims["iat"] <= 3600):
                raise ValueError
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            raise AuthenticationError("AUTH_REQUIRED") from None
        if (claims["sub"] != self.config.subject or claims["client_id"] != self.config.client_id
                or not isinstance(claims["scope"], str) or SCOPE not in claims["scope"].split()):
            raise AuthorizationError("FORBIDDEN")
        # Only this configured external subject/client pair maps to the service
        # identity. Token claims and caller headers can never select a tenant.
        return AuthenticationResult(provider=self.name, subject=self.config.identity_id)

    def authenticate(self, authorization: str | None):
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationError("AUTH_REQUIRED")
        with readonly_session() as session:
            principal = SecurityService(session).authenticate(
                self, authorization[7:].strip(), self.config.organization_id,
            )
            organization = session.query(Organization).filter_by(
                id=principal.organization_id, slug="mor-logistics", status="active",
            ).first()
            if organization is None or principal.role != ROLE or principal.permissions != frozenset({Permission.PICKUP_READ}):
                raise AuthorizationError("FORBIDDEN")
            SecurityService.require(principal, Permission.PICKUP_READ)
            return principal
