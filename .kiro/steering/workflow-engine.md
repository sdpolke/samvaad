---
inclusion: fileMatch
fileMatchPattern: 'api/services/{workflow,switchboard,pipecat,telephony}/**'
---

# Workflow Engine — Authoring on the Graph

A workflow is a **validated directed graph** of nodes and edges (`api/services/workflow/`),
executed live by the Pipecat engine (`api/services/pipecat/`). Build features **on these
primitives**; do not fork the engine for a single application.

## Nodes (`workflow/dto.py`, `node_data.py`, `node_specs/`)

| Type | Purpose |
|---|---|
| `startCall` | Inbound/telephony entry; optional greeting; `pre_call_fetch_*` runs before the first turn |
| `trigger` | API-triggered (non-telephony) entry point |
| `agentNode` | LLM conversation step (most mid-call logic) |
| `endCall` | Terminal node; extraction may run before hangup |
| `globalNode` | Persona/tone/rules prepended to prompted nodes with `add_global_prompt=true` (≤1 per graph) |
| `webhook` | Fire an HTTP request after completion |
| `qa` | Post-call quality analysis |

Shared node fields: `name`, `prompt`, `allow_interrupt`, `add_global_prompt`,
`extraction_enabled`/`extraction_prompt`/`extraction_variables`, `tool_uuids`, `document_uuids`.

## Edges (`EdgeDataDTO`)

- `condition` — natural-language condition the LLM evaluates to fire the transition.
- `transition_speech` — optional line spoken **on** the transition. **Empty = a silent turn.**
- Model deterministic transitions as edge conditions; model verbatim spoken lines as
  `transition_speech` (or as a node's mandated prompt output).

## State: extraction / gathered-context variables

- Per-call state is carried as extraction/gathered-context variables (`ExtractionVariableDTO`,
  types `string`/`number`/`boolean`), threaded across edges and referenced in prompts/speech via
  `{{template_variables}}`.
- Guard collection nodes on the variable so a fact is never re-asked once populated.

## Tools

- Backend capabilities are workflow tools (custom HTTP tools via `ToolModel`, or MCP tools),
  attached per-node through `tool_uuids`.
- **Per-node tool scoping is a control mechanism:** a node can only invoke the tools it lists, so
  scoping (e.g. transfer only on routing nodes) enforces gates structurally rather than by prompt.

## Validation (`WorkflowGraph`)

`WorkflowGraph` enforces graph invariants at build time: exactly one start/entry node, ≤1 global
node, per-type edge cardinality (`GraphConstraints`), and referential integrity. Any graph you
assemble must pass this. Add a smoke test that constructs and validates the graph.

## Adding capabilities the right way

- Prefer new nodes/edges/tools/extraction variables over new engine behavior.
- If an integration node is needed, use the self-registering integration seam
  (`services/integrations/`) — never edit `workflow/dto.py` for it.
- Telephony transfer/hangup must go through the telephony providers
  (`api/services/telephony/`), resolved via the registry/factory — not instantiated directly.
- Keep pure decision logic (schedule evaluation, reducers, classifiers, formatters, gate
  decisions) in plain, side-effect-free functions so they are unit- and property-testable
  independent of the LLM/TTS/telephony. Wire those functions into nodes/tools afterward.
- If you genuinely must change the engine core (new node type, new edge field, new built-in),
  update `docs/developer/workflow-schema.mdx` and the relevant node spec in the same change.
