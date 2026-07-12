from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Relationship:
    source: str
    target: str
    relation: str


class RelationshipRegistry:
    def __init__(self) -> None:
        self._relationships: list[Relationship] = []

    def add(self, source: str, target: str, relation: str) -> Relationship:
        relationship = Relationship(
            source=source,
            target=target,
            relation=relation,
        )

        if relationship not in self._relationships:
            self._relationships.append(relationship)

        return relationship

    def all(self) -> list[Relationship]:
        return list(self._relationships)

    def for_entity(self, entity: str) -> list[Relationship]:
        return [
            relationship
            for relationship in self._relationships
            if relationship.source == entity
            or relationship.target == entity
        ]

    def clear(self) -> None:
        self._relationships.clear()

    def count(self) -> int:
        return len(self._relationships)


relationship_registry = RelationshipRegistry()
