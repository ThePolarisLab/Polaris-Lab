from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: str
    source: str
    target: str
    relation: str
    created_at: datetime
