# Implementation Plan: Switchboard Frontend Enablement

## Overview

The enablement layer is built bottom-up: pure serialization/reconciliation/masking
helpers first, then the DB-touching provisioner and instantiator orchestration on
top of them, then the thin route wiring, then the frontend surfaces. This keeps
every property-testable transformation implemented and unit/property-tested before
anything that depends on it, and keeps routes thin per repo layering
(routes → services → db). All new backend code lives under
`api/services/switchboard/enablement/`, mirroring the design's package layout; no
existing switchboard decision logic or graph builders are modified except the
one minimal serialization-seam extraction in `graph.py`.

Tests source `api/.env.test` (see `api/AGENTS.md`):

```bash
source venv/bin/activate && set -a && source api/.env.test && set +a && python -m pytest api/tests/...
```

## Tasks

- [x] 1. Extract the serialization seam and scaffold the enablement package
  - [x] 1.1 Add `build_switchboard_reactflow_dto()` and enablement package stubs
    - Add `build_switchboard_reactflow_dto() -> ReactFlowDTO` to
      `api/services/switchboard/graph.py`: move the existing DTO-assembly body
      (steps 1–4, i.e. everything through `dto = ReactFlowDTO(...)`) into this
      new function and have `build_switchboard_graph()` call it, then validate
      as before (unchanged external behavior — Design "Serialization seam")
    - Create `api/services/switchboard/enablement/__init__.py` and empty module
      stubs `registrar.py`, `serialize.py`, `provisioner.py`, `reconcile.py`,
      `instantiator.py`, `scoping.py`, `masking.py`, `config_source.py` per the
      design's package layout
    - _Requirements: 1.1_

  - [x] 1.2 Write unit test for the serialization seam
    - Assert `build_switchboard_reactflow_dto()` returns a `ReactFlowDTO` equal
      (same node ids/types, edge conditions/transition_speech) to the DTO
      `build_switchboard_graph()` validates internally, and that
      `build_switchboard_graph()` still returns a valid `WorkflowGraph`
      unchanged
    - _Requirements: 1.1_
    - File: `api/tests/switchboard/enablement/test_serialization_seam.py`

- [x] 2. Implement Template_Registrar and the round-trip/idempotence properties
  - [x] 2.1 Implement `serialize.py` and `registrar.py`
    - In `enablement/serialize.py`, implement
      `serialize_switchboard_template_json() -> dict` that calls
      `build_switchboard_reactflow_dto()`, validates it via `WorkflowGraph(dto)`
      and `validate_tool_scoping(dto.nodes)`, and returns
      `dto.model_dump(mode="json")`; raise `SwitchboardTemplateInvalid` (define
      in `enablement/registrar.py`) carrying validation errors on failure
      (Design "Template_Registrar", Req 1.6)
    - In `enablement/registrar.py`, implement `SWITCHBOARD_TEMPLATE_NAME`,
      `SWITCHBOARD_TEMPLATE_DESCRIPTION`, and
      `register_switchboard_template(template_client: WorkflowTemplateClient | None = None) -> WorkflowTemplates`:
      look up by `get_workflow_template_by_name`, call
      `create_workflow_template` when absent or `update_workflow_template` when
      present, using the `template_json` from `serialize.py`
      (Req 1.1, 1.2, 1.3, 1.4)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

  - [x] 2.2 Write property test for template serialization round-trip
    - **Property 1: Template serialization round-trip**
    - **Validates: Requirements 1.1, 1.5**
    - Generate structure-preserving perturbations of the real assembled
      `ReactFlowDTO` (reordered nodes/edges, added extraction variables, added
      silent/verbatim edges); assert serializing then reloading through
      `WorkflowGraph` reconstructs the same node ids, node types, edge
      `condition`/`transition_speech` values, `extraction_variables`, and node
      `tool_uuids`
    - File: `api/tests/switchboard/enablement/test_registrar_roundtrip_property.py`

  - [x] 2.3 Write property test for template registration idempotence
    - **Property 2: Template registration idempotence**
    - **Validates: Requirements 1.3, 1.4**
    - Use an in-memory fake `WorkflowTemplateClient`; for N in 1..~10, call
      `register_switchboard_template` N times and assert exactly one row keyed
      by `SWITCHBOARD_TEMPLATE_NAME` remains, with `template_json` equal to the
      latest serialization
    - File: `api/tests/switchboard/enablement/test_registrar_idempotence_property.py`

  - [x] 2.4 Write unit/edge tests for registrar create/update/abort paths
    - Create branch when absent (Req 1.3); update branch when present (Req 1.4)
      with stable `template_name`/`template_description` (Req 1.2); registrar
      aborts and writes nothing on an invalid DTO (Req 1.6)
    - File: `api/tests/switchboard/enablement/test_registrar.py`

