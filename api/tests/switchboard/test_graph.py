"""WorkflowGraph validation smoke tests for the assembled switchboard graph.

Validates structural invariants of the assembled graph:
- Single start node, ≤1 global node, edge cardinality, referential integrity
- Connector tools registered and scoped to the correct clusters
- Gate-by-scoping (transfer/route_metadata_resolution only on Routing nodes)
- Inbound-only entry (no outbound dial)

Requirements: 1.1, 1.7.
"""


from api.services.switchboard.graph import build_switchboard_graph
from api.services.switchboard.tools.base import ToolCluster
from api.services.switchboard.tools.registry import get_connector_tools, tools_for_cluster
from api.services.workflow.workflow_graph import WorkflowGraph


class TestBuildSwitchboardGraphValidates:
    """Smoke test: the assembled graph builds and validates without exceptions."""

    def test_build_switchboard_graph_validates(self):
        """build_switchboard_graph() returns a valid WorkflowGraph instance.

        Asserts:
        - No exceptions raised during assembly and validation
        - Returns a WorkflowGraph instance
        - Has exactly 1 start node (start_node_id is not None)
        - Has at most 1 global node (global_node_id may be None or a string)
        - All edges have valid source/target references (referential integrity)
        """
        workflow_graph = build_switchboard_graph()

        # Returns a WorkflowGraph instance
        assert isinstance(workflow_graph, WorkflowGraph)

        # Exactly 1 start node
        assert workflow_graph.start_node_id is not None
        assert workflow_graph.start_node_id in workflow_graph.nodes

        # At most 1 global node (can be None or a valid node ID)
        if workflow_graph.global_node_id is not None:
            assert workflow_graph.global_node_id in workflow_graph.nodes

        # Referential integrity: all edges reference existing nodes
        for edge in workflow_graph.edges:
            assert edge.source in workflow_graph.nodes, (
                f"Edge source '{edge.source}' not found in graph nodes"
            )
            assert edge.target in workflow_graph.nodes, (
                f"Edge target '{edge.target}' not found in graph nodes"
            )


class TestConnectorToolsRegisteredAndScoped:
    """Validate connector tool registration and cluster scoping."""

    def test_connector_tools_registered_and_scoped(self):
        """All 11 connector tools are registered with correct cluster scoping.

        Asserts:
        - Exactly 11 connector tools registered
        - transfer and route_metadata_resolution are ONLY scoped to ROUTING
        - patient_lookup is scoped to GREETING and AUTHENTICATION
        - directory_lookup and faq_kb are scoped to BUSINESS_HOURS and AFTER_HOURS
        - scheduling_handoff and scheduling_engine are scoped to SCHEDULING
        """
        all_tools = get_connector_tools()
        assert len(all_tools) == 11

        # transfer and route_metadata_resolution → ROUTING only
        routing_tools = tools_for_cluster(ToolCluster.ROUTING)
        routing_tool_names = {t.function_name for t in routing_tools}
        assert "transfer" in routing_tool_names
        assert "route_metadata_resolution" in routing_tool_names

        # Verify transfer is ONLY in ROUTING
        transfer_tool = next(t for t in all_tools if t.function_name == "transfer")
        assert transfer_tool.clusters == frozenset({ToolCluster.ROUTING})

        # Verify route_metadata_resolution is ONLY in ROUTING
        rmd_tool = next(
            t for t in all_tools if t.function_name == "route_metadata_resolution"
        )
        assert rmd_tool.clusters == frozenset({ToolCluster.ROUTING})

        # patient_lookup → GREETING and AUTHENTICATION
        patient_lookup_tool = next(
            t for t in all_tools if t.function_name == "patient_lookup"
        )
        assert patient_lookup_tool.clusters == frozenset(
            {ToolCluster.GREETING, ToolCluster.AUTHENTICATION}
        )

        # directory_lookup and faq_kb → BUSINESS_HOURS and AFTER_HOURS
        dir_tool = next(
            t for t in all_tools if t.function_name == "directory_lookup"
        )
        assert dir_tool.clusters == frozenset(
            {ToolCluster.BUSINESS_HOURS, ToolCluster.AFTER_HOURS}
        )

        faq_tool = next(t for t in all_tools if t.function_name == "faq_kb")
        assert faq_tool.clusters == frozenset(
            {ToolCluster.BUSINESS_HOURS, ToolCluster.AFTER_HOURS}
        )

        # scheduling_handoff and scheduling_engine → SCHEDULING
        sched_handoff = next(
            t for t in all_tools if t.function_name == "scheduling_handoff"
        )
        assert sched_handoff.clusters == frozenset({ToolCluster.SCHEDULING})

        sched_engine = next(
            t for t in all_tools if t.function_name == "scheduling_engine"
        )
        assert sched_engine.clusters == frozenset({ToolCluster.SCHEDULING})


