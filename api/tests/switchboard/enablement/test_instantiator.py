"""Unit/edge tests for Template_Instantiator validation failure and unresolved
tool reference rejection.

Covers:
- An invalid reconciled ``ReactFlowDTO`` (here: a template with two start
  nodes, which ``WorkflowGraph`` rejects) is rejected with a structured
  ``SwitchboardInstantiationError`` and no workflow row is ever created
  (Req 3.4).
- A node naming a connector tool that was not provisioned for the
  organization rejects instantiation with ``reason="unresolved_tool_reference"``,
  reporting the unresolved connector name, and no workflow row is created
  (Req 5.4).

Uses an in-memory fake DB client exposing the subset of the combined
``ToolClient``/``WorkflowClient``/``AgentTriggerClient`` surface that
``instantiate_switchboard`` depends on (``get_tools_for_organization``,
``create_tool``, ``archive_tool``, ``assert_trigger_paths_available``,
``create_workflow``, ``sync_triggers_for_workflow``), so no real database is
touched.

Design references:
- ``design.md`` -> "Template_Instantiator", "Error Handling"
- ``requirements.md`` -> Requirements 3.4, 5.4

Task: 9.5.
"""

from __future__ import annotations

import itertools
import uuid

import pytest

from api.db.models import ToolModel, WorkflowModel, WorkflowTemplates
from api.enums import ToolCategory, ToolStatus
from api.services.switchboard.enablement.instantiator import (
    SwitchboardInstantiationError,
    instantiate_switchboard,
)


