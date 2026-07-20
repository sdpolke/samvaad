"""Per-cluster tool scoping validation for the SpinSci switchboard (Req 1.7, 9.2).

Provides validation and application of the gate-by-scoping design principle:
the ``transfer`` and ``route_metadata_resolution`` tools are attached ONLY to
Routing-cluster nodes. Because a node can only invoke tools listed in its own
``tool_uuids``, the engine cannot transfer before the graph reaches Routing.

This makes GATE-AUTH (Req 9.2, POC-10) a structural property, not a runtime
check that could be bypassed.

Design references:
- ``design.md`` → "Gate-by-scoping"
- ``requirements.md`` → Requirements 1.7, 9.2

Requirements: 1.7, 9.2.
"""

from __future__ import annotations

from typing import Sequence

from api.services.switchboard.tools.base import ToolCluster
from api.services.switchboard.tools.registry import tools_for_cluster
from api.services.workflow.dto import RFNodeDTO

# Tools that must ONLY appear on Routing-cluster nodes (gate-by-scoping).
ROUTING_ONLY_TOOLS: frozenset[str] = frozenset({"transfer", "route_metadata_resolution"})


def _get_node_tool_uuids(node: RFNodeDTO) -> list[str]:
    """Extract the tool_uuids from a node, returning an empty list if None."""
    if hasattr(node.data, "tool_uuids") and node.data.tool_uuids is not None:
        return list(node.data.tool_uuids)
    return []


def validate_tool_scoping(nodes: Sequence[RFNodeDTO]) -> list[str]:
    """Verify the structural tool-scoping invariant across all nodes.

    The ``transfer`` and ``route_metadata_resolution`` tools must ONLY appear on
    Routing cluster nodes (identified by their node IDs starting with ``routing_``
    or by being in the Routing cluster's known node set).

    This function checks all provided nodes and returns a list of violation
    descriptions. An empty list means the invariant holds.

    Args:
        nodes: All nodes in the switchboard graph (or a subset to validate).

    Returns:
        A list of violation description strings. Empty if the invariant holds.
    """
    violations: list[str] = []

    for node in nodes:
        tool_uuids = _get_node_tool_uuids(node)
        if not tool_uuids:
            continue

        # A node is considered a "Routing node" if its ID starts with "routing_"
        is_routing_node = node.id.startswith("routing_")

        for tool_name in tool_uuids:
            if tool_name in ROUTING_ONLY_TOOLS and not is_routing_node:
                violations.append(
                    f"Node '{node.id}' has routing-only tool '{tool_name}' "
                    f"in its tool_uuids but is not a Routing cluster node. "
                    f"Gate-by-scoping invariant violated (Req 1.7, 9.2)."
                )

    return violations


def get_expected_tools_for_cluster(cluster: ToolCluster) -> list[str]:
    """Return the expected tool function names for a given cluster.

    Uses the tool registry to determine which tools should be available
    to nodes in the specified cluster.

    Args:
        cluster: The cluster type to get expected tools for.

    Returns:
        A sorted list of tool function names scoped to the cluster.
    """
    return sorted(tool.function_name for tool in tools_for_cluster(cluster))


def validate_node_tools_within_cluster(
    nodes: Sequence[RFNodeDTO],
    cluster: ToolCluster,
) -> list[str]:
    """Validate that nodes only have tools belonging to their cluster.

    Checks that every tool UUID on a node is one that the cluster is allowed to
    have according to the tool registry. Nodes with no tools (``tool_uuids=None``)
    are valid — not all nodes in a cluster need tools.

    Args:
        nodes: Nodes belonging to a single cluster.
        cluster: The cluster these nodes belong to.

    Returns:
        A list of violation descriptions. Empty if all tools are valid.
    """
    allowed_tools = set(get_expected_tools_for_cluster(cluster))
    violations: list[str] = []

    for node in nodes:
        tool_uuids = _get_node_tool_uuids(node)
        if not tool_uuids:
            continue

        for tool_name in tool_uuids:
            if tool_name not in allowed_tools:
                violations.append(
                    f"Node '{node.id}' in cluster '{cluster.value}' has tool "
                    f"'{tool_name}' which is not scoped to that cluster. "
                    f"Expected tools: {sorted(allowed_tools)}."
                )

    return violations


__all__ = [
    "ROUTING_ONLY_TOOLS",
    "get_expected_tools_for_cluster",
    "validate_node_tools_within_cluster",
    "validate_tool_scoping",
]
