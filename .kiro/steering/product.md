---
inclusion: always
---

# Product — Dograh (Samvaad) Voice AI Platform

Dograh is a voice AI platform for building and deploying conversational AI agents with
telephony and WebRTC support. Agents are authored as **workflows** — validated directed
graphs of conversation steps — and executed in real time over phone or browser.

## What the platform does

- Lets users build voice agents visually (ReactFlow node graph) or via API/SDK; the visual
  builder and the API both read/write the same `workflow_definition` (nodes + edges).
- Runs those workflows live through a Pipecat pipeline (STT → LLM → TTS) over multiple
  telephony providers, inbound and outbound.
- Supports campaigns (bulk outbound), knowledge bases (RAG), tools (HTTP + MCP), QA analysis,
  webhooks, and post-call processing.

## Who it serves

- **Multi-tenant SaaS.** The unit of isolation is the **organization**. Almost every resource
  (workflows, runs, phone numbers, campaigns, credentials) is organization-scoped. Treat
  tenant isolation as a hard security boundary — see `security-tenancy.md`.

## How to think about changes

- A new capability is almost always **built on the existing engine primitives** (nodes, edges,
  tools, extraction variables, integrations), not a new bespoke pipeline. Prefer configuring
  and extending documented seams over modifying the engine core.
- Customer-specific applications (e.g. the SpinSci switchboard PoC) live as their own package
  under `api/services/` and as workflow/tool configuration — not as edits to the shared engine.

## Authoritative references

- Repo conventions: `api/AGENTS.md` (and per-subtree `AGENTS.md` files). Steering here distills
  and complements those — when they conflict, the closest `AGENTS.md` to the code wins.
- Product docs: `docs/` (Mintlify). Feature specs: `.kiro/specs/<feature>/`.
