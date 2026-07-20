"""Unit tests for the After Hours cluster graph builder.

Validates that ``build_after_hours_cluster()`` produces the correct node and edge
structure conforming to the workflow engine DTOs, wiring the pure decision logic
from ``api.services.switchboard.after_hours`` and verbatim lines from
``api.services.switchboard.scripts``.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 21.3.
"""

import os


from api.services.switchboard import scripts
from api.services.switchboard.clusters.after_hours import (
    EDGE_AH_HOTWORD_TO_ROUTING,
    EDGE_AH_INTENT_TO_BILLING_CLOSED,
    EDGE_AH_INTENT_TO_MYCHART_CLOSED,
    EDGE_AH_INTENT_TO_PAGING_CLARIFIER,
    EDGE_AH_INTENT_TO_RESTRICTED_CONNECT,
    EDGE_AH_RESTRICTED_CONNECT_TO_AUTH,
    EDGE_AH_RESTRICTED_CONNECT_TO_END,
    EDGE_AH_RETRY_1,
    EDGE_AH_RETRY_2,
    EDGE_AH_RETRY_3_SILENT,
    NODE_AH_BILLING_CLOSED,
    NODE_AH_INTENT,
    NODE_AH_MYCHART_CLOSED,
    NODE_AH_PAGING_CLARIFIER,
    NODE_AH_RESTRICTED_CONNECT,
    build_after_hours_cluster,
)
from api.services.workflow.dto import AgentNodeData


class TestAfterHoursClusterNodes:
    """Tests for the nodes produced by the After Hours cluster builder."""

    def setup_method(self):
        self.result = build_after_hours_cluster()

    def test_produces_five_nodes(self):
        assert len(self.result.nodes) == 5

    def test_all_nodes_are_agent_nodes(self):
        """All After Hours nodes are agentNode type."""
        for node in self.result.nodes:
            assert node.type == "agentNode"
            assert isinstance(node.data, AgentNodeData)

    def test_ah_intent_node_structure(self):
        node = next(n for n in self.result.nodes if n.id == NODE_AH_INTENT)
        assert node.data.name == "AH Intent"
        assert node.data.allow_interrupt is True
        assert node.data.add_global_prompt is True

    def test_ah_intent_extraction_variables(self):
        """AH Intent extracts intent, specialty, provider_name, ah_intent_selection, caller_is_provider."""
        node = next(n for n in self.result.nodes if n.id == NODE_AH_INTENT)
        assert node.data.extraction_enabled is True
        var_names = {v.name for v in node.data.extraction_variables}
        assert "intent" in var_names
        assert "specialty" in var_names
        assert "provider_name" in var_names
        assert "ah_intent_selection" in var_names
        assert "caller_is_provider" in var_names

    def test_ah_intent_tool_scoping(self):
        """AH Intent has directory_lookup and faq_kb tools."""
        node = next(n for n in self.result.nodes if n.id == NODE_AH_INTENT)
        assert node.data.tool_uuids is not None
        assert "directory_lookup" in node.data.tool_uuids
        assert "faq_kb" in node.data.tool_uuids

    def test_restricted_connect_node_structure(self):
        node = next(
            n for n in self.result.nodes if n.id == NODE_AH_RESTRICTED_CONNECT
        )
        assert node.data.name == "AH Restricted Connect"
        assert node.data.allow_interrupt is True

    def test_restricted_connect_extraction(self):
        """Restricted Connect extracts the connect response."""
        node = next(
            n for n in self.result.nodes if n.id == NODE_AH_RESTRICTED_CONNECT
        )
        assert node.data.extraction_enabled is True
        var_names = {v.name for v in node.data.extraction_variables}
        assert "connect_response" in var_names

    def test_billing_closed_node_structure(self):
        """Req 8.4: Billing Closed speaks the mandated line, no global prompt."""
        node = next(n for n in self.result.nodes if n.id == NODE_AH_BILLING_CLOSED)
        assert node.data.name == "AH Billing Closed"
        assert node.data.add_global_prompt is False
        assert node.data.allow_interrupt is False
        assert scripts.AH_BILLING_CLOSED in node.data.prompt

    def test_mychart_closed_node_structure(self):
        """Req 8.5: MyChart Closed speaks the mandated line, no global prompt."""
        node = next(n for n in self.result.nodes if n.id == NODE_AH_MYCHART_CLOSED)
        assert node.data.name == "AH MyChart Closed"
        assert node.data.add_global_prompt is False
        assert node.data.allow_interrupt is False
        assert scripts.AH_MYCHART_CLOSED in node.data.prompt

    def test_paging_clarifier_node_structure(self):
        """Req 8.8: Paging Clarifier has mandated options in prompt."""
        node = next(n for n in self.result.nodes if n.id == NODE_AH_PAGING_CLARIFIER)
        assert node.data.name == "AH Paging Clarifier"
        assert node.data.allow_interrupt is True
        assert scripts.AH_PAGING_CLARIFIER_OPTION_1 in node.data.prompt

    def test_paging_clarifier_extraction(self):
        """Req 8.8: Paging Clarifier extracts caller_is_provider, ah_intent_selection."""
        node = next(n for n in self.result.nodes if n.id == NODE_AH_PAGING_CLARIFIER)
        assert node.data.extraction_enabled is True
        var_names = {v.name for v in node.data.extraction_variables}
        assert "caller_is_provider" in var_names
        assert "ah_intent_selection" in var_names


