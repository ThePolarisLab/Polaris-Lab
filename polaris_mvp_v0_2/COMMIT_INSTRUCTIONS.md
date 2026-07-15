# GitHub Commit Instructions

1. Stop the running Polaris server.
2. Back up `polaris.db`.
3. Copy this release over the current project, preserving the existing `polaris.db`.
4. Activate Python 3.13 and run:

```powershell
python -m pip install -r requirements.txt
pytest
python scripts/migrate_memories_to_knowledge.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

5. Verify `/health`, `/api/v1/knowledge`, and `/api/v1/briefing/today` in Swagger.
6. In GitHub Desktop commit with:

```text
feat(knowledge): add structured knowledge objects and relationships
```

Description:

```text
- Add versioned Knowledge Objects
- Add knowledge classification and search
- Add evidence-bearing relationships
- Add idempotent memory migration
- Make Daily Briefing knowledge-aware
- Add tests and ADR-003
```
