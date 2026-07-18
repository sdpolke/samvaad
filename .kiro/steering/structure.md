---
inclusion: always
---

# Project Structure & Layering

## Backend layout (`api/`)

```
api/
├── routes/         # HTTP endpoint handlers (thin), mounted under /api/v1
├── services/       # Domain logic, runtime systems, extension seams
├── db/             # SQLAlchemy models + data-access clients
├── schemas/        # Pydantic request/response types
├── tasks/          # ARQ background jobs and post-call work
├── mcp_server/     # MCP surface exposed by the backend
├── utils/          # Shared utilities
├── alembic/        # Migrations
└── tests/          # Test suite (mirrors the package layout)
```

## Layering rules (non-negotiable)

**routes → services → db.** Data flows one direction; do not skip or reverse layers.

- **Route handlers stay thin:** parse/validate the request, resolve auth + `organization_id`,
  delegate to a service, shape the response. No business logic, no SQL, no external clients,
  no `os.getenv()` in handlers.
- **Business logic lives in `services/`.** Litmus test: if a `task/`, the `mcp_server/`, or
  another route could reuse it, it belongs in a service so it is importable.
- **DB access lives in `db/` clients.** Routes call services; services call DB clients. Do not
  open sessions or write SQL from routes.

## Where does new code go?

| Code type | Home |
|---|---|
| Route handler / request parsing | `api/routes/<domain>.py` |
| Domain orchestration / business rules | `api/services/<domain>/` |
| SQL / DB session / model access | `api/db/<entity>_client.py`, `api/db/models.py` |
| Pydantic request/response | `api/schemas/` |
| Background / post-call work | `api/tasks/` |
| Workflow graph / node data | `api/services/workflow/` |
| Live pipeline runtime | `api/services/pipecat/` |
| Telephony (transfer/hangup/providers) | `api/services/telephony/` (+ `providers/`) |
| Third-party integration | `api/services/integrations/<name>/` (self-registering) |

- Extend the existing `services/<domain>/` that owns a concern before adding a focused new
  module. Never create catch-all "misc"/"helpers" dumping grounds.
- **New customer applications get their own service package** (e.g. `api/services/switchboard/`),
  keeping pure decision logic separate from graph-builders and connector tools.

## Extension seams — do not bleed into the core

- **Integrations self-register** via `register_package(...)`; discovery is automatic. Do NOT add
  integration node classes to `api/services/workflow/dto.py` — resolve them through the registry.
  Read `api/services/integrations/AGENTS.md` before touching this seam.
- **Telephony providers** resolve through the registry/factory; never instantiate a provider class
  directly from routes/tasks. Read `api/services/telephony/AGENTS.md`.

## Code quality

- One responsibility per file; split files that grow past ~300 lines.
- No dead/commented-out code; remove unused imports.
- Type hints on all function signatures; docstrings on public functions/classes.
- Use `logging.getLogger(__name__)`/`loguru` — never `print()`.
- Match existing style and libraries; do not introduce a new library for something already solved.
