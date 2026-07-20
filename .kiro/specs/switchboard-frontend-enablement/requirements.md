# Requirements Document

## Introduction

The SpinSci AI Virtual Switchboard is **already implemented** in the backend under
`api/services/switchboard/` as the completed PoC spec (`.kiro/specs/spinsci-switchboard-poc/`).
It is composed entirely from existing workflow-engine primitives — `startCall`/`trigger`/
`agentNode`/`endCall`/`globalNode` nodes, edges carrying `condition` + `transition_speech`,
`extraction_variables` (the Call State Ledger), node-scoped `tool_uuids`, `pre_call_fetch_*` on the
entry node, and a config-driven audio greeting. It introduced no new node types, edge fields, or
workflow schema. `build_switchboard_graph()` assembles and validates the whole graph.

This feature closes the **enablement gap**: making the already-built switchboard creatable, tool-
bindable, and configurable end-to-end through the product (frontend UI plus the minimal backend
glue that surfaces the switchboard to the UI), for a multi-tenant organization, **without rebuilding
the workflow builder**. The frontend already models everything the switchboard needs
(`pre_call_fetch_*`, `greeting_type='audio'`, `greeting_recording_id`, `add_global_prompt`,
`extraction_variables`, `tool_uuids`, `document_uuids`), edits nodes from backend node specs,
supports `transition_speech` (text/audio) and silent (empty) transitions on edges, selects
recordings/audio, and attaches HTTP and MCP tools by `tool_uuid`. Those capabilities are **reused,
not rebuilt**.

Three concrete gaps define this feature's scope:

1. **Instantiation gap.** `build_switchboard_graph()` is referenced only in tests. No route, task,
   seed, or template registers it, so no user can create or run the switchboard from the product.
   The backend exposes a workflow-template catalog (`GET /api/v1/workflow/templates`,
   `POST /api/v1/workflow/templates/duplicate`) and a `WorkflowTemplateClient`; this feature
   registers the switchboard graph as a template and surfaces it in the create-agent flow.
2. **Connector-tool gap.** The 11 SpinSci connector tools are a bespoke `ConnectorTool` abstraction
   bound to mock backends (the `[DEFERRED — SpinSci contract]` seam). They are not org-scoped
   `ToolModel` rows with real `tool_uuid`s, and the switchboard graph references them by
   name-strings (e.g. `"patient_lookup"`), so the frontend `ToolSelector` cannot attach them and
   operators cannot bind endpoints/credentials. This feature materializes them as bindable
   `ToolModel` tools and reconciles the graph's references to real UUIDs.
3. **Config-surface gap.** The America/Chicago business-hours schedule, the welcome-audio recording,
   and the after-hours hotword keyword list live in `api/services/switchboard/config.py`. This
   feature makes each operable through configuration or the existing UI without switchboard code
   changes.

**Non-goals.** This feature does not add new node types, edge fields, or workflow schema; does not
rebuild the node/edge editors, recording selectors, or tool-attach UI that already exist; and does
not define SpinSci wire formats (they remain external and deferred per PoC Requirement 16.2).

Traceability tags reference the PoC spec (`PoC Req N`) where a switchboard structural guarantee
must be preserved by this enablement work.

## Glossary

