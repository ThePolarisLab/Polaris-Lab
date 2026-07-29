"""Authentication provider adapters.

The local provider is development-only and uses signed, expiring credentials. Future
OIDC providers can implement the same AuthenticationProvider protocol.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from app.security.models import AuthenticationResult
from app.security.service import AuthenticationError

DEFAULT_LOCAL_AUTH_SECRET = "polaris-dev-only"
PRODUCTION_ENVIRONMENTS = {"production", "prod", "staging"}


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _local_auth_secret(explicit_secret: str | None = None) -> bytes:
    environment = os.getenv("POLARIS_ENV", "development").strip().lower()
    configured = explicit_secret if explicit_secret is not None else os.getenv("POLARIS_LOCAL_AUTH_SECRET")

    if environment in PRODUCTION_ENVIRONMENTS:
        if not configured or configured == DEFAULT_LOCAL_AUTH_SECRET:
            raise AuthenticationError("local authentication secret is not configured")
        if len(configured) < 32:
            raise AuthenticationError("local authentication secret is too short")
        return configured.encode()

    return (configured or DEFAULT_LOCAL_AUTH_SECRET).encode()


class LocalTokenProvider:
    name = "local"

    def __init__(self, secret: str | None = None) -> None:
        self._secret = _local_auth_secret(secret)

    def issue(self, identity_id: str, *, ttl_seconds: int = 3600) -> str:
        payload: dict[str, Any] = {
            "sub": identity_id,
            "provider": self.name,
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl_seconds,
        }
        encoded = _encode(json.dumps(payload, separators=(",", ":")).encode())
        signature = _encode(hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def validate(self, credential: str) -> AuthenticationResult:
        try:
            encoded, signature = credential.split(".", 1)
            expected = _encode(hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise AuthenticationError("invalid credential signature")
            payload = json.loads(_decode(encoded))
            if int(payload["exp"]) <= int(time.time()):
                raise AuthenticationError("credential expired")
            subject = str(payload["sub"])
        except AuthenticationError:
            raise
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise AuthenticationError("invalid credential") from exc
        return AuthenticationResult(provider=self.name, subject=subject, claims=payload)