class TestToolScopingGateAuth:
    """Validate gate-by-scoping: transfer/route_metadata_resolution only on Routing nodes."""

    def test_tool_scoping_gate_auth(self):
        """For every non-routing node, transfer and route_metadata_resolution are NOT
        in its tool_uuids. For routing nodes with tools, they ARE available.
        """
        workflow_graph = build_switchboard_graph()

        routing_only_tools = {"transfer", "route_metadata_resolution"}

        for node_id, node in workflow_graph.nodes.items():
            tool_uuids = node.tool_uuids or []
            is_routing_node = node_id.startswith("routing_")

            if not is_routing_node:
                # Non-routing nodes must NOT have routing-only tools
                for tool_name in routing_only_tools:
                    assert tool_name not in tool_uuids, (
                        f"Non-routing node '{node_id}' has routing-only tool "
                        f"'{tool_name}' — GATE-AUTH invariant violated (Req 1.7, 9.2)"
                    )
            else:
                # Routing nodes that have tools should include routing-only tools.
                # Terminal nodes (endCall type like goodbye/transfer_error) have no
                # tool_uuids — they don't invoke tools, so skip the assertion.
                if tool_uuids:
                    has_routing_tool = any(
                        t in routing_only_tools for t in tool_uuids
                    )
                    assert has_routing_tool, (
                        f"Routing node '{node_id}' has tools but no routing-only "
                        f"tools — expected transfer or route_metadata_resolution"
                    )


class TestGraphHasSingleStartNode:
    """Validate the graph has exactly one start node."""

    def test_graph_has_single_start_node(self):
        """The assembled graph has exactly 1 node where is_start is True."""
        workflow_graph = build_switchboard_graph()

        start_nodes = [
            node for node in workflow_graph.nodes.values() if node.is_start
        ]
        assert len(start_nodes) == 1, (
            f"Expected exactly 1 start node, found {len(start_nodes)}: "
            f"{[n.id for n in start_nodes]}"
        )


class TestGraphHasAtMostOneGlobalNode:
    """Validate the graph has at most one global node."""

    def test_graph_has_at_most_one_global_node(self):
        """The assembled graph has ≤1 node with type 'globalNode'."""
        workflow_graph = build_switchboard_graph()

        global_nodes = [
            node
            for node in workflow_graph.nodes.values()
            if node.node_type == "globalNode"
        ]
        assert len(global_nodes) <= 1, (
            f"Expected at most 1 global node, found {len(global_nodes)}: "
            f"{[n.id for n in global_nodes]}"
        )


class TestGraphNoOutboundDial:
    """Validate the graph is inbound-only (no outbound dial)."""

    def test_graph_no_outbound_dial(self):
        """The start node type is 'startCall' (inbound entry, not outbound).

        The switchboard is an inbound virtual receptionist — it receives calls,
        never initiates outbound dials.
        """
        workflow_graph = build_switchboard_graph()

        start_node = workflow_graph.nodes[workflow_graph.start_node_id]
        assert start_node.node_type == "startCall", (
            f"Expected start node type 'startCall' (inbound), "
            f"got '{start_node.node_type}'"
        )