class FakeInstantiatorDBClient:
    """In-memory stand-in for the combined DB client ``instantiate_switchboard``
    depends on.

    Mirrors ``get_tools_for_organization``, ``create_tool``, ``archive_tool``
    (``ToolClient``), ``assert_trigger_paths_available``,
    ``sync_triggers_for_workflow`` (``AgentTriggerClient``), and
    ``create_workflow`` (``WorkflowClient``), without touching a real
    database.
    """

    def __init__(self) -> None:
        self._tools: list[ToolModel] = []
        self._tool_id_counter = itertools.count(1)
        self._workflow_id_counter = itertools.count(1)
        self.create_workflow_calls: list[dict] = []
        self.sync_triggers_calls: list[dict] = []

    # -- ToolClient surface -------------------------------------------------

    async def get_tools_for_organization(
        self,
        organization_id: int,
        status: str | None = None,
        category: str | None = None,
    ) -> list[ToolModel]:
        results = [t for t in self._tools if t.organization_id == organization_id]
        if status:
            status_list = [s.strip() for s in status.split(",")]
            results = [t for t in results if t.status in status_list]
        if category:
            results = [t for t in results if t.category == category]
        return list(results)

    async def create_tool(
        self,
        organization_id: int,
        user_id: int,
        name: str,
        definition: dict,
        category: str = ToolCategory.HTTP_API.value,
        description: str | None = None,
        icon: str | None = None,
        icon_color: str | None = None,
    ) -> ToolModel:
        tool = ToolModel(
            id=next(self._tool_id_counter),
            tool_uuid=str(uuid.uuid4()),
            organization_id=organization_id,
            created_by=user_id,
            name=name,
            description=description,
            category=category,
            icon=icon,
            icon_color=icon_color,
            definition=definition,
            status=ToolStatus.ACTIVE.value,
        )
        self._tools.append(tool)
        return tool

    async def archive_tool(self, tool_uuid: str, organization_id: int) -> bool:
        for tool in self._tools:
            if (
                tool.tool_uuid == tool_uuid
                and tool.organization_id == organization_id
                and tool.status != ToolStatus.ARCHIVED.value
            ):
                tool.status = ToolStatus.ARCHIVED.value
                return True
        return False

    # -- AgentTriggerClient surface ------------------------------------------

    async def assert_trigger_paths_available(
        self, trigger_paths: list[str], exclude_workflow_id: int | None = None
    ) -> None:
        # No pre-existing triggers in this fake, so nothing ever conflicts.
        return None

    async def sync_triggers_for_workflow(
        self, workflow_id: int, organization_id: int, trigger_paths: list[str]
    ) -> None:
        self.sync_triggers_calls.append(
            {
                "workflow_id": workflow_id,
                "organization_id": organization_id,
                "trigger_paths": list(trigger_paths),
            }
        )

    # -- WorkflowClient surface -----------------------------------------------

    async def create_workflow(
        self,
        name: str,
        workflow_definition: dict,
        user_id: int,
        organization_id: int | None = None,
    ) -> WorkflowModel:
        self.create_workflow_calls.append(
            {
                "name": name,
                "workflow_definition": workflow_definition,
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )
        workflow = WorkflowModel(
            id=next(self._workflow_id_counter),
            name=name,
            workflow_definition=workflow_definition,
            user_id=user_id,
            organization_id=organization_id,
        )
        return workflow


def _two_start_nodes_template_json() -> dict:
    """A minimal ``template_json`` that fails ``WorkflowGraph`` validation.

    Two ``startCall`` nodes (each defaulting ``is_start=True``) with no edges:
    valid per-node data and referential integrity (so it passes the
    ``ReactFlowDTO``/reconciliation stages), but ``WorkflowGraph`` rejects any
    workflow with more than one start node — exercising the
    ``graph_validation_failed`` branch of instantiation (Req 3.4). Neither
    node references any tool, so reconciliation is a no-op.
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


def _unresolved_connector_template_json() -> dict:
    """A ``template_json`` whose only node references a connector name that
    is never provisioned (Req 5.4).

    Single, otherwise-valid ``startCall`` node so the only failure mode
    exercised is the unresolved tool reference, not a graph-shape issue.
    """
    return {
        "nodes": [
            {
                "id": "start_1",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {
                    "name": "Start 1",
                    "prompt": "Greet the caller.",
                    "tool_uuids": ["nonexistent_connector"],
                },
            },
        ],
        "edges": [],
    }


async def test_invalid_reconciled_dto_rejected_and_no_workflow_created():
    """Req 3.4: a reconciled definition that fails Graph_Validator validation
    is rejected with a structured SwitchboardInstantiationError carrying
    non-empty errors, and no workflow row is ever created."""
    template = WorkflowTemplates(
        id=1,
        template_name="spinsci-switchboard",
        template_description="SpinSci AI Virtual Switchboard (inbound).",
        template_json=_two_start_nodes_template_json(),
    )
    client = FakeInstantiatorDBClient()

    with pytest.raises(SwitchboardInstantiationError) as exc_info:
        await instantiate_switchboard(
            template=template,
            organization_id=1,
            user_id=1,
            workflow_name="My Switchboard",
            db_client=client,
        )

    assert exc_info.value.reason in {
        "graph_validation_failed",
        "gate_by_scoping_violation",
        "invalid_reconciled_definition",
    }
    assert exc_info.value.errors

    assert client.create_workflow_calls == []


async def test_unresolved_tool_reference_rejected_and_no_workflow_created():
    """Req 5.4: a node naming a connector tool that was not provisioned for
    the organization rejects instantiation with
    reason="unresolved_tool_reference", reporting the unresolved connector
    name, and no workflow row is created."""
    template = WorkflowTemplates(
        id=2,
        template_name="spinsci-switchboard",
        template_description="SpinSci AI Virtual Switchboard (inbound).",
        template_json=_unresolved_connector_template_json(),
    )
    client = FakeInstantiatorDBClient()

    with pytest.raises(SwitchboardInstantiationError) as exc_info:
        await instantiate_switchboard(
            template=template,
            organization_id=1,
            user_id=1,
            workflow_name="My Switchboard",
            db_client=client,
        )

    assert exc_info.value.reason == "unresolved_tool_reference"
    assert exc_info.value.errors
    assert any("nonexistent_connector" in error for error in exc_info.value.errors)

    assert client.create_workflow_calls == []
