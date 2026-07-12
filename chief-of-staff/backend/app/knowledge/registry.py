from collections.abc import Iterable
from app.knowledge.entities import ALL_ENTITIES
from app.knowledge.models import Entity


class KnowledgeRegistry:
    def __init__(self, entities: Iterable[Entity]) -> None:
        self._entities = tuple(entities)
        self._by_id = {entity.id: entity for entity in self._entities}

        if len(self._by_id) != len(self._entities):
            raise ValueError("Knowledge Registry contains duplicate entity IDs.")

    def get(self, entity_id: str) -> Entity | None:
        return self._by_id.get(entity_id)

    def find(self, text: str) -> Entity | None:
        normalized = " ".join(text.lower().split()).strip()
        if not normalized:
            return None

        exact_matches = []
        partial_matches = []

        for entity in self._entities:
            for candidate in (entity.name, *entity.aliases):
                candidate_normalized = " ".join(candidate.lower().split())

                if normalized == candidate_normalized:
                    exact_matches.append(entity)
                    break

                if candidate_normalized in normalized:
                    partial_matches.append(entity)
                    break

        if exact_matches:
            return max(exact_matches, key=lambda item: len(item.name))

        if partial_matches:
            return max(partial_matches, key=lambda item: len(item.name))

        return None

    def find_all(self, text: str) -> list[Entity]:
        matches = [entity for entity in self._entities if entity.matches(text)]
        return sorted(matches, key=lambda item: len(item.name), reverse=True)

    def all(self) -> tuple[Entity, ...]:
        return self._entities


knowledge_registry = KnowledgeRegistry(ALL_ENTITIES)
