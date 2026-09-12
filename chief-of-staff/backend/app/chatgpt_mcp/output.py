"""Explicit, minimized structured result contract for ChatGPT clients."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scheduled(OutputModel):
    is_window: bool | None
    date: str | None
    date2: str | None
    time: str | None
    time2: str | None


class Stop(OutputModel):
    city: str | None
    province: str | None
    country: str | None
    scheduled: Scheduled


class Load(OutputModel):
    load_number: str
    order_number: str
    customer: str | None
    status: str | None
    driver: str | None
    truck: str | None
    trailer: str | None
    pickups: list[Stop]
    deliveries: list[Stop]
    attention_flags: list[str]
    last_changed_at: str


class Summary(OutputModel):
    pickup_load_count: int = Field(ge=0)
    attention_required_count: int = Field(ge=0)
    missing_driver_count: int = Field(ge=0)
    missing_truck_count: int = Field(ge=0)


class Freshness(OutputModel):
    basis: Literal["organization_last_successful_sync"]
    status: Literal["unknown", "stale", "recent"]
    requested_window_start: str | None
    requested_window_end: str | None


class RequestEcho(OutputModel):
    date: str
    province: str
    city: str | None


class PickupSuccess(OutputModel):
    status: Literal["success"]
    source: Literal["polaris_durable_torqueai"]
    as_of: str | None
    freshness: Freshness
    request: RequestEcho
    summary: Summary
    loads: list[Load]


class Error(OutputModel):
    code: Literal["AUTH_REQUIRED", "FORBIDDEN", "INVALID_DATE", "INVALID_PROVINCE", "INVALID_INPUT", "UNKNOWN_TOOL", "RESULT_LIMIT_EXCEEDED", "INTERNAL_ERROR"]


class PickupFailure(OutputModel):
    status: Literal["error"]
    error: Error


OUTPUT_SCHEMA = TypeAdapter(PickupSuccess | PickupFailure).json_schema()
OUTPUT_SCHEMA["type"] = "object"