- **Switchboard**: The already-built SpinSci AI Virtual Switchboard workflow graph produced by `build_switchboard_graph()` in `api/services/switchboard/`.
- **Switchboard_Enablement**: The overall system defined by this document, spanning the frontend surfaces and backend glue that make the Switchboard creatable, tool-bindable, and configurable through the product.
- **Workflow_Engine**: The repository's graph-based workflow engine (`api/services/workflow/`) whose `WorkflowGraph` validates a directed graph of nodes and edges.
- **ReactFlow_Definition**: The `workflow_definition` JSON (nodes + edges + viewport) that the visual builder and API both read and write, and that `WorkflowGraph` validates.
- **Template_Registrar**: The backend component that serializes the Switchboard graph into a workflow-template catalog entry (`workflow_templates` row via `WorkflowTemplateClient`).
- **Switchboard_Template**: The registered workflow-template catalog entry whose `template_json` is the Switchboard `ReactFlow_Definition`.
- **Template_Instantiator**: The backend path (`POST /api/v1/workflow/templates/duplicate`) that creates a new, organization-scoped workflow from a `Switchboard_Template`.
- **Create_Agent_UI**: The frontend agent-creation surface (`CreateWorkflowButton` and `ui/src/app/workflow/create`) through which a user starts a new workflow.
- **Workflow_Builder**: The frontend ReactFlow node/edge editor (`ui/src/components/flow/`) used to author and edit a workflow.
- **Tool_Selector**: The frontend node tool-attach component (`ui/src/components/flow/ToolSelector.tsx`) that attaches tools to a node by `tool_uuid`.
- **Connector_Tool**: One of the 11 SpinSci backend connector tools defined in `api/services/switchboard/tools/registry.py` (patient_lookup, directory_lookup, faq_kb, dob_validation, identity_verify, routing_intent_resolution, route_metadata_resolution, transfer, hangup, scheduling_handoff, scheduling_engine).
- **Connector_Tool_Provisioner**: The backend component that materializes each Connector_Tool into an organization-scoped `ToolModel` row with a real `tool_uuid`, using `ConnectorTool.to_tool_definition()`.
- **ToolModel**: The organization-scoped, `tool_uuid`-referenced database tool record (`api/db/models.py`, `ToolClient`) that the `Tool_Selector` attaches by UUID.
- **Tool_Binding**: The `ConnectorBinding` seam (endpoint URL, credential reference, field mapping) that points a Connector_Tool at a real SpinSci backend without hardcoding SpinSci wire formats (PoC Req 16.2).
- **Tool_Binding_Editor**: The frontend/config surface through which an operator sets a Connector_Tool's endpoint, credential, and field mapping.
- **Sensitive_Field**: A Connector_Tool contract field declared in `sensitive_fields` (e.g. `phone`, `patient_id`, `provided_dob`, `dob_on_file`, credential values) that must be masked in UI, logs, and API responses.
- **Switchboard_Config**: The configuration holding the business-hours schedule and timezone, the welcome-audio recording reference, and the after-hours hotword keyword list.
- **Business_Hours**: Monday–Friday 08:00–17:00 and Saturday 08:00–12:00 in the America/Chicago timezone, with Sunday closed (PoC Req 17.1, 17.2).
- **Hotword_List**: The after-hours urgent keyword list read from configuration (PoC Req 21.1, 21.2).
- **Welcome_Audio**: The pre-configured audio greeting played on turn 1, referenced by the Greeting `startCall` node's `greeting_recording_id` with `greeting_type='audio'` (PoC Req 6.4).
- **Gate_By_Scoping**: The structural guarantee that the `transfer` and `route_metadata_resolution` tools are attached only to Routing-cluster nodes, so no transfer can occur before Routing (PoC Req 1.7, 9.2).
- **Silent_Transition**: A workflow edge whose `transition_speech` is empty, representing a turn on which the Switchboard emits no speech (PoC Req 1.5, 3.3, 3.4).
- **Verbatim_Script**: A mandated caller line reproduced exactly, carried as a node prompt output or an edge `transition_speech` (PoC Req 18).
- **Graph_Validator**: The validation performed by `WorkflowGraph` plus `validate_tool_scoping()` that a Switchboard workflow must pass.
- **organization_id**: The tenant isolation key; almost every resource is scoped to an organization.

## Requirements

### Requirement 1: Register the Switchboard as a workflow template

**User Story:** As a platform operator, I want the already-built Switchboard graph registered as a workflow template, so that it appears in the product's template catalog and can be instantiated by users.

#### Acceptance Criteria

1. THE Template_Registrar SHALL serialize the graph produced by `build_switchboard_graph()` into a ReactFlow_Definition stored as the `template_json` of a Switchboard_Template.
2. THE Template_Registrar SHALL register the Switchboard_Template with a stable `template_name` and a `template_description` that identifies the SpinSci Switchboard.
3. WHEN template registration runs and no Switchboard_Template with the configured `template_name` exists, THE Template_Registrar SHALL create the Switchboard_Template.
4. WHEN template registration runs and a Switchboard_Template with the configured `template_name` already exists, THE Template_Registrar SHALL update the existing entry rather than create a duplicate.
5. FOR ALL nodes and edges in the Switchboard graph, THE Template_Registrar SHALL produce a `template_json` such that loading it and validating it through the Graph_Validator reconstructs a graph with the same node ids, node types, edge `condition` values, edge `transition_speech` values, `extraction_variables`, and node `tool_uuids` references (round-trip property).
6. IF serialization produces a `template_json` that fails Graph_Validator validation, THEN THE Template_Registrar SHALL abort registration and SHALL report the validation error.

### Requirement 2: Surface the Switchboard template in the create-agent flow

**User Story:** As a user, I want to create the Switchboard from the existing create-agent flow, so that I can start a switchboard workflow without hand-building the graph.

#### Acceptance Criteria

