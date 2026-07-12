from dataclasses import dataclass, field
from enum import Enum


class EntityType(str, Enum):
    COMPANY = "Company"
    VENDOR = "Vendor"
    CUSTOMER = "Customer"
    SYSTEM = "System"
    GOVERNMENT = "Government"
    MISSION = "Mission"
    WORKFLOW = "Workflow"
    TASK = "Task"
    TRUCK = "Truck"
    DRIVER = "Driver"
    DOCUMENT = "Document"
    PROJECT = "Project"
    LOCATION = "Location"


class BusinessArea(str, Enum):
    GENERAL = "General"
    OPERATIONS = "Operations"
    FLEET = "Fleet"
    FINANCE = "Finance"
    COMPLIANCE = "Compliance"
    KNOWLEDGE = "Knowledge"
    STRATEGY = "Strategy"


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    name: str
    entity_type: EntityType
    business_area: BusinessArea = BusinessArea.GENERAL
    default_category: str = "General"
    default_priority: str = "Medium"
    tags: tuple[str, ...] = field(default_factory=tuple)
    aliases: tuple[str, ...] = field(default_factory=tuple)
    systems: tuple[str, ...] = field(default_factory=tuple)
    related_entities: tuple[str, ...] = field(default_factory=tuple)

    def matches(self, text: str) -> bool:
        normalized = " ".join(text.lower().split())
        return any(
            " ".join(candidate.lower().split()) in normalized
            for candidate in (self.name, *self.aliases)
            if candidate
        )
