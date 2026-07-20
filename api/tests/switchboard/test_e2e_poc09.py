"""E2E acceptance scenario tests: POC-09

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes. They do NOT use a live LLM or TTS pipeline; instead they:

1. Drive the pure logic functions (changed-request transition) through each
   scenario.
2. Inspect graph/cluster structure (edges, transition_speech, node IDs, labels)
   to verify the structural invariants.
3. Assert all observable outcomes: verbatim line, return-phase selection, graph-edge
   targeting.

Scenarios:
  POC-09 — changed request during auth. Both Business Hours (BH) and After
            Hours (AH): the caller changes their request during authentication,
            the system speaks the AUTH_CHANGED_REQUEST line and returns to
            Business Hours or After Hours (never to Routing).

Requirements: 20.11 (Req 9.8, AC-06)
"""

from __future__ import annotations


from api.services.switchboard.auth import (
    ChangedRequestTransition,
    ReturnPhase,
    changed_request_return_phase,
    changed_request_transition,
)
from api.services.switchboard.scripts import AUTH_CHANGED_REQUEST
from api.services.switchboard.clusters.authentication import (
    AH_INTENT_NODE_ID,
    AUTH_NODE_IDS,
    BH_INTENT_CLASSIFY_NODE_ID,
    build_authentication_cluster,
)
from api.services.switchboard.clusters.routing import build_routing_cluster
from api.services.switchboard.graph import build_switchboard_graph


# ---------------------------------------------------------------------------
# POC-09 Pure logic: changed_request_transition()
# ---------------------------------------------------------------------------


class TestPOC09ChangedRequestTransitionPureLogic:
    """POC-09 Pure logic: changed_request_transition() returns correct results.

    Requirements: 20.11 (Req 9.8, AC-06)
    """

    # ── 1. Business Hours scenario ───────────────────────────────────────

    def test_bh_transition_line_is_auth_changed_request(self) -> None:
        """changed_request_transition(after_hours=False) speaks AUTH_CHANGED_REQUEST."""
        transition = changed_request_transition(after_hours=False)
        assert transition.line == AUTH_CHANGED_REQUEST

    def test_bh_transition_return_phase_is_business_hours(self) -> None:
        """changed_request_transition(after_hours=False) returns to BUSINESS_HOURS."""
        transition = changed_request_transition(after_hours=False)
        assert transition.return_phase == ReturnPhase.BUSINESS_HOURS

    def test_bh_transition_to_routing_is_false(self) -> None:
        """changed_request_transition(after_hours=False) never goes to Routing."""
        transition = changed_request_transition(after_hours=False)
        assert transition.to_routing is False

    # ── 2. After Hours scenario ──────────────────────────────────────────

    def test_ah_transition_line_is_auth_changed_request(self) -> None:
        """changed_request_transition(after_hours=True) speaks AUTH_CHANGED_REQUEST."""
        transition = changed_request_transition(after_hours=True)
        assert transition.line == AUTH_CHANGED_REQUEST

    def test_ah_transition_return_phase_is_after_hours(self) -> None:
        """changed_request_transition(after_hours=True) returns to AFTER_HOURS."""
        transition = changed_request_transition(after_hours=True)
        assert transition.return_phase == ReturnPhase.AFTER_HOURS

    def test_ah_transition_to_routing_is_false(self) -> None:
        """changed_request_transition(after_hours=True) never goes to Routing."""
        transition = changed_request_transition(after_hours=True)
        assert transition.to_routing is False

    # ── 3. Transition dataclass structure ────────────────────────────────

    def test_transition_is_changed_request_transition_type(self) -> None:
        """changed_request_transition() returns a ChangedRequestTransition."""
        transition = changed_request_transition(after_hours=False)
        assert isinstance(transition, ChangedRequestTransition)

    def test_auth_changed_request_verbatim_value(self) -> None:
        """AUTH_CHANGED_REQUEST is the verbatim Appendix C line."""
        assert AUTH_CHANGED_REQUEST == "Sure, let me get you to the right place for that."


# ---------------------------------------------------------------------------
# POC-09 Pure logic: changed_request_return_phase()
# ---------------------------------------------------------------------------


