"""Signed machine-only bridge to one control-ledger-only historical preview."""
from datetime import date
import json
import os
import re

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.connectors.torqueai_history_certification import certify_history
from app.security.job_auth import JobAuthenticationError, verify_job_signature

router = APIRouter(prefix="/api/v1/internal/torqueai", tags=["internal-torqueai"])
FEATURE_FLAG = "POLARIS_TORQUEAI_HISTORICAL_PREVIEW_CERTIFICATION_ENABLED"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


@router.post("/historical-preview-certification", include_in_schema=False)
async def historical_preview_certification(
    request: Request,
    timestamp: str | None = Header(None, alias="X-Polaris-Job-Timestamp"),
    signature: str | None = Header(None, alias="X-Polaris-Job-Signature"),
):
    body = await request.body()
    try:
        verify_job_signature(method=request.method, path=request.url.path, body=body,
                             timestamp=timestamp, signature=signature,
                             secret_env="POLARIS_TORQUEAI_SYNC_TRIGGER_SECRET")
    except JobAuthenticationError:
        raise HTTPException(401, "machine authentication failed") from None
    if os.getenv(FEATURE_FLAG, "").strip().lower() != "true":
        raise HTTPException(503, {"status": "disabled", "secrets_exposed": False})
    # Manual parsing avoids FastAPI validation responses echoing caller input.
    try:
        if len(body) > 256 or request.query_params:
            raise ValueError("invalid request")
        values = json.loads(body, object_pairs_hook=_unique_object)
        if not isinstance(values, dict) or set(values) != {"date_from", "date_to"}:
            raise ValueError("invalid keys")
        for value in values.values():
            if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
                raise ValueError("invalid date")
        start, end = date.fromisoformat(values["date_from"]), date.fromisoformat(values["date_to"])
        if not 0 <= (end - start).days <= 6:
            raise ValueError("invalid interval")
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(400, "invalid historical preview interval") from None
    return await run_in_threadpool(certify_history, date_from=start, date_to=end)
