"""Read-only Motive vehicle-utilization pagination primitive.

This module certifies the provider pagination contract for
``GET /v1/vehicle_utilization`` against CURRENT OFFICIAL Motive documentation
and implements a reusable, fail-closed, READ-ONLY pagination reader for
future vehicle-utilization writer use.

This is NOT the writer-enablement module. Nothing here persists a
``MotiveVehicleUtilizationRecord``, advances a ``MotiveSyncCheckpoint``,
writes sync history, or makes more than one HTTP attempt per requested page.
The primitives below must not be exposed as a public API route; only the
sanitized, zero-call, zero-write contract status function
(``motive_vehicle_utilization_pagination_contract_status``) is public.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from app.connectors.models import ConnectorStatus
from app.connectors.motive import MotiveConnectorError, _api_key, _timeout_seconds
from app.connectors.motive_vehicle_utilization import (
    MotiveVehicleUtilizationParseError,
    MotiveVehicleUtilizationRequestContext,
    MotiveVehicleUtilizationRollup,
    parse_vehicle_utilization_rollups,
)
from app.connectors.motive_vehicle_utilization_contract import (
    MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
    _base_url,
    _contract_json_response,
)
from app.motive.vehicle_utilization_unit_policy import (
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
    vehicle_utilization_writer_metric_units_header_value,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Official Motive pagination contract (CURRENT OFFICIAL Motive documentation).
# ---------------------------------------------------------------------------
MOTIVE_VEHICLE_UTILIZATION_PAGINATION_PAGE_NUMBERING = "one_based"
MOTIVE_VEHICLE_UTILIZATION_PAGINATION_FIRST_PAGE = 1
MOTIVE_VEHICLE_UTILIZATION_PAGINATION_DEFAULT_PROVIDER_PAGE_SIZE = 25
MOTIVE_VEHICLE_UTILIZATION_PAGINATION_MAX_PROVIDER_PAGE_SIZE = 100

# Polaris request decision based on Motive's documented maximum page size.
MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE = 100

# Polaris-owned runaway-loop safety guard. This is NOT Motive provider
# semantics; it exists purely to prevent an unbounded number of provider
# requests if provider pagination metadata becomes malformed.
MAX_VEHICLE_UTILIZATION_PAGES = 100


class MotiveVehicleUtilizationPaginationError(ValueError):
    """Safe, fail-closed pagination error that never includes provider values."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class VehicleUtilizationPaginationMetadata:
    """Strictly validated ``pagination`` envelope for one provider page."""

    per_page: int
    page_no: int
    total: int


@dataclass(frozen=True, slots=True)
class VehicleUtilizationPageRead:
    """One successfully validated page within a paginated read."""

    page_no: int
    per_page: int
    rollups: list[MotiveVehicleUtilizationRollup] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class VehicleUtilizationPaginatedRead:
    """Sanitized, read-only result of a completed paginated read."""

    rollups: list[MotiveVehicleUtilizationRollup]
    pages: list[VehicleUtilizationPageRead]
    pagination_total: int
    pages_read: int
    provider_calls: int
    expected_pages: int


