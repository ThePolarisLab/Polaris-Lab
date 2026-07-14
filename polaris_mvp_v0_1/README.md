# Polaris MVP v0.1

Polaris is a memory-first organizational intelligence platform for Builders.

This first vertical slice provides:

- persistent organizational memory
- decision journal
- daily briefing
- timeline retrieval
- FastAPI REST API
- SQLite persistence
- automated tests

## Architecture

```text
Builder
   |
FastAPI
   |
Application Services
   |
SQLite Repository
```

This release intentionally uses a modular monolith. The internal boundaries allow future extraction into services without introducing premature distributed-system complexity.

## Requirements

- Python 3.11 or newer

## Run locally

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Test

```bash
pytest
```

## Initial API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| POST | `/api/v1/memories` | Capture a memory |
| GET | `/api/v1/memories` | List/search memories |
| GET | `/api/v1/memories/{id}` | Retrieve a memory |
| POST | `/api/v1/decisions` | Record a decision |
| GET | `/api/v1/decisions` | List decisions |
| GET | `/api/v1/timeline` | Unified timeline |
| GET | `/api/v1/briefing/today` | Generate today's briefing |

## Status vocabulary

- **Implemented**: present and tested in this package
- **Approved**: accepted design, not necessarily implemented
- **Planned**: on the roadmap
- **Research**: under evaluation

## Foundation principle

> Polaris remembers so Builders can think.
