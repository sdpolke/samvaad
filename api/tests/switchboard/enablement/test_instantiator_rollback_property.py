"""Property-based test for instantiation atomic rollback (task 9.4).

Covers Property 9 — Instantiation atomic rollback (Requirements 3.6).

``instantiate_switchboard`` (``api/services/switchboard/enablement/instantiator.py``,
task 9.1) provisions 11 connector tools for the organization (step 1) *before*
attempting reconciliation, validation, and persistence (steps 2-6). Any
failure in steps 2-6 rolls back exactly the tool rows newly created during
that run (archiving them) before re-raising a structured
``SwitchboardInstantiationError`` (Req 3.6).

This test parametrizes failure injection across each of those post-
provisioning steps (reconciliation, graph/scoping validation, workflow
creation) using an in-memory fake DB client and crafted ``template_json``
inputs, asserting that after each injected failure:

- no workflow row was created, and
- every tool row the fake actually created during that run has been rolled
  back (archived) — i.e. no *active* org-scoped artifact survives the
  failed run.

**Known limitation (documented, not hidden):** a failure *during* step 1
itself (provisioning) is NOT covered by the rollback net above, because
``provision_connector_tools`` (``provisioner.py``) iterates its 11 connector
tools sequentially and does not report which of them it managed to create
before raising — see the ``KNOWN LIMITATION`` comment in
``instantiate_switchboard``. Tool rows created before such a mid-loop
failure remain ACTIVE (un-rolled-back). This is exercised separately, below,
by ``test_provisioning_failure_does_not_roll_back_tools_created_before_it``,
which is deliberately excluded from the parametrized "atomic rollback"
scenarios since it demonstrates the documented exception to the guarantee,
not the guarantee itself.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 9: Instantiation
  atomic rollback"
- ``requirements.md`` -> Requirement 3.6

Requirements: 3.6.
"""

from __future__ import annotations

import itertools
import uuid
from typing import Callable, Optional

import pytest

from api.db.models import ToolModel, WorkflowModel, WorkflowTemplates
from api.enums import ToolCategory, ToolStatus
from api.services.switchboard.enablement.instantiator import (
    SwitchboardInstantiationError,
    instantiate_switchboard,
)


class FakeInstantiatorDBClient:
    """In-memory stand-in for the combined ``ToolClient`` + ``WorkflowClient``
    + ``AgentTriggerClient`` surface ``instantiate_switchboard`` depends on.

    Exposes ``all_tools_unfiltered()``/``all_workflows_unfiltered()`` raw
    accessors (mirroring the pattern in
    ``test_instantiator_tenant_isolation_property.py``) to inspect the true
    internal state of the fake's storage regardless of organization or
    status, so tests can assert "no active artifact survives the failed
    run" independent of whatever org-scoped query is under test.

    Two constructor-level failure-injection knobs are provided, both
    defaulted off:

    - ``fail_create_tool_after_n``: when set, the ``n``-th successful
      ``create_tool`` call succeeds normally, but the very next call raises
      before creating/storing a tool — simulating a mid-provisioning-loop
      DB failure (used only by the separate known-limitation test below).
    - ``should_fail_create_workflow``: when true, ``create_workflow`` always
      raises instead of persisting a workflow row — simulating a DB failure
      at the final persistence step (Req 3.6's "workflow creation" failure
      scenario).
    """

    def __init__(
        self,
        *,
        fail_create_tool_after_n: Optional[int] = None,
        should_fail_create_workflow: bool = False,
    ) -> None:
        self._tools: list[ToolModel] = []
        self._workflows: list[WorkflowModel] = []
        self._tool_id_counter = itertools.count(1)
        self._workflow_id_counter = itertools.count(1)
        self._fail_create_tool_after_n = fail_create_tool_after_n
        self._tool_create_calls = 0
        self._should_fail_create_workflow = should_fail_create_workflow

    # -- ToolClient surface -------------------------------------------------

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
        if (
            self._fail_create_tool_after_n is not None
            and self._tool_create_calls >= self._fail_create_tool_after_n
        ):
            raise RuntimeError(
                f"Simulated DB failure creating connector tool "
                f"#{self._tool_create_calls + 1}"
            )

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
        self._tool_create_calls += 1
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
        self, trigger_paths: list[str], exclude_workflow_id: Optional[int] = None
    ) -> None:
        # No pre-existing triggers in this fake, so nothing ever conflicts.
        return None

    async def sync_triggers_for_workflow(
        self, workflow_id: int, organization_id: int, trigger_paths: list[str]
    ) -> None:
        return None

    # -- WorkflowClient surface -----------------------------------------------

    async def create_workflow(
        self,
        name: str,
        workflow_definition: dict,
        user_id: int,
        organization_id: Optional[int] = None,
    ) -> WorkflowModel:
        if self._should_fail_create_workflow:
            raise RuntimeError("Simulated DB failure creating workflow")

        workflow = WorkflowModel(
            id=next(self._workflow_id_counter),
            name=name,
            workflow_definition=workflow_definition,
            user_id=user_id,
            organization_id=organization_id,
        )
        self._workflows.append(workflow)
        return workflow

    # -- unscoped/raw accessors (test-only inspection surface) --------------

    def all_tools_unfiltered(self) -> list[ToolModel]:
        """Every tool ever stored, regardless of ``organization_id``/status."""
        return list(self._tools)

    def all_workflows_unfiltered(self) -> list[WorkflowModel]:
        """Every workflow ever stored, regardless of ``organization_id``."""
        return list(self._workflows)


