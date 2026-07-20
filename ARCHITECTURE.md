# SpinSci Voice AI— Architecture Overview

SpinSci Voice AI is a multi-tenant voice AI platform for building and running conversational
agents over telephony and WebRTC. Agents are authored as **workflows** (validated
directed graphs of conversation steps) and executed in real time through a Pipecat
pipeline (STT → LLM → TTS).

The unit of tenant isolation is the **organization**; nearly every resource
(workflows, runs, phone numbers, campaigns, credentials) is organization-scoped.

---

## System Topology

```
                    ┌─────────────────────────┐
                    │  Next.js UI (ui/)        │
                    │  React 19 / TS / Tailwind│
                    └───────────┬─────────────┘
                                │  /api/* proxy (rewrites)
                                ▼
┌───────────────────────────────────────────────────────────┐
│  FastAPI backend (api/)  —  mounted under /api/v1           │
│                                                             │
│  routes/ ──► services/ ──► db/   (one-directional layering) │
│                                                             │
│  ├─ Pipecat voice runtime (STT → LLM → TTS)                 │
│  ├─ ARQ background workers (tasks/)                         │
│  ├─ MCP server (/api/v1/mcp)                                │
│  └─ WorkerSyncManager (cross-worker cache/config sync)      │
└───────┬───────────────┬───────────────┬───────────────┬────┘
        │               │               │               │
        ▼               ▼               ▼               ▼
   PostgreSQL         Redis          MinIO / S3     Telephony
   (+ pgvector)     (cache/ARQ)     (audio/files)   (Twilio, …)
```

---

## Backend (`api/`)

### Language & Runtime
- **Python ≥ 3.12**
- **Async-first** across the request and voice-runtime paths — do not block the event loop.

### Layering (non-negotiable)
`routes → services → db`. Data flows one direction only.
- `routes/` — thin HTTP handlers: parse/validate, resolve auth + `organization_id`, delegate, shape response.
- `services/` — domain logic and runtime systems (reusable by tasks, MCP, other routes).
- `db/` — SQLAlchemy models and data-access clients (all SQL/session handling).
- `schemas/` — Pydantic request/response types.
- `tasks/` — ARQ background jobs and post-call work.
- `mcp_server/` — MCP surface exposed to agents.

### Service subsystems (`api/services/`)
| Package | Responsibility |
|---|---|
| `pipecat/` | Live voice pipeline runtime (STT → LLM → TTS), tracing config |
| `workflow/` | Workflow graph / node + edge definitions and execution |
| `telephony/` | Call transfer/hangup + provider registry (`providers/`) |
| `integrations/` | Self-registering third-party integrations |
| `campaign/` | Bulk outbound campaigns |
| `switchboard/` | Customer-specific application package (SpinSci PoC) |
| `auth/` | Authentication / org resolution |
| `configuration/` | Env/config surfaced through the config service |
| `worker_sync/` | Cross-worker propagation via `WorkerSyncManager` |
| `filesystem/`, `storage.py` | MinIO / S3-compatible object storage |
| `gen_ai/`, `smart_turn/`, `gender/` | AI helpers (generation, turn detection, etc.) |
| `pricing/`, `quota_service.py` | Usage metering and quotas |
| `reports/`, `callbacks/` | QA/analytics reporting and callback handling |

### Critical backend packages (`api/requirements.txt`)
| Package | Version | Role |
|---|---|---|
| `fastapi` | 0.135.3 | Web framework / API layer |
| `uvicorn` | 0.35.0 | ASGI server |
| `sqlalchemy[asyncio]` | 2.0.43 | Async ORM |
| `asyncpg` | 0.30.0 | Async PostgreSQL driver |
| `alembic` | 1.16.5 | DB migrations (+ `alembic-postgresql-enum`) |
| `pgvector` | 0.4.2 | Vector columns for RAG / knowledge bases |
| `redis` | 5.3.1 | Cache + queue backend |
| `arq` | 0.26.3 | Redis-based background task queue |
| `aioboto3` | 15.1.0 | Async AWS/S3 client |
| `minio` | 7.2.16 | S3-compatible object storage client |
| `twilio` | 9.8.0 | Telephony provider SDK |
| `fastmcp` | 3.2.4 | MCP server implementation |
| `tuner-pipecat-sdk` | 0.2.0 | Pipecat tuning SDK |
| `langfuse` | 3.9.3 | LLM observability / tracing |
| `sentry-sdk[fastapi]` | 2.38.0 | Error monitoring |
| `posthog` | 7.11.1 | Product analytics |
| `bcrypt` / `PyNaCl` | 5.0.0 / 1.6.2 | Password hashing / crypto |
| `msgpack` | 1.1.2 | Compact serialization |
| `python-multipart` | 0.0.27 | Multipart/form parsing |
| `email-validator` | 2.3.0 | Email validation |

Dev tooling (`requirements.dev.txt`): `mypy`, `watchfiles`, `datamodel-code-generator`,
`twine`, and the editable Python SDK (`./sdk/python`).

