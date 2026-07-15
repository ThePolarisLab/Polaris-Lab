import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from app.core.config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 title TEXT NOT NULL,
 content TEXT NOT NULL,
 memory_type TEXT NOT NULL,
 source TEXT NOT NULL,
 importance INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
 occurred_at TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 title TEXT NOT NULL,
 decision TEXT NOT NULL,
 rationale TEXT NOT NULL,
 status TEXT NOT NULL,
 decided_at TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 title TEXT NOT NULL,
 content TEXT NOT NULL,
 knowledge_type TEXT NOT NULL,
 author TEXT NOT NULL,
 organization TEXT,
 importance INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
 confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
 truth_status TEXT NOT NULL DEFAULT 'asserted',
 source TEXT NOT NULL,
 source_memory_id INTEGER UNIQUE,
 version INTEGER NOT NULL DEFAULT 1,
 visibility TEXT NOT NULL DEFAULT 'private',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(source_memory_id) REFERENCES memories(id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge(knowledge_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_importance ON knowledge(importance DESC);
CREATE TABLE IF NOT EXISTS knowledge_relationships (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source_knowledge_id INTEGER NOT NULL,
 target_knowledge_id INTEGER NOT NULL,
 relationship_type TEXT NOT NULL,
 evidence TEXT,
 confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
 created_at TEXT NOT NULL,
 UNIQUE(source_knowledge_id, target_knowledge_id, relationship_type),
 FOREIGN KEY(source_knowledge_id) REFERENCES knowledge(id),
 FOREIGN KEY(target_knowledge_id) REFERENCES knowledge(id)
);
"""

@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection=sqlite3.connect(DATABASE_PATH)
    connection.row_factory=sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback(); raise
    finally:
        connection.close()

def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.executescript(SCHEMA)