# ---------------------------------------------------------------------------
# Failure-injection scenario templates
# ---------------------------------------------------------------------------


def _unresolved_connector_template_json() -> dict:
    """Reconciliation failure: a node's ``tool_uuids`` references a connector
    name that is never provisioned -> ``UnresolvedToolReference`` ->
    ``reason="unresolved_tool_reference"`` (Req 5.4). Mirrors the pattern in
    ``test_instantiator.py``."""
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


def _two_start_nodes_template_json() -> dict:
    """Graph validation failure: two ``startCall`` nodes with no tool
    references and no edges -- passes reconciliation trivially (no
    ``tool_uuids`` anywhere), but ``WorkflowGraph`` rejects more than one
    start node -> ``reason="graph_validation_failed"``. Mirrors the pattern
    in ``test_instantiator.py``."""
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


def _gate_by_scoping_template_json() -> dict:
    """Gate-by-scoping failure: a non-Routing ``agentNode`` lists the real,
    provisioned routing-only connector ``"transfer"`` in its ``tool_uuids``,
    but its node id does not start with ``routing_`` -> passes reconciliation
    (``transfer`` IS a provisioned connector name) and graph validation
    (single start node, one valid edge, no cardinality violations), but fails
    the UUID-aware gate-by-scoping check ->
    ``reason="gate_by_scoping_violation"`` (Req 11.2, 11.3, 11.4)."""
    return {
        "nodes": [
            {
                "id": "start_1",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {"name": "Start 1", "prompt": "Greet the caller."},
            },
            {
                "id": "agent_1",
                "type": "agentNode",
                "position": {"x": 100, "y": 0},
                "data": {
                    "name": "Agent 1",
                    "prompt": "Do something with transfer.",
                    "tool_uuids": ["transfer"],
                },
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "start_1",
                "target": "agent_1",
                "data": {"label": "Next", "condition": "always"},
            },
        ],
    }


def _trivial_template_json() -> dict:
    """A minimal, otherwise-valid template (single start node, no tool
    references, no edges) used for the workflow-creation-failure scenario,
    where the injected failure is the fake client's ``create_workflow``
    itself rather than anything in the template."""
    return {
        "nodes": [
            {
                "id": "start_1",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {"name": "Start 1", "prompt": "Greet the caller."},
            },
        ],
        "edges": [],
    }


def _build_template(template_json: dict, *, template_id: int) -> WorkflowTemplates:
    return WorkflowTemplates(
        id=template_id,
        template_name="spinsci-switchboard",
        template_description="SpinSci AI Virtual Switchboard (inbound).",
        template_json=template_json,
    )


# ---------------------------------------------------------------------------
# Property 9: Instantiation atomic rollback
# ---------------------------------------------------------------------------

# Each scenario: (name, template_json builder, expected reason, client factory).
_ROLLBACK_SCENARIOS: list[tuple[str, Callable[[], dict], str, Callable[[], FakeInstantiatorDBClient]]] = [
    (
        "reconciliation_failure",
        _unresolved_connector_template_json,
        "unresolved_tool_reference",
        FakeInstantiatorDBClient,
    ),
    (
        "graph_validation_failure",
        _two_start_nodes_template_json,
        "graph_validation_failed",
        FakeInstantiatorDBClient,
    ),
    (
        "gate_by_scoping_failure",
        _gate_by_scoping_template_json,
        "gate_by_scoping_violation",
        FakeInstantiatorDBClient,
    ),
    (
        "workflow_creation_failure",
        _trivial_template_json,
        "unexpected_instantiation_failure",
        lambda: FakeInstantiatorDBClient(should_fail_create_workflow=True),
    ),
]


