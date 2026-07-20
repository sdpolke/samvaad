"""Unit test confirming provisioned tools are listed by the ToolSelector-facing
query against the real test database.

Uses the real ``db_session``/``async_session`` fixtures (transaction-rolled-back
test DB isolation) rather than the in-memory fake ``ToolClient`` used by the
property test (task 3.2), to confirm the actual DB-backed
``get_tools_for_organization`` query — the query the frontend ``ToolSelector``
relies on — surfaces every provisioned connector tool.

Design references:
- ``design.md`` -> "Connector_Tool_Provisioner"
- ``requirements.md`` -> Requirement 4.5

Task: 3.3.
"""

from __future__ import annotations

from api.db.models import OrganizationModel, UserModel
from api.enums import ToolStatus
from api.services.switchboard.enablement.provisioner import (
    CONNECTOR_NAME_KEY,
    provision_connector_tools,
)
from api.services.switchboard.tools.registry import get_connector_tools


async def test_provisioned_tools_are_listed_by_get_tools_for_organization(
    db_session, async_session
):
    """Req 4.5: once provisioned, all 11 connector tools are returned by
    ``db_client.get_tools_for_organization(org_id, status="active")`` — the
    query the frontend ``ToolSelector`` uses to list attachable tools."""
    org = OrganizationModel(provider_id="test-org-provisioner-listing")
    async_session.add(org)
    await async_session.flush()

    user = UserModel(
        provider_id="test-user-provisioner-listing",
        selected_organization_id=org.id,
    )
    async_session.add(user)
    await async_session.flush()

    name_to_uuid = await provision_connector_tools(
        organization_id=org.id,
        user_id=user.id,
        tool_client=db_session,
    )

    connector_names = {tool.name for tool in get_connector_tools()}
    assert len(connector_names) == 11
    assert set(name_to_uuid.keys()) == connector_names

    active_tools = await db_session.get_tools_for_organization(
        org.id, status=ToolStatus.ACTIVE.value
    )

    listed_connector_names = {
        (tool.definition or {}).get("switchboard", {}).get(CONNECTOR_NAME_KEY)
        for tool in active_tools
    }
    assert listed_connector_names == connector_names

    listed_uuids_by_connector_name = {
        (tool.definition or {}).get("switchboard", {}).get(CONNECTOR_NAME_KEY): (
            tool.tool_uuid
        )
        for tool in active_tools
    }
    for connector_name, tool_uuid in name_to_uuid.items():
        assert listed_uuids_by_connector_name[connector_name] == tool_uuid