### Voice runtime — Pipecat (vendored in `pipecat/`)
The Pipecat framework (`pipecat-ai`) is vendored in-repo and powers the real-time
STT → LLM → TTS pipeline. Core deps include `openai`, `pydantic`, `numpy`, `aiohttp`,
`transformers`, and `onnxruntime`. Optional provider extras cover a broad set of
STT/LLM/TTS and transport vendors, e.g.:
- **LLM:** OpenAI, Anthropic, Google (Gemini), Groq, Mistral, AWS Nova Sonic
- **STT/TTS:** Deepgram, Cartesia, ElevenLabs, Azure, Google, AssemblyAI, Rime, Sarvam
- **Transports:** Daily, LiveKit, WebRTC (`aiortc`), WebSockets
- **Tracing:** OpenTelemetry SDK

### Data & Infrastructure
- **PostgreSQL** (async via SQLAlchemy + `asyncpg`), with **pgvector** for embeddings.
- **Redis** for caching and the ARQ task queue.
- **MinIO / S3** for audio and file storage.
- **Alembic** for schema migrations (`./scripts/makemigrate.sh`, `./scripts/migrate.sh`).
- **loguru** for logging (never `print()` in service/library code).
- **MCP server** mounted at `/api/v1/mcp` (Streamable HTTP, same `X-API-Key` auth as REST).
- **WorkerSyncManager** propagates cache/config changes across workers (multi-worker safe).

---

## Frontend (`ui/`)

### Language & Framework
- **Next.js 15** (App Router, `output: standalone`, Turbopack dev)
- **React 19** + **TypeScript 5**
- **Tailwind CSS v4** (via `@tailwindcss/postcss`)

### Critical frontend packages (`ui/package.json`)
| Package | Role |
|---|---|
| `next` (^15.3.3) / `react` (^19.1.0) | Framework + UI runtime |
| `@xyflow/react` (^12.10.2) | ReactFlow node graph — visual workflow builder |
| `@dagrejs/dagre` | Auto-layout for workflow graphs |
| `zustand` (^5.0.8) + `zundo` | Client state management + undo/redo |
| `@radix-ui/*` | Accessible UI primitives (dialog, select, tabs, etc.) |
| `shadcn-ui` + `class-variance-authority` + `tailwind-merge` + `clsx` | Component system / styling utilities |
| `lucide-react` | Icon set |
| `react-hook-form` | Form state and validation |
| `recharts` | Charts / analytics visualizations |
| `@stackframe/stack` | Authentication (Stack Auth) |
| `@sentry/nextjs` | Error monitoring + source maps |
| `posthog-js` / `posthog-node` | Product analytics |
| `pino` / `pino-pretty` | Structured logging |
| `sonner` | Toast notifications |
| `next-themes` | Theme (dark/light) support |
| `date-fns`, `react-day-picker`, `react-timezone-select`, `react-international-phone` | Date/time, scheduling, and phone-number inputs |

### Frontend structure (`ui/src/`)
- `app/` — Next.js App Router pages and API routes
- `components/` — UI components (incl. workflow builder)
- `client/` — generated API client (`@hey-api/openapi-ts` from backend OpenAPI)
- `context/`, `hooks/`, `lib/`, `constants/`, `types/` — shared state, utilities, and types
- `middleware.ts` — request middleware (auth/routing)

### Frontend ↔ Backend integration
- API calls proxy to the backend via Next.js `rewrites` (`/api/* → BACKEND_URL`),
  excluding `config`/`auth` paths and PostHog `/ingest` routes.
- The typed client is generated from the backend OpenAPI spec via
  `@hey-api/openapi-ts` (`npm run generate-client`, config in `openapi-ts.config.ts`).

### Frontend dev tooling
- **Vitest** + **Testing Library** + **jsdom** for tests
- **ESLint 9** (`eslint-config-next`, import-sort, unused-imports)
- **TypeScript** strict typing; `@hey-api/openapi-ts` for client generation

---

## Cross-Cutting Concerns

- **Multi-tenancy:** organization is a hard security boundary. All org-scoped reads/writes
  must filter/validate by `organization_id`; referenced foreign keys are re-fetched with the
  caller's org before use.
- **Observability:** Sentry (frontend + backend), PostHog analytics, Langfuse LLM tracing,
  OpenTelemetry in the Pipecat runtime.
- **Config & secrets:** surfaced through `api/constants.py` and the configuration service;
  secrets come from env/config or the credentials service, never hardcoded or logged.
- **Extension seams:** integrations self-register via `register_package(...)`; telephony
  providers resolve through a registry/factory — neither is instantiated directly from routes.

---

## Deployment

- **Docker Compose:** `docker-compose.yaml` (production/OSS) and
  `docker-compose-local.yaml` (local services).
- **nginx** reverse proxy (`nginx/`); backend and MCP both routed under `/api/v1`.
- Backend and UI each ship a `Dockerfile`; the UI builds as a standalone Next.js output.
```
