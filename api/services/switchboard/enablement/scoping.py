"""UUID-aware gate-by-scoping validation for the SpinSci switchboard (fail-closed).

Once the switchboard's node ``tool_uuids`` are reconciled from connector
name-strings to real, organization-scoped tool UUIDs (see
``enablement/reconcile.py``), the structural gate-by-scoping check in
``api.services.switchboard.clusters.tool_scoping.validate_tool_scoping`` (which
matches on name-strings) can no longer be applied directly to the reconciled
graph. This module re-applies the same invariant against UUID-referencing
nodes by resolving each ``tool_uuid`` back to its connector identity via the
provisioned ``ToolModel`` definition marker
(``definition["switchboard"]["connector_name"]``).

Fail-closed (Req 11.5): if a node's ``tool_uuid`` cannot be positively
resolved to a known connector identity, the check cannot confirm the
invariant holds, so it is always treated as a violation — regardless of
whether the node is a Routing node.

Design references:
- ``design.md`` -> "Gate-by-scoping preservation"
- ``requirements.md`` -> Requirements 11.1, 11.2, 11.3, 11.4, 11.5

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5.
"""

from __future__ import annotations

from typing import Sequence

from api.services.switchboard.clusters.tool_scoping import ROUTING_ONLY_TOOLS
from api.services.workflow.dto import RFNodeDTO


def _get_node_tool_uuids(node: RFNodeDTO) -> list[str]:
    """Extract the tool_uuids from a node, returning an empty list if None."""
    if hasattr(node.data, "tool_uuids") and node.data.tool_uuids is not None:
        return list(node.data.tool_uuids)
    return []


def validate_uuid_tool_scoping(
    nodes: Sequence[RFNodeDTO],
    uuid_to_connector_name: dict[str, str],
) -> list[str]:
    """Verify the gate-by-scoping invariant against UUID-referencing nodes.

    For each node with ``tool_uuids``, each UUID is resolved to its connector
    name via ``uuid_to_connector_name``. If a UUID cannot be positively
    resolved, it is treated as a ``ROUTING_ONLY_TOOLS`` violation — fail-closed,
    regardless of the node's cluster (Req 11.5). If a resolved name is in
    ``ROUTING_ONLY_TOOLS`` and the node is not a Routing node (its id does not
    start with ``routing_``, matching
    ``api.services.switchboard.clusters.tool_scoping.validate_tool_scoping``),
    a violation is recorded (Req 11.2, 11.3, 11.4).

    Args:
        nodes: All nodes in the (reconciled) switchboard graph, or a subset
            to validate.
        uuid_to_connector_name: Mapping of provisioned ``tool_uuid`` to the
            connector name it identifies (see
            ``build_uuid_to_connector_name``).

    Returns:
        A list of violation description strings. Empty if the invariant
        holds for every node.
    """
    violations: list[str] = []

    for node in nodes:
        tool_uuids = _get_node_tool_uuids(node)
        if not tool_uuids:
            continue

        # A node is considered a "Routing node" if its ID starts with "routing_",
        # matching api.services.switchboard.clusters.tool_scoping.validate_tool_scoping.
        is_routing_node = node.id.startswith("routing_")

        for tool_uuid in tool_uuids:
            resolved_name = uuid_to_connector_name.get(tool_uuid)

            if resolved_name is None:
                # Fail-closed: an unresolvable tool identity cannot positively
                # confirm the invariant holds, so it is always a violation,
                # regardless of node type (Req 11.5).
                violations.append(
                    f"Node '{node.id}' has tool_uuid '{tool_uuid}' that could not "
                    f"be resolved to a known connector identity. Gate-by-scoping "
                    f"cannot be positively confirmed; failing closed (Req 11.5)."
                )
                continue

            if resolved_name in ROUTING_ONLY_TOOLS and not is_routing_node:
                violations.append(
                    f"Node '{node.id}' has routing-only tool '{resolved_name}' "
                    f"(tool_uuid '{tool_uuid}') in its tool_uuids but is not a "
                    f"Routing cluster node. Gate-by-scoping invariant violated "
                    f"(Req 11.2, 11.3, 11.4)."
                )

    return violations


def build_uuid_to_connector_name(tool_definitions: dict[str, dict]) -> dict[str, str]:
    """Build the ``tool_uuid`` -> connector-name resolution map.

    Reads ``definition["switchboard"]["connector_name"]`` off each provisioned
    ``ToolModel`` definition to build the map consumed by
    ``validate_uuid_tool_scoping``. Tool definitions missing the
    ``switchboard`` marker or its ``connector_name`` are skipped, which
    (by design) makes their UUIDs unresolvable to callers of
    ``validate_uuid_tool_scoping`` — preserving the fail-closed behavior.

    Args:
        tool_definitions: Mapping of ``tool_uuid`` to that tool's definition
            dict, as stored on the provisioned ``ToolModel``.

    Returns:
        A mapping of ``tool_uuid`` to connector name.
    """
    uuid_to_connector_name: dict[str, str] = {}

    for tool_uuid, definition in tool_definitions.items():
        switchboard_meta = definition.get("switchboard")
        if not switchboard_meta:
            continue

        connector_name = switchboard_meta.get("connector_name")
        if connector_name:
            uuid_to_connector_name[tool_uuid] = connector_name

    return uuid_to_connector_name


__all__ = [
    "build_uuid_to_connector_name",
    "validate_uuid_tool_scoping",
]
