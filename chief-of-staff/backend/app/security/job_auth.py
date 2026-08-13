"""Machine authentication helpers for narrow scheduled job triggers."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass


class JobAuthenticationError(RuntimeError):
    """Controlled authentication failure for internal job triggers."""


@dataclass(frozen=True)
class JobSignatureParts:
    method: str
    path: str
    timestamp: str
    body_digest: str

    def canonical(self) -> str:
        return "\n".join([self.method.upper(), self.path, self.timestamp, self.body_digest])


def body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def verify_job_signature(
    *,
    method: str,
    path: str,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    secret_env: str = "POLARIS_ACE_CRON_TRIGGER_SECRET",
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    secret = os.getenv(secret_env, "")
    if not secret.strip():
        raise JobAuthenticationError("machine authentication unavailable")
    if not timestamp:
        raise JobAuthenticationError("machine authentication failed")
    if not signature:
        raise JobAuthenticationError("machine authentication failed")
    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise JobAuthenticationError("machine authentication failed") from exc
    current = int(time.time()) if now is None else int(now)
    if abs(current - timestamp_int) > tolerance_seconds:
        raise JobAuthenticationError("machine authentication failed")
    if len(signature) != 64 or any(char not in "0123456789abcdefABCDEF" for char in signature):
        raise JobAuthenticationError("machine authentication failed")

    parts = JobSignatureParts(
        method=method,
        path=path,
        timestamp=timestamp,
        body_digest=body_digest(body),
    )
    expected = hmac.new(secret.encode("utf-8"), parts.canonical().encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        raise JobAuthenticationError("machine authentication failed")


def sign_job_request(*, method: str, path: str, body: bytes, timestamp: str, secret: str) -> str:
    parts = JobSignatureParts(method=method, path=path, timestamp=timestamp, body_digest=body_digest(body))
    return hmac.new(secret.encode("utf-8"), parts.canonical().encode("utf-8"), hashlib.sha256).hexdigest()
