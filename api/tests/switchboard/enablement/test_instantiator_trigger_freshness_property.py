"""Property-based test for trigger identifier freshness (task 9.2).

Covers Property 5 — Trigger identifier freshness (Requirements 3.2).

For all instantiations of the switchboard template, every trigger node
identifier in the created workflow is freshly minted and differs from the
corresponding identifier in the source template, so no created workflow
collides with existing triggers.

The real assembled switchboard graph (``build_switchboard_reactflow_dto()``)
contains no ``trigger`` nodes — the graph's inbound entry point is the
``startCall`` node (``is_start=True``); the conceptual trigger→startCall link
noted in ``graph.py`` is realized without a physical trigger node. To exercise
this property against "switchboard-derived template definitions with trigger
nodes" (per the task), this test builds a structure-preserving perturbation
of the real graph that adds one or more ``trigger`` nodes with an initial
``trigger_path``, mirroring the perturbation pattern used by task 2.2's
round-trip property test (see ``test_registrar_roundtrip_property.py``).

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 5: Trigger
  identifier freshness"
- ``requirements.md`` -> Requirement 3.2

Requirements: 3.2.
"""

from __future__ import annotations

import asyncio
import itertools
import string
import uuid
from typing import Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from api.db.models import ToolModel, WorkflowModel
from api.enums import ToolCategory, ToolStatus
from api.services.switchboard.enablement.instantiator import instantiate_switchboard
from api.services.switchboard.graph import build_switchboard_reactflow_dto
from api.services.workflow.dto import Position, ReactFlowDTO, RFNodeDTO, TriggerNodeData

# ---------------------------------------------------------------------------
# Real assembled switchboard DTO — the trigger-node perturbation is built on
# top of this so the property exercises the actual switchboard shape rather
# than an invented graph.
# ---------------------------------------------------------------------------

_BASE_DTO: ReactFlowDTO = build_switchboard_reactflow_dto()

assert not any(n.type == "trigger" for n in _BASE_DTO.nodes), (
    "Expected the real assembled switchboard graph to contain no trigger "
    "nodes (the inbound entry point is the startCall node); if this "
    "assumption changes, the perturbation below may need to be revisited."
)


def _build_trigger_node(node_id: str, initial_trigger_path: str) -> RFNodeDTO:
    """Build a ``trigger`` node with a caller-supplied initial ``trigger_path``.

    Trigger nodes have ``max_incoming=0`` and no outgoing-edge constraint, so
    an unconnected trigger node added alongside the real graph's nodes/edges
    is structure-preserving: it never violates ``WorkflowGraph`` cardinality
    rules for any other node type.
    """
    return RFNodeDTO(
        id=node_id,
        type="trigger",
        position=Position(x=0, y=0),
        data=TriggerNodeData(
            name="PBT Trigger",
            trigger_path=initial_trigger_path,
            enabled=True,
        ),
    )


def _build_template_json_with_triggers(trigger_paths: list[str]) -> dict:
    """Return switchboard ``template_json`` with one added trigger node per
    entry in ``trigger_paths``, each carrying that entry as its initial
    ``trigger_path``."""
    trigger_nodes = [
        _build_trigger_node(f"pbt_trigger_{idx}", trigger_path)
        for idx, trigger_path in enumerate(trigger_paths)
    ]
    dto_with_triggers = ReactFlowDTO(
        nodes=[*_BASE_DTO.nodes, *trigger_nodes], edges=_BASE_DTO.edges
    )
    return dto_with_triggers.model_dump(mode="json")


class _FakeTemplate:
    """Minimal ``WorkflowTemplates``-like stand-in.

    ``instantiate_switchboard`` only reads ``template.template_json`` off the
    template argument, so a lightweight stand-in (rather than a real
    ``WorkflowTemplates`` row) is sufficient.
    """

    def __init__(self, template_json: dict) -> None:
        self.id = 1
        self.template_name = "spinsci-switchboard"
        self.template_json = template_json