class TestPOC09ChangedRequestReturnPhasePureLogic:
    """POC-09 Pure logic: changed_request_return_phase() return-phase selection.

    Requirements: 20.11 (Req 9.8, AC-06)
    """

    def test_return_phase_bh_when_not_after_hours(self) -> None:
        """changed_request_return_phase(after_hours=False) → BUSINESS_HOURS."""
        assert changed_request_return_phase(after_hours=False) == ReturnPhase.BUSINESS_HOURS

    def test_return_phase_ah_when_after_hours(self) -> None:
        """changed_request_return_phase(after_hours=True) → AFTER_HOURS."""
        assert changed_request_return_phase(after_hours=True) == ReturnPhase.AFTER_HOURS

    def test_return_phase_never_routing(self) -> None:
        """ReturnPhase has no ROUTING member — routing is never a valid return."""
        members = [m.value for m in ReturnPhase]
        assert "routing" not in members

    def test_return_phase_only_has_two_members(self) -> None:
        """ReturnPhase has exactly two members: BUSINESS_HOURS and AFTER_HOURS."""
        assert len(ReturnPhase) == 2
        assert ReturnPhase.BUSINESS_HOURS in ReturnPhase
        assert ReturnPhase.AFTER_HOURS in ReturnPhase


# ---------------------------------------------------------------------------
# POC-09 Graph structure: Authentication cluster changed-request edges
# ---------------------------------------------------------------------------


class TestPOC09AuthClusterChangedRequestEdges:
    """POC-09 Graph structure: changed-request edges in the Authentication cluster.

    Requirements: 20.11 (Req 9.8, AC-06)
    """

    # ── 3. Changed-request → BH edges ───────────────────────────────────

    def test_cluster_has_changed_bh_edges_for_each_auth_node(self) -> None:
        """Auth cluster has a 'Changed request → Business Hours' edge from each
        auth node targeting the BH intent classify node."""
        cluster = build_authentication_cluster(
            routing_entry_node_id="routing_entry",
            bh_intent_classify_node_id=BH_INTENT_CLASSIFY_NODE_ID,
            ah_intent_node_id=AH_INTENT_NODE_ID,
        )
        bh_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Changed request" in (e.data.label or "")
            and "Business Hours" in (e.data.label or "")
        ]
        assert len(bh_edges) == len(AUTH_NODE_IDS), (
            f"Expected {len(AUTH_NODE_IDS)} BH changed-request edges, got {len(bh_edges)}"
        )

    def test_cluster_bh_edges_target_bh_intent_classify_node(self) -> None:
        """All BH changed-request edges target bh_intent_classify_node_id."""
        cluster = build_authentication_cluster(
            routing_entry_node_id="routing_entry",
            bh_intent_classify_node_id=BH_INTENT_CLASSIFY_NODE_ID,
            ah_intent_node_id=AH_INTENT_NODE_ID,
        )
        bh_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Changed request" in (e.data.label or "")
            and "Business Hours" in (e.data.label or "")
        ]
        for edge in bh_edges:
            assert edge.target == BH_INTENT_CLASSIFY_NODE_ID

    def test_cluster_bh_edges_carry_auth_changed_request_speech(self) -> None:
        """All BH changed-request edges carry transition_speech=AUTH_CHANGED_REQUEST."""
        cluster = build_authentication_cluster(
            routing_entry_node_id="routing_entry",
            bh_intent_classify_node_id=BH_INTENT_CLASSIFY_NODE_ID,
            ah_intent_node_id=AH_INTENT_NODE_ID,
        )
        bh_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Changed request" in (e.data.label or "")
            and "Business Hours" in (e.data.label or "")
        ]
        for edge in bh_edges:
            assert edge.data.transition_speech == AUTH_CHANGED_REQUEST

    # ── 4. Changed-request → AH edges ───────────────────────────────────

    def test_cluster_has_changed_ah_edges_for_each_auth_node(self) -> None:
        """Auth cluster has a 'Changed request → After Hours' edge from each
        auth node targeting the AH intent node."""
        cluster = build_authentication_cluster(
            routing_entry_node_id="routing_entry",
            bh_intent_classify_node_id=BH_INTENT_CLASSIFY_NODE_ID,
            ah_intent_node_id=AH_INTENT_NODE_ID,
        )
        ah_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Changed request" in (e.data.label or "")
            and "After Hours" in (e.data.label or "")
        ]
        assert len(ah_edges) == len(AUTH_NODE_IDS), (
            f"Expected {len(AUTH_NODE_IDS)} AH changed-request edges, got {len(ah_edges)}"
        )

    def test_cluster_ah_edges_target_ah_intent_node(self) -> None:
        """All AH changed-request edges target ah_intent_node_id."""
        cluster = build_authentication_cluster(
            routing_entry_node_id="routing_entry",
            bh_intent_classify_node_id=BH_INTENT_CLASSIFY_NODE_ID,
            ah_intent_node_id=AH_INTENT_NODE_ID,
        )
        ah_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Changed request" in (e.data.label or "")
            and "After Hours" in (e.data.label or "")
        ]
        for edge in ah_edges:
            assert edge.target == AH_INTENT_NODE_ID

    def test_cluster_ah_edges_carry_auth_changed_request_speech(self) -> None:
        """All AH changed-request edges carry transition_speech=AUTH_CHANGED_REQUEST."""
        cluster = build_authentication_cluster(
            routing_entry_node_id="routing_entry",
            bh_intent_classify_node_id=BH_INTENT_CLASSIFY_NODE_ID,
            ah_intent_node_id=AH_INTENT_NODE_ID,
        )
        ah_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Changed request" in (e.data.label or "")
            and "After Hours" in (e.data.label or "")
        ]
        for edge in ah_edges:
            assert edge.data.transition_speech == AUTH_CHANGED_REQUEST

    # ── Edge IDs follow naming convention ────────────────────────────────

    def test_cluster_bh_edge_ids_follow_naming_convention(self) -> None:
        """BH changed-request edge IDs are auth_e_changed_bh_{node_id}."""
        cluster = build_authentication_cluster(
            routing_entry_node_id="routing_entry",
            bh_intent_classify_node_id=BH_INTENT_CLASSIFY_NODE_ID,
            ah_intent_node_id=AH_INTENT_NODE_ID,
        )
        for node_id in AUTH_NODE_IDS:
            expected_id = f"auth_e_changed_bh_{node_id}"
            matching = [e for e in cluster.edges if e.id == expected_id]
            assert len(matching) == 1, f"Missing BH changed-request edge for {node_id}"

    def test_cluster_ah_edge_ids_follow_naming_convention(self) -> None:
        """AH changed-request edge IDs are auth_e_changed_ah_{node_id}."""
        cluster = build_authentication_cluster(
            routing_entry_node_id="routing_entry",
            bh_intent_classify_node_id=BH_INTENT_CLASSIFY_NODE_ID,
            ah_intent_node_id=AH_INTENT_NODE_ID,
        )
        for node_id in AUTH_NODE_IDS:
            expected_id = f"auth_e_changed_ah_{node_id}"
            matching = [e for e in cluster.edges if e.id == expected_id]
            assert len(matching) == 1, f"Missing AH changed-request edge for {node_id}"


