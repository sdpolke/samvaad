"""Property-based test for the tenant-isolation invariant (task 9.3).

Covers Property 8 — Tenant-isolation invariant
(Requirements 3.1, 3.5, 4.2, 13.1, 13.2, 13.5).

For arbitrary pairs of distinct organization ids, instantiating the
switchboard for one org (``org_a``) must scope every record it creates to
exactly ``org_a``'s ``organization_id`` — never ``org_b``'s or any other
value — and an org-scoped listing/read against the *other* organization
(``org_b``) must return empty rather than any cross-org record, even when
the org filter is simulated as absent/bypassed against the same underlying
in-memory storage.

**Scope limitation (read this before extending):** ``instantiate_switchboard``
(``api/services/switchboard/enablement/instantiator.py``, task 9.1) creates
exactly two kinds of records: the workflow row (via
``db_client.create_workflow``) and the provisioned ``ToolModel`` rows (via
``provision_connector_tools`` -> ``db_client.create_tool``). It does **not**
create tool-binding or ``Switchboard_Config`` records itself — those are
separate seams introduced by later tasks (``Tool_Binding_Editor`` is task
12.3; ``Switchboard_Config`` is task 8, already implemented, but it is not
invoked by the instantiator). This test therefore asserts tenant isolation
only over what ``instantiate_switchboard`` actually creates: the workflow row
and the provisioned ``ToolModel`` rows. It does not invent binding/config
assertions that do not apply to this function.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 8: Tenant-isolation
  invariant"
- ``requirements.md`` -> Requirements 3.1, 3.5, 4.2, 13.1, 13.2, 13.5

Requirements: 3.1, 3.5, 4.2, 13.1, 13.2, 13.5.
"""

from __future__ import annotations

import asyncio
import itertools
import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from api.db.agent_trigger_client import TriggerPathConflictError
from api.db.models import ToolModel, WorkflowModel, WorkflowTemplates
from api.enums import ToolCategory, ToolStatus
from api.services.switchboard.enablement.instantiator import instantiate_switchboard
from api.services.switchboard.enablement.registrar import (
    SWITCHBOARD_TEMPLATE_DESCRIPTION,
    SWITCHBOARD_TEMPLATE_NAME,
)
from api.services.switchboard.enablement.serialize import (
    serialize_switchboard_template_json,
)


class FakeInstantiatorDBClient:
    """In-memory stand-in combining the ``ToolClient`` + ``WorkflowClient`` +
    ``AgentTriggerClient`` methods that ``instantiate_switchboard`` depends on:
    ``get_tools_for_organization``, ``create_tool``, ``archive_tool``,
    ``assert_trigger_paths_available``, ``create_workflow``, and
    ``sync_triggers_for_workflow``.

    Tools and workflows are stored keyed by ``organization_id`` internally
    (a flat list, filtered by the org-scoped methods below), but the fake
    also exposes ``all_tools_unfiltered()``/``all_workflows_unfiltered()`` —
    a raw internal view that ignores ``organization_id`` entirely. Tests use
    that raw view as an independent way to inspect *every* stored record
    regardless of org, so they can assert "every record created carries
    exactly the requesting organization_id" without relying on the org-scoped
    query itself (since that query being correct is precisely what is under
    test). The raw view also lets a test simulate "the org filter is
    bypassed" (Req 13.5): compare what the raw/unfiltered store contains
    against what the properly org-scoped accessor returns for a *different*
    org, to demonstrate the scoped accessor -- not the absence of data -- is
    what enforces isolation.
    """

    def __init__(self) -> None:
        self._tools: list[ToolModel] = []
        self._workflows: list[WorkflowModel] = []
        self._trigger_paths: set[str] = set()
        self._tool_id_counter = itertools.count(1)
        self._workflow_id_counter = itertools.count(1)

    # -- org-scoped accessors (what production code is meant to call) -----

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
        else:
            results = [t for t in results if t.status != ToolStatus.ARCHIVED.value]
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

    async def assert_trigger_paths_available(
        self, trigger_paths: list[str], exclude_workflow_id: int | None = None
    ) -> None:
        conflicts = [p for p in trigger_paths if p in self._trigger_paths]
        if conflicts:
            raise TriggerPathConflictError(conflicts)

    async def create_workflow(
        self,
        name: str,
        workflow_definition: dict,
        user_id: int,
        organization_id: int | None = None,
    ) -> WorkflowModel:
        workflow = WorkflowModel(
            id=next(self._workflow_id_counter),
            name=name,
            workflow_definition=workflow_definition,
            user_id=user_id,
            organization_id=organization_id,
        )
        self._workflows.append(workflow)
        return workflow

    async def sync_triggers_for_workflow(
        self, workflow_id: int, organization_id: int, trigger_paths: list[str]
    ) -> None:
        self._trigger_paths.update(trigger_paths)

    # -- unscoped/raw accessors (test-only "what if the filter were absent"
    # inspection surface — never called by production code) -------------

    def all_tools_unfiltered(self) -> list[ToolModel]:
        """Every tool ever stored, regardless of ``organization_id`` — the
        raw store an org-scoping bug would otherwise leak through."""
        return list(self._tools)

    def all_workflows_unfiltered(self) -> list[WorkflowModel]:
        """Every workflow ever stored, regardless of ``organization_id``."""
        return list(self._workflows)