- [x] 3. Implement Connector_Tool_Provisioner
  - [x] 3.1 Implement `provisioner.py`
    - In `enablement/provisioner.py`, implement `CONNECTOR_NAME_KEY` and
      `provision_connector_tools(*, organization_id: int, user_id: int, tool_client: ToolClient) -> dict[str, str]`:
      for each tool from `get_connector_tools()`, build the definition via
      `ConnectorTool.to_tool_definition()`, set
      `definition["switchboard"]["connector_name"] = tool.name`, look up
      existing active org tools whose
      `definition["switchboard"]["connector_name"]` matches (reuse `tool_uuid`
      if found), else `tool_client.create_tool(...)` with
      `category=ToolCategory.HTTP_API.value`, `organization_id`; return
      `{connector_name: tool_uuid}` (Design "Connector_Tool_Provisioner",
      Req 4.1, 4.2, 4.3, 4.4)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 3.2 Write property test for connector-tool provisioning fidelity and idempotence
    - **Property 3: Connector-tool provisioning fidelity and idempotence**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    - Use an in-memory fake `ToolClient`; for arbitrary organization ids and N
      in 1..~10, provision N times and assert exactly one active `ToolModel`
      per connector identity (11 total), each with the requester's
      `organization_id`, a definition equal to
      `ConnectorTool.to_tool_definition()` (plus the `connector_name` marker),
      correct `clusters`/`sensitive_fields`, and stable `tool_uuid`s across
      repeats
    - File: `api/tests/switchboard/enablement/test_provisioner_property.py`

  - [x] 3.3 Write unit test confirming provisioned tools are listed by ToolSelector-facing query
    - Assert `db_client.get_tools_for_organization(org_id, status="active")`
      includes all 11 provisioned connector tools (Req 4.5)
    - File: `api/tests/switchboard/enablement/test_provisioner.py`

- [x] 4. Implement the tool-reference reconciler
  - [x] 4.1 Implement `reconcile.py`
    - In `enablement/reconcile.py`, implement `UnresolvedToolReference` (raise
      on missing mapping) and
      `reconcile_tool_references(dto: ReactFlowDTO, name_to_uuid: dict[str, str]) -> ReactFlowDTO`:
      for each node's `tool_uuids`, map each name-string via `name_to_uuid`,
      raising `UnresolvedToolReference` for any unmapped name; bind the
      greeting `startCall` node's `pre_call_fetch` patient-lookup reference to
      `name_to_uuid["patient_lookup"]`; return a new `ReactFlowDTO` with
      nodes/edges otherwise unchanged (Design "Tool-reference reconciler",
      Req 5.1, 5.2, 5.3, 5.4)
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 4.2 Write property test for tool-reference reconciliation completeness
    - **Property 4: Tool-reference reconciliation completeness**
    - **Validates: Requirements 5.1, 5.2, 3.3**
    - Generate `name_to_uuid` maps covering all node tool-name references in
      the real switchboard DTO (plus perturbed variants); assert every node's
      `tool_uuids` after reconciliation are real UUIDs (no connector
      name-string remains), each node's resolved connector identities equal
      its pre-reconciliation set (cluster scoping preserved), and the
      reconciled DTO passes `WorkflowGraph` validation
    - File: `api/tests/switchboard/enablement/test_reconcile_property.py`

  - [x] 4.3 Write unit tests for greeting pre_call_fetch binding and unresolved reference
    - Greeting `startCall` node's patient-lookup `pre_call_fetch` binds to the
      provisioned `patient_lookup` UUID (Req 5.3); a node naming an
      unprovisioned connector raises `UnresolvedToolReference` (Req 5.4)
    - File: `api/tests/switchboard/enablement/test_reconcile.py`

