# Implementation Plan — Conversational Workflow-Template Authoring

Incremental, test-first tasks. Each task is small, verifiable, and builds on the previous one.
Every code task sources `api/.env.test` for tests and validates against the test DB per project
conventions. Requirement references map to `requirements.md`.

Recommended order: build the **pure compiler + reference core first** (no I/O, fully testable),
then storage, then the MCP tools, then documents, then the REST/MPS path, then instantiation, then
end-to-end.

---

## Phase 1 — Pure core (no I/O)

- [ ] 1.1 Create `api/services/workflow_authoring/errors.py` with `AuthoringError(error_code,
      message, errors=None)` and the `error_code` taxonomy string constants (`parse_error`,
      `validation_error`, `schema_validation`, `graph_validation`, `reference_error`, `too_large`,
      `missing_name`, `trigger_path_conflict`, `bridge_error`). _(Req 1.4, 5)_
  - Unit test: each constant exists; `AuthoringError` serializes to `{error_code, error, errors?}`.

- [ ] 1.2 Create `api/services/workflow_authoring/compiler.py` with `CompiledTemplate` dataclass and
      `TemplateCompiler.compile_definition(definition: dict) -> CompiledTemplate`. Pure: sanitize →
      `ReactFlowDTO.model_validate` → `WorkflowGraph` → collect `required_variables` +
      `logical_tool_refs`; raise `AuthoringError` per stage. No I/O. _(Req 4.1–4.4, 5)_
  - Unit tests (TDD): valid graph compiles; missing/duplicate start node, >1 global node, dangling
    edge, unknown node type, unknown field, out-of-range option → correct `error_code`.
  - Property test: any accepted definition re-validates under a fresh `WorkflowGraph`;
    `required_variables` equals `WorkflowGraph.get_required_template_variables()`.

- [ ] 1.3 Add `TemplateCompiler.compile_code(code: str)` that wraps `ts_bridge.parse_code` then
      delegates to `compile_definition`, mapping parse/validation stages to `error_code`s (mirror
      `create_workflow`). Keep `ts_bridge` the only TS entry point. _(Req 1.2, 4.1)_
  - Unit test with a small SDK snippet fixture (reuse an existing `create_workflow` test fixture).

- [ ] 1.4 Add size/limits guard in the compiler (max nodes, max edges, max payload bytes) raising
      `too_large`. Bounds defined as module constants. _(Req 10.1)_
  - Unit test: over-limit definition rejected; at-limit accepted.

## Phase 2 — Reference resolution (org-scoped)

- [ ] 2.1 Create `api/services/workflow_authoring/references.py`:
      `extract_references(definition) -> {tool_uuids, document_uuids, recording_ids,
      credential_uuids, logical_tool_names}`. Pure. _(Req 6.1, 6.2)_
  - Unit test over a definition with mixed direct-uuid and logical-name tool refs.

- [ ] 2.2 Add `validate_org_ownership(definition, organization_id, db_client) -> list[WorkflowError]`
      that rejects any direct uuid not owned by the org (query-level checks against tools/documents/
      recordings/credentials clients). _(Req 6.2, 11.2)_
  - Unit test with a fake db_client: cross-tenant uuid → error; same-org → clean.

- [ ] 2.3 Add `reconcile_tool_refs(template_json, organization_id, db_client) -> dict` mapping
      logical tool names to concrete org `tool_uuid`s; provision where a contract exists; itemized
      error when unresolved. Model on the switchboard enablement instantiator. _(Req 6.5, 8.2)_
  - Unit test: existing tool resolves; missing tool with no provisioning → clear error.

## Phase 3 — Org-scoped template storage

- [ ] 3.1 Add `organization_id` (nullable, FK, `ondelete=CASCADE`), `source`, `created_by` columns
      and `ix_workflow_templates_org_id` index to `WorkflowTemplates` in `api/db/models.py`. _(Req 9)_

- [ ] 3.2 Create the additive Alembic migration (down_revision = current head) adding the three
      columns + index, with a reversible `downgrade()`. Existing rows default `organization_id
      = NULL` (built-in/global). **Flag as schema change; confirm before applying to shared DBs.**
      _(Req 9.2)_
  - Verify: `alembic heads` single head; migration imports; apply to dev DB and confirm columns.

- [ ] 3.3 Extend `WorkflowTemplateClient` with org-scoped ops: `create_org_template(name,
      description, template_json, organization_id, source, created_by)`; `list_templates_for_org
      (organization_id)` returning `organization_id IS NULL OR = org`; `get_org_template(id, org)`
      and `update_org_template(id, org, ...)` returning `None`/raising for other orgs; keep the
      existing global name-lookup used by the switchboard registrar (filter `organization_id IS
      NULL`). _(Req 9.1, 9.3, 9.4)_
  - Unit tests: listing returns global + own org only; cross-org get/update → not found.

## Phase 4 — MCP authoring tools

- [ ] 4.1 Create `api/mcp_server/tools/template_authoring.py` with `preview_workflow_template(code)`
      — authenticate, `compile_code`, return summary (node/edge counts, node names/types,
      `required_variables`, `logical_tool_refs`) or structured errors. Side-effect-free. Wrap with
      `traced_tool`. _(Req 2)_
  - Test: valid code → summary; invalid → errors; asserts no DB write.

