# Polaris MVP v0.2 — Knowledge Engine

Polaris v0.2 extends the working memory-first MVP with structured knowledge and first-class relationships.

## Implemented

- Existing memory and decision APIs
- Structured Knowledge Objects
- Knowledge classification by meaning
- Knowledge search and retrieval
- First-class relationships between Knowledge Objects
- Idempotent migration of existing memories into knowledge
- Knowledge-aware daily briefing
- Automated tests

## Supported Python

Python 3.13 is the supported development version for this release.

## Run

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/docs`.

## Preserve existing memories

After copying this release over v0.1, run:

```powershell
python scripts/migrate_memories_to_knowledge.py
```

The migration is safe to run more than once. Existing memories remain in the memory table and are linked through `source_memory_id`.

## Foundation principle

> Every Builder matters.

> Dedicated to every Builder whose wisdom deserved to outlive them.
