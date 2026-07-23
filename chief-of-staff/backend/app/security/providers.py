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


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class LocalTokenProvider:
    name = "local"

    def __init__(self, secret: str | None = None) -> None:
        self._secret = (secret or os.getenv("POLARIS_LOCAL_AUTH_SECRET", "polaris-dev-only")).encode()

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