1. THE Create_Agent_UI SHALL present a "create from template" entry point that lists the registered workflow templates retrieved from `GET /api/v1/workflow/templates`.
2. WHERE a Switchboard_Template is registered, THE Create_Agent_UI SHALL display the Switchboard_Template as a selectable option with its `template_name` and `template_description`.
3. WHEN a user selects the Switchboard_Template and confirms creation, THE Create_Agent_UI SHALL invoke the Template_Instantiator with the selected template and a user-provided workflow name.
4. WHEN the Template_Instantiator returns a created workflow, THE Create_Agent_UI SHALL navigate the user to the Workflow_Builder for that workflow.
5. IF template instantiation fails, THEN THE Create_Agent_UI SHALL display an error message and SHALL keep the user on the create-agent surface.
6. WHERE the Switchboard_Template is not confirmed present in the registered-templates list retrieved from `GET /api/v1/workflow/templates`, THE Create_Agent_UI SHALL still display the Switchboard_Template as a selectable option rather than hide it.
7. IF template instantiation fails after a workflow record was partially created, THEN THE Create_Agent_UI SHALL keep the user on the create-agent surface and SHALL NOT navigate to the partially-created workflow.

### Requirement 3: Organization-scoped instantiation of the Switchboard

**User Story:** As a security-conscious operator, I want each created switchboard scoped to my organization and validated, so that tenants stay isolated and only valid graphs are created.

#### Acceptance Criteria

1. WHEN the Template_Instantiator creates a workflow from a Switchboard_Template, THE Template_Instantiator SHALL set the new workflow's `organization_id` to the requesting user's `selected_organization_id`.
2. WHEN the Template_Instantiator creates a workflow from a Switchboard_Template, THE Template_Instantiator SHALL regenerate trigger node identifiers so the new workflow does not collide with existing triggers.
3. WHEN the Template_Instantiator creates a workflow from a Switchboard_Template, THE Template_Instantiator SHALL produce a workflow whose ReactFlow_Definition passes Graph_Validator validation.
4. IF the created workflow's ReactFlow_Definition fails Graph_Validator validation, THEN THE Template_Instantiator SHALL reject the creation and SHALL return an error identifying the validation failure.
5. THE Template_Instantiator SHALL scope every workflow, tool, recording, credential, and configuration record it creates to the requesting user's `organization_id`.
6. IF instantiation fails Graph_Validator validation after partially creating resources, THEN THE Template_Instantiator SHALL roll back every workflow, provisioned ToolModel, Tool_Binding, and Switchboard_Config record created during that instantiation so that no partial artifacts remain.

### Requirement 4: Provision connector tools as bindable, organization-scoped tools

**User Story:** As an operator, I want the 11 connector tools to exist as real, organization-scoped tools, so that I can attach them to nodes and bind their endpoints through the product.

#### Acceptance Criteria

1. WHEN the Switchboard is instantiated for an organization, THE Connector_Tool_Provisioner SHALL create one organization-scoped ToolModel for each of the 11 Connector_Tools using `ConnectorTool.to_tool_definition()` as the tool definition.
2. THE Connector_Tool_Provisioner SHALL set each provisioned ToolModel's `organization_id` to the requesting user's `selected_organization_id`.
3. THE Connector_Tool_Provisioner SHALL record each Connector_Tool's cluster scoping and `sensitive_fields` in the provisioned ToolModel definition.
4. WHEN a Connector_Tool with the same identity has already been provisioned for the organization, THE Connector_Tool_Provisioner SHALL reuse the existing ToolModel rather than create a duplicate.
5. WHEN a provisioned Connector_Tool ToolModel is active for the organization, THE Tool_Selector SHALL list that tool as an attachable tool for a node.

### Requirement 5: Reconcile graph tool references to organization tool UUIDs

**User Story:** As a platform engineer, I want the Switchboard graph's name-string tool references replaced with the organization's real tool UUIDs at instantiation, so that node tool bindings resolve to actual tools.

#### Acceptance Criteria

1. WHEN the Switchboard is instantiated for an organization, THE Template_Instantiator SHALL replace each node `tool_uuids` name-string reference (e.g. `"patient_lookup"`) with the `tool_uuid` of the corresponding provisioned ToolModel for that organization.
2. THE Template_Instantiator SHALL preserve each node's original cluster tool scoping so that the tools attached to a node after reconciliation are exactly the Connector_Tools scoped to that node's cluster.
3. WHEN the Greeting `startCall` node references the patient-lookup capability for its `pre_call_fetch`, THE Template_Instantiator SHALL bind that reference to the provisioned patient-lookup ToolModel for the organization.
4. IF a node references a Connector_Tool that was not provisioned for the organization, THEN THE Template_Instantiator SHALL reject the instantiation and SHALL report the unresolved tool reference.