- [x] 5. Implement UUID-aware gate-by-scoping validation (fail-closed)
  - [x] 5.1 Implement `scoping.py`
    - In `enablement/scoping.py`, implement
      `validate_uuid_tool_scoping(nodes: Sequence[RFNodeDTO], uuid_to_connector_name: dict[str, str]) -> list[str]`:
      for each node with `tool_uuids`, resolve each UUID to its connector name
      via `uuid_to_connector_name`; if a UUID cannot be positively resolved,
      treat it as a `ROUTING_ONLY_TOOLS` violation (fail-closed); if a resolved
      name is in `ROUTING_ONLY_TOOLS` and the node is not a Routing node,
      record a violation string, reusing the `ROUTING_ONLY_TOOLS` set and the
      "node id starts with `routing_`" check from
      `api.services.switchboard.clusters.tool_scoping.validate_tool_scoping`
      (Design "Gate-by-scoping preservation", Req 11.2, 11.4, 11.5)
    - Add a helper
      `build_uuid_to_connector_name(tool_definitions: dict[str, dict]) -> dict[str, str]`
      that reads `definition["switchboard"]["connector_name"]` per provisioned
      `ToolModel` to build the resolution map consumed above
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 5.2 Write property test for the gate-by-scoping invariant
    - **Property 6: Gate-by-scoping invariant**
    - **Validates: Requirements 11.1, 11.2, 11.4**
    - Generate switchboard-derived graphs with arbitrary tool-uuid ↔ connector
      resolution maps, including maps with unresolvable UUIDs and maps that
      place a `transfer`/`route_metadata_resolution` UUID on a non-Routing
      node; assert `validate_uuid_tool_scoping` returns violations if and only
      if a non-Routing node carries a routing-only tool or a tool identity
      cannot be positively resolved, and returns no violations for the real,
      correctly scoped switchboard graph
    - File: `api/tests/switchboard/enablement/test_scoping_property.py`

  - [x] 5.3 Write edge-case tests for gate-by-scoping rejection
    - A non-Routing node listing `transfer`/`route_metadata_resolution` is
      rejected with a gate-by-scoping violation (Req 11.3); an unresolvable
      tool identity fails closed and is rejected (Req 11.5)
    - File: `api/tests/switchboard/enablement/test_scoping.py`