# ---------------------------------------------------------------------------
# Section 4 — page request primitive.
# ---------------------------------------------------------------------------
def request_vehicle_utilization_page(
    *,
    organization_id: str,
    provider_vehicle_ids: Sequence[str],
    start_date: date,
    end_date: date,
    page_no: int,
    per_page: int,
    metric_units: bool = True,
    http_client: httpx.Client | None = None,
) -> tuple[Any, int]:
    """Perform one no-retry, read-only paginated vehicle-utilization request.

    Not exposed as a public API route. Callers are responsible for validating
    the returned pagination envelope with :func:`parse_pagination_metadata`.
    """
    selected_provider_vehicle_ids = [provider_vehicle_id for provider_vehicle_id in provider_vehicle_ids if provider_vehicle_id]
    if not selected_provider_vehicle_ids:
        raise MotiveConnectorError(
            "Motive vehicle utilization pagination request requires a stored vehicle id",
            status=ConnectorStatus.FAILED,
            code="provider_contract_error",
        )
    if isinstance(page_no, bool) or not isinstance(page_no, int) or page_no < MOTIVE_VEHICLE_UTILIZATION_PAGINATION_FIRST_PAGE:
        raise MotiveConnectorError(
            "Motive vehicle utilization pagination page_no must be an exact positive integer",
            status=ConnectorStatus.FAILED,
            code="invalid_pagination_request",
        )
    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or per_page < 1
        or per_page > MOTIVE_VEHICLE_UTILIZATION_PAGINATION_MAX_PROVIDER_PAGE_SIZE
    ):
        raise MotiveConnectorError(
            "Motive vehicle utilization pagination per_page must be an exact integer between 1 and 100",
            status=ConnectorStatus.FAILED,
            code="invalid_pagination_request",
        )
    if metric_units is not True:
        raise MotiveConnectorError(
            "Motive vehicle utilization pagination requires the certified canonical metric unit policy",
            status=ConnectorStatus.FAILED,
            code="invalid_pagination_request",
        )

    params: list[tuple[str, str]] = [("vehicle_ids[]", provider_vehicle_id) for provider_vehicle_id in selected_provider_vehicle_ids]
    params.extend(
        [
            ("start_date", start_date.isoformat()),
            ("end_date", end_date.isoformat()),
            ("per_page", str(per_page)),
            ("page_no", str(page_no)),
        ]
    )
    headers = {
        "Accept": "application/json",
        "X-API-Key": _api_key(),
        "X-Metric-Units": vehicle_utilization_writer_metric_units_header_value(metric_units),
    }
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=_timeout_seconds())
    try:
        response = client.get(f"{_base_url()}{MOTIVE_VEHICLE_UTILIZATION_ENDPOINT}", params=params, headers=headers)
        payload = _contract_json_response(response)
        logger.info(
            "MOTIVE VEHICLE UTILIZATION PAGE REQUEST",
            extra={
                "motive_operation": "vehicle_utilization_pagination_request",
                "organization_id": organization_id,
                "http_status": response.status_code,
                "page_no": page_no,
                "per_page": per_page,
            },
        )
        return payload, response.status_code
    except httpx.TimeoutException as exc:
        raise MotiveConnectorError(
            "Motive vehicle utilization pagination request timed out",
            status=ConnectorStatus.FAILED,
            retryable=False,
            code="provider_timeout",
        ) from exc
    except httpx.HTTPError as exc:
        raise MotiveConnectorError(
            "Motive vehicle utilization pagination request failed due to a network error",
            status=ConnectorStatus.FAILED,
            retryable=False,
            code="network_failure",
        ) from exc
    finally:
        if owns_client:
            client.close()


# ---------------------------------------------------------------------------
# Section 5/6 — strict pagination metadata parser.
# ---------------------------------------------------------------------------
def parse_pagination_metadata(
    payload: Any,
    *,
    expected_page_no: int,
    expected_per_page: int,
) -> VehicleUtilizationPaginationMetadata:
    """Fail-closed parse of the provider ``pagination`` envelope for one page."""
    if not isinstance(payload, dict):
        raise MotiveVehicleUtilizationPaginationError(
            "invalid_envelope", "Motive vehicle utilization pagination response must be an object."
        )
    pagination = payload.get("pagination")
    if pagination is None:
        raise MotiveVehicleUtilizationPaginationError(
            "missing_pagination", "Motive vehicle utilization response did not include pagination metadata."
        )
    if not isinstance(pagination, dict):
        raise MotiveVehicleUtilizationPaginationError(
            "invalid_pagination", "Motive vehicle utilization pagination metadata must be an object."
        )

    per_page = _pagination_int(pagination, "per_page", minimum=1, maximum=MOTIVE_VEHICLE_UTILIZATION_PAGINATION_MAX_PROVIDER_PAGE_SIZE)
    page_no = _pagination_int(pagination, "page_no", minimum=1, maximum=None)
    total = _pagination_int(pagination, "total", minimum=0, maximum=None)

    if page_no != expected_page_no:
        raise MotiveVehicleUtilizationPaginationError(
            "pagination_page_no_mismatch",
            "Motive vehicle utilization pagination page_no did not match the requested page.",
        )
    if per_page != expected_per_page:
        raise MotiveVehicleUtilizationPaginationError(
            "pagination_per_page_mismatch",
            "Motive vehicle utilization pagination per_page did not match the requested page size.",
        )

    return VehicleUtilizationPaginationMetadata(per_page=per_page, page_no=page_no, total=total)


