"""Unit tests for the Greeting cluster graph builder.

Validates that ``build_greeting_cluster()`` produces the correct node and edge
structure conforming to the workflow engine DTOs.

Requirements: 1.2, 1.3, 1.4, 3.5, 6.1, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11.
"""


from api.services.switchboard import scripts
from api.services.switchboard.clusters.greeting import (
    EDGE_PATH_A,
    EDGE_PATH_E_LOOP,
    EDGE_ROUTING_REQUEST,
    EDGE_START_TO_COLLECT,
    EDGE_TRIGGER_TO_START,
    GREETING_COLLECT_NODE_ID,
    GREETING_RECORDING_ID_PLACEHOLDER,
    PRE_CALL_FETCH_URL_PLACEHOLDER,
    START_CALL_NODE_ID,
    TRIGGER_NODE_ID,
    build_greeting_cluster,
)
from api.services.workflow.dto import (
    AgentNodeData,
    StartCallNodeData,
    TriggerNodeData,
)


class TestGreetingClusterNodes:
    """Tests for the nodes produced by the Greeting cluster builder."""

    def setup_method(self):
        self.result = build_greeting_cluster()

    def test_produces_three_nodes(self):
        assert len(self.result.nodes) == 3

    def test_trigger_node_structure(self):
        trigger = next(n for n in self.result.nodes if n.id == TRIGGER_NODE_ID)
        assert trigger.type == "trigger"
        assert isinstance(trigger.data, TriggerNodeData)
        assert trigger.data.enabled is True

    def test_start_call_node_structure(self):
        start = next(n for n in self.result.nodes if n.id == START_CALL_NODE_ID)
        assert start.type == "startCall"
        assert isinstance(start.data, StartCallNodeData)

    def test_start_call_pre_call_fetch_enabled(self):
        """Req 6.1: 2s pre_call_fetch ANI lookup."""
        start = next(n for n in self.result.nodes if n.id == START_CALL_NODE_ID)
        assert start.data.pre_call_fetch_enabled is True
        assert start.data.pre_call_fetch_url == PRE_CALL_FETCH_URL_PLACEHOLDER

    def test_start_call_greeting_text_default(self):
        """Default build speaks a deterministic TTS text greeting so the caller
        is always greeted (no reliance on a recording asset)."""
        start = next(n for n in self.result.nodes if n.id == START_CALL_NODE_ID)
        assert start.data.greeting_type == "text"
        assert start.data.greeting == scripts.GREETING_SCRIPT_4_STANDARD_IN_HOURS
        assert start.data.greeting_recording_id is None

    def test_start_call_greeting_type_audio_when_recording_configured(self):
        """Req 6.4: Config-driven welcome audio when a recording is provided."""
        result = build_greeting_cluster(
            greeting_recording_id=GREETING_RECORDING_ID_PLACEHOLDER
        )
        start = next(n for n in result.nodes if n.id == START_CALL_NODE_ID)
        assert start.data.greeting_type == "audio"
        assert start.data.greeting_recording_id == GREETING_RECORDING_ID_PLACEHOLDER
        assert start.data.greeting is None

    def test_start_call_extraction_enabled(self):
        """Extraction variables for caller_name, intent, etc."""
        start = next(n for n in self.result.nodes if n.id == START_CALL_NODE_ID)
        assert start.data.extraction_enabled is True
        assert start.data.extraction_variables is not None
        var_names = {v.name for v in start.data.extraction_variables}
        assert "caller_name" in var_names
        assert "intent" in var_names
        assert "specialty" in var_names
        assert "provider_name" in var_names
        assert "scan_type" in var_names
        assert "appointment_action" in var_names

    def test_start_call_tool_scoping(self):
        """Req 1.7: patient_lookup tool scoped to Greeting."""
        start = next(n for n in self.result.nodes if n.id == START_CALL_NODE_ID)
        assert start.data.tool_uuids is not None
        assert "patient_lookup" in start.data.tool_uuids

    def test_greeting_collect_node_structure(self):
        collect = next(
            n for n in self.result.nodes if n.id == GREETING_COLLECT_NODE_ID
        )
        assert collect.type == "agentNode"
        assert isinstance(collect.data, AgentNodeData)

    def test_greeting_collect_extraction(self):
        collect = next(
            n for n in self.result.nodes if n.id == GREETING_COLLECT_NODE_ID
        )
        assert collect.data.extraction_enabled is True
        var_names = {v.name for v in collect.data.extraction_variables}
        assert "caller_name" in var_names
        assert "intent" in var_names

    def test_path_a_edge_speaks_ack_script(self):
        """Req 3.5: Path A same-turn ack is spoken via the edge transition_speech.

        The mandated wording is delivered by the engine on the transition
        (``transition_speech``), not embedded in the node prompt — the node
        prompt must not instruct the LLM to speak or "call" anything, so the
        verbatim line lives on the Path A edge.
        """
        edge = next(e for e in self.result.edges if e.id == EDGE_PATH_A)
        assert edge.data.transition_speech == scripts.GREETING_PATH_A_STANDARD

    def test_path_e_edge_speaks_retry_script(self):
        """Req 6.9: Path E retry line is spoken via the edge transition_speech."""
        edge = next(e for e in self.result.edges if e.id == EDGE_PATH_E_LOOP)
        assert edge.data.transition_speech == scripts.GREETING_PATH_E

    def test_routing_request_edge_speaks_fallback_script(self):
        """Req 6.10: ROUTING REQUEST fallback is spoken via the edge transition_speech."""
        edge = next(e for e in self.result.edges if e.id == EDGE_ROUTING_REQUEST)
        assert edge.data.transition_speech == scripts.GREETING_ROUTING_REQUEST


