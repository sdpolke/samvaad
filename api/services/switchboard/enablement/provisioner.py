"""Connector_Tool_Provisioner: materialize connector tools as org-scoped tools.

Creates (or reuses) one organization-scoped ``ToolModel`` per connector tool
defined in ``api/services/switchboard/tools/registry.py``, using
``ConnectorTool.to_tool_definition()`` as the tool definition.

The provisioning identity is ``(organization_id, connector_name)``: before
creating a tool, existing active org tools are checked for a definition whose
``switchboard.connector_name`` marker matches, and that tool's ``tool_uuid`` is
reused rather than creating a duplicate (idempotent provisioning).

Design: "Connector_Tool_Provisioner". Requirements: 4.1, 4.2, 4.3, 4.4.
"""

from __future__ import annotations

from loguru import logger

from api.db.tool_client import ToolClient
from api.enums import ToolCategory, ToolStatus
from api.services.switchboard.tools.registry import get_connector_tools

#: Key under ``definition["switchboard"]`` that stores the stable connector
#: identity marker used for idempotent provisioning lookups (Req 4.4) and for
#: UUID -> connector-name resolution elsewhere in the enablement layer.
CONNECTOR_NAME_KEY = "connector_name"


async def provision_connector_tools(
    *, organization_id: int, user_id: int, tool_client: ToolClient
) -> dict[str, str]:
    """Create (or reuse) one org-scoped ``ToolModel`` per connector tool.

    For each :class:`~api.services.switchboard.tools.base.ConnectorTool` returned
    by ``get_connector_tools()``, builds the tool definition via
    ``ConnectorTool.to_tool_definition()`` (Req 4.1), augmented with the stable
    identity marker ``definition["switchboard"][CONNECTOR_NAME_KEY] = tool.name``.
    The definition already records ``switchboard.clusters`` and
    ``switchboard.sensitive_fields`` (Req 4.3).

    Before creating a tool, existing active tools for ``organization_id`` are
    checked for a definition whose ``switchboard.connector_name`` marker matches
    the connector's name; if found, that tool's ``tool_uuid`` is reused instead of
    creating a duplicate (Req 4.4). Otherwise a new organization-scoped tool is
    created via ``tool_client.create_tool(...)`` with
    ``category=ToolCategory.HTTP_API.value`` (Req 4.2).

    Args:
        organization_id: The requester's ``selected_organization_id``; every
            provisioned tool is scoped to this organization (Req 4.2).
        user_id: The requesting user, recorded as the tool's creator.
        tool_client: The org-scoped tool DB client used to look up and create
            tools.

    Returns:
        A mapping of ``{connector_name: tool_uuid}`` covering every connector
        tool in the registry, whether newly created or reused.
    """
    existing_tools = await tool_client.get_tools_for_organization(
        organization_id, status=ToolStatus.ACTIVE.value
    )
    existing_by_connector_name: dict[str, str] = {}
    for existing_tool in existing_tools:
        connector_name = (existing_tool.definition or {}).get("switchboard", {}).get(
            CONNECTOR_NAME_KEY
        )
        if connector_name:
            existing_by_connector_name[connector_name] = existing_tool.tool_uuid

    name_to_uuid: dict[str, str] = {}
    for tool in get_connector_tools():
        reused_uuid = existing_by_connector_name.get(tool.name)
        if reused_uuid:
            logger.debug(
                "Reusing provisioned tool for connector {} (org {})",
                tool.name,
                organization_id,
            )
            name_to_uuid[tool.name] = reused_uuid
            continue

        definition = tool.to_tool_definition()
        definition["switchboard"][CONNECTOR_NAME_KEY] = tool.name

        created_tool = await tool_client.create_tool(
            organization_id=organization_id,
            user_id=user_id,
            name=tool.name,
            definition=definition,
            category=ToolCategory.HTTP_API.value,
        )
        logger.info(
            "Provisioned connector tool {} as tool_uuid {} (org {})",
            tool.name,
            created_tool.tool_uuid,
            organization_id,
        )
        name_to_uuid[tool.name] = created_tool.tool_uuid

    return name_to_uuid


__all__ = ["CONNECTOR_NAME_KEY", "provision_connector_tools"]
