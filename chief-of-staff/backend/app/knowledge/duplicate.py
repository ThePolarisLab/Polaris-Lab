import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.memory import MemoryEntry


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    memory: MemoryEntry
    score: float


def find_duplicate_memory(
    db: Session,
    details: str,
    *,
    threshold: float = 0.88,
    limit: int = 100,
) -> DuplicateMatch | None:
    """Return the closest existing memory when it is effectively the same."""

    candidate = normalize_memory_text(details)
    if not candidate:
        return None

    memories = (
        db.query(MemoryEntry)
        .order_by(MemoryEntry.created_at.desc())
        .limit(limit)
        .all()
    )

    best_match: DuplicateMatch | None = None

    for memory in memories:
        existing = normalize_memory_text(memory.details or memory.title)
        if not existing:
            continue

        if existing == candidate:
            return DuplicateMatch(memory=memory, score=1.0)

        score = SequenceMatcher(None, existing, candidate).ratio()
        if score >= threshold and (
            best_match is None or score > best_match.score
        ):
            best_match = DuplicateMatch(memory=memory, score=score)

    return best_match


def normalize_memory_text(text: str) -> str:
    """Normalize punctuation, spacing, and minor update words."""

    value = text.casefold()
    value = re.sub(
        r"\b(again|still|currently|now|today|already)\b",
        " ",
        value,
    )
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value