### Requirement 6: Bind connector-tool endpoints and credentials (deferred SpinSci seam)

**User Story:** As an integration engineer, I want to set each connector tool's endpoint, credential, and field mapping in the product, so that the SpinSci contract seam can be connected later without code changes.

#### Acceptance Criteria

1. THE Tool_Binding_Editor SHALL allow an operator to set a provisioned Connector_Tool's endpoint URL, credential reference, and field mapping (the Tool_Binding).
2. THE Tool_Binding_Editor SHALL resolve credential references through the organization-scoped credentials service and SHALL reference credentials by identifier rather than by raw secret value.
3. WHERE a Connector_Tool has no configured endpoint, THE Switchboard_Enablement SHALL indicate that the tool is unbound and SHALL continue to run the tool against its mock backend.
4. THE Tool_Binding_Editor SHALL allow the endpoint, credential, and field mapping to be set for a Connector_Tool without modifying switchboard code (PoC Req 16.2).
5. WHEN an operator saves a Tool_Binding, THE Switchboard_Enablement SHALL persist the endpoint, credential reference, and field mapping on the organization-scoped ToolModel for that Connector_Tool.
6. IF persisting a Tool_Binding fails after an operator saves, THEN THE Switchboard_Enablement SHALL display an error and SHALL NOT present the save as successful.

### Requirement 7: Mask sensitive connector-tool fields

**User Story:** As a compliance reviewer, I want patient identifiers and credentials masked in the product, so that sensitive data is not exposed through the UI, logs, or API responses.

#### Acceptance Criteria

1. THE Switchboard_Enablement SHALL mask every Sensitive_Field value in Tool_Binding_Editor displays.
2. THE Switchboard_Enablement SHALL exclude Sensitive_Field values from log output and SHALL reference such fields by field name only.
3. WHEN an API response includes a provisioned Connector_Tool definition, THE Switchboard_Enablement SHALL mask configured credential values in that response.
4. THE Switchboard_Enablement SHALL treat `phone`, `patient_id`, `provided_dob`, `dob_on_file`, and credential values as Sensitive_Fields.

### Requirement 8: Welcome-audio recording selection

**User Story:** As an operator, I want to select or upload the welcome-audio recording for the greeting, so that turn 1 plays the configured audio greeting (PoC Req 6.4).

#### Acceptance Criteria

1. THE Workflow_Builder SHALL allow an operator to select an organization-scoped recording as the Welcome_Audio for the Greeting `startCall` node.
2. WHEN an operator selects a Welcome_Audio recording, THE Workflow_Builder SHALL set the Greeting `startCall` node's `greeting_type` to `audio` and its `greeting_recording_id` to the selected recording identifier.
3. THE Workflow_Builder SHALL allow an operator to upload a new organization-scoped recording for use as the Welcome_Audio.
4. WHILE no Welcome_Audio recording is selected for the Greeting `startCall` node, THE Workflow_Builder SHALL indicate that a welcome recording is required before the Switchboard is ready to run.

### Requirement 9: Business-hours schedule and timezone configuration

**User Story:** As an operator, I want the business-hours schedule and timezone to be configurable, so that after-hours behavior triggers correctly for the deployment (PoC Req 17).

#### Acceptance Criteria

1. THE Switchboard_Config SHALL provide the Business_Hours schedule and timezone as configuration values read at runtime by the after-hours evaluation.
2. WHERE no Business_Hours schedule is configured, THE Switchboard_Config SHALL default the timezone to America/Chicago and the schedule to Monday–Friday 08:00–17:00, Saturday 08:00–12:00, and Sunday closed.
3. THE Switchboard_Config SHALL allow the Business_Hours schedule and timezone to be changed without modifying switchboard code.
4. WHEN the after-hours evaluation runs at call start, THE Switchboard SHALL determine `after_hours` from the configured Business_Hours schedule and timezone.

### Requirement 10: After-hours hotword keyword list configuration

**User Story:** As a QA engineer, I want the after-hours hotword list configurable, so that the urgent path is ready when SpinSci supplies the keywords (PoC Req 21).

#### Acceptance Criteria

1. THE Switchboard_Config SHALL read the Hotword_List from configuration rather than from hardcoded switchboard code.
2. WHERE no Hotword_List is configured, THE Switchboard_Config SHALL provide an empty Hotword_List.
3. THE Switchboard_Config SHALL allow the Hotword_List to be supplied later without modifying switchboard code.
4. WHEN a configured hotword matches after hours, THE Switchboard SHALL trigger the urgent silent-routing path (PoC Req 8.3).
5. WHILE the Hotword_List is empty or unconfigured, THE Switchboard SHALL NOT match any hotword and SHALL NOT trigger the urgent silent-routing path.