def _pagination_int(pagination: dict[str, Any], key: str, *, minimum: int, maximum: int | None) -> int:
    if key not in pagination:
        raise MotiveVehicleUtilizationPaginationError(
            f"missing_{key}", f"Motive vehicle utilization pagination metadata did not include {key}."
        )
    value = pagination[key]
    # Explicit int required. bool is a subclass of int in Python and is
    # rejected here on purpose (section 5: "bool is NOT an acceptable int").
    if isinstance(value, bool) or not isinstance(value, int):
        raise MotiveVehicleUtilizationPaginationError(
            f"invalid_{key}_type", f"Motive vehicle utilization pagination {key} had an invalid type."
        )
    if value < minimum or (maximum is not None and value > maximum):
        raise MotiveVehicleUtilizationPaginationError(
            f"invalid_{key}_value", f"Motive vehicle utilization pagination {key} was out of range."
        )
    return value


# ---------------------------------------------------------------------------
# Section 7-15 — reusable READ-ONLY paginated reader for future writer use.
# ---------------------------------------------------------------------------
def read_vehicle_utilization_pages(
    *,
    organization_id: str,
    organization_slug: str,
    provider_vehicle_ids: Sequence[str],
    start_date: date,
    end_date: date,
    per_page: int = MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE,
    metric_units: bool = MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
    http_client: httpx.Client | None = None,
) -> VehicleUtilizationPaginatedRead:
    """Read every provider page for one request window and fail closed on any
    pagination-contract violation.

    NO persistence. NO checkpoint. NO commit. NO flush. NO add. This function
    performs only read-only HTTP requests and in-memory validation.
    """
    selected_provider_vehicle_ids = [provider_vehicle_id for provider_vehicle_id in provider_vehicle_ids if provider_vehicle_id]
    if not selected_provider_vehicle_ids:
        raise MotiveVehicleUtilizationPaginationError(
            "no_stored_vehicle", "Motive vehicle utilization pagination requires at least one selected vehicle id."
        )
    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or per_page < 1
        or per_page > MOTIVE_VEHICLE_UTILIZATION_PAGINATION_MAX_PROVIDER_PAGE_SIZE
    ):
        raise MotiveVehicleUtilizationPaginationError(
            "invalid_per_page_request", "Motive vehicle utilization pagination per_page must be an exact integer between 1 and 100."
        )

    selected_vehicle_set = set(selected_provider_vehicle_ids)
    request_context = MotiveVehicleUtilizationRequestContext(request_start_date=start_date, request_end_date=end_date)

    all_rollups: list[MotiveVehicleUtilizationRollup] = []
    pages: list[VehicleUtilizationPageRead] = []
    seen_provider_vehicle_ids: set[str] = set()
    provider_calls = 0
    pagination_total: int | None = None
    expected_pages: int | None = None

    page_no = MOTIVE_VEHICLE_UTILIZATION_PAGINATION_FIRST_PAGE
    while True:
        provider_calls += 1
        payload, _http_status = request_vehicle_utilization_page(
            organization_id=organization_id,
            provider_vehicle_ids=selected_provider_vehicle_ids,
            start_date=start_date,
            end_date=end_date,
            page_no=page_no,
            per_page=per_page,
            metric_units=metric_units,
            http_client=http_client,
        )

        metadata = parse_pagination_metadata(payload, expected_page_no=page_no, expected_per_page=per_page)

        if pagination_total is None:
            pagination_total = metadata.total
            expected_pages = 1 if pagination_total == 0 else math.ceil(pagination_total / per_page)
            if expected_pages > MAX_VEHICLE_UTILIZATION_PAGES:
                raise MotiveVehicleUtilizationPaginationError(
                    "pagination_page_guard_exceeded",
                    "Motive vehicle utilization pagination exceeded the Polaris safety page guard.",
                )
        elif metadata.total != pagination_total:
            raise MotiveVehicleUtilizationPaginationError(
                "pagination_total_changed", "Motive vehicle utilization pagination total changed between pages."
            )

        try:
            page_rollups = parse_vehicle_utilization_rollups(
                payload,
                organization_id=organization_id,
                organization_slug=organization_slug,
                request_context=request_context,
            )
        except MotiveVehicleUtilizationParseError as exc:
            raise MotiveVehicleUtilizationPaginationError(
                exc.code, "Motive vehicle utilization pagination response did not match the certified provider schema."
            ) from exc

        if len(page_rollups) > per_page:
            raise MotiveVehicleUtilizationPaginationError(
                "page_item_count_exceeded",
                "Motive vehicle utilization pagination page returned more rollups than the requested page size.",
            )

        if not page_rollups and len(all_rollups) < pagination_total:
            raise MotiveVehicleUtilizationPaginationError(
                "premature_empty_page",
                "Motive vehicle utilization pagination returned an empty page before the pagination total was reached.",
            )

        for rollup in page_rollups:
            if rollup.provider_vehicle_id in seen_provider_vehicle_ids:
                raise MotiveVehicleUtilizationPaginationError(
                    "duplicate_vehicle_observed",
                    "Motive vehicle utilization pagination returned a duplicate vehicle rollup for this request window.",
                )
            seen_provider_vehicle_ids.add(rollup.provider_vehicle_id)
            if rollup.provider_vehicle_id not in selected_vehicle_set:
                raise MotiveVehicleUtilizationPaginationError(
                    "unexpected_vehicle_observed",
                    "Motive vehicle utilization pagination returned a vehicle outside the selected vehicle set.",
                )
            # Deliberately no returned-unit-indicator readiness check here.
            # Provider schema parse success is distinct from durable
            # persistence readiness (see
            # app.motive.vehicle_utilization_unit_policy). The returned
            # metric_units Boolean is preserved on the rollup as observed
            # context; a future writer that calls this reader is responsible
            # for the persistence-readiness gate
            # (validate_vehicle_utilization_unit_persistence_readiness)
            # before any commit.

        all_rollups.extend(page_rollups)
        pages.append(VehicleUtilizationPageRead(page_no=page_no, per_page=per_page, rollups=page_rollups))

        logger.info(
            "MOTIVE VEHICLE UTILIZATION PAGE VALIDATED",
            extra={
                "motive_operation": "vehicle_utilization_pagination_page_validated",
                "organization_id": organization_id,
                "page_no": page_no,
                "per_page": per_page,
                "page_item_count": len(page_rollups),
                "cumulative_item_count": len(all_rollups),
                "pagination_total": pagination_total,
            },
        )

        if len(pages) >= expected_pages:
            break
        page_no += 1

    if len(all_rollups) != pagination_total:
        code = "cumulative_rollup_count_below_total" if len(all_rollups) < pagination_total else "cumulative_rollup_count_above_total"
        raise MotiveVehicleUtilizationPaginationError(
            code, "Motive vehicle utilization pagination cumulative rollup count did not equal the pagination total."
        )

    logger.info(
        "MOTIVE VEHICLE UTILIZATION PAGINATED READ",
        extra={
            "motive_operation": "vehicle_utilization_pagination_read",
            "organization_id": organization_id,
            "pages_read": len(pages),
            "provider_calls": provider_calls,
            "pagination_total": pagination_total,
        },
    )

    return VehicleUtilizationPaginatedRead(
        rollups=all_rollups,
        pages=pages,
        pagination_total=pagination_total,
        pages_read=len(pages),
        provider_calls=provider_calls,
        expected_pages=expected_pages,
    )


