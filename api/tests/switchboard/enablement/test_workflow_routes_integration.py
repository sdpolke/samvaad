"""Full-stack integration tests for switchboard ``POST /templates/duplicate``.

Covers:
- Success: instantiating the registered switchboard template creates an
  organization-scoped workflow whose definition passes Graph_Validator, and
  whose provisioned connector tools are listed as attachable via
  ``GET /tools`` (Req 3.1, 3.3, 4.5).
- Failure: an invalid switchboard ``template_json`` returns HTTP 422 and
  leaves no workflow row for the organization (Req 2.5, 2.7, 3.4).
- Tenant isolation: a foreign tool, recording, or credential reference is
  rejected with HTTP 404 (Req 13.3, 13.4).

Uses ``test_client_factory`` against the real test database (transaction-
rolled-back-per-test isolation), per ``.kiro/steering/testing.md``.

The route constructs a fresh ``WorkflowTemplateClient()`` (its own engine)
rather than the shared ``db_client``, so these tests monkeypatch
``api.routes.workflow.WorkflowTemplateClient`` to return the patched
``db_session`` fixture — otherwise the route cannot see templates created
inside the test transaction.

Design references:
- ``design.md`` -> "Template_Instantiator", "Routes are extended, not
  replaced", "Error Handling", "Tenant-isolation failures"
- ``requirements.md`` -> Requirements 2.5, 2.7, 3.1, 3.3, 3.4, 4.5, 13.3, 13.4

Task: 12.5.
"""

from __future__ import annotations

from api.db.models import OrganizationModel, UserModel, WorkflowTemplates
from api.enums import StorageBackend, ToolStatus, WebhookCredentialType
from api.services.switchboard.enablement.provisioner import (
    CONNECTOR_NAME_KEY,
    provision_connector_tools,
)
from api.services.switchboard.enablement.registrar import (
    SWITCHBOARD_TEMPLATE_DESCRIPTION,
    SWITCHBOARD_TEMPLATE_NAME,
)
from api.services.switchboard.enablement.serialize import (
    serialize_switchboard_template_json,
)
from api.services.switchboard.tools.registry import get_connector_tools
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph


def _patch_template_client(monkeypatch, db_session) -> None:
    """Route ``WorkflowTemplateClient()`` through the test-session DBClient.

    ``duplicate_workflow_template`` / ``get_workflow_templates`` construct a
    fresh ``WorkflowTemplateClient()`` with its own engine, which cannot see
    rows created inside the rolled-back test transaction. Pointing the
    constructor at ``db_session`` keeps template reads/writes on the same
    session the rest of the stack (and ``instantiate_switchboard``) uses.
    """
    monkeypatch.setattr(
        "api.routes.workflow.WorkflowTemplateClient",
        lambda: db_session,
    )


async def _create_org_and_user(
    async_session, *, suffix: str
) -> tuple[OrganizationModel, UserModel]:
    org = OrganizationModel(provider_id=f"test-org-wf-routes-{suffix}")
    async_session.add(org)
    await async_session.flush()

    user = UserModel(
        provider_id=f"test-user-wf-routes-{suffix}",
        selected_organization_id=org.id,
    )
    async_session.add(user)
    await async_session.flush()
    return org, user


async def _register_switchboard_template(
    async_session, *, template_json: dict | None = None
) -> WorkflowTemplates:
    """Insert a ``spinsci-switchboard`` catalog row visible to the test session."""
    template = WorkflowTemplates(
        template_name=SWITCHBOARD_TEMPLATE_NAME,
        template_description=SWITCHBOARD_TEMPLATE_DESCRIPTION,
        template_json=(
            template_json
            if template_json is not None
            else serialize_switchboard_template_json()
        ),
    )
    async_session.add(template)
    await async_session.flush()
    return template