class TestAfterHoursClusterEdges:
    """Tests for the edges produced by the After Hours cluster builder."""

    def setup_method(self):
        self.result = build_after_hours_cluster()

    def test_produces_ten_edges(self):
        assert len(self.result.edges) == 10

    def test_hotword_silent_route_edge(self):
        """Req 8.3: Hotword edge is silent (transition_speech='') to Routing."""
        edge = next(e for e in self.result.edges if e.id == EDGE_AH_HOTWORD_TO_ROUTING)
        assert edge.source == NODE_AH_INTENT
        assert edge.target == "routing_resolve"
        assert edge.data.transition_speech == ""

    def test_billing_closed_edge(self):
        """Req 8.4: AH Intent → Billing Closed."""
        edge = next(
            e for e in self.result.edges if e.id == EDGE_AH_INTENT_TO_BILLING_CLOSED
        )
        assert edge.source == NODE_AH_INTENT
        assert edge.target == NODE_AH_BILLING_CLOSED

    def test_mychart_closed_edge(self):
        """Req 8.5: AH Intent → MyChart Closed."""
        edge = next(
            e for e in self.result.edges if e.id == EDGE_AH_INTENT_TO_MYCHART_CLOSED
        )
        assert edge.source == NODE_AH_INTENT
        assert edge.target == NODE_AH_MYCHART_CLOSED

    def test_paging_clarifier_edge(self):
        """Req 8.8: AH Intent → Paging Clarifier."""
        edge = next(
            e for e in self.result.edges if e.id == EDGE_AH_INTENT_TO_PAGING_CLARIFIER
        )
        assert edge.source == NODE_AH_INTENT
        assert edge.target == NODE_AH_PAGING_CLARIFIER

    def test_restricted_connect_edge(self):
        """Req 8.2: AH Intent → Restricted Connect with offer speech."""
        edge = next(
            e
            for e in self.result.edges
            if e.id == EDGE_AH_INTENT_TO_RESTRICTED_CONNECT
        )
        assert edge.source == NODE_AH_INTENT
        assert edge.target == NODE_AH_RESTRICTED_CONNECT
        assert edge.data.transition_speech == scripts.AH_RESTRICTED_SERVICE_SCHEDULING

    def test_restricted_connect_to_auth_edge(self):
        """Req 8.9: Restricted Connect → Auth (silent) when caller agreed."""
        edge = next(
            e for e in self.result.edges if e.id == EDGE_AH_RESTRICTED_CONNECT_TO_AUTH
        )
        assert edge.source == NODE_AH_RESTRICTED_CONNECT
        assert edge.target == "auth_phone"
        assert edge.data.transition_speech == ""

    def test_restricted_connect_to_end_edge(self):
        """Req 8.10, 8.11: Restricted Connect → end when declined/timeout."""
        edge = next(
            e for e in self.result.edges if e.id == EDGE_AH_RESTRICTED_CONNECT_TO_END
        )
        assert edge.source == NODE_AH_RESTRICTED_CONNECT
        assert edge.target == "end_goodbye"

    def test_retry_1_edge(self):
        """Req 8.6: First retry loops AH Intent with AH_RETRY_1 speech."""
        edge = next(e for e in self.result.edges if e.id == EDGE_AH_RETRY_1)
        assert edge.source == NODE_AH_INTENT
        assert edge.target == NODE_AH_INTENT
        assert edge.data.transition_speech == scripts.AH_RETRY_1

    def test_retry_2_edge(self):
        """Req 8.6: Second retry loops AH Intent with AH_RETRY_2 speech."""
        edge = next(e for e in self.result.edges if e.id == EDGE_AH_RETRY_2)
        assert edge.source == NODE_AH_INTENT
        assert edge.target == NODE_AH_INTENT
        assert edge.data.transition_speech == scripts.AH_RETRY_2

    def test_retry_3_silent_edge(self):
        """Req 8.7: Third failure routes silently to Routing."""
        edge = next(e for e in self.result.edges if e.id == EDGE_AH_RETRY_3_SILENT)
        assert edge.source == NODE_AH_INTENT
        assert edge.target == "routing_resolve"
        assert edge.data.transition_speech == ""


