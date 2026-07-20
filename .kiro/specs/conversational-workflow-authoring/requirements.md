# Requirements Document — Conversational Workflow-Template Authoring

## Introduction

Today a user builds a Samvaad voice agent by hand-drawing a node/edge graph in the ReactFlow
editor, or by duplicating a pre-built template. This feature lets a user **author a reusable
workflow template from natural-language instructions or an uploaded specification document**,
driven from a chat surface. The user describes the agent ("greet the caller, verify their DOB,
book an appointment, otherwise transfer to a human") or uploads a document that lists the steps,
prompts, and tools; the system reasons about that intent, assembles a **validated** Samvaad
workflow graph, and saves it as a **workflow template** the user can then instantiate into a
runnable agent.

The feature is built **on the existing workflow engine primitives** (nodes, edges, extraction
variables, tools) and the existing MCP server — it does not fork the engine or introduce a bespoke
runtime. It reuses the same validation path (`ReactFlowDTO` + `WorkflowGraph`) that guards every
workflow, and the same template catalog (`WorkflowTemplates`) that the visual editor already
consumes. The generation intelligence is delegated to an LLM through one of two seams that already
exist in the repo: the **MCP client's LLM** (the chat window) or the **Model Proxy Service (MPS)**.

This document defines *what* the feature must do. The `design.md` defines *how*.

### What already exists (and is reused, not rebuilt)

- **Workflow schema & validation** — `ReactFlowDTO` (nodes + edges), per-type node data classes,
  `ExtractionVariableDTO`, and `WorkflowGraph` structural validation (`api/services/workflow/`).
- **MCP authoring surface** — `create_workflow(code)` / `save_workflow(workflow_id, code)` accept
  LLM-authored SDK TypeScript, parse it (`ts_bridge`), and validate it before persisting; discovery
  tools (`list_node_types`, `get_node_type`, `list_tools`, `list_documents`, `list_recordings`,
  `list_credentials`) expose the authoring catalog (`api/mcp_server/`).
- **NL→workflow via MPS** — `POST /workflow/create/template` calls `mps_service_key_client
  .call_workflow_api(call_type, use_case, activity_description)` and creates a *workflow*.
- **Template catalog & instantiation** — `WorkflowTemplates` + `WorkflowTemplateClient`;
  `POST /workflow/templates/duplicate` instantiates a template into a workflow; the switchboard
  enablement layer (`api/services/switchboard/enablement/`) shows the reference pattern for
  serializing a programmatically-built graph into `template_json` and reconciling tool references
  at instantiation.
- **Document ingestion** — `mps_service_key_client.process_document(...)` converts + chunks an
  uploaded file; storage via `storage_fs`.

### The gap this feature closes

1. Generation targets a **reusable, org-scoped template** (a `WorkflowTemplates` entry), not only a
   single throwaway workflow.
2. A **document-upload** authoring mode (spec doc → template), in addition to chat NL.
3. An **iterative, conversational** authoring loop (preview → refine → save) exposed over MCP.
4. **Tenant-safe** template storage and tool/document reference resolution.

## Glossary

- **Authoring Session**: A conversational interaction (over MCP or REST) in which a user builds or
  refines one workflow template.
- **Authoring Intent**: The normalized, structured description of the desired agent derived from
  the user's NL instructions and/or an uploaded document — the intermediate representation the
  generation step consumes. Not persisted long-term; it is the working input to the compiler.
- **Template Compiler**: The backend component that turns a candidate workflow definition
  (LLM-authored SDK code or an MPS-returned definition) into a **validated** `ReactFlowDTO` and,
  from it, `template_json`. It never persists an invalid graph.
- **Workflow Template**: A `WorkflowTemplates` catalog row whose `template_json` is a full
  `ReactFlow_Definition`. Instantiated into a runnable workflow via the existing duplicate path.
- **Logical Tool Reference**: A stable, name-based reference to a tool inside a template
  (e.g. `"patient_lookup"`), resolved to a concrete org-scoped `tool_uuid` at instantiation — the
  same pattern the switchboard template uses.
- **MCP Client**: The chat application (e.g. Claude Desktop, Cursor, or the Dograh chat UI) that
  connects to the Dograh MCP server; its LLM performs the reasoning.
- **MPS**: The external Model Proxy Service that already performs NL→workflow generation and
  document conversion. Its wire contracts are external and out of scope to define here.
- **Generation Seam**: The place the LLM reasoning happens — either the **MCP client's LLM**
  (client-driven) or **MPS** (backend-driven). The feature supports both; both converge on the same
  validation + persistence path.
- **Spec Document**: An uploaded file (PDF/DOCX/MD/TXT) describing an agent's steps, prompts, and
  tools that the user wants turned into a template.

## Requirements

### Requirement 1: MCP-driven conversational template authoring

**User Story:** As a builder using a chat client, I want to describe an agent in plain English and
have the backend produce a saved workflow template, so that I can build agents by conversation
instead of hand-drawing a graph.

#### Acceptance Criteria

1. THE system SHALL expose an MCP tool `create_workflow_template` that accepts an LLM-authored
   workflow definition (SDK TypeScript, as `create_workflow` already does), a `name`, and a
   `description`, and persists it as a `WorkflowTemplates` entry.
2. THE system SHALL reuse the existing authoring pipeline for that tool: parse (`ts_bridge`) →
   `ReactFlowDTO.model_validate` → `WorkflowGraph` validation, and SHALL NOT persist a template
   whose graph fails validation.
3. WHERE the MCP client's LLM needs the node catalog or the organization's tools/documents/
   recordings/credentials, THE system SHALL serve them through the existing discovery tools
   (`list_node_types`, `get_node_type`, `list_tools`, `list_documents`, `list_recordings`,
   `list_credentials`) — no new discovery surface is required.
4. WHEN `create_workflow_template` fails, THE system SHALL return a machine-readable `error_code`
   and a human-readable message (mirroring `create_workflow`'s error contract) so the client LLM
   can correct and resubmit the full definition.
5. THE `create_workflow_template` tool SHALL resolve the caller's organization from the MCP API key
   (as existing MCP tools do) and SHALL scope the created template to that organization.

### Requirement 2: Preview / dry-run before saving

**User Story:** As a builder, I want to validate and preview a generated template without saving
it, so that I can iterate conversationally until it is correct.

#### Acceptance Criteria

1. THE system SHALL expose an MCP tool `preview_workflow_template` that accepts a candidate
   workflow definition and runs the full validation pipeline WITHOUT persisting anything.
2. WHEN a preview succeeds, THE system SHALL return a structural summary: node count, edge count,
   the ordered list of node names/types, the set of required template variables
   (`WorkflowGraph.get_required_template_variables`), and the set of referenced logical tool names.
3. WHEN a preview fails validation, THE system SHALL return the same structured error list that
   `create_workflow_template` would return, without side effects.
4. THE preview tool SHALL be side-effect-free: it SHALL NOT write to the database, storage, or any
   external system.

### Requirement 3: Document-driven template authoring

**User Story:** As a builder, I want to upload a document that defines my agent's steps, prompts,
and tools and have it turned into a template, so that I can convert an existing runbook or design
doc into a working agent.

#### Acceptance Criteria

1. THE system SHALL accept a Spec Document upload (PDF, DOCX, Markdown, or plain text) scoped to the
   caller's organization, enforcing a maximum file size and an allowlist of MIME types.
2. THE system SHALL convert the uploaded document to text using the existing MPS document pipeline
   (`mps_service_key_client.process_document`) and SHALL make the extracted text available to the
   generation seam.
3. WHERE authoring is MCP-client-driven, THE system SHALL expose an MCP tool that returns the
   extracted, normalized text (and any structured outline) of a previously uploaded document so the
   client LLM can read it and author the template.
4. WHERE authoring is backend-driven, THE system SHALL pass the extracted document text to the
   generation seam (MPS) alongside any NL instructions.
5. THE system SHALL treat all extracted document content as **untrusted input**: it SHALL NOT
   execute instructions embedded in the document that attempt to change system behavior, exfiltrate
   data, or escalate permissions, and SHALL constrain the document's influence to *workflow
   authoring* only.
6. IF document conversion fails or yields empty text, THEN THE system SHALL return a clear error and
   SHALL NOT create a partial template.

### Requirement 4: Backend template generation core

**User Story:** As the platform, I want a single generation core that turns an Authoring Intent
into a validated workflow definition, so that both the chat and document paths converge on one
correct, testable component.

#### Acceptance Criteria

1. THE system SHALL provide a Template Compiler that accepts a candidate workflow definition (from
   the MCP client's SDK code, or from an MPS-returned definition) and produces a validated
   `ReactFlowDTO`.
2. THE Template Compiler SHALL be the single place that converts a validated `ReactFlowDTO` into
   `template_json` (via `dto.model_dump(mode="json")`), mirroring the switchboard serializer.
3. THE Template Compiler SHALL reject any definition that fails `ReactFlowDTO` schema validation or
   `WorkflowGraph` structural validation, returning the collected `WorkflowError`s.
4. THE Template Compiler SHALL be a pure, side-effect-free function of its input (no DB, storage, or
   network calls) so it is unit-testable independent of the LLM/MCP/MPS.
5. WHERE the backend-driven (MPS) path is used, THE system SHALL expose a REST endpoint that accepts
   NL instructions and/or a reference to an uploaded document, invokes MPS to synthesize a
   definition, compiles + validates it, and persists it as a template.

### Requirement 5: Graph-safety validation gate

**User Story:** As an operator, I want every generated template to satisfy the same invariants as a
hand-built workflow, so that generated agents are always runnable.

#### Acceptance Criteria

1. THE system SHALL validate every candidate definition against `ReactFlowDTO` (node/edge shape,
   referential integrity) before persistence.
2. THE system SHALL validate every candidate definition against `WorkflowGraph` (exactly one start
   node, at most one global node, per-type edge cardinality via `GraphConstraints`) before
   persistence.
3. IF a generated definition references a node type that is not in the node registry
   (`all_node_type_names`), THEN THE system SHALL reject it with a validation error.
4. THE system SHALL run node-data validation via the per-type node data models so unknown fields,
   missing required fields, and out-of-range option values are rejected.
5. THE system SHALL NOT persist a template that fails any validation step; the operation SHALL be
   all-or-nothing.

### Requirement 6: Tool, document, and credential reference resolution (tenant-safe)

**User Story:** As a security-conscious operator, I want a generated template to reference only
resources the caller's organization owns, so that authoring can never leak or attach another org's
resources.

#### Acceptance Criteria

1. WHERE a generated node references a tool, THE template SHALL store a **Logical Tool Reference**
   (stable name), and THE system SHALL resolve it to a concrete org-scoped `tool_uuid` at
   instantiation — mirroring the switchboard enablement pattern.
2. IF a generated definition references a `tool_uuid`, `document_uuid`, `recording_id`, or
   `credential_uuid` directly, THEN THE system SHALL verify each referenced resource belongs to the
   caller's organization and SHALL reject the definition if any does not.
3. WHERE the Spec Document defines a NEW tool (e.g. an HTTP endpoint), THE system MAY propose a tool
   specification, and THE system SHALL create it in the caller's organization's tool catalog only
   after explicit confirmation, validating the endpoint URL and never inlining secrets.
4. THE system SHALL NOT bake secret values (API keys, tokens) into `template_json`; secrets SHALL be
   referenced via credential references and masked using the existing masking utilities.
5. WHEN a template is instantiated, THE system SHALL reconcile every Logical Tool Reference to a
   concrete org tool, provisioning missing tools where a provisioning contract exists, and SHALL
   fail instantiation with a clear error when a required tool cannot be resolved.

### Requirement 7: Iterative refinement loop

**User Story:** As a builder, I want to refine a draft template over several chat turns, so that I
can add nodes, change prompts, and fix conditions incrementally.

#### Acceptance Criteria

1. THE system SHALL allow a candidate template to be re-previewed and re-submitted any number of
   times before it is saved.
2. WHEN the user asks to modify an already-saved template, THE system SHALL expose an MCP tool
   `update_workflow_template` that accepts a full replacement definition, validates it, and updates
   the existing template row (org-scoped).
3. THE refinement operations SHALL require the full corrected definition on each submission (no
   partial patches), consistent with the existing `create_workflow`/`save_workflow` contract.
4. WHEN a refinement fails validation, THE previously-saved template SHALL remain unchanged.

### Requirement 8: Instantiate a generated template into a runnable workflow

**User Story:** As a builder, once my template is saved, I want to turn it into a runnable workflow,
so that I can test and deploy the agent.

#### Acceptance Criteria

1. THE system SHALL allow a generated template to be instantiated into a workflow via the existing
   template-duplicate path (`POST /workflow/templates/duplicate`).
2. WHEN instantiating, THE system SHALL regenerate trigger UUIDs (as the existing path does) and
   SHALL reconcile Logical Tool References to concrete org tools.
3. WHERE the user requests it during authoring, THE system MAY both save the template AND
   instantiate a workflow in one step, returning both the template id and the workflow id.
4. THE instantiated workflow SHALL pass the same publish-time validation as any other workflow
   before it can be published.

### Requirement 9: Org-scoped template storage

**User Story:** As a multi-tenant platform, I want generated templates scoped to the organization
that created them, so that one org's generated templates are never visible to another.

#### Acceptance Criteria

1. THE system SHALL associate every generated template with the creating organization.
2. THE system SHALL distinguish **built-in/global** templates (e.g. the switchboard template, which
   has no owning org) from **org-owned** generated templates, and SHALL preserve existing built-in
   templates unchanged.
3. WHEN a user lists templates, THE system SHALL return the global built-in templates plus only the
   templates owned by the user's organization.
4. THE system SHALL reject read, update, or delete of a template that belongs to a different
   organization with a not-found response (no existence disclosure).

### Requirement 10: Limits, observability, and cost control

**User Story:** As an operator, I want generation bounded and observable, so that authoring cannot
run away on cost or produce silent failures.

#### Acceptance Criteria

1. THE system SHALL enforce a maximum candidate definition size (node/edge count and payload bytes)
   and reject definitions that exceed it with a clear error.
2. THE system SHALL emit a product analytics event when a template is generated, previewed, saved,
   or instantiated (reusing the existing analytics client), tagged with organization and source
   (`chat_mcp` | `document` | `mps_rest`).
3. THE system SHALL log validation failures with enough structure to diagnose which node/edge/field
   was rejected, without logging secret values.
4. WHERE the backend-driven MPS path is used, THE system SHALL apply request timeouts consistent
   with the existing MPS client and surface MPS errors without leaking internal detail.

### Requirement 11: Security & multi-tenant isolation (hard boundary)

**User Story:** As a security owner, I want authoring to honor tenant isolation and safe-input
handling as a hard boundary, so that the feature cannot be used to cross tenants or inject behavior.

#### Acceptance Criteria

1. THE system SHALL authenticate every authoring operation (MCP API key or REST session) and
   resolve `organization_id` from the authenticated principal, never from client-supplied body.
2. THE system SHALL validate every org-scoped reference (tools, documents, recordings, credentials,
   templates) against the caller's `organization_id` at the query level.
3. THE system SHALL treat NL instructions and document content as untrusted, and SHALL confine their
   effect to producing a workflow definition — never to changing authorization, accessing other
   tenants' data, or performing outbound requests not part of authoring.
4. THE system SHALL enforce upload constraints (size, MIME allowlist) and SHALL store uploaded
   documents under an organization-scoped storage key.
5. IF an authoring request would create a network-exposed capability (e.g. a webhook/HTTP tool),
   THEN THE system SHALL require explicit confirmation and SHALL validate the target before
   creating it.

### Requirement 12: Build on engine primitives (non-functional)

**User Story:** As a platform engineer, I want this feature to reuse the workflow engine and MCP
seams rather than fork them, so that generated templates stay compatible as the engine evolves.

#### Acceptance Criteria

1. THE feature SHALL represent generated agents strictly as `ReactFlowDTO` graphs using existing
   node types, edge fields, extraction variables, and tool references.
2. THE feature SHALL NOT add a new node type, edge field, or runtime behavior to the engine core to
   satisfy authoring; if any such change is genuinely required, it SHALL be raised as an explicit
   design change with schema-doc and node-spec updates.
3. THE feature SHALL reuse `WorkflowTemplates` for storage and the existing duplicate/instantiate
   path for turning templates into workflows.
4. THE feature SHALL keep pure decision logic (compilation, reference resolution, validation
   orchestration) in side-effect-free functions, wired into MCP tools / routes afterward, so it is
   unit- and property-testable independent of the LLM, MCP, and MPS.

## Out of scope (non-goals)

- Building a new in-repo chat LLM or replacing MPS as the generation backend. Generation
  intelligence stays in the MCP client's LLM or MPS.
- Changing the runtime execution path (Pipecat) or introducing a new execution engine.
- Replacing the visual ReactFlow editor; conversational authoring is additive.
- Defining MPS wire contracts (treated as external integration contracts, like the switchboard
  spec).
- Real-time collaborative editing of a template by multiple users.