# ---------------------------------------------------------------------------
# Section 16 — public, zero-call, zero-write, sanitized contract status.
# ---------------------------------------------------------------------------
def motive_vehicle_utilization_pagination_contract_status() -> dict[str, Any]:
    """Return the sanitized read-only pagination contract.

    Makes ZERO Motive provider calls and ZERO database writes.
    """
    return {
        "provider": "motive",
        "resource": "vehicle_utilization_pagination_contract",
        "source_endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
        "pagination_contract": {
            "classification": "CERTIFIED",
            "page_numbering": MOTIVE_VEHICLE_UTILIZATION_PAGINATION_PAGE_NUMBERING,
            "first_page": MOTIVE_VEHICLE_UTILIZATION_PAGINATION_FIRST_PAGE,
            "default_provider_page_size": MOTIVE_VEHICLE_UTILIZATION_PAGINATION_DEFAULT_PROVIDER_PAGE_SIZE,
            "max_provider_page_size": MOTIVE_VEHICLE_UTILIZATION_PAGINATION_MAX_PROVIDER_PAGE_SIZE,
            "canonical_writer_page_size": MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE,
            "pagination_fields": ["pagination.per_page", "pagination.page_no", "pagination.total"],
        },
        "completion_rule": {
            "pagination_total_required": True,
            "total_must_remain_stable": True,
            "cumulative_rows_must_equal_total": True,
            "premature_empty_page_fails_closed": True,
        },
        "batch_rules": {
            "duplicate_vehicle_fails_closed": True,
            "unexpected_vehicle_fails_closed": True,
            "canonical_metric_units_required": True,
        },
        "safety": {
            "max_page_guard": MAX_VEHICLE_UTILIZATION_PAGES,
            "provider_calls_from_status_endpoint": 0,
            "persistence_enabled": False,
            "checkpoint_enabled": False,
            "scheduled_ingestion_enabled": False,
            "raw_provider_values_exposed": False,
        },
    }
