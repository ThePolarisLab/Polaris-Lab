from dataclasses import dataclass

from app.knowledge.models import Entity
from app.knowledge.registry import knowledge_registry


@dataclass(frozen=True, slots=True)
class MemoryClassification:
    category: str
    importance: str
    entities: tuple[Entity, ...]
    tags: tuple[str, ...]


def classify_memory(text: str) -> MemoryClassification:
    entities = tuple(knowledge_registry.find_all(text))

    if entities:
        primary = entities[0]
        tags = _merge_tags(entities)
        importance = _highest_priority(entities)

        return MemoryClassification(
            category=primary.default_category,
            importance=importance,
            entities=entities,
            tags=tags,
        )

    return MemoryClassification(
        category=_fallback_category(text),
        importance=_fallback_importance(text),
        entities=(),
        tags=(),
    )


def _merge_tags(entities: tuple[Entity, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []

    for entity in entities:
        for tag in (entity.name, entity.entity_type.value, *entity.tags):
            key = tag.casefold()
            if key not in seen:
                seen.add(key)
                ordered.append(tag)

    return tuple(ordered)


def _highest_priority(entities: tuple[Entity, ...]) -> str:
    ranking = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    return max(
        (entity.default_priority for entity in entities),
        key=lambda priority: ranking.get(priority, 2),
        default="Medium",
    )


def _fallback_category(text: str) -> str:
    value = text.lower()

    if any(word in value for word in ("truck", "trailer", "driver", "fleet")):
        return "Fleet"

    if any(word in value for word in (
        "gst", "invoice", "cash", "payment", "payroll",
        "accounts receivable", "accounts payable",
    )):
        return "Finance"

    if any(word in value for word in ("ifta", "kyu", "compliance", "tax", "fuel")):
        return "Compliance"

    if any(word in value for word in (
        "constitution", "founder", "decision", "history", "policy",
    )):
        return "History"

    return "General"


def _fallback_importance(text: str) -> str:
    value = text.lower()

    if any(word in value for word in (
        "critical", "deadline today", "due today", "overdue",
    )):
        return "Critical"

    if any(word in value for word in (
        "urgent", "deadline", "delayed", "missing", "blocked",
    )):
        return "High"

    return "Medium"
