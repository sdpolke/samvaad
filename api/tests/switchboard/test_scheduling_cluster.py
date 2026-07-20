"""Tests for the Scheduling-phase node cluster builder.

Validates that :func:`build_scheduling_cluster` produces a structurally correct
cluster with the expected nodes, edges, tool scoping, and prompt content.
"""

from __future__ import annotations

from api.services.switchboard.clusters.scheduling import (
    SCHEDULING_ENGINE_PROMPT,
    SCHEDULING_INIT_PROMPT,
    SCHEDULING_NEW_PATIENT_INTAKE_PROMPT,
    SchedulingClusterResult,
    build_scheduling_cluster,
)
from api.services.switchboard.scripts import (
    E_SCHEDULING_NEW,
    SCHED_INIT_VISIT_REASON,
    SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION,
)


class TestSchedulingClusterStructure:
    """Structural tests for the scheduling cluster builder."""

    def setup_method(self) -> None:
        self.result = build_scheduling_cluster()

    def test_returns_scheduling_cluster_result(self) -> None:
        assert isinstance(self.result, SchedulingClusterResult)

    def test_has_four_nodes(self) -> None:
        assert len(self.result.nodes) == 4

    def test_has_three_edges(self) -> None:
        assert len(self.result.edges) == 3

    def test_node_ids_use_scheduling_prefix(self) -> None:
        for node in self.result.nodes:
            assert node.id.startswith("scheduling_"), f"Node {node.id} missing prefix"

    def test_edge_ids_use_scheduling_prefix(self) -> None:
        for edge in self.result.edges:
            assert edge.id.startswith("scheduling_edge_"), (
                f"Edge {edge.id} missing prefix"
            )

    def test_exposed_ids_match_nodes(self) -> None:
        node_ids = {node.id for node in self.result.nodes}
        assert self.result.scheduling_init_id in node_ids
        assert self.result.scheduling_engine_id in node_ids
        assert self.result.scheduling_new_patient_intake_id in node_ids
        assert self.result.scheduling_complete_id in node_ids

    def test_scheduling_init_is_agent_node(self) -> None:
        init_node = next(
            n for n in self.result.nodes if n.id == self.result.scheduling_init_id
        )
        assert init_node.type == "agentNode"

    def test_scheduling_engine_is_agent_node(self) -> None:
        engine_node = next(
            n for n in self.result.nodes if n.id == self.result.scheduling_engine_id
        )
        assert engine_node.type == "agentNode"

    def test_new_patient_intake_is_end_call(self) -> None:
        npi_node = next(
            n
            for n in self.result.nodes
            if n.id == self.result.scheduling_new_patient_intake_id
        )
        assert npi_node.type == "endCall"

    def test_scheduling_complete_is_end_call(self) -> None:
        complete_node = next(
            n for n in self.result.nodes if n.id == self.result.scheduling_complete_id
        )
        assert complete_node.type == "endCall"


class TestSchedulingClusterToolScoping:
    """Verify per-node tool scoping for the scheduling cluster."""

    def setup_method(self) -> None:
        self.result = build_scheduling_cluster()

    def test_init_node_scoped_to_scheduling_handoff(self) -> None:
        init_node = next(
            n for n in self.result.nodes if n.id == self.result.scheduling_init_id
        )
        assert init_node.data.tool_uuids == ["scheduling_handoff"]

    def test_engine_node_scoped_to_scheduling_engine(self) -> None:
        engine_node = next(
            n for n in self.result.nodes if n.id == self.result.scheduling_engine_id
        )
        assert engine_node.data.tool_uuids == ["scheduling_engine"]

    def test_end_nodes_have_no_tools(self) -> None:
        """EndCallNodeData does not carry tool_uuids (no _ToolDocumentRefsMixin)."""
        npi_node = next(
            n
            for n in self.result.nodes
            if n.id == self.result.scheduling_new_patient_intake_id
        )
        assert not hasattr(npi_node.data, "tool_uuids")

        complete_node = next(
            n for n in self.result.nodes if n.id == self.result.scheduling_complete_id
        )
        assert not hasattr(complete_node.data, "tool_uuids")


