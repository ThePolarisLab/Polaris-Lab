"""Bounded read-only TorqueAI external dispatch connector.

Implements the first connector gate certified by
``TORQUEAI_EXTERNAL_DISPATCH_CONNECTOR_DESIGN.md``: one explicit dispatch page,
GET-only, backend-only secrets, no persistence, no scheduler, and no retries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import logging
import os
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

TORQUEAI_API_TOKEN_ENV = "POLARIS_TORQUEAI_API_TOKEN"
TORQUEAI_BASE_URL_ENV = "POLARIS_TORQUEAI_BASE_URL"
TORQUEAI_ORGANIZATION_SLUG_ENV = "POLARIS_TORQUEAI_ORGANIZATION_SLUG"
TORQUEAI_DISPATCH_PATH = "/api/external/dispatches"
TORQUEAI_MAX_RANGE_DAYS = 31
TORQUEAI_MAX_LIMIT = 500
TORQUEAI_DEFAULT_LIMIT = 100
TORQUEAI_REQUEST_TIMEOUT_SECONDS = 30.0


class TorqueAIConnectorError(RuntimeError):
    """Sanitized connector error that never contains credentials or raw payloads."""

    def __init__(self, code: str, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.retryable = False


@dataclass(frozen=True, slots=True)
class TorqueAIDispatchPage:
    """Validated in-memory representation of one TorqueAI dispatch page."""

    data: tuple[dict[str, Any], ...]
    total_count: int
    page: int
    items_per_page: int
    date_from: date
    date_to: date


class TorqueAIConnector:
    """Issue exactly one bounded GET against TorqueAI's certified dispatch endpoint."""

    def __init__(
        self,
        *,
        organization_slug: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.organization_slug = organization_slug
        self._client = http_client

    def fetch_dispatches(
        self,
        *,
        date_from: date | str,
        date_to: date | str,
        page: int = 1,
        limit: int = TORQUEAI_DEFAULT_LIMIT,
    ) -> TorqueAIDispatchPage:
        """Fetch and validate one page with no retries and no persistence."""
        request_from = _coerce_date(date_from, "from")
        request_to = _coerce_date(date_to, "to")
        _validate_request_bounds(request_from, request_to, page, limit)
        base_url, token = _validated_configuration(self.organization_slug)

        logger.info(
            "TORQUEAI DISPATCH REQUEST",
            extra={
                "torqueai_operation": "external_dispatch_page",
                "organization_slug": self.organization_slug,
                "endpoint_path": TORQUEAI_DISPATCH_PATH,
                "date_from": request_from.isoformat(),
                "date_to": request_to.isoformat(),
                "page": page,
                "limit": limit,
            },
        )

        try:
            response = self._http().get(
                f"{base_url}{TORQUEAI_DISPATCH_PATH}",
                params={
                    "from": request_from.isoformat(),
                    "to": request_to.isoformat(),
                    "page": page,
                    "limit": limit,
                },
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
        except httpx.TimeoutException as exc:
            raise TorqueAIConnectorError("provider_timeout", "TorqueAI request timed out") from exc
        except httpx.HTTPError as exc:
            raise TorqueAIConnectorError("network_failure", "TorqueAI request failed due to a network error") from exc

        if response.status_code != 200:
            raise _status_error(response.status_code)

        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise TorqueAIConnectorError("provider_contract_error", "TorqueAI response was not valid JSON") from exc

        return _parse_dispatch_page(
            payload,
            request_from=request_from,
            request_to=request_to,
            requested_page=page,
            requested_limit=limit,
        )

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=TORQUEAI_REQUEST_TIMEOUT_SECONDS)
        return self._client


def _validated_configuration(organization_slug: str) -> tuple[str, str]:
    configured_slug = str(os.getenv(TORQUEAI_ORGANIZATION_SLUG_ENV) or "").strip()
    if not configured_slug:
        raise TorqueAIConnectorError("organization_not_configured", "TorqueAI organization scope is not configured")
    if not isinstance(organization_slug, str) or not organization_slug.strip() or organization_slug != configured_slug:
        raise TorqueAIConnectorError("organization_scope_mismatch", "TorqueAI is not configured for this organization")

    token = str(os.getenv(TORQUEAI_API_TOKEN_ENV) or "").strip()
    if not token:
        raise TorqueAIConnectorError("token_missing", "TorqueAI API token is not configured")

    base_url = str(os.getenv(TORQUEAI_BASE_URL_ENV) or "").strip().rstrip("/")
    if not base_url:
        raise TorqueAIConnectorError("base_url_missing", "TorqueAI base URL is not configured")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise TorqueAIConnectorError("invalid_base_url", "TorqueAI base URL must be an HTTPS origin")
    return f"https://{parsed.netloc}", token


def _coerce_date(value: date | str, field_name: str) -> date:
    if isinstance(value, datetime):
        raise TorqueAIConnectorError("invalid_request", f"TorqueAI {field_name} date must be an ISO date")
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise TorqueAIConnectorError("invalid_request", f"TorqueAI {field_name} date must be an ISO date") from exc
    raise TorqueAIConnectorError("invalid_request", f"TorqueAI {field_name} date must be an ISO date")


def _validate_request_bounds(date_from: date, date_to: date, page: int, limit: int) -> None:
    if date_from > date_to:
        raise TorqueAIConnectorError("invalid_request", "TorqueAI from date must not be after to date")
    if (date_to - date_from).days + 1 > TORQUEAI_MAX_RANGE_DAYS:
        raise TorqueAIConnectorError("invalid_request", "TorqueAI date range must not exceed 31 days")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise TorqueAIConnectorError("invalid_request", "TorqueAI page must be a positive integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= TORQUEAI_MAX_LIMIT:
        raise TorqueAIConnectorError("invalid_request", "TorqueAI limit must be between 1 and 500")


def _status_error(status_code: int) -> TorqueAIConnectorError:
    mapping = {
        400: ("provider_bad_request", "TorqueAI rejected the bounded request"),
        401: ("authorization_required", "TorqueAI authorization failed"),
        403: ("permission_denied", "TorqueAI denied this request"),
        405: ("method_not_allowed", "TorqueAI rejected the request method"),
        429: ("rate_limited", "TorqueAI rate limited the request"),
        500: ("provider_unavailable", "TorqueAI provider is unavailable"),
    }
    code, message = mapping.get(status_code, ("provider_unexpected_status", "TorqueAI returned an unexpected HTTP status"))
    return TorqueAIConnectorError(code, message, http_status=status_code)


def _parse_dispatch_page(
    payload: Any,
    *,
    request_from: date,
    request_to: date,
    requested_page: int,
    requested_limit: int,
) -> TorqueAIDispatchPage:
    if not isinstance(payload, dict):
        raise _contract_error()

    data = payload.get("data")
    total_count = _non_negative_int(payload.get("totalCount"))
    response_page = _positive_int(payload.get("page"))
    items_per_page = _positive_int(payload.get("itemsPerPage"))
    date_range = payload.get("dateRange")

    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise _contract_error()
    if total_count is None or response_page != requested_page or items_per_page is None:
        raise _contract_error()
    if items_per_page > requested_limit or items_per_page > TORQUEAI_MAX_LIMIT:
        raise _contract_error()
    if len(data) > items_per_page:
        raise _contract_error()
    if not isinstance(date_range, dict):
        raise _contract_error()

    try:
        response_from = _coerce_date(date_range.get("from"), "response from")
        response_to = _coerce_date(date_range.get("to"), "response to")
    except TorqueAIConnectorError as exc:
        raise _contract_error() from exc
    if response_from != request_from or response_to != request_to:
        raise _contract_error()

    consumed_before = (requested_page - 1) * items_per_page
    if consumed_before > total_count or consumed_before + len(data) > total_count:
        raise _contract_error()

    return TorqueAIDispatchPage(
        data=tuple(dict(item) for item in data),
        total_count=total_count,
        page=response_page,
        items_per_page=items_per_page,
        date_from=response_from,
        date_to=response_to,
    )


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _contract_error() -> TorqueAIConnectorError:
    return TorqueAIConnectorError("provider_contract_error", "TorqueAI response did not match the certified dispatch contract")