# Feature: switchboard-frontend-enablement, Property 9: Instantiation atomic rollback
@pytest.mark.parametrize(
    "scenario_name, build_template_json, expected_reason, make_client",
    _ROLLBACK_SCENARIOS,
    ids=[scenario[0] for scenario in _ROLLBACK_SCENARIOS],
)
async def test_failure_after_provisioning_rolls_back_newly_created_tools(
    scenario_name: str,
    build_template_json: Callable[[], dict],
    expected_reason: str,
    make_client: Callable[[], FakeInstantiatorDBClient],
) -> None:
    """**Validates: Requirements 3.6**

    For a failure injected at each post-provisioning step (reconciliation,
    graph/scoping validation, workflow creation), instantiation raises the
    expected structured error, no workflow row is created, and every tool
    row created during the run has been rolled back (archived) -- i.e. no
    active org-scoped artifact from this failed run remains.
    """
    client = make_client()
    template = _build_template(build_template_json(), template_id=1)

    with pytest.raises(SwitchboardInstantiationError) as exc_info:
        await instantiate_switchboard(
            template=template,
            organization_id=1,
            user_id=1,
            workflow_name=f"My Switchboard ({scenario_name})",
            db_client=client,
        )

    assert exc_info.value.reason == expected_reason

    # (a) No workflow row was ever created (equals the pre-instantiation
    # state -- zero workflows -- for every failure mode).
    assert client.all_workflows_unfiltered() == []

    # (b) All 11 connector tools are always provisioned in step 1 regardless
    # of the downstream failure mode (provisioning itself succeeds in every
    # scenario here -- the injected failure is always in a later step), so
    # every one of them must have been rolled back (archived) by the single
    # rollback net in `instantiate_switchboard` (Req 3.6). No *active* tool
    # row survives the failed run.
    all_tools = client.all_tools_unfiltered()
    assert len(all_tools) == 11
    assert all(tool.status == ToolStatus.ARCHIVED.value for tool in all_tools), (
        f"[{scenario_name}] expected every newly-created tool to be rolled "
        f"back (archived) after the injected failure, but found active "
        f"tools: {[t.tool_uuid for t in all_tools if t.status != ToolStatus.ARCHIVED.value]}"
    )


# ---------------------------------------------------------------------------
# Known limitation: a mid-provisioning-loop failure is NOT rolled back.
#
# This is deliberately a separate, clearly-labeled test -- not part of the
# parametrized "atomic rollback" scenarios above -- because it documents the
# one gap in the atomic-rollback guarantee that instantiator.py's own
# "KNOWN LIMITATION" comment (step 1's except-block) calls out: a failure
# *during* provisioning itself, rather than after it, leaves whatever tools
# were already created by that same provisioning call un-rolled-back, since
# `provision_connector_tools` does not report partial progress to its caller
# on failure. This test asserts the ACTUAL current behavior, not a stronger
# guarantee the implementation does not provide.
# ---------------------------------------------------------------------------


async def test_provisioning_failure_does_not_roll_back_tools_created_before_it() -> None:
    """KNOWN LIMITATION (see ``instantiate_switchboard``'s step-1 except
    block docstring/comment): when provisioning itself fails partway through
    its 11-connector loop, the tools created before the failing call are
    NOT rolled back -- there is no rollback net for step 1, because
    `provision_connector_tools` doesn't expose which tools it already
    created when it raises. This is a documented exception to Req 3.6's
    atomic-rollback guarantee, not a violation of it (the guarantee only
    covers failures *after* step 1 completes).

    This test injects a failure on the 5th ``create_tool`` call (after 4
    succeed), asserts ``reason="tool_provisioning_failed"``, no workflow row
    is created, and -- documenting the limitation rather than hiding it --
    the 4 tools created before the injected failure remain ACTIVE
    (un-rolled-back) in the fake's raw store.
    """
    client = FakeInstantiatorDBClient(fail_create_tool_after_n=4)
    template = _build_template(_trivial_template_json(), template_id=1)

    with pytest.raises(SwitchboardInstantiationError) as exc_info:
        await instantiate_switchboard(
            template=template,
            organization_id=1,
            user_id=1,
            workflow_name="My Switchboard (mid-provisioning failure)",
            db_client=client,
        )

    assert exc_info.value.reason == "tool_provisioning_failed"
    assert client.all_workflows_unfiltered() == []

    all_tools = client.all_tools_unfiltered()
    # Exactly the 4 tools created before the injected failure exist.
    assert len(all_tools) == 4
    # KNOWN LIMITATION: none of them were rolled back -- they remain ACTIVE,
    # not archived, because a step-1 failure never reaches `_rollback(...)`.
    assert all(tool.status == ToolStatus.ACTIVE.value for tool in all_tools)
