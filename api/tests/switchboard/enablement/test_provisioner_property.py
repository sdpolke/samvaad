"""Property test for Connector_Tool_Provisioner fidelity and idempotence.

Uses an in-memory fake ``ToolClient`` to exercise ``provision_connector_tools``
across arbitrary organization ids and repeat-call counts, asserting that
provisioning is idempotent (no duplicate rows, stable ``tool_uuid``s) and
faithful (each provisioned ``ToolModel`` carries the requester's
``organization_id`` and a definition equal to
``ConnectorTool.to_tool_definition()`` plus the ``connector_name`` marker,
including the connector's declared ``clusters``/``sensitive_fields``).

Design references:
- ``design.md`` -> "Connector_Tool_Provisioner", "Property 3: Connector-tool
  provisioning fidelity and idempotence"
- ``requirements.md`` -> Requirements 4.1, 4.2, 4.3, 4.4

Task: 3.2.
"""

from __future__ import annotations

import asyncio
import itertools
import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from api.db.models import ToolModel
from api.enums import ToolCategory, ToolStatus
from api.services.switchboard.enablement.provisioner import (
    CONNECTOR_NAME_KEY,
    provision_connector_tools,
)
from api.services.switchboard.tools.registry import get_connector_tools


class FakeToolClient:
    """In-memory stand-in for ``ToolClient``.

    Mirrors the subset of the real client's interface that
    ``provision_connector_tools`` depends on (``get_tools_for_organization``,
    ``create_tool``), without touching a real database.
    """

    def __init__(self) -> None:
        self._tools: list[ToolModel] = []
        self._id_counter = itertools.count(1)

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
            id=next(self._id_counter),
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


async def _provision_n_times(
    tool_client: FakeToolClient, organization_id: int, user_id: int, n: int
) -> list[dict[str, str]]:
    """Call ``provision_connector_tools`` ``n`` times and return every
    returned ``{connector_name: tool_uuid}`` mapping, in call order."""
    name_to_uuid_runs: list[dict[str, str]] = []
    for _ in range(n):
        name_to_uuid = await provision_connector_tools(
            organization_id=organization_id,
            user_id=user_id,
            tool_client=tool_client,
        )
        name_to_uuid_runs.append(name_to_uuid)
    return name_to_uuid_runs


# Feature: switchboard-frontend-enablement, Property 3: Connector-tool
# provisioning fidelity and idempotence
# Validates: Requirements 4.1, 4.2, 4.3, 4.4
@given(
    organization_id=st.integers(min_value=1, max_value=1_000_000),
    n=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100, deadline=None)
def test_provisioning_is_faithful_and_idempotent(organization_id: int, n: int) -> None:
    asyncio.run(_check_provisioning_is_faithful_and_idempotent(organization_id, n))


async def _check_provisioning_is_faithful_and_idempotent(
    organization_id: int, n: int
) -> None:
    tool_client = FakeToolClient()
    user_id = 42

    name_to_uuid_runs = await _provision_n_times(
        tool_client, organization_id, user_id, n
    )

    connector_tools_by_name = {tool.name: tool for tool in get_connector_tools()}
    connector_names = set(connector_tools_by_name.keys())
    assert len(connector_names) == 11

    # Every call returns a mapping covering every connector tool.
    for name_to_uuid in name_to_uuid_runs:
        assert set(name_to_uuid.keys()) == connector_names

    # No duplicate rows were ever created for this organization, regardless of
    # how many times provisioning ran (idempotence).
    all_org_tools = [
        t for t in tool_client._tools if t.organization_id == organization_id
    ]
    assert len(all_org_tools) == 11

    # Exactly one *active* ToolModel per connector identity (11 total).
    active_tools = await tool_client.get_tools_for_organization(
        organization_id, status=ToolStatus.ACTIVE.value
    )
    assert len(active_tools) == 11

    tools_by_connector_name: dict[str, ToolModel] = {}
    for tool in active_tools:
        connector_name = (tool.definition or {}).get("switchboard", {}).get(
            CONNECTOR_NAME_KEY
        )
        assert connector_name is not None, "provisioned tool missing connector_name marker"
        assert connector_name not in tools_by_connector_name, (
            f"duplicate active ToolModel for connector {connector_name!r}"
        )
        tools_by_connector_name[connector_name] = tool

    assert set(tools_by_connector_name.keys()) == connector_names

    for connector_name, tool in tools_by_connector_name.items():
        connector = connector_tools_by_name[connector_name]

        # Requester's organization_id (Req 4.2).
        assert tool.organization_id == organization_id

        # Definition equal to ConnectorTool.to_tool_definition() plus the
        # connector_name marker (Req 4.1).
        expected_definition = connector.to_tool_definition()
        expected_definition["switchboard"][CONNECTOR_NAME_KEY] = connector_name
        assert tool.definition == expected_definition

        # Cluster scoping and sensitive_fields recorded correctly (Req 4.3).
        assert tool.definition["switchboard"]["clusters"] == sorted(
            c.value for c in connector.clusters
        )
        assert tool.definition["switchboard"]["sensitive_fields"] == sorted(
            connector.sensitive_fields
        )

        # Stable tool_uuid across every repeated provisioning call (Req 4.4) —
        # never regenerated, and equal to the ToolModel actually stored.
        first_uuid = name_to_uuid_runs[0][connector_name]
        assert tool.tool_uuid == first_uuid
        for name_to_uuid in name_to_uuid_runs:
            assert name_to_uuid[connector_name] == first_uuid