- [x] 6. Implement connector-tool masking
  - [x] 6.1 Implement `masking.py`
    - In `enablement/masking.py`, implement `FIXED_SENSITIVE_FIELDS` (`phone`,
      `patient_id`, `provided_dob`, `dob_on_file`) and
      `mask_connector_tool_definition(definition: dict) -> dict`: deep-copy the
      definition, mask every value under a key in
      `definition["switchboard"]["sensitive_fields"] | FIXED_SENSITIVE_FIELDS`
      wherever it appears in `config.parameters`/nested config, and always
      mask any configured credential value while leaving the
      `config.credential_uuid` identifier itself visible (Req 6.2); never
      return raw secret values (Design "Connector-tool masking", Req 7.1, 7.3,
      7.4)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 6.2 Write property test for sensitive-field masking
    - **Property 11: Sensitive-field masking**
    - **Validates: Requirements 6.2, 7.1, 7.3, 7.4**
    - Generate connector-tool definitions with random sensitive-field values
      and credential references (including the fixed fields and each
      connector's declared `sensitive_fields`); assert every declared-sensitive
      value and every configured credential value is masked in the output, and
      credential references are represented by identifier only, never a raw
      secret value
    - File: `api/tests/switchboard/enablement/test_masking_property.py`

  - [x] 6.3 Write unit test that enablement logging references sensitive fields by name only
    - Assert log calls in `provisioner.py`/`reconcile.py` never include a
      sensitive field's value (Req 7.2)
    - File: `api/tests/switchboard/enablement/test_masking.py`

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement Switchboard_Config (business hours + hotwords)
  - [x] 8.1 Implement `config_source.py` and wire it into after-hours evaluation
    - In `enablement/config_source.py`, implement `BUSINESS_HOURS_CONFIG_KEY`,
      `HOTWORDS_CONFIG_KEY`, a `BusinessHoursConfig` dataclass/model
      (`timezone: str`, `schedule: Mapping[int, tuple[str, str] | None]`),
      `load_business_hours(organization_id: int, *, config_client: OrganizationConfigurationClient | None = None) -> BusinessHoursConfig`
      (org override via `get_configuration_value` → fallback to
      `api.services.switchboard.config.SCHEDULE_TIMEZONE` +
      `BUSINESS_HOURS_SCHEDULE` on missing/malformed value, logging the key
      only on malformed input), and
      `load_hotwords(organization_id: int, *, config_client: OrganizationConfigurationClient | None = None) -> list[str]`
      (org override → `load_afterhours_hotwords()` env fallback → `[]`)
      (Design "Switchboard_Config", Req 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3)
    - Wire `load_business_hours`/`load_hotwords` into the after-hours
      evaluation call sites (`api/services/switchboard/after_hours.py` /
      `business_hours.py` callers, or their graph-builder wiring point) so the
      after-hours evaluator reads from the config source rather than the
      module-level constants directly, preserving current behavior when
      unconfigured
    - Propagate org-config changes to this key across workers via
      `WorkerSyncManager` when `upsert_configuration` is called for these keys
      (repo multi-worker rule)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 8.2 Write property test for empty hotword list matches nothing
    - **Property 12: Empty hotword list matches nothing**
    - **Validates: Requirements 10.5**
    - Generate arbitrary caller utterances (including ones containing common
      urgent words); assert `detect_hotword(utterance, keywords=[])` and
      `detect_hotword(utterance, keywords=None)` with no configured hotwords
      always return `None`/no match and never trigger the urgent
      silent-routing path
    - File: `api/tests/switchboard/enablement/test_config_source_property.py`

  - [x] 8.3 Write unit tests for config defaults and representative evaluations
    - Default America/Chicago schedule when unconfigured (Req 9.2); default
      empty hotword list when unconfigured (Req 10.2); malformed org override
      falls back to defaults (Req 9.2/10.2 error-handling); representative
      in/after-hours and hotword-match evaluations using an org override
      (Req 9.4, 10.4)
    - File: `api/tests/switchboard/enablement/test_config_source.py`

  - [x] 8.4 Write smoke test for config plumbing without code changes
    - Assert schedule/timezone and hotwords are read from
      `OrganizationConfigurationClient` at runtime and change when the org
      config value is upserted, with no switchboard code changes required
      (Req 9.1, 9.3, 10.1, 10.3)
    - File: `api/tests/switchboard/enablement/test_config_source_smoke.py`

- [x] 9. Implement Template_Instantiator orchestration with rollback
  - [x] 9.1 Implement `instantiator.py`
    - In `enablement/instantiator.py`, implement
      `instantiate_switchboard(*, template: WorkflowTemplates, organization_id: int, user_id: int, workflow_name: str) -> WorkflowModel`
      following the design's numbered steps: (1) `provision_connector_tools`,
      tracking newly-created tool uuids vs reused ones; (2) load the
      template's `template_json` into a `ReactFlowDTO`, call
      `reconcile_tool_references`; (3) call the existing
      `regenerate_trigger_uuids` (from `api/routes/workflow.py`, or relocate it
      to a shared services helper if needed to avoid a route→instantiator
      import) on the reconciled definition; (4) stamp `organization_id`;
      (5) validate via `WorkflowGraph` and `validate_uuid_tool_scoping` in
      memory; (6) on success, `db_client.create_workflow(...)` +
      `sync_triggers_for_workflow(...)`; (7) on any failure after step (1),
      call a `_rollback(created_tool_uuids, ...)` helper that
      archives/deletes exactly the newly-created tool rows (never reused ones)
      and re-raises a structured `SwitchboardInstantiationError` (Design
      "Template_Instantiator", "Error Handling", Req 3.1–3.6, 5.4)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.4_

  - [x] 9.2 Write property test for trigger identifier freshness
    - **Property 5: Trigger identifier freshness**
    - **Validates: Requirements 3.2**
    - Generate switchboard-derived template definitions with trigger nodes;
      assert every trigger node identifier in the instantiated definition
      differs from the corresponding identifier in the source template, for
      every instantiation
    - File: `api/tests/switchboard/enablement/test_instantiator_trigger_freshness_property.py`

  - [x] 9.3 Write property test for the tenant-isolation invariant
    - **Property 8: Tenant-isolation invariant**
    - **Validates: Requirements 3.1, 3.5, 4.2, 13.1, 13.2, 13.5**
    - Using in-memory fake DB clients, generate arbitrary pairs of distinct
      organization ids and instantiate for one; assert every record created
      (workflow, `ToolModel`s, bindings, config) carries exactly the
      requesting `organization_id`, and that a listing/read scoped to the
      other organization returns empty rather than any cross-org record,
      including when the org filter is simulated as absent/bypassed
    - File: `api/tests/switchboard/enablement/test_instantiator_tenant_isolation_property.py`

  - [x] 9.4 Write property test for instantiation atomic rollback
    - **Property 9: Instantiation atomic rollback**
    - **Validates: Requirements 3.6**
    - Using in-memory fake DB clients, parametrize injected failures across
      each instantiation step (provisioning, reconciliation, validation,
      workflow creation); assert that after each injected failure, the set of
      organization-scoped records newly created during that run is empty and
      equals the pre-instantiation state
    - File: `api/tests/switchboard/enablement/test_instantiator_rollback_property.py`

  - [x] 9.5 Write unit/edge tests for instantiation validation failure and unresolved reference
    - Invalid reconciled DTO is rejected with a structured validation error
      and no workflow row is created (Req 3.4); unresolved tool reference
      rejects instantiation and reports the unresolved reference (Req 5.4)
    - File: `api/tests/switchboard/enablement/test_instantiator.py`

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Prove speech/prompt preservation across the full pipeline
  - [x] 11.1 Add a pipeline-level preservation check helper (if needed)
    - No new production transformation is required (Design "Silent-transition
      / verbatim / global-prompt preservation" is satisfied by the existing
      `model_dump(mode="json")` serialization from task 2 and the reconciler's
      tool_uuids-only rewrite from task 4); add a small test-support helper
      (e.g. `api/tests/switchboard/enablement/_pipeline_helpers.py`) that
      chains `serialize_switchboard_template_json` → reload →
      `reconcile_tool_references` for use by the property test below
    - _Requirements: 12.1, 12.3, 12.4_

  - [x] 11.2 Write property test for speech and prompt preservation
    - **Property 7: Speech and prompt preservation**
    - **Validates: Requirements 12.1, 12.3, 12.4**
    - Generate switchboard-derived graphs with added silent (empty
      `transition_speech`) edges, verbatim node prompts/edge speech, and nodes
      with `add_global_prompt=false`; assert that after
      `serialize_switchboard_template_json` → reload →
      `reconcile_tool_references`, every empty `transition_speech` stays
      empty, every node prompt and edge `transition_speech` value is
      unchanged, and every node's `add_global_prompt` value is unchanged
    - File: `api/tests/switchboard/enablement/test_speech_preservation_property.py`

- [x] 12. Wire the extended `/templates/duplicate` route and tool-binding persistence
  - [x] 12.1 Wire Template_Instantiator into `/templates/duplicate`
    - In `api/routes/workflow.py`, replace the body of
      `duplicate_workflow_template` with a call to
      `instantiate_switchboard(...)` when
      `template.template_name == SWITCHBOARD_TEMPLATE_NAME` (otherwise keep
      the existing bare-create path for non-switchboard templates), and map
      `SwitchboardInstantiationError`/`UnresolvedToolReference` to an HTTP 422
      response identifying the validation/rollback failure, matching the
      existing `WorkflowError` → HTTP 422 shape (Design "Routes are extended,
      not replaced", Req 2.5, 2.7, 3.4)
    - _Requirements: 2.3, 2.4, 2.5, 2.7, 3.3, 3.4_

  - [x] 12.2 Apply masking to tool API responses
    - In `api/routes/tool.py`, apply `mask_connector_tool_definition` inside
      `build_tool_response` for tools whose `definition.get("switchboard")` is
      present, so connector-tool API responses mask sensitive fields
      (Req 7.3)
    - _Requirements: 7.3_

  - [x] 12.3 Implement tool-binding persistence
    - In `api/routes/tool.py`, extend `update_tool`'s handling (or add a new
      `PUT /tools/{tool_uuid}/binding` sub-route, following existing HTTP tool
      config conventions) so operators can set/persist a connector tool's
      `config.url`, `config.credential_uuid`, and `config.field_mapping` via
      `db_client.update_tool`, resolving `credential_uuid` through
      `WebhookCredentialClient.get_credential_by_uuid` scoped to the caller's
      organization and rejecting a foreign credential reference with 404
      (Design "Tool_Binding_Editor + binding persistence", Req 6.1, 6.2, 6.4,
      6.5, 6.6, 13.3, 13.4)
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.6, 13.3, 13.4_

  - [x] 12.4 Write property test for binding persistence round-trip
    - **Property 10: Binding persistence round-trip**
    - **Validates: Requirements 6.5**
    - Generate arbitrary valid bindings (endpoint URL, credential reference,
      field mapping) for a provisioned connector `ToolModel`; assert saving via
      the update path then reading the tool back yields a definition whose
      `config.url`/`config.credential_uuid`/`config.field_mapping` equal what
      was saved
    - File: `api/tests/switchboard/enablement/test_tool_binding_property.py`

  - [x] 12.5 Write integration tests for /templates/duplicate instantiation
    - Full-stack `POST /templates/duplicate` for the switchboard template
      using `test_client_factory`: success creates an org-scoped,
      tool-selectable workflow (Req 3.1, 3.3, 4.5); invalid/failed
      instantiation returns 422 with no workflow row created (Req 2.5, 2.7,
      3.4); a foreign tool/recording/credential reference is rejected with
      404 (Req 13.3, 13.4)
    - File: `api/tests/switchboard/enablement/test_workflow_routes_integration.py`

  - [x] 12.6 Write edge-case test for binding persistence failure
    - Simulate a DB failure during `update_tool` for a binding save; assert
      the route returns an error and does not report success, with no partial
      binding persisted (Req 6.6)
    - File: `api/tests/switchboard/enablement/test_tool_binding.py`

- [x] 13. Add a registration entry point (seed/admin task)
  - [x] 13.1 Implement the registration entry point
    - Add a callable admin/seed entry point (e.g.
      `api/services/admin_utils/register_switchboard_template.py` or an ARQ
      task under `api/tasks/`, matching the nearest existing one-off-script
      convention in the repo) that calls `register_switchboard_template()` so
      an operator can run registration once per deployment (Design
      "Registration (admin/seed, run once per deployment)")
    - _Requirements: 1.3, 1.4_

  - [x] 13.2 Write unit test for the registration entry point
    - Invoke the entry point against a fake/test `WorkflowTemplateClient` and
      assert it delegates to `register_switchboard_template()`
    - File: `api/tests/switchboard/enablement/test_registration_entrypoint.py`

- [x] 14. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Add the welcome-audio readiness indicator to the Workflow_Builder
  - [x] 15.1 Surface a "welcome recording required" readiness message
    - Welcome-audio selection itself reuses the existing `startCall` node
      editor's `recording_ref` field (`greeting_recording_id` +
      `greeting_type='audio'`) and the existing recording upload path — no new
      selector/upload UI is built (Design "Welcome-audio selection (Workflow
      Builder, reused)", Req 8.1, 8.2, 8.3)
    - Add a readiness check (in the switchboard-specific node/workflow render
      path in `ui/src/components/flow/renderer/` or the node validation
      surface already used for `invalid`/`validationMessage` node states) that
      flags the Greeting `startCall` node when `greeting_recording_id` is unset,
      indicating a welcome recording is required before the switchboard is
      ready to run (Req 8.4)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 15.2 Write unit tests for the welcome-audio readiness indicator
    - Selecting a recording sets `greeting_type='audio'` +
      `greeting_recording_id` (Req 8.1, 8.2); the readiness indicator appears
      while `greeting_recording_id` is unset and disappears once set (Req 8.4)
    - File: `ui/src/components/flow/__tests__/WelcomeAudioReadiness.test.tsx`
      (match this repo's existing frontend test runner/conventions if
      different — check for an existing `ui/` test setup before adding one)