class TestSchedulingClusterPrompts:
    """Verify prompt content enforces the requirements."""

    def setup_method(self) -> None:
        self.result = build_scheduling_cluster()

    def test_init_prompt_references_visit_reason_question(self) -> None:
        assert SCHED_INIT_VISIT_REASON in SCHEDULING_INIT_PROMPT

    def test_init_prompt_references_disambiguation_question(self) -> None:
        assert SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION in SCHEDULING_INIT_PROMPT

    def test_init_prompt_mentions_manage_action_skip(self) -> None:
        assert "Skip sick/wellness" in SCHEDULING_INIT_PROMPT
        assert "Req 13.7" in SCHEDULING_INIT_PROMPT

    def test_init_prompt_mentions_new_patient_create(self) -> None:
        assert "Req 12.7" in SCHEDULING_INIT_PROMPT
        assert "new" in SCHEDULING_INIT_PROMPT.lower()

    def test_engine_prompt_covers_all_actions(self) -> None:
        for action in ("CREATE", "RESCHEDULE", "CANCEL", "LIST", "CONFIRM"):
            assert action in SCHEDULING_ENGINE_PROMPT

    def test_engine_prompt_mentions_urgency_escalation(self) -> None:
        assert "Req 14.9" in SCHEDULING_ENGINE_PROMPT

    def test_engine_prompt_mentions_specialty_fallback(self) -> None:
        assert "Req 14.10" in SCHEDULING_ENGINE_PROMPT

    def test_new_patient_intake_prompt_uses_transfer_line(self) -> None:
        assert E_SCHEDULING_NEW in SCHEDULING_NEW_PATIENT_INTAKE_PROMPT


class TestSchedulingClusterEdges:
    """Verify internal edge wiring is correct."""

    def setup_method(self) -> None:
        self.result = build_scheduling_cluster()

    def test_init_to_engine_edge_exists(self) -> None:
        edge = next(
            (
                e
                for e in self.result.edges
                if e.source == self.result.scheduling_init_id
                and e.target == self.result.scheduling_engine_id
            ),
            None,
        )
        assert edge is not None
        assert "visit type" in edge.data.condition.lower() or "manage" in edge.data.condition.lower()

    def test_init_to_new_patient_edge_exists(self) -> None:
        edge = next(
            (
                e
                for e in self.result.edges
                if e.source == self.result.scheduling_init_id
                and e.target == self.result.scheduling_new_patient_intake_id
            ),
            None,
        )
        assert edge is not None
        assert "new" in edge.data.condition.lower()
        assert "Req 12.7" in edge.data.condition

    def test_engine_to_complete_edge_exists(self) -> None:
        edge = next(
            (
                e
                for e in self.result.edges
                if e.source == self.result.scheduling_engine_id
                and e.target == self.result.scheduling_complete_id
            ),
            None,
        )
        assert edge is not None

    def test_no_self_loops(self) -> None:
        for edge in self.result.edges:
            assert edge.source != edge.target

    def test_all_edge_targets_are_valid_node_ids(self) -> None:
        node_ids = {node.id for node in self.result.nodes}
        for edge in self.result.edges:
            assert edge.target in node_ids, f"Edge {edge.id} target {edge.target} not in nodes"
            assert edge.source in node_ids, f"Edge {edge.id} source {edge.source} not in nodes"


class TestSchedulingClusterGlobalPromptDisabled:
    """Verify add_global_prompt=False on verbatim/exact-wording nodes."""

    def setup_method(self) -> None:
        self.result = build_scheduling_cluster()

    def test_all_nodes_have_global_prompt_disabled(self) -> None:
        for node in self.result.nodes:
            assert node.data.add_global_prompt is False, (
                f"Node {node.id} should have add_global_prompt=False"
            )