# ---------------------------------------------------------------------------
# POC-09 Full graph integration: changed-request edges
# ---------------------------------------------------------------------------


class TestPOC09FullGraphChangedRequestEdges:
    """POC-09 Full graph integration: changed-request edges in assembled graph.

    Requirements: 20.11 (Req 9.8, AC-06)
    """

    def test_full_graph_has_changed_request_edges_from_auth_nodes(self) -> None:
        """The assembled graph contains changed-request edges from auth nodes."""
        wg = build_switchboard_graph()
        changed_request_edges = [
            e for e in wg.edges
            if e.transition_speech == AUTH_CHANGED_REQUEST
        ]
        # Should have edges for both BH and AH from each auth node
        assert len(changed_request_edges) == len(AUTH_NODE_IDS) * 2, (
            f"Expected {len(AUTH_NODE_IDS) * 2} changed-request edges "
            f"(BH+AH for each auth node), got {len(changed_request_edges)}"
        )

    def test_full_graph_changed_request_edges_never_target_routing(self) -> None:
        """Changed-request edges never target the routing resolve node."""
        wg = build_switchboard_graph()
        routing = build_routing_cluster()
        changed_request_edges = [
            e for e in wg.edges
            if e.transition_speech == AUTH_CHANGED_REQUEST
        ]
        for edge in changed_request_edges:
            assert edge.target != routing.resolve_route_id, (
                f"Changed-request edge from {edge.source} targets routing — "
                "should never go to Routing (Req 9.8, AC-06)"
            )

    def test_full_graph_changed_request_edges_target_bh_or_ah(self) -> None:
        """All changed-request edges target either BH intent classify or AH intent."""
        wg = build_switchboard_graph()
        from api.services.switchboard.clusters.after_hours import NODE_AH_INTENT

        # Find the BH intent classify node (it has a dynamic ID based on UUID)
        # We identify it by being a non-AH target of changed-request edges
        changed_request_edges = [
            e for e in wg.edges
            if e.transition_speech == AUTH_CHANGED_REQUEST
        ]
        targets = {e.target for e in changed_request_edges}
        # One target is AH intent, the other is BH intent classify
        assert NODE_AH_INTENT in targets, (
            "Expected AH intent node as a changed-request target"
        )
        # Remaining targets should be one BH intent classify node (not routing/end)
        non_ah_targets = targets - {NODE_AH_INTENT}
        assert len(non_ah_targets) == 1, (
            f"Expected exactly 1 non-AH target (BH intent classify), got {non_ah_targets}"
        )

    def test_full_graph_bh_changed_request_edges_source_from_auth_nodes(self) -> None:
        """BH changed-request edges originate from auth nodes."""
        wg = build_switchboard_graph()
        from api.services.switchboard.clusters.after_hours import NODE_AH_INTENT

        # BH edges are those with AUTH_CHANGED_REQUEST that don't target AH
        bh_edges = [
            e for e in wg.edges
            if e.transition_speech == AUTH_CHANGED_REQUEST
            and e.target != NODE_AH_INTENT
        ]
        for edge in bh_edges:
            assert edge.source in AUTH_NODE_IDS, (
                f"BH changed-request edge source {edge.source} is not an auth node"
            )

    def test_full_graph_ah_changed_request_edges_source_from_auth_nodes(self) -> None:
        """AH changed-request edges originate from auth nodes."""
        wg = build_switchboard_graph()
        from api.services.switchboard.clusters.after_hours import NODE_AH_INTENT

        ah_edges = [
            e for e in wg.edges
            if e.transition_speech == AUTH_CHANGED_REQUEST
            and e.target == NODE_AH_INTENT
        ]
        for edge in ah_edges:
            assert edge.source in AUTH_NODE_IDS, (
                f"AH changed-request edge source {edge.source} is not an auth node"
            )