- [x] 16. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Implement the Create_Agent_UI template gallery
  - [x] 17.1 Build the template gallery dialog and wire it into CreateWorkflowButton
    - Create `ui/src/components/workflow/CreateFromTemplateDialog.tsx`:
      fetches templates from
      `getWorkflowTemplatesApiV1WorkflowTemplatesGet` (the generated SDK
      client for `GET /api/v1/workflow/templates`), renders each with
      `template_name` + `template_description` (Req 2.2), and **always**
      renders a switchboard entry (hardcoded name/id fallback keyed by the
      stable `spinsci-switchboard` template name) even if absent from the
      fetched list (Req 2.6); accepts a user-provided workflow name and, on
      confirm, calls
      `duplicateWorkflowTemplateApiV1WorkflowTemplatesDuplicatePost` (Design
      "Create_Agent_UI", Req 2.1, 2.2, 2.3, 2.6)
    - On success, navigate to `/workflow/{id}` (Workflow_Builder) (Req 2.4);
      on failure, show an error toast/message and keep the user on the
      dialog/create surface without navigating (Req 2.5, 2.7)
    - Add a "From template" item to
      `ui/src/components/workflow/CreateWorkflowButton.tsx`'s dropdown that
      opens `CreateFromTemplateDialog` (Design "Create_Agent_UI")
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 17.2 Write unit tests for CreateFromTemplateDialog
    - Renders fetched templates plus the always-present switchboard fallback
      when the fetch omits/degrades it (Req 2.1, 2.2, 2.6); confirms call the
      duplicate endpoint with the selected template + name (Req 2.3); success
      navigates to the Workflow_Builder route (Req 2.4); a failed duplicate
      call shows an error and keeps the dialog open without navigating
      (Req 2.5, 2.7)
    - File: `ui/src/components/workflow/__tests__/CreateFromTemplateDialog.test.tsx`
      (match this repo's existing frontend test runner/conventions if
      different — check for an existing `ui/` test setup before adding one)