class TestAfterHoursClusterSilentTransitions:
    """Tests that silent transitions are correctly marked (Req 8.3, 8.7, 8.9)."""

    def setup_method(self):
        self.result = build_after_hours_cluster()

    def test_exactly_three_silent_edges(self):
        """Three edges should have empty transition_speech (silent turns)."""
        silent = [
            e for e in self.result.edges if e.data.transition_speech == ""
        ]
        assert len(silent) == 3

    def test_silent_edges_are_hotword_auth_retry3(self):
        silent_ids = {
            e.id for e in self.result.edges if e.data.transition_speech == ""
        }
        assert EDGE_AH_HOTWORD_TO_ROUTING in silent_ids
        assert EDGE_AH_RESTRICTED_CONNECT_TO_AUTH in silent_ids
        assert EDGE_AH_RETRY_3_SILENT in silent_ids


class TestAfterHoursClusterExportedIDs:
    """Tests that the exported node IDs are correct for downstream connections."""

    def setup_method(self):
        self.result = build_after_hours_cluster()

    def test_entry_node_is_ah_intent(self):
        assert self.result.entry_node_id == NODE_AH_INTENT

    def test_exposed_ids_contain_all_nodes(self):
        assert len(self.result.exposed_node_ids) == 5
        assert "ah_intent" in self.result.exposed_node_ids
        assert "ah_restricted_connect" in self.result.exposed_node_ids
        assert "ah_billing_closed" in self.result.exposed_node_ids
        assert "ah_mychart_closed" in self.result.exposed_node_ids
        assert "ah_paging_clarifier" in self.result.exposed_node_ids

    def test_exposed_ids_match_actual_nodes(self):
        node_ids = {n.id for n in self.result.nodes}
        for exposed_id in self.result.exposed_node_ids.values():
            assert exposed_id in node_ids


class TestAfterHoursClusterHotwordConfig:
    """Tests that the hotword keyword list is read from config (Req 21.3)."""

    def test_no_hotwords_configured_prompt_has_no_hotword_section(self):
        """Without config, no hotword keywords appear in the prompt."""
        # Ensure env var is not set
        env_backup = os.environ.pop("SWITCHBOARD_AFTERHOURS_HOTWORDS", None)
        try:
            result = build_after_hours_cluster()
            intent_node = next(
                n for n in result.nodes if n.id == NODE_AH_INTENT
            )
            assert "HOTWORD DETECTION" not in intent_node.data.prompt
        finally:
            if env_backup is not None:
                os.environ["SWITCHBOARD_AFTERHOURS_HOTWORDS"] = env_backup

    def test_hotwords_from_config_injected_into_prompt(self):
        """Req 21.3: Hotword list from config appears in AH Intent prompt."""
        os.environ["SWITCHBOARD_AFTERHOURS_HOTWORDS"] = "chest pain,stroke,bleeding"
        try:
            result = build_after_hours_cluster()
            intent_node = next(
                n for n in result.nodes if n.id == NODE_AH_INTENT
            )
            assert "HOTWORD DETECTION" in intent_node.data.prompt
            assert "chest pain" in intent_node.data.prompt
            assert "stroke" in intent_node.data.prompt
            assert "bleeding" in intent_node.data.prompt
        finally:
            del os.environ["SWITCHBOARD_AFTERHOURS_HOTWORDS"]


class TestAfterHoursClusterCustomTargets:
    """Tests that custom external node IDs are wired correctly."""

    def test_custom_routing_entry(self):
        result = build_after_hours_cluster(routing_entry_node_id="custom_routing")
        hotword_edge = next(
            e for e in result.edges if e.id == EDGE_AH_HOTWORD_TO_ROUTING
        )
        assert hotword_edge.target == "custom_routing"
        retry3_edge = next(
            e for e in result.edges if e.id == EDGE_AH_RETRY_3_SILENT
        )
        assert retry3_edge.target == "custom_routing"

    def test_custom_auth_entry(self):
        result = build_after_hours_cluster(auth_entry_node_id="custom_auth")
        auth_edge = next(
            e for e in result.edges if e.id == EDGE_AH_RESTRICTED_CONNECT_TO_AUTH
        )
        assert auth_edge.target == "custom_auth"

    def test_custom_end_node(self):
        result = build_after_hours_cluster(end_node_id="custom_end")
        end_edge = next(
            e for e in result.edges if e.id == EDGE_AH_RESTRICTED_CONNECT_TO_END
        )
        assert end_edge.target == "custom_end"
