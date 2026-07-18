---
inclusion: always
---

# Tech Stack & Commands

## Stack

- **Language:** Python ≥ 3.12 (backend). Frontend is Next.js 15 / React 19 / TypeScript / Tailwind (`ui/`).
- **API:** FastAPI, mounted under `/api/v1`. App factory: `api/app.py`.
- **Database:** PostgreSQL via SQLAlchemy (**async**). Migrations via Alembic.
- **Cache/queue:** Redis with **ARQ** for background tasks (`api/tasks/`).
- **Storage:** MinIO / S3-compatible (`api/services/filesystem/`, `api/services/storage.py`).
- **Voice runtime:** Pipecat pipeline (`api/services/pipecat/`) — STT → LLM → TTS.
- **Logging:** `loguru`. Never use `print()` in library/service code.
- **Config:** environment variables surfaced through `api/constants.py` and the configuration
  service. Do not scatter raw `os.getenv()` calls through business logic.

## Environment files

- `api/.env` — dev environment. Source it for diagnostics/scripts run against the dev DB.
- `api/.env.test` — test-only environment. **Always** source this for pytest so tests hit the
  test DB and never dev/prod credentials.
- `ui/.env` — frontend.

## Common commands

```bash
# Run the API locally (do NOT background this in a blocking shell — run in a terminal)
uvicorn api.app:app --reload --port 8000

# Tests (source the test env first so the test DB is used)
source venv/bin/activate && set -a && source api/.env.test && set +a && python -m pytest api/tests/...

# Diagnostics / one-off scripts against the dev DB
source venv/bin/activate && set -a && source api/.env && set +a && python -m api.services.admin_utils.local_exec

# Migrations
./scripts/makemigrate.sh "short description"   # create a migration
./scripts/migrate.sh                            # apply migrations
```

## Rules

- The virtual environment lives in the project folder (`venv/`). Activate it before running
  Python, tests, or scripts.
- Prefer async everywhere in the request/runtime path; do not block the event loop.
- Add dependencies deliberately (pin versions); prefer well-maintained packages already in use.
- Multi-worker gotcha: in-memory state changes only affect the worker that handled the request.
  To propagate cache/config changes across workers, use `WorkerSyncManager`
  (`api/services/worker_sync/`) — do not mutate local state and assume it is global.
