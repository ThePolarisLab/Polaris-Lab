from datetime import UTC, datetime

from app.core.database import get_connection
from app.models.schemas import MemoryCreate, MemoryRead


class MemoryRepository:
    def create(self, item: MemoryCreate) -> MemoryRead:
        created_at = datetime.now(UTC)
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories
                (title, content, memory_type, source, importance, occurred_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.title,
                    item.content,
                    item.memory_type.value,
                    item.source,
                    item.importance,
                    item.occurred_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
            memory_id = int(cursor.lastrowid)

        return self.get(memory_id)

    def get(self, memory_id: int) -> MemoryRead:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        if row is None:
            raise KeyError(memory_id)
        return self._to_model(row)

    def list(self, query: str | None = None, limit: int = 100) -> list[MemoryRead]:
        sql = "SELECT * FROM memories"
        parameters: list[object] = []
        if query:
            sql += " WHERE title LIKE ? OR content LIKE ?"
            term = f"%{query}%"
            parameters.extend([term, term])
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        parameters.append(limit)

        with get_connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [self._to_model(row) for row in rows]

    def count(self) -> int:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM memories"
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def _to_model(row) -> MemoryRead:
        return MemoryRead(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            memory_type=row["memory_type"],
            source=row["source"],
            importance=row["importance"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
