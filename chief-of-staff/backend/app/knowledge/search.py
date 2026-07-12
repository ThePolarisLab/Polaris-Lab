import re
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.knowledge.registry import knowledge_registry
from app.knowledge.relationships import relationships_for_entity
from app.models.memory import MemoryEntry


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    memory: MemoryEntry
    score: int
    reasons: tuple[str, ...]


def search_memories(
    db: Session,
    query: str,
    *,
    limit: int = 20,
) -> list[MemorySearchResult]:
    """
    Knowledge-aware memory search.

    This is deterministic Version 1 search. It combines:
    - direct text matches
    - recognized Knowledge Registry entities
    - persistent relationship links
    - category matches

    It is not vector-embedding semantic search yet.
    """

    normalized_query = _normalize(query)

    if not normalized_query:
        return []

    recognized_entities = tuple(
        knowledge_registry.find_all(query)
    )

    entity_ids = {
        entity.id
        for entity in recognized_entities
    }

    related_memory_ids = _related_memory_ids(
        db,
        entity_ids,
    )

    query_terms = {
        term
        for term in normalized_query.split()
        if len(term) >= 3
    }

    candidates = _load_candidates(
        db,
        query=query,
        related_memory_ids=related_memory_ids,
        limit=max(limit * 5, 100),
    )

    results: list[MemorySearchResult] = []

    for memory in candidates:
        score, reasons = _score_memory(
            memory=memory,
            query=normalized_query,
            query_terms=query_terms,
            related_memory_ids=related_memory_ids,
            recognized_entities=recognized_entities,
        )

        if score > 0:
            results.append(
                MemorySearchResult(
                    memory=memory,
                    score=score,
                    reasons=tuple(reasons),
                )
            )

    return sorted(
        results,
        key=lambda result: (
            result.score,
            result.memory.created_at,
        ),
        reverse=True,
    )[:limit]


def _load_candidates(
    db: Session,
    *,
    query: str,
    related_memory_ids: set[int],
    limit: int,
) -> list[MemoryEntry]:
    pattern = f"%{query.strip()}%"

    filters = [
        MemoryEntry.title.ilike(pattern),
        MemoryEntry.details.ilike(pattern),
        MemoryEntry.category.ilike(pattern),
        MemoryEntry.source.ilike(pattern),
    ]

    if related_memory_ids:
        filters.append(
            MemoryEntry.id.in_(related_memory_ids)
        )

    direct_matches = (
        db.query(MemoryEntry)
        .filter(or_(*filters))
        .order_by(MemoryEntry.created_at.desc())
        .limit(limit)
        .all()
    )

    if direct_matches:
        return direct_matches

    # Fallback: inspect recent memories so term-overlap can still find results.
    return (
        db.query(MemoryEntry)
        .order_by(MemoryEntry.created_at.desc())
        .limit(limit)
        .all()
    )


def _related_memory_ids(
    db: Session,
    entity_ids: set[str],
) -> set[int]:
    memory_ids: set[int] = set()

    for entity_id in entity_ids:
        relationships = relationships_for_entity(
            db,
            entity_id,
            limit=1000,
        )

        for relationship in relationships:
            for key in (
                relationship.source,
                relationship.target,
            ):
                memory_id = _memory_id_from_key(key)

                if memory_id is not None:
                    memory_ids.add(memory_id)

    return memory_ids


def _score_memory(
    *,
    memory: MemoryEntry,
    query: str,
    query_terms: set[str],
    related_memory_ids: set[int],
    recognized_entities,
) -> tuple[int, list[str]]:
    title = _normalize(memory.title or "")
    details = _normalize(memory.details or "")
    category = _normalize(memory.category or "")
    combined = f"{title} {details} {category}"

    score = 0
    reasons: list[str] = []

    if query == title or query == details:
        score += 100
        reasons.append("exact text match")
    elif query in combined:
        score += 60
        reasons.append("phrase match")

    overlap = query_terms.intersection(
        set(combined.split())
    )

    if overlap:
        score += min(len(overlap) * 8, 32)
        reasons.append(
            "matching terms: "
            + ", ".join(sorted(overlap))
        )

    if memory.id in related_memory_ids:
        score += 50
        reasons.append("linked through Knowledge Relationships")

    for entity in recognized_entities:
        entity_name = _normalize(entity.name)

        if entity_name in combined:
            score += 25
            reasons.append(
                f"mentions recognized entity: {entity.name}"
            )

        if _normalize(entity.default_category) == category:
            score += 10
            reasons.append(
                f"same category as {entity.name}"
            )

    return score, _deduplicate(reasons)


def _memory_id_from_key(value: str) -> int | None:
    match = re.fullmatch(
        r"memory\.(\d+)",
        value.strip(),
    )

    if match is None:
        return None

    return int(match.group(1))


def _normalize(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        key = value.casefold()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result
