# ARC-001 — Verified Repository Map

## Primary application

```text
chief-of-staff/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── database/
│   │   ├── dashboard/
│   │   ├── github_engine/
│   │   ├── missions/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── main.py
│   ├── tests/
│   └── .env.github.example
└── frontend/
    ├── src/
    │   ├── components/
    │   └── App.jsx
    └── package.json
```

This map includes only paths verified from repository files and commit history during the first ARC-001 inspection.

## Backend application assembly

`app/main.py` imports database models and registers the current routers. Verified model/domain references include:

- `Company`
- `Truck`
- `MemoryEntry`
- `KnowledgeRelationship`
- `Mission`
- `MissionTask`
- `Workflow`
- `TeamNote`

Verified API modules include:

- `app/api/chat.py`
- `app/api/company.py`
- `app/api/truck.py`
- `app/api/memory.py`
- `app/api/missions.py`
- `app/api/relationships.py`
- `app/api/memory_search.py`
- `app/api/reasoning.py`
- `app/api/team_notes.py`
- `app/api/dashboard.py`
- `app/api/github_engine.py`
- `app/api/work_context.py`

## Confirmed service and engine packages

### Dashboard

```text
app/dashboard/service.py
app/schemas/dashboard.py
app/api/dashboard.py
```

The API router delegates executive-dashboard construction to `build_executive_dashboard` and serializes domain results into response schemas.

### GitHub Engine — PGE-001

```text
app/github_engine/__init__.py
app/github_engine/client.py
app/github_engine/schemas.py
app/api/github_engine.py
```

The client owns GitHub HTTP communication and write safeguards. The API module exposes the engine through FastAPI.

### Missions

```text
app/missions/models.py
app/api/missions.py
```

The application entry point confirms the presence of Mission, MissionTask, and Workflow models.

## Persistence

```text
app/database/database.py
```

Current persistence is a shared SQLite database using SQLAlchemy.

## Frontend

```text
frontend/src/App.jsx
frontend/src/components/ExecutiveDashboard.jsx
frontend/src/components/ExecutiveDashboard.css
```

The current application root directly renders `ExecutiveDashboard`. API access is currently performed inside the dashboard component through `fetch` calls to a hard-coded local backend base URL.

## Tests

PGE-001 introduced tests under:

```text
chief-of-staff/backend/tests/
```

Verified GitHub Engine tests cover:

- write operations disabled by default;
- repository allowlist enforcement.

A complete test inventory remains an ARC-001 follow-up item.

## Documentation and governance

Existing GitHub Engine work introduced a decision document describing Builder authority, GitHub as source of truth, secret handling, safe write defaults, and pull-request preference.

ARC-001 adds the living architecture area under:

```text
docs/architecture/
```

## PGE-002 placement

Repository Intelligence should extend the existing GitHub Engine rather than create an unrelated top-level application.

Recommended placement:

```text
chief-of-staff/backend/app/github_engine/
├── client.py
├── schemas.py
└── repository_intelligence.py
```

API additions should remain in `app/api/github_engine.py` unless the router becomes large enough to justify a dedicated `repository_intelligence` API module while preserving the same `/api/v1/github` boundary.