# ---------------------------------------------------------------------------
# The real switchboard template — built once (serialization is validated and
# deterministic-shape, matching the pattern used by the other instantiator/
# reconciliation property tests) and reused across every generated example.
# ---------------------------------------------------------------------------


def _build_switchboard_template() -> WorkflowTemplates:
    template_json = serialize_switchboard_template_json()
    return WorkflowTemplates(
        id=1,
        template_name=SWITCHBOARD_TEMPLATE_NAME,
        template_description=SWITCHBOARD_TEMPLATE_DESCRIPTION,
        template_json=template_json,
    )


_TEMPLATE: WorkflowTemplates = _build_switchboard_template()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _st_distinct_org_pair(draw: st.DrawFn) -> tuple[int, int]:
    org_a = draw(st.integers(min_value=1, max_value=10_000))
    org_b = draw(
        st.integers(min_value=1, max_value=10_000).filter(lambda value: value != org_a)
    )
    return org_a, org_b


_st_user_id = st.integers(min_value=1, max_value=10_000)
_st_workflow_name = st.text(min_size=1, max_size=30)


async def _instantiate_for_org_a(
    org_a: int, org_b: int, user_id: int, workflow_name: str
) -> tuple[FakeInstantiatorDBClient, WorkflowModel]:
    client = FakeInstantiatorDBClient()
    workflow = await instantiate_switchboard(
        template=_TEMPLATE,
        organization_id=org_a,
        user_id=user_id,
        workflow_name=workflow_name,
        db_client=client,
    )
    return client, workflow


# Feature: switchboard-frontend-enablement, Property 8: Tenant-isolation invariant
@given(
    org_pair=_st_distinct_org_pair(),
    user_id=_st_user_id,
    workflow_name=_st_workflow_name,
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
def test_instantiation_scopes_every_created_record_to_the_requesting_org(
    org_pair: tuple[int, int], user_id: int, workflow_name: str
) -> None:
    """**Validates: Requirements 3.1, 3.5, 4.2, 13.1, 13.2, 13.5**

    Instantiating the switchboard for ``org_a`` scopes the created workflow
    row and every provisioned ``ToolModel`` row to exactly ``org_a`` (never
    ``org_b`` or any other value), a scoped listing/read for ``org_b``
    returns empty (no cross-org record), and — simulating the org filter
    being absent/bypassed — the raw unfiltered store is shown to actually
    contain ``org_a``'s rows even though the properly scoped accessor
    correctly withholds them from an ``org_b`` request (Req 13.5's
    "fails closed to empty" expectation).
    """
    org_a, org_b = org_pair
    assert org_a != org_b

    client, workflow = asyncio.run(
        _instantiate_for_org_a(org_a, org_b, user_id, workflow_name)
    )

    # ------------------------------------------------------------------
    # (a) The created workflow row carries exactly org_a's organization_id
    # (Req 3.1, 3.5, 13.1).
    # ------------------------------------------------------------------
    assert workflow.organization_id == org_a
    assert workflow.organization_id != org_b

    # ------------------------------------------------------------------
    # (b) Every provisioned ToolModel row -- inspected via the fake's
    # unfiltered internal store, independent of the org-scoped query under
    # test -- carries exactly org_a's organization_id (Req 3.1, 3.5, 4.2,
    # 13.1). This instantiator creates 11 connector tools per run.
    # ------------------------------------------------------------------
    all_tools = client.all_tools_unfiltered()
    assert len(all_tools) == 11
    for tool in all_tools:
        assert tool.organization_id == org_a
        assert tool.organization_id != org_b

    all_workflows = client.all_workflows_unfiltered()
    assert len(all_workflows) == 1
    assert all_workflows[0].organization_id == org_a

    # ------------------------------------------------------------------
    # (c) An org-scoped listing for org_a does find its own tools (sanity:
    # the scoped query is not just trivially empty for every org).
    # ------------------------------------------------------------------
    org_a_tools = asyncio.run(
        client.get_tools_for_organization(org_a, status=ToolStatus.ACTIVE.value)
    )
    assert len(org_a_tools) == 11

    # ------------------------------------------------------------------
    # (d) An org-scoped listing/read for org_b -- who had nothing
    # instantiated for it in this run -- returns empty rather than any
    # cross-org record (Req 13.2, 13.5).
    # ------------------------------------------------------------------
    org_b_tools = asyncio.run(
        client.get_tools_for_organization(org_b, status=ToolStatus.ACTIVE.value)
    )
    assert org_b_tools == []

    # ------------------------------------------------------------------
    # (e) Simulated "org filter bypassed" scenario (Req 13.5): the raw,
    # unfiltered store genuinely contains org_a's rows (the leak this
    # scenario is guarding against is real, not vacuous) ...
    # ------------------------------------------------------------------
    assert any(tool.organization_id == org_a for tool in all_tools)
    # ... yet none of those rows carry org_b's id, and the properly
    # org-scoped accessor -- unlike an unscoped/bypassed listing would --
    # still returns empty for org_b even though org_a's data exists
    # side-by-side with it in the same underlying store. This demonstrates
    # the scoped accessor, not the absence of data, is what enforces
    # isolation and fails closed to empty.
    assert not any(tool.organization_id == org_b for tool in all_tools)
    assert org_b_tools == [] and len(all_tools) > 0
