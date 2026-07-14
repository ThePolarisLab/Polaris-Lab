from datetime import UTC, datetime

from app.core.database import initialize_database
from app.models.schemas import DecisionCreate, MemoryCreate, MemoryType
from app.repositories.decision_repository import DecisionRepository
from app.repositories.memory_repository import MemoryRepository


def main() -> None:
    initialize_database()

    memories = MemoryRepository()
    decisions = DecisionRepository()

    memories.create(
        MemoryCreate(
            title="Review supplier payments",
            content="Review the payment schedule before approving supplier transfers.",
            memory_type=MemoryType.OPERATIONAL,
            importance=5,
            occurred_at=datetime.now(UTC),
        )
    )

    decisions.create(
        DecisionCreate(
            title="Adopt modular monolith",
            decision="Build Polaris v0.1 as a modular monolith.",
            rationale="Minimize operational complexity while preserving boundaries.",
        )
    )

    print("Polaris seed data created.")


if __name__ == "__main__":
    main()
