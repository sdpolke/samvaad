"""Unit test for the serialization seam (Task 1.2).

`build_switchboard_reactflow_dto()` was extracted out of
`build_switchboard_graph()` so the enablement layer's `Template_Registrar` can
serialize the assembled `ReactFlowDTO` without re-implementing graph assembly.
This test locks in that `build_switchboard_graph()` still calls the extracted
helper internally (same node ids/types, edge conditions/transition_speech) and
that `build_switchboard_graph()` continues to return a valid `WorkflowGraph`
unchanged.

Note: all cluster builders now assign deterministic node/edge ids, so builds are
reproducible. To assert that `build_switchboard_graph()` validates *the same* DTO
that `build_switchboard_reactflow_dto()` produces, this test still spies on the
module-level `build_switchboard_reactflow_dto` reference used inside
`build_switchboard_graph()` and captures the exact DTO instance it returned, then
compares that captured DTO against the resulting `WorkflowGraph`.

Requirements: 1.1.
"""

from collections import Counter
from unittest import mock

from api.services.switchboard import graph as graph_module
from api.services.switchboard.graph import (
    build_switchboard_graph,
    build_switchboard_reactflow_dto,
)
from api.services.workflow.workflow_graph import WorkflowGraph


def _edge_signature(source: str, target: str, condition: str, transition_speech):
    """Build a comparable tuple for an edge, ignoring the synthetic edge id."""
    return (source, target, condition, transition_speech)


class TestSerializationSeamMatchesValidatedGraph:
    """`build_switchboard_graph()` validates exactly the `ReactFlowDTO` produced
    by `build_switchboard_reactflow_dto()` (same node ids/types, edge
    conditions/transition_speech)."""

    def _build_graph_and_capture_dto(self):
        """Call `build_switchboard_graph()` while capturing the exact DTO
        instance returned by its internal call to
        `build_switchboard_reactflow_dto()`."""
        real_fn = graph_module.build_switchboard_reactflow_dto
        captured = []

        def _capture(*args, **kwargs):
            dto = real_fn(*args, **kwargs)
            captured.append(dto)
            return dto

        with mock.patch.object(
            graph_module, "build_switchboard_reactflow_dto", side_effect=_capture
        ) as spy:
            workflow_graph = graph_module.build_switchboard_graph()

        spy.assert_called_once()
        assert len(captured) == 1
        return captured[0], workflow_graph

    def test_dto_has_same_node_ids_and_types_as_validated_graph(self):
        dto, workflow_graph = self._build_graph_and_capture_dto()

        dto_node_ids = {node.id for node in dto.nodes}
        graph_node_ids = set(workflow_graph.nodes.keys())
        assert dto_node_ids == graph_node_ids

        for node in dto.nodes:
            graph_node = workflow_graph.nodes[node.id]
            assert graph_node.node_type == node.type, (
                f"Node '{node.id}' type mismatch: dto={node.type!r} "
                f"graph={graph_node.node_type!r}"
            )

    def test_dto_has_same_edge_conditions_and_transition_speech(self):
        dto, workflow_graph = self._build_graph_and_capture_dto()

        dto_edge_signatures = Counter(
            _edge_signature(
                edge.source, edge.target, edge.data.condition, edge.data.transition_speech
            )
            for edge in dto.edges
        )
        graph_edge_signatures = Counter(
            _edge_signature(
                edge.source, edge.target, edge.condition, edge.transition_speech
            )
            for edge in workflow_graph.edges
        )

        assert dto_edge_signatures == graph_edge_signatures

    def test_dto_edge_and_node_counts_match_validated_graph(self):
        dto, workflow_graph = self._build_graph_and_capture_dto()

        assert len(dto.nodes) == len(workflow_graph.nodes)
        assert len(dto.edges) == len(workflow_graph.edges)

    def test_build_switchboard_reactflow_dto_is_independently_callable(self):
        """`build_switchboard_reactflow_dto()` can be called standalone (as the
        enablement layer's `Template_Registrar` will do) and returns a
        structurally valid, unvalidated `ReactFlowDTO`."""
        dto = build_switchboard_reactflow_dto()

        assert len(dto.nodes) > 0
        assert len(dto.edges) > 0
        node_ids = {node.id for node in dto.nodes}
        assert "greeting_start_call" in node_ids
        assert all(edge.source in node_ids and edge.target in node_ids for edge in dto.edges)


class TestBuildSwitchboardGraphStillValidatesUnchanged:
    """`build_switchboard_graph()` continues to return a valid `WorkflowGraph`
    after the serialization-seam extraction (matches `test_graph.py`)."""

    def test_returns_valid_workflow_graph(self):
        workflow_graph = build_switchboard_graph()

        assert isinstance(workflow_graph, WorkflowGraph)

        # Exactly one start node.
        assert workflow_graph.start_node_id is not None
        assert workflow_graph.start_node_id in workflow_graph.nodes

        # At most one global node.
        if workflow_graph.global_node_id is not None:
            assert workflow_graph.global_node_id in workflow_graph.nodes

        # Referential integrity: every edge references an existing node.
        for edge in workflow_graph.edges:
            assert edge.source in workflow_graph.nodes
            assert edge.target in workflow_graph.nodes