class TestGreetingClusterEdges:
    """Tests for the edges produced by the Greeting cluster builder."""

    def setup_method(self):
        self.result = build_greeting_cluster()

    def test_produces_five_edges(self):
        assert len(self.result.edges) == 5

    def test_trigger_to_start_edge(self):
        edge = next(e for e in self.result.edges if e.id == EDGE_TRIGGER_TO_START)
        assert edge.source == TRIGGER_NODE_ID
        assert edge.target == START_CALL_NODE_ID

    def test_start_to_collect_edge(self):
        edge = next(e for e in self.result.edges if e.id == EDGE_START_TO_COLLECT)
        assert edge.source == START_CALL_NODE_ID
        assert edge.target == GREETING_COLLECT_NODE_ID

    def test_path_a_edge_transition_speech(self):
        """Req 3.5: Path A carries the ack line as transition_speech."""
        edge = next(e for e in self.result.edges if e.id == EDGE_PATH_A)
        assert edge.source == GREETING_COLLECT_NODE_ID
        assert edge.data.transition_speech == scripts.GREETING_PATH_A_STANDARD

    def test_path_e_loop_edge(self):
        """Req 6.9-6.11: Path E loops on Greeting Collect."""
        edge = next(e for e in self.result.edges if e.id == EDGE_PATH_E_LOOP)
        assert edge.source == GREETING_COLLECT_NODE_ID
        assert edge.target == GREETING_COLLECT_NODE_ID
        assert edge.data.transition_speech == scripts.GREETING_PATH_E

    def test_routing_request_edge(self):
        """Req 6.10: ROUTING REQUEST fallback edge."""
        edge = next(e for e in self.result.edges if e.id == EDGE_ROUTING_REQUEST)
        assert edge.source == GREETING_COLLECT_NODE_ID
        assert edge.data.transition_speech == scripts.GREETING_ROUTING_REQUEST


class TestGreetingClusterExportedIDs:
    """Tests that the exported node IDs are correct for downstream connections."""

    def setup_method(self):
        self.result = build_greeting_cluster()

    def test_trigger_id_exported(self):
        assert self.result.trigger_node_id == TRIGGER_NODE_ID

    def test_start_call_id_exported(self):
        assert self.result.start_call_node_id == START_CALL_NODE_ID

    def test_greeting_collect_id_exported(self):
        assert self.result.greeting_collect_node_id == GREETING_COLLECT_NODE_ID

    def test_exported_ids_match_actual_nodes(self):
        node_ids = {n.id for n in self.result.nodes}
        assert self.result.trigger_node_id in node_ids
        assert self.result.start_call_node_id in node_ids
        assert self.result.greeting_collect_node_id in node_ids


class TestGreetingClusterCustomConfig:
    """Tests that the builder accepts custom configuration."""

    def test_custom_pre_call_fetch_url(self):
        result = build_greeting_cluster(
            pre_call_fetch_url="https://custom.api.com/lookup"
        )
        start = next(n for n in result.nodes if n.id == START_CALL_NODE_ID)
        assert start.data.pre_call_fetch_url == "https://custom.api.com/lookup"

    def test_custom_recording_id(self):
        result = build_greeting_cluster(greeting_recording_id="custom_recording_123")
        start = next(n for n in result.nodes if n.id == START_CALL_NODE_ID)
        assert start.data.greeting_recording_id == "custom_recording_123"

    def test_custom_tool_uuid(self):
        result = build_greeting_cluster(
            patient_lookup_tool_uuid="uuid-patient-lookup-123"
        )
        start = next(n for n in result.nodes if n.id == START_CALL_NODE_ID)
        assert "uuid-patient-lookup-123" in start.data.tool_uuids