- [x] 18. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP; they
  are all test-writing sub-tasks (property, unit, edge, integration, or smoke
  tests) and are not required for the core implementation path.
- Property-based tests use Hypothesis, run under pytest with `api/.env.test`
  sourced, `@settings(max_examples=100)` or higher, one test per property, and
  each tagged with `# Feature: switchboard-frontend-enablement, Property N: {text}`
  per the design's Testing Strategy.
- Tasks 15.1/15.2 and 17.1/17.2 (frontend) have no correctness-properties
  mapping in the design — they are covered by unit tests only, per the
  design's Testing Strategy ("UI behaviors ... covered by example/edge/
  integration tests").
- Checkpoints (7, 10, 14, 16, 18) are placed after each cohesive layer (pure
  transforms; instantiation/rollback; routes/wiring; welcome-audio readiness;
  create-agent gallery) so failures are caught close to the change that
  introduced them.
- Task 9.1 (Template_Instantiator) depends on tasks 2.1–6.1 and 8.1
  (registrar's validation reuse, provisioner, reconciler, scoping, masking,
  config source) being implemented first, matching the design's dependency
  chain Provisioner → Reconciler → Validator → Instantiator.
- Task 12.1–12.3's route wiring depends on task 9.1 (instantiator), task 6.1
  (masking), and task 3.1 (provisioner, for binding persistence onto
  provisioned tools).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1", "5.1", "6.1", "8.1"] },
    { "id": 2, "tasks": ["1.2", "2.2", "2.3", "2.4", "3.2", "3.3", "4.2", "4.3", "5.2", "5.3", "6.2", "6.3", "8.2", "8.3", "8.4", "13.1"] },
    { "id": 3, "tasks": ["9.1", "13.2"] },
    { "id": 4, "tasks": ["9.2", "9.3", "9.4", "9.5", "11.1"] },
    { "id": 5, "tasks": ["12.1", "12.2", "11.2"] },
    { "id": 6, "tasks": ["12.3"] },
    { "id": 7, "tasks": ["12.4", "12.5", "12.6", "15.1"] },
    { "id": 8, "tasks": ["15.2", "17.1"] },
    { "id": 9, "tasks": ["17.2"] }
  ]
}
```
