"""Tests for per-cluster tool scoping (gate-by-scoping invariant).

Validates that the structural tool-scoping invariant holds across all clusters:
- ``transfer`` and ``route_metadata_resolution`` exist ONLY on Routing nodes
- Each cluster's nodes only have tools belonging to that cluster
- The Routing cluster's Resolve Route node has the correct tools
- The Routing cluster's Transfer node has ``transfer``

This makes GATE-AUTH (Req 9.2, POC-10) a structural property enforced by
construction, not a runtime check that could be bypassed.

Requirements: 1.7, 9.2.
"""


from api.services.switchboard.clusters.after_hours import build_after_hours_cluster
from api.services.switchboard.clusters.authentication import (
    build_authentication_cluster,
)
from api.services.switchboard.clusters.business_hours import (
    build_business_hours_cluster,
)
from api.services.switchboard.clusters.greeting import build_greeting_cluster
from api.services.switchboard.clusters.routing import build_routing_cluster
from api.services.switchboard.clusters.tool_scoping import (
    get_expected_tools_for_cluster,
    validate_node_tools_within_cluster,
    validate_tool_scoping,
)
from api.services.switchboard.tools.base import ToolCluster
from api.services.workflow.dto import RFNodeDTO


def _all_cluster_nodes() -> list[RFNodeDTO]:
    """Build all 5 clusters and collect all nodes."""
    greeting = build_greeting_cluster()
    bh = build_business_hours_cluster()
    ah = build_after_hours_cluster()
    auth = build_authentication_cluster()
    routing = build_routing_cluster()

    all_nodes: list[RFNodeDTO] = []
    all_nodes.extend(greeting.nodes)
    all_nodes.extend(bh.nodes)
    all_nodes.extend(ah.nodes)
    all_nodes.extend(auth.nodes)
    all_nodes.extend(routing.nodes)
    return all_nodes


class TestGateByScoping:
    """Verify the gate-by-scoping invariant: transfer and route_metadata_resolution
    exist ONLY on Routing cluster nodes."""

    def test_no_non_routing_node_has_transfer(self):
        """No non-Routing node has 'transfer' in its tool_uuids."""
        all_nodes = _all_cluster_nodes()
        non_routing_nodes = [n for n in all_nodes if not n.id.startswith("routing_")]

        for node in non_routing_nodes:
            tool_uuids = (
                node.data.tool_uuids
                if hasattr(node.data, "tool_uuids") and node.data.tool_uuids
                else []
            )
            assert "transfer" not in tool_uuids, (
                f"Non-routing node '{node.id}' has 'transfer' tool — "
                f"gate-by-scoping invariant violated (Req 1.7, 9.2)"
            )

    def test_no_non_routing_node_has_route_metadata_resolution(self):
        """No non-Routing node has 'route_metadata_resolution' in its tool_uuids."""
        all_nodes = _all_cluster_nodes()
        non_routing_nodes = [n for n in all_nodes if not n.id.startswith("routing_")]

        for node in non_routing_nodes:
            tool_uuids = (
                node.data.tool_uuids
                if hasattr(node.data, "tool_uuids") and node.data.tool_uuids
                else []
            )
            assert "route_metadata_resolution" not in tool_uuids, (
                f"Non-routing node '{node.id}' has 'route_metadata_resolution' — "
                f"gate-by-scoping invariant violated (Req 1.7, 9.2)"
            )

    def test_validate_tool_scoping_returns_no_violations(self):
        """validate_tool_scoping() finds zero violations across all clusters."""
        all_nodes = _all_cluster_nodes()
        violations = validate_tool_scoping(all_nodes)
        assert violations == [], (
            f"Gate-by-scoping violations found: {violations}"
        )


class TestRoutingClusterToolPresence:
    """Verify the Routing cluster nodes have the expected tools."""

    def setup_method(self):
        self.routing = build_routing_cluster()

    def test_resolve_route_has_routing_intent_resolution(self):
        """The Resolve Route node HAS routing_intent_resolution."""
        resolve_node = next(
            n for n in self.routing.nodes if n.id == self.routing.resolve_route_id
        )
        assert resolve_node.data.tool_uuids is not None
        assert "routing_intent_resolution" in resolve_node.data.tool_uuids

    def test_resolve_route_has_route_metadata_resolution(self):
        """The Resolve Route node HAS route_metadata_resolution."""
        resolve_node = next(
            n for n in self.routing.nodes if n.id == self.routing.resolve_route_id
        )
        assert resolve_node.data.tool_uuids is not None
        assert "route_metadata_resolution" in resolve_node.data.tool_uuids

    def test_transfer_node_has_transfer(self):
        """The Transfer node HAS transfer in its tool_uuids."""
        transfer_node = next(
            n for n in self.routing.nodes if n.id == self.routing.transfer_id
        )
        assert transfer_node.data.tool_uuids is not None
        assert "transfer" in transfer_node.data.tool_uuids