class FakeSwitchboardDBClient:
    """In-memory fake combining the ``ToolClient`` + ``WorkflowClient`` +
    ``AgentTriggerClient`` methods ``instantiate_switchboard`` depends on.

    Each Hypothesis example constructs a fresh instance so instantiation
    state never leaks across examples.
    """

    def __init__(self) -> None:
        self._tools: list[ToolModel] = []
        self._tool_id_counter = itertools.count(1)
        self._workflow_id_counter = itertools.count(1)
        self.created_workflows: list[WorkflowModel] = []

    # -- ToolClient-shaped methods -----------------------------------
    async def get_tools_for_organization(
        self,
        organization_id: int,
        status: Optional[str] = None,
        category: Optional[str] = None,
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
        description: Optional[str] = None,
        icon: Optional[str] = None,
        icon_color: Optional[str] = None,
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

    # -- AgentTriggerClient-shaped methods -----------------------------
    async def assert_trigger_paths_available(
        self, trigger_paths: list[str], exclude_workflow_id: Optional[int] = None
    ) -> None:
        # Fresh fake per example, no pre-existing triggers to conflict with.
        return None

    async def sync_triggers_for_workflow(
        self, *, workflow_id: int, organization_id: int, trigger_paths: list[str]
    ) -> None:
        return None

    # -- WorkflowClient-shaped methods ---------------------------------
    async def create_workflow(
        self,
        name: str,
        workflow_definition: dict,
        user_id: int,
        organization_id: int = None,
    ) -> WorkflowModel:
        workflow = WorkflowModel(
            id=next(self._workflow_id_counter),
            name=name,
            workflow_definition=workflow_definition,
            user_id=user_id,
            organization_id=organization_id,
        )
        self.created_workflows.append(workflow)
        return workflow


def _collect_trigger_paths_by_node_id(definition: dict) -> dict[str, str | None]:
    """Map ``node_id -> trigger_path`` for every ``trigger`` node in a
    workflow definition dict."""
    result: dict[str, str | None] = {}
    for node in definition.get("nodes", []):
        if node.get("type") == "trigger":
            result[node["id"]] = node.get("data", {}).get("trigger_path")
    return result


# ---------------------------------------------------------------------------
# Property 5: Trigger identifier freshness
# ---------------------------------------------------------------------------


_st_workflow_name = st.text(
    alphabet=string.ascii_letters + string.digits + " -_",
    min_size=1,
    max_size=30,
)


# Feature: switchboard-frontend-enablement, Property 5: Trigger identifier freshness
@given(
    organization_id=st.integers(min_value=1, max_value=1_000_000),
    user_id=st.integers(min_value=1, max_value=1_000_000),
    workflow_name=_st_workflow_name,
    trigger_paths=st.lists(
        st.uuids().map(str), min_size=1, max_size=3, unique=True
    ),
)
@settings(max_examples=100, deadline=None)
def test_trigger_identifiers_are_regenerated_on_instantiation(
    organization_id: int,
    user_id: int,
    workflow_name: str,
    trigger_paths: list[str],
) -> None:
    """Every trigger node identifier in the instantiated definition differs
    from the corresponding identifier in the source template.

    **Validates: Requirements 3.2**
    """
    # Feature: switchboard-frontend-enablement, Property 5: Trigger identifier freshness
    asyncio.run(
        _check_trigger_identifiers_are_regenerated(
            organization_id, user_id, workflow_name, trigger_paths
        )
    )


async def _check_trigger_identifiers_are_regenerated(
    organization_id: int,
    user_id: int,
    workflow_name: str,
    trigger_paths: list[str],
) -> None:
    template_json = _build_template_json_with_triggers(trigger_paths)
    template = _FakeTemplate(template_json)

    # Fresh fake db_client per example — isolated state, no cross-example
    # tool/workflow/trigger leakage.
    db_client = FakeSwitchboardDBClient()

    source_trigger_paths = _collect_trigger_paths_by_node_id(template_json)
    assert set(source_trigger_paths.values()) == set(trigger_paths)

    workflow = await instantiate_switchboard(
        template=template,
        organization_id=organization_id,
        user_id=user_id,
        workflow_name=workflow_name,
        db_client=db_client,
    )

    instantiated_trigger_paths = _collect_trigger_paths_by_node_id(
        workflow.workflow_definition
    )

    # Same set of trigger node ids survives instantiation (only the
    # trigger_path values are regenerated, per regenerate_trigger_uuids).
    assert set(instantiated_trigger_paths.keys()) == set(source_trigger_paths.keys())

    for node_id, source_path in source_trigger_paths.items():
        instantiated_path = instantiated_trigger_paths[node_id]
        assert instantiated_path is not None
        # Every trigger node identifier in the instantiated definition
        # differs from the corresponding identifier in the source template.
        assert instantiated_path != source_path

    # The regenerated trigger_paths are themselves distinct from one another
    # (regenerate_trigger_uuids mints a fresh uuid4 per trigger node).
    assert len(set(instantiated_trigger_paths.values())) == len(
        instantiated_trigger_paths
    )
