"""Schema and read-only handler for the loaded trailer MCP tool."""
import json
from typing import Literal

from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from app.chatgpt_mcp.output import OutputModel, PickupFailure
from app.chatgpt_mcp.security import readonly_session
from app.security.models import Permission
from app.security.service import SecurityService
from app.services.loaded_trailer_intelligence import query_loaded_trailers

LOADED_SCOPE = Permission.LOADED_TRAILER_READ.value


class LoadedTrailerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    city: str = Field(min_length=1, max_length=255, pattern=r"\S")
    province: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"\S")
    country: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"\S")

    @field_validator("city", "province", "country")
    @classmethod
    def location(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("invalid location")
        return value


class Trailer(OutputModel):
    trailer_number: str
    load_number: str
    load_status: str | None
    truck_number: str | None
    current_city: str | None
    current_province: str | None
    current_country: str | None
    location_source: Literal["motive_gps", "dispatch_inference"]
    location_observed_at: str | None
    dispatch_last_changed_at: str | None
    dispatch_last_observed_at: str | None
    pairing_observed_at: str | None
    loaded_state: Literal["confirmed", "uncertain"]
    loaded_evidence: list[str]
    confidence: Literal["high", "medium", "low", "unknown"]
    attention_flags: list[str]


class LoadedSummary(OutputModel):
    confirmed_loaded_trailer_count: int = Field(ge=0)
    uncertain_loaded_trailer_count: int = Field(ge=0)


class LoadedTrailerSuccess(OutputModel):
    status: Literal["success"]
    source: Literal["polaris_operational_intelligence"]
    request: LoadedTrailerInput
    as_of: str
    location_staleness_threshold_minutes: float
    summary: LoadedSummary
    trailers: list[Trailer]
    uncertain_trailers: list[Trailer]


LOADED_OUTPUT_SCHEMA = TypeAdapter(LoadedTrailerSuccess | PickupFailure).json_schema()
LOADED_OUTPUT_SCHEMA["type"] = "object"
LOADED_TOOL = Tool(
    name="get_loaded_trailers", title="Review loaded trailers by city",
    description="Use this to count or review loaded trailers currently in a city, optionally filtered by province and country. Returns separate confirmed and uncertain counts with location and freshness evidence. Confirmation uses fresh dispatch status, assignment and Motive truck GPS, not a physical cargo sensor. Scheduled stops alone never confirm current location. Report uncertainty and observation times.",
    input_schema=LoadedTrailerInput.model_json_schema(), output_schema=LOADED_OUTPUT_SCHEMA,
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False),
    meta={"securitySchemes": [{"type": "oauth2", "scopes": [LOADED_SCOPE]}]},
)


def loaded_trailer_result(arguments, principal):
    SecurityService.require(principal, Permission.LOADED_TRAILER_READ)
    with readonly_session() as session:
        payload = query_loaded_trailers(session, organization_id=principal.organization_id, request=arguments.model_dump())
    payload = LoadedTrailerSuccess.model_validate(payload).model_dump()
    return CallToolResult(structured_content=payload, content=[TextContent(type="text", text=json.dumps(payload))])
