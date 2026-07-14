from datetime import UTC, datetime

from app.core.database import get_connection
from app.models.schemas import DecisionCreate, DecisionRead


class DecisionRepository:
    def create(self, item: DecisionCreate) -> DecisionRead:
        created_at = datetime.now(UTC)
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO decisions
                (title, decision, rationale, status, decided_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.title,
                    item.decision,
                    item.rationale,
                    item.status.value,
                    item.decided_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
            decision_id = int(cursor.lastrowid)
        return self.get(decision_id)

    def get(self, decision_id: int) -> DecisionRead:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM decisions WHERE id = ?", (decision_id,)
            ).fetchone()
        if row is None:
            raise KeyError(decision_id)
        return self._to_model(row)

    def list(self, limit: int = 100) -> list[DecisionRead]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM decisions
                ORDER BY decided_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._to_model(row) for row in rows]

    def count(self) -> int:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM decisions"
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def _to_model(row) -> DecisionRead:
        return DecisionRead(
            id=row["id"],
            title=row["title"],
            decision=row["decision"],
            rationale=row["rationale"],
            status=row["status"],
            decided_at=datetime.fromisoformat(row["decided_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