### Requirement 11: Preserve gate-by-tool-scoping when authoring and editing

**User Story:** As a platform engineer, I want the transfer gate enforced structurally in the builder, so that editing the Switchboard cannot place a transfer capability before the Routing phase.

#### Acceptance Criteria

1. THE Switchboard_Enablement SHALL attach the `transfer` and `route_metadata_resolution` Connector_Tools only to Routing-cluster nodes (Gate_By_Scoping).
2. WHEN a Switchboard workflow is saved, THE Graph_Validator SHALL validate that no non-Routing node lists the `transfer` or `route_metadata_resolution` tool in its `tool_uuids`.
3. IF a non-Routing node lists the `transfer` or `route_metadata_resolution` tool, THEN THE Graph_Validator SHALL reject the save and SHALL report the Gate_By_Scoping violation (PoC Req 1.7, 9.2).
4. WHEN a Switchboard workflow is instantiated, THE Graph_Validator SHALL confirm that Gate_By_Scoping holds before the workflow is made runnable.
5. WHERE the Gate_By_Scoping validation cannot positively confirm that no non-Routing node references the `transfer` or `route_metadata_resolution` tool, THE Switchboard_Enablement SHALL treat the workflow as failing the Gate_By_Scoping check and SHALL reject the save or run.

### Requirement 12: Preserve silent transitions, verbatim scripts, and global-prompt suppression

**User Story:** As a compliance reviewer, I want the Switchboard's speech guarantees preserved through authoring, so that silent turns stay silent and mandated lines stay verbatim.

#### Acceptance Criteria

1. WHEN the Switchboard graph is serialized and instantiated, THE Switchboard_Enablement SHALL preserve every Silent_Transition as an edge with empty `transition_speech`.
2. THE Workflow_Builder SHALL persist an edge with empty `transition_speech` as a Silent_Transition without substituting default speech text.
3. WHEN the Switchboard graph is serialized and instantiated, THE Switchboard_Enablement SHALL preserve every Verbatim_Script node prompt and edge `transition_speech` value unchanged.
4. WHEN the Switchboard graph is serialized and instantiated, THE Switchboard_Enablement SHALL preserve `add_global_prompt=false` on nodes that emit Verbatim_Scripts (PoC Req 18).

### Requirement 13: Tenant isolation for all created records and endpoint references

**User Story:** As a security-conscious operator, I want every new record and reference scoped and validated by organization, so that one organization can never touch another organization's switchboard data.

#### Acceptance Criteria

1. THE Switchboard_Enablement SHALL scope every instantiated workflow, provisioned ToolModel, Tool_Binding, recording, credential, and Switchboard_Config record to a single `organization_id`.
2. WHEN reading or listing switchboard tools, recordings, or credentials, THE Switchboard_Enablement SHALL filter by the requesting user's `organization_id` at the query level.
3. IF a request references a tool, recording, or credential that does not belong to the requesting user's organization, THEN THE Switchboard_Enablement SHALL reject the request with a not-found result.
4. WHEN a node references a recording or credential, THE Switchboard_Enablement SHALL validate that the referenced record belongs to the workflow's `organization_id` before accepting the reference.
5. IF the organization filtering mechanism is bypassed or fails to apply, THEN THE Switchboard_Enablement SHALL return an empty result rather than unfiltered cross-organization records.

### Requirement 14: Deferred SpinSci wire contracts

**User Story:** As an integration engineer, I want the SpinSci wire contracts to stay external and bindable later, so that the switchboard is usable now on mocks and connectable later without code changes.

#### Acceptance Criteria

1. THE Switchboard_Enablement SHALL treat SpinSci API schemas and wire formats as external contracts and SHALL NOT hardcode SpinSci wire formats in switchboard code (PoC Req 16.2).
2. WHILE a Connector_Tool has no configured Tool_Binding endpoint, THE Switchboard_Enablement SHALL service that tool through its deterministic mock backend.
3. WHEN a Connector_Tool's Tool_Binding endpoint and credential are configured, THE Switchboard_Enablement SHALL route that tool's invocations to the configured endpoint using the configured field mapping.
4. THE Switchboard_Enablement SHALL allow every Connector_Tool to be bound to a real SpinSci endpoint through configuration without modifying switchboard code.
5. IF a Connector_Tool's Tool_Binding endpoint is configured but the configured endpoint is unavailable, THEN THE Switchboard_Enablement SHALL fail the tool invocation and SHALL NOT fall back to the mock backend.