- [ ] 4.2 Add `create_workflow_template(code, name, description)` — compile, `validate_org_ownership`,
      persist via `create_org_template(source="chat_mcp")`, emit analytics. Error contract mirrors
      `create_workflow`. _(Req 1, 6.2, 10.2)_
  - Test: persists org-scoped; missing name → `missing_name`; cross-tenant ref → `reference_error`.

- [ ] 4.3 Add `update_workflow_template(template_id, code)` — full-replace an org-owned template;
      404 semantics for other orgs; unchanged on validation failure. _(Req 7.2, 7.4, 9.4)_
  - Test: update own; other-org id → not found; invalid code leaves row unchanged.

- [ ] 4.4 Register the three tools in `api/mcp_server/server.py`. Document every `error_code` in each
      tool docstring and add/extend the instructions-drift test that keeps docstrings in sync.
      _(Req 1.4)_

## Phase 5 — Document-driven authoring

- [ ] 5.1 Add a spec-document model or reuse `KnowledgeBaseDocumentModel` scoped by a `source`
      marker (decision: prefer a lightweight dedicated table `spec_documents` with org scoping +
      extracted text + status to avoid polluting the KB retrieval catalog). Migration additive.
      _(Req 3.1)_

- [ ] 5.2 Create `api/services/workflow_authoring/document_intake.py`: given an uploaded file,
      store under `spec-documents/{org_id}/{uuid}_{name}`, call
      `mps_service_key_client.process_document`, persist extracted text + status. Enforce size + MIME
      allowlist. Conversion failure → status=failed, no partial template. _(Req 3.1, 3.2, 3.6, 11.4)_
  - Test with `NullFileSystem` + faked MPS client: MIME/size rejection; success stores text; failure
    marks failed.

- [ ] 5.3 Add REST upload route `POST /workflow/spec-documents/upload` (presigned-URL variant like
      ambient-noise, or direct multipart), org-scoped via `get_user`. Returns `spec_document_id`.
      _(Req 3.1, 11.1, 11.4)_

- [ ] 5.4 Create `api/mcp_server/tools/spec_documents.py`: `list_spec_documents()` and
      `read_spec_document(spec_document_id)` returning extracted text/outline for the client LLM;
      org-scoped; register in `server.py`. _(Req 3.3)_
  - Test: read returns text; other-org id → not found.

## Phase 6 — Backend/MPS generation path

- [ ] 6.1 Add `POST /workflow/template/generate` in `api/routes/workflow.py`: body `{instructions?,
      spec_document_id?, call_type}`; resolve org via `get_user`; fetch document text if provided;
      call `mps_service_key_client.call_workflow_api(...)`; `compile_definition`; persist via
      `create_org_template(source="mps_rest")`. Apply MPS timeouts; surface errors safely. _(Req 4.5,
      3.4, 10.4)_
  - Test with faked MPS returning a valid/invalid definition → template created / 422.

## Phase 7 — Instantiation

- [ ] 7.1 Extend the generated-template branch of `POST /workflow/templates/duplicate` to run
      `reconcile_tool_refs` before `create_workflow`, then regenerate trigger UUIDs + sync triggers
      as today. Leave the switchboard branch untouched. Support optional "save + instantiate" return
      shape `{template_id, workflow_id}`. _(Req 8.1–8.3)_
  - Test: instantiated workflow passes publish-time validation; unresolved tool → clear error.

## Phase 8 — Listing, analytics, end-to-end

- [ ] 8.1 Filter `GET /workflow/templates` to global + caller-org templates. _(Req 9.3)_
  - Test: only global + own-org rows returned.

- [ ] 8.2 Emit analytics events on generate/preview/save/instantiate tagged with org + source via
      `posthog_client`; structured validation-failure logs without secrets. _(Req 10.2, 10.3)_

- [ ] 8.3 End-to-end smoke test: author a small template over the MCP tool path → persist → list →
      instantiate → assert the resulting workflow constructs and validates via `WorkflowGraph`
      (mirror the switchboard smoke test). _(Req 8.4, 12)_

## Phase 9 — Docs

- [ ] 9.1 Add a short usage doc under `docs/` (Mintlify) describing the chat + document authoring
      flows and the MCP tools. Update MCP instructions if a new capability affects the tool catalog.
      _(supports Req 1–3)_

---

## Suggested delivery slices (for incremental PRs)

1. **Slice A (compiler + storage):** Phase 1 + Phase 3 — pure compiler and org-scoped templates,
   fully unit-tested, no external surface yet. Lowest risk, highest reuse-value.
2. **Slice B (MCP authoring):** Phase 2 + Phase 4 — reference resolution + the three MCP tools. This
   alone delivers "build agents by chat" for orgs whose tools already exist.
3. **Slice C (documents):** Phase 5 — upload + MPS conversion + read tools.
4. **Slice D (MPS REST + instantiation + e2e):** Phase 6 + 7 + 8 + 9.

Each slice is independently shippable and testable. Start with Slice A.
