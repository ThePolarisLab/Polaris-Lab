# ARC-001 — Polaris System Overview

**Status:** Baseline in progress  
**Repository:** `ThePolarisLab/Polaris-Lab`  
**Primary application:** `chief-of-staff`

## 1. Current system

Polaris is currently implemented as a full-stack Chief of Staff application with:

- a FastAPI backend;
- a React/Vite frontend;
- a SQLite database accessed through SQLAlchemy;
- modular backend packages for memory, knowledge relationships, reasoning, missions, dashboard aggregation, team notes, work context, and GitHub operations;
- direct integration with the GitHub REST API through the Polaris GitHub Engine.

## 2. Verified runtime architecture

```text
React/Vite frontend
        |
        | HTTP/JSON
        v
FastAPI application
        |
        +--> API routers
        |       |
        |       +--> domain services / engines
        |       |
        |       +--> SQLAlchemy sessions
        |
        +--> SQLite database (polaris.db)
        |
        +--> GitHub REST API through GitHubClient
```

## 3. Backend entry point

The backend application is assembled in:

```text
chief-of-staff/backend/app/main.py
```

The current FastAPI application identifies itself as `Polaris Chief of Staff API`, version `0.3`.

Verified router registrations include:

- chat;
- company;
- truck;
- memory;
- missions;
- knowledge relationships;
- memory search;
- reasoning;
- team notes;
- executive dashboard;
- GitHub Engine;
- work context.

## 4. Data layer

The database configuration currently uses:

```text
sqlite:///./polaris.db
```

SQLAlchemy provides the engine, session factory, and declarative base. Database tables are created at application startup through `Base.metadata.create_all(bind=engine)`.

## 5. Frontend

The frontend is a Vite-powered React application. Its current root component renders the Executive Dashboard.

The dashboard currently:

- loads executive dashboard data from the backend;
- shows business status, priorities, carry-forward items, upcoming items, and watch items;
- allows the Builder to create a Team Note action;
- refreshes dashboard data after a successful action is saved.

## 6. GitHub Engine

PGE-001 is implemented inside the backend as:

```text
chief-of-staff/backend/app/github_engine/
```

The API adapter is:

```text
chief-of-staff/backend/app/api/github_engine.py
```

Current capabilities include:

- repository status and metadata retrieval;
- branch listing;
- protected branch creation through an explicit write gate;
- file writing;
- draft pull-request creation.

Security controls currently include:

- token supplied through environment configuration;
- repository allowlisting;
- writes disabled by default;
- unsafe parent-path rejection;
- pull requests preferred over direct changes to `main`.

## 7. Architectural interpretation

The repository currently follows an emerging modular-monolith pattern:

- one deployable FastAPI backend;
- one React frontend;
- domain-oriented Python packages inside the backend;
- shared database and API process;
- external integrations isolated behind clients where implemented.

This is a description of the current state, not a recommendation to split the system into microservices.

## 8. Target architectural direction

The proposed direction is to retain the modular monolith while strengthening boundaries between:

1. **Application/API layer** — HTTP routing, request validation, response serialization.
2. **Domain and intelligence layer** — memory, relationships, reasoning, missions, dashboard synthesis, work context.
3. **Engineering layer** — GitHub operations and repository intelligence.
4. **Persistence layer** — SQLAlchemy models, sessions, and repositories.
5. **Presentation layer** — React components and future frontend services/hooks.

## 9. ARC-001 limitations

This baseline records components verified during the first repository inspection. Further ARC-001 work should expand the endpoint inventory, model relationships, test coverage, and full dependency map before PGE-002 implementation begins.