def _two_start_nodes_template_json() -> dict:
    """Minimal switchboard-named ``template_json`` that fails Graph_Validator.

    Two ``startCall`` nodes (each defaulting ``is_start=True``) with no edges:
    valid per-node data so reconciliation succeeds, but ``WorkflowGraph``
    rejects more than one start node — exercising the route's 422 mapping of
    ``SwitchboardInstantiationError`` (Req 3.4).
    """
    return {
        "nodes": [
            {
                "id": "start_1",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {"name": "Start 1", "prompt": "Greet the caller."},
            },
            {
                "id": "start_2",
                "type": "startCall",
                "position": {"x": 100, "y": 0},
                "data": {"name": "Start 2", "prompt": "Greet the caller again."},
            },
        ],
        "edges": [],
    }


async def test_duplicate_switchboard_template_creates_org_scoped_tool_selectable_workflow(
    test_client_factory,
    db_session,
    async_session,
    monkeypatch,
):
    """Req 3.1, 3.3, 4.5: successful ``POST /templates/duplicate`` creates an
    org-scoped, Graph_Validator-valid workflow, and provisioned connector tools
    are listed by ``GET /tools`` (Tool_Selector surface)."""
    _patch_template_client(monkeypatch, db_session)

    org, user = await _create_org_and_user(async_session, suffix="success")
    template = await _register_switchboard_template(async_session)
    user = await db_session.get_user_by_id(user.id)

    workflow_name = "Integration Switchboard"

    async with test_client_factory(user) as client:
        response = await client.post(
            "/api/v1/workflow/templates/duplicate",
            json={
                "template_id": template.id,
                "workflow_name": workflow_name,
            },
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["name"] == workflow_name
        assert body["id"] is not None

        # Req 3.3: the created definition must pass Graph_Validator.
        WorkflowGraph(ReactFlowDTO.model_validate(body["workflow_definition"]))

        # Req 4.5: provisioned active connector tools appear in the Tool_Selector
        # listing endpoint.
        tools_response = await client.get("/api/v1/tools/", params={"status": "active"})
        assert tools_response.status_code == 200, (
            f"Expected 200 from GET /tools, got {tools_response.status_code}: "
            f"{tools_response.text}"
        )
        tools_body = tools_response.json()

    # Req 3.1: the persisted workflow row is scoped to the caller's org.
    persisted = await db_session.get_workflow(
        body["id"], organization_id=org.id
    )
    assert persisted is not None
    assert persisted.organization_id == org.id
    assert persisted.name == workflow_name

    connector_names = {tool.name for tool in get_connector_tools()}
    assert len(connector_names) == 11

    listed_connector_names = {
        (tool.get("definition") or {})
        .get("switchboard", {})
        .get(CONNECTOR_NAME_KEY)
        for tool in tools_body
    }
    assert connector_names.issubset(listed_connector_names)

    # Reconciled node tool_uuids should be real provisioned UUIDs, not
    # connector name-strings.
    name_to_uuid = {
        (tool.get("definition") or {})
        .get("switchboard", {})
        .get(CONNECTOR_NAME_KEY): tool["tool_uuid"]
        for tool in tools_body
        if (tool.get("definition") or {}).get("switchboard", {}).get(CONNECTOR_NAME_KEY)
    }
    provisioned_uuids = set(name_to_uuid.values())
    for node in body["workflow_definition"].get("nodes", []):
        for tool_ref in (node.get("data") or {}).get("tool_uuids") or []:
            assert tool_ref in provisioned_uuids, (
                f"Node {node.get('id')!r} still references unresolved tool "
                f"{tool_ref!r}; expected a provisioned tool_uuid"
            )


async def test_duplicate_invalid_switchboard_template_returns_422_and_creates_no_workflow(
    test_client_factory,
    db_session,
    async_session,
    monkeypatch,
):
    """Req 2.5, 2.7, 3.4: failed instantiation surfaces as HTTP 422 and does
    not leave a workflow row for the organization."""
    _patch_template_client(monkeypatch, db_session)

    org, user = await _create_org_and_user(async_session, suffix="invalid")
    template = await _register_switchboard_template(
        async_session, template_json=_two_start_nodes_template_json()
    )
    user = await db_session.get_user_by_id(user.id)

    workflows_before = await db_session.get_all_workflows(organization_id=org.id)
    assert workflows_before == []

    async with test_client_factory(user) as client:
        response = await client.post(
            "/api/v1/workflow/templates/duplicate",
            json={
                "template_id": template.id,
                "workflow_name": "Should Not Be Created",
            },
        )

    assert response.status_code == 422, (
        f"Expected 422, got {response.status_code}: {response.text}"
    )
    detail = response.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("is_valid") is False
    assert detail.get("errors")

    workflows_after = await db_session.get_all_workflows(organization_id=org.id)
    assert workflows_after == [], (
        "Failed instantiation must not leave a workflow row (Req 2.5, 2.7, 3.4); "
        f"found {[w.id for w in workflows_after]}"
    )


async def test_foreign_tool_credential_and_recording_references_return_404(
    test_client_factory,
    db_session,
    async_session,
):
    """Req 13.3, 13.4: cross-org tool, credential, and recording references
    are rejected with HTTP 404 (org-scoped clients fail closed to not-found)."""
    org_a, user_a = await _create_org_and_user(async_session, suffix="tenant-a")
    org_b, user_b = await _create_org_and_user(async_session, suffix="tenant-b")

    # Org A: provision a connector tool and create a credential + recording.
    name_to_uuid = await provision_connector_tools(
        organization_id=org_a.id,
        user_id=user_a.id,
        tool_client=db_session,
    )
    tool_uuid_a = name_to_uuid["patient_lookup"]

    credential_a = await db_session.create_credential(
        organization_id=org_a.id,
        user_id=user_a.id,
        name="org-a-credential",
        credential_type=WebhookCredentialType.BEARER_TOKEN.value,
        credential_data={"token": "secret-a"},
    )

    recording_a = await db_session.create_recording(
        recording_id="rec-org-a",
        organization_id=org_a.id,
        transcript="Welcome to org A",
        storage_key="recordings/org-a/welcome.wav",
        storage_backend=StorageBackend.MINIO.value,
        created_by=user_a.id,
    )

    # Org B: provision its own tool so binding can target a same-org tool while
    # attempting to attach Org A's credential (foreign credential reference).
    name_to_uuid_b = await provision_connector_tools(
        organization_id=org_b.id,
        user_id=user_b.id,
        tool_client=db_session,
    )
    tool_uuid_b = name_to_uuid_b["patient_lookup"]

    user_b = await db_session.get_user_by_id(user_b.id)

    async with test_client_factory(user_b) as client:
        # Foreign tool (owned by org A) — Req 13.3.
        foreign_tool_response = await client.get(f"/api/v1/tools/{tool_uuid_a}")
        assert foreign_tool_response.status_code == 404, (
            f"Expected 404 for foreign tool, got {foreign_tool_response.status_code}: "
            f"{foreign_tool_response.text}"
        )

        # Foreign credential on a same-org tool binding — Req 13.3, 13.4.
        foreign_credential_response = await client.put(
            f"/api/v1/tools/{tool_uuid_b}/binding",
            json={
                "url": "https://spinsci.example.com/patient-lookup",
                "credential_uuid": credential_a.credential_uuid,
                "field_mapping": {"mrn": "patient_id"},
            },
        )
        assert foreign_credential_response.status_code == 404, (
            f"Expected 404 for foreign credential, got "
            f"{foreign_credential_response.status_code}: "
            f"{foreign_credential_response.text}"
        )

        # Foreign recording — Req 13.3, 13.4.
        foreign_recording_response = await client.delete(
            f"/api/v1/workflow-recordings/{recording_a.recording_id}"
        )
        assert foreign_recording_response.status_code == 404, (
            f"Expected 404 for foreign recording, got "
            f"{foreign_recording_response.status_code}: "
            f"{foreign_recording_response.text}"
        )

    # Confirm org A's resources were untouched by the rejected cross-org ops.
    still_active_tool = await db_session.get_tool_by_uuid(
        tool_uuid_a, org_a.id, include_archived=True
    )
    assert still_active_tool is not None
    assert still_active_tool.status == ToolStatus.ACTIVE.value

    still_credential = await db_session.get_credential_by_uuid(
        credential_a.credential_uuid, org_a.id
    )
    assert still_credential is not None

    still_recording = await db_session.get_recording_by_recording_id(
        recording_a.recording_id, org_a.id
    )
    assert still_recording is not None