class TestClusterToolContainment:
    """Verify no node in a non-Routing cluster has tools from another cluster."""

    def test_greeting_nodes_only_have_greeting_tools(self):
        """No Greeting node has tools that don't belong to the Greeting cluster."""
        greeting = build_greeting_cluster()
        allowed = set(get_expected_tools_for_cluster(ToolCluster.GREETING))

        for node in greeting.nodes:
            tool_uuids = (
                node.data.tool_uuids
                if hasattr(node.data, "tool_uuids") and node.data.tool_uuids
                else []
            )
            for tool in tool_uuids:
                assert tool in allowed, (
                    f"Greeting node '{node.id}' has tool '{tool}' which is not "
                    f"scoped to Greeting. Allowed: {sorted(allowed)}"
                )

    def test_business_hours_nodes_only_have_bh_tools(self):
        """No BH node has tools that don't belong to the Business Hours cluster."""
        bh = build_business_hours_cluster()
        allowed = set(get_expected_tools_for_cluster(ToolCluster.BUSINESS_HOURS))

        for node in bh.nodes:
            tool_uuids = (
                node.data.tool_uuids
                if hasattr(node.data, "tool_uuids") and node.data.tool_uuids
                else []
            )
            for tool in tool_uuids:
                assert tool in allowed, (
                    f"BH node '{node.id}' has tool '{tool}' which is not "
                    f"scoped to Business Hours. Allowed: {sorted(allowed)}"
                )

    def test_after_hours_nodes_only_have_ah_tools(self):
        """No AH node has tools that don't belong to the After Hours cluster."""
        ah = build_after_hours_cluster()
        allowed = set(get_expected_tools_for_cluster(ToolCluster.AFTER_HOURS))

        for node in ah.nodes:
            tool_uuids = (
                node.data.tool_uuids
                if hasattr(node.data, "tool_uuids") and node.data.tool_uuids
                else []
            )
            for tool in tool_uuids:
                assert tool in allowed, (
                    f"AH node '{node.id}' has tool '{tool}' which is not "
                    f"scoped to After Hours. Allowed: {sorted(allowed)}"
                )

    def test_authentication_nodes_only_have_auth_tools(self):
        """No Auth node has tools that don't belong to the Authentication cluster."""
        auth = build_authentication_cluster()
        allowed = set(get_expected_tools_for_cluster(ToolCluster.AUTHENTICATION))

        for node in auth.nodes:
            tool_uuids = (
                node.data.tool_uuids
                if hasattr(node.data, "tool_uuids") and node.data.tool_uuids
                else []
            )
            for tool in tool_uuids:
                assert tool in allowed, (
                    f"Auth node '{node.id}' has tool '{tool}' which is not "
                    f"scoped to Authentication. Allowed: {sorted(allowed)}"
                )

    def test_validate_node_tools_within_cluster_greeting(self):
        """validate_node_tools_within_cluster returns no violations for Greeting."""
        greeting = build_greeting_cluster()
        violations = validate_node_tools_within_cluster(
            greeting.nodes, ToolCluster.GREETING
        )
        assert violations == []

    def test_validate_node_tools_within_cluster_bh(self):
        """validate_node_tools_within_cluster returns no violations for BH."""
        bh = build_business_hours_cluster()
        violations = validate_node_tools_within_cluster(
            bh.nodes, ToolCluster.BUSINESS_HOURS
        )
        assert violations == []

    def test_validate_node_tools_within_cluster_ah(self):
        """validate_node_tools_within_cluster returns no violations for AH."""
        ah = build_after_hours_cluster()
        violations = validate_node_tools_within_cluster(
            ah.nodes, ToolCluster.AFTER_HOURS
        )
        assert violations == []

    def test_validate_node_tools_within_cluster_auth(self):
        """validate_node_tools_within_cluster returns no violations for Auth."""
        auth = build_authentication_cluster()
        violations = validate_node_tools_within_cluster(
            auth.nodes, ToolCluster.AUTHENTICATION
        )
        assert violations == []

    def test_validate_node_tools_within_cluster_routing(self):
        """validate_node_tools_within_cluster returns no violations for Routing."""
        routing = build_routing_cluster()
        violations = validate_node_tools_within_cluster(
            routing.nodes, ToolCluster.ROUTING
        )
        assert violations == []