# ---------------------------------------------------------------------------
# POC-09 E2E scenario walkthrough
# ---------------------------------------------------------------------------


class TestPOC09E2EScenarioWalkthrough:
    """POC-09 E2E scenario: caller changes request during authentication.

    Requirements: 20.11 (Req 9.8, AC-06)
    """

    def test_e2e_bh_changed_request_speaks_line_and_returns_to_bh(self) -> None:
        """E2E BH: caller changes request during auth → speaks AUTH_CHANGED_REQUEST,
        returns to Business Hours, never goes to Routing."""
        transition = changed_request_transition(after_hours=False)

        # The system speaks the mandated line
        assert transition.line == AUTH_CHANGED_REQUEST
        assert transition.line == "Sure, let me get you to the right place for that."

        # Returns to Business Hours
        assert transition.return_phase == ReturnPhase.BUSINESS_HOURS

        # Never goes to Routing
        assert transition.to_routing is False

    def test_e2e_ah_changed_request_speaks_line_and_returns_to_ah(self) -> None:
        """E2E AH: caller changes request during auth → speaks AUTH_CHANGED_REQUEST,
        returns to After Hours, never goes to Routing."""
        transition = changed_request_transition(after_hours=True)

        # The system speaks the mandated line
        assert transition.line == AUTH_CHANGED_REQUEST
        assert transition.line == "Sure, let me get you to the right place for that."

        # Returns to After Hours
        assert transition.return_phase == ReturnPhase.AFTER_HOURS

        # Never goes to Routing
        assert transition.to_routing is False

    def test_e2e_neither_scenario_goes_to_routing(self) -> None:
        """E2E: in neither BH nor AH scenario does the changed request go to Routing."""
        bh_transition = changed_request_transition(after_hours=False)
        ah_transition = changed_request_transition(after_hours=True)

        assert bh_transition.to_routing is False
        assert ah_transition.to_routing is False
        assert bh_transition.return_phase != "routing"
        assert ah_transition.return_phase != "routing"

    def test_e2e_graph_bh_scenario_edge_carries_speech_to_bh_node(self) -> None:
        """E2E BH graph: an auth node's changed-request edge carries
        AUTH_CHANGED_REQUEST and targets the BH intent classify node."""
        wg = build_switchboard_graph()
        from api.services.switchboard.clusters.after_hours import NODE_AH_INTENT

        # Pick the first auth node as representative
        auth_node = AUTH_NODE_IDS[0]
        bh_edges = [
            e for e in wg.edges
            if e.source == auth_node
            and e.transition_speech == AUTH_CHANGED_REQUEST
            and e.target != NODE_AH_INTENT
        ]
        assert len(bh_edges) == 1, (
            f"Expected 1 BH changed-request edge from {auth_node}, got {len(bh_edges)}"
        )
        # Verify it speaks the mandated line
        assert bh_edges[0].transition_speech == AUTH_CHANGED_REQUEST

    def test_e2e_graph_ah_scenario_edge_carries_speech_to_ah_node(self) -> None:
        """E2E AH graph: an auth node's changed-request edge carries
        AUTH_CHANGED_REQUEST and targets the AH intent node."""
        wg = build_switchboard_graph()
        from api.services.switchboard.clusters.after_hours import NODE_AH_INTENT

        # Pick the first auth node as representative
        auth_node = AUTH_NODE_IDS[0]
        ah_edges = [
            e for e in wg.edges
            if e.source == auth_node
            and e.transition_speech == AUTH_CHANGED_REQUEST
            and e.target == NODE_AH_INTENT
        ]
        assert len(ah_edges) == 1, (
            f"Expected 1 AH changed-request edge from {auth_node}, got {len(ah_edges)}"
        )
        assert ah_edges[0].target == NODE_AH_INTENT
