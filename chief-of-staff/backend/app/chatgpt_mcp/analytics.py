"""Read-only TorqueAI lane analytics exposed to the dedicated ChatGPT MCP scope."""
from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Any

from mcp_types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, func

import json

from app.chatgpt_mcp.security import readonly_session
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop, TorqueAIDispatchSyncState
from app.security.models import Permission
from app.security.service import SecurityService

ANALYTICS_SCOPE = Permission.ANALYTICS_READ.value
ROLE_JOBS = {"pickup": "Pick Up", "delivery": "Drop Off"}


class LaneAnalyticsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    date_from: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    customer: str = Field(min_length=1, max_length=255, pattern=r".*\S.*", description="Target customer to compare with all other customers on the same lane.")
    pickup_city: str | None = Field(default=None, min_length=1, max_length=255, pattern=r".*\S.*")
    pickup_province: str | None = Field(default=None, min_length=1, max_length=120, pattern=r".*\S.*")
    pickup_country: str | None = Field(default=None, min_length=1, max_length=120, pattern=r".*\S.*")
    delivery_city: str | None = Field(default=None, min_length=1, max_length=255, pattern=r".*\S.*")
    delivery_province: str | None = Field(default=None, min_length=1, max_length=120, pattern=r".*\S.*")
    delivery_country: str | None = Field(default=None, min_length=1, max_length=120, pattern=r".*\S.*")

    @field_validator("date_from", "date_to")
    @classmethod
    def valid_date(cls, value: str) -> str:
        Date.fromisoformat(value)
        return value

    @field_validator("customer", "pickup_city", "pickup_province", "pickup_country", "delivery_city", "delivery_province", "delivery_country")
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid text")
        return value


LANE_ANALYTICS_TOOL = Tool(
    name="get_lane_analytics",
    title="Compare lane revenue and loaded-mile performance",
    description="Read-only comparison of one customer against all other customers on the same pickup/delivery lane using durable TorqueAI data. Revenue is never converted across currencies. Weighted revenue per loaded mile uses only loads with both revenue and positive loaded miles. Report missing-data and freshness evidence.",
    input_schema=LaneAnalyticsInput.model_json_schema(),
    output_schema={"type": "object", "additionalProperties": True},
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
    meta={"securitySchemes": [{"type": "oauth2", "scopes": [ANALYTICS_SCOPE]}]},
)


def _role_match(principal, role: str, prefix: str, args: LaneAnalyticsInput):
    criteria = [
        TorqueAIDispatchStop.organization_id == principal.organization_id,
        func.lower(TorqueAIDispatchStop.job) == ROLE_JOBS[role].lower(),
    ]
    for suffix, column in (("city", TorqueAIDispatchStop.city), ("province", TorqueAIDispatchStop.province), ("country", TorqueAIDispatchStop.country)):
        value = getattr(args, f"{prefix}_{suffix}")
        if value is not None:
            criteria.append(func.lower(column) == value.lower())
    return and_(*criteria)


def _metrics(rows) -> dict[str, Any]:
    currencies: dict[str, dict[str, Any]] = {}
    missing_miles = missing_revenue = 0
    for row in rows:
        op = row.operational_enrichment
        miles = row.loaded_miles
        charge = op.total_charge if op is not None else None
        currency = (op.currency or op.billing_currency) if op is not None else None
        if miles is None:
            missing_miles += 1
        if charge is None or currency is None:
            missing_revenue += 1
            continue
        key = currency.upper()
        bucket = currencies.setdefault(key, {"revenue_load_count": 0, "miles_load_count": 0, "rpm_eligible_load_count": 0, "total_revenue": 0.0, "total_loaded_miles": 0.0, "_rpm_revenue": 0.0, "_rpm_miles": 0.0})
        bucket["revenue_load_count"] += 1
        bucket["total_revenue"] += float(charge)
        if miles is not None:
            bucket["miles_load_count"] += 1
            bucket["total_loaded_miles"] += float(miles)
            if miles > 0:
                bucket["rpm_eligible_load_count"] += 1
                bucket["_rpm_revenue"] += float(charge)
                bucket["_rpm_miles"] += float(miles)
    for bucket in currencies.values():
        bucket["average_revenue_per_load"] = bucket["total_revenue"] / bucket["revenue_load_count"] if bucket["revenue_load_count"] else None
        bucket["weighted_revenue_per_loaded_mile"] = bucket["_rpm_revenue"] / bucket["_rpm_miles"] if bucket["_rpm_miles"] else None
        del bucket["_rpm_revenue"]; del bucket["_rpm_miles"]
    return {"load_count": len(rows), "missing_loaded_miles_count": missing_miles, "missing_revenue_or_currency_count": missing_revenue, "currency_metrics": dict(sorted(currencies.items()))}


def lane_analytics_result(arguments: LaneAnalyticsInput, principal):
    SecurityService.require(principal, Permission.ANALYTICS_READ)
    start, end = Date.fromisoformat(arguments.date_from), Date.fromisoformat(arguments.date_to)
    if start > end or (end - start).days + 1 > 366:
        raise ValueError("INVALID_DATE_RANGE")
    with readonly_session() as session:
        query = session.query(TorqueAIDispatch).outerjoin(
            TorqueAIDispatchOperational,
            (TorqueAIDispatchOperational.dispatch_id == TorqueAIDispatch.id)
            & (TorqueAIDispatchOperational.organization_id == principal.organization_id),
        ).filter(
            TorqueAIDispatch.organization_id == principal.organization_id,
            TorqueAIDispatch.ship_date_text.is_not(None),
            TorqueAIDispatch.ship_date_text >= start.isoformat(),
            TorqueAIDispatch.ship_date_text < (end + timedelta(days=1)).isoformat(),
        )
        if any(getattr(arguments, f"pickup_{x}") is not None for x in ("city", "province", "country")):
            query = query.filter(TorqueAIDispatch.operational_stops.any(_role_match(principal, "pickup", "pickup", arguments)))
        if any(getattr(arguments, f"delivery_{x}") is not None for x in ("city", "province", "country")):
            query = query.filter(TorqueAIDispatch.operational_stops.any(_role_match(principal, "delivery", "delivery", arguments)))
        target_rows = query.filter(func.lower(TorqueAIDispatch.customer_name) == arguments.customer.lower()).all()
        other_rows = query.filter(
            TorqueAIDispatch.customer_name.is_not(None),
            func.lower(TorqueAIDispatch.customer_name) != arguments.customer.lower(),
        ).all()
        sync = session.query(TorqueAIDispatchSyncState).filter_by(organization_id=principal.organization_id).first()
        payload = {
            "status": "success", "source": "polaris_durable_torqueai",
            "request": arguments.model_dump(),
            "comparison_definition": "target customer versus all other customers matching the same lane and date window",
            "target": {"customer": arguments.customer, **_metrics(target_rows)},
            "others": _metrics(other_rows),
            "freshness": {
                "last_successful_sync": sync.last_successful_completed_at.isoformat() if sync and sync.last_successful_completed_at else None,
                "last_successful_window_start": sync.last_successful_window_start.isoformat() if sync else None,
                "last_successful_window_end": sync.last_successful_window_end.isoformat() if sync else None,
            },
            "currency_conversion_performed": False,
            "provider_called": False, "database_writes_performed": False,
            "tenant_scope_validated": True, "secrets_exposed": False,
        }
    return CallToolResult(structured_content=payload, content=[TextContent(type="text", text=json.dumps(payload))])
