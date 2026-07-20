"""E2E acceptance scenario tests: POC-08

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes. They do NOT use a live LLM or TTS pipeline; instead they:

1. Drive the pure logic functions (classification-retry machines) through each
   scenario.
2. Inspect graph/cluster structure (edges, transition_speech, node IDs, labels)
   to verify the structural invariants.
3. Assert all observable outcomes: verbatim retry lines, silent transitions,
   graph-edge targeting.

Scenarios:
  POC-08 — two retries then silent route. Both Business Hours (BH) and After
            Hours (AH): the retry machine speaks Retry 1 on the first classification
            failure, Retry 2 on the second, and silently transitions to Routing
            (no speech) on the third consecutive failure.

Requirements: 20.10 (Req 7.11, 7.12, 8.6, 8.7)
"""

from __future__ import annotations


from api.services.switchboard.business_hours import (
    BH_CLASSIFICATION_MAX_RETRIES,
    BHClassificationRetryState,
    SILENT_TO_ROUTING,
    bh_classification_retry,
)
from api.services.switchboard.after_hours import (
    AH_CLASSIFICATION_MAX_RETRIES,
    AHClassificationRetryState,
    ah_classification_retry,
)
from api.services.switchboard.scripts import (
    AH_RETRY_1,
    AH_RETRY_2,
    BH_RETRY_1,
    BH_RETRY_2,
)
from api.services.switchboard.clusters.business_hours import (
    build_business_hours_cluster,
)
from api.services.switchboard.clusters.after_hours import (
    EDGE_AH_RETRY_1,
    EDGE_AH_RETRY_2,
    EDGE_AH_RETRY_3_SILENT,
    NODE_AH_INTENT,
    build_after_hours_cluster,
)
from api.services.switchboard.clusters.routing import build_routing_cluster
from api.services.switchboard.graph import build_switchboard_graph
from api.services.switchboard.transitions import (
    SilentTransitionType,
    classify_silent_transition,
    is_silent_transition,
)


# ---------------------------------------------------------------------------
# POC-08 Business Hours: two retries then silent route
# ---------------------------------------------------------------------------


class TestPOC08TwoRetriesThenSilentRouteBH:
    """POC-08 Business Hours: two retries then silent route.

    Requirements: 20.10 (Req 7.11, 7.12)
    """

    # ── 1. BH retry machine — pure logic ─────────────────────────────────

    def test_bh_retry_1_speaks_bh_retry_1_line(self) -> None:
        """bh_classification_retry(1) speaks the BH_RETRY_1 line."""
        decision = bh_classification_retry(1)
        assert decision.spoken_line == BH_RETRY_1

    def test_bh_retry_1_is_not_silent(self) -> None:
        """bh_classification_retry(1) is NOT silent (it speaks)."""
        decision = bh_classification_retry(1)
        assert decision.is_silent is False

    def test_bh_retry_1_has_no_silent_transition(self) -> None:
        """bh_classification_retry(1) has silent_transition=None."""
        decision = bh_classification_retry(1)
        assert decision.silent_transition is None

    def test_bh_retry_2_speaks_bh_retry_2_line(self) -> None:
        """bh_classification_retry(2) speaks the BH_RETRY_2 line."""
        decision = bh_classification_retry(2)
        assert decision.spoken_line == BH_RETRY_2

    def test_bh_retry_2_is_not_silent(self) -> None:
        """bh_classification_retry(2) is NOT silent (it speaks)."""
        decision = bh_classification_retry(2)
        assert decision.is_silent is False

    def test_bh_retry_2_has_no_silent_transition(self) -> None:
        """bh_classification_retry(2) has silent_transition=None."""
        decision = bh_classification_retry(2)
        assert decision.silent_transition is None

    def test_bh_retry_3_spoken_line_is_none(self) -> None:
        """bh_classification_retry(3) speaks nothing (spoken_line=None)."""
        decision = bh_classification_retry(3)
        assert decision.spoken_line is None

    def test_bh_retry_3_is_silent(self) -> None:
        """bh_classification_retry(3) is silent (is_silent=True)."""
        decision = bh_classification_retry(3)
        assert decision.is_silent is True

    def test_bh_retry_3_silent_transition_is_silent_to_routing(self) -> None:
        """bh_classification_retry(3) has silent_transition=SILENT_TO_ROUTING."""
        decision = bh_classification_retry(3)
        assert decision.silent_transition is SILENT_TO_ROUTING

    def test_bh_beyond_3_stays_silent(self) -> None:
        """bh_classification_retry(5) is still silent (beyond 3rd)."""
        decision = bh_classification_retry(5)
        assert decision.is_silent is True
        assert decision.silent_transition is SILENT_TO_ROUTING

    def test_bh_max_retries_is_2(self) -> None:
        """BH_CLASSIFICATION_MAX_RETRIES is 2 (two spoken retries before silent)."""
        assert BH_CLASSIFICATION_MAX_RETRIES == 2

    # ── 2. BHClassificationRetryState tracks consecutive failures ────────

    def test_bh_state_initial_has_zero_failures(self) -> None:
        """Fresh BHClassificationRetryState has consecutive_failures=0."""
        state = BHClassificationRetryState()
        assert state.consecutive_failures == 0

    def test_bh_state_record_failure_increments(self) -> None:
        """record_failure() returns a new state with incremented count."""
        state = BHClassificationRetryState()
        state1 = state.record_failure()
        assert state1.consecutive_failures == 1
        state2 = state1.record_failure()
        assert state2.consecutive_failures == 2

    def test_bh_state_reset_clears_failures(self) -> None:
        """reset() returns a state with consecutive_failures=0."""
        state = BHClassificationRetryState(consecutive_failures=3)
        assert state.reset().consecutive_failures == 0

    def test_bh_state_has_fallen_back_after_3_failures(self) -> None:
        """has_fallen_back is True after 3 consecutive failures."""
        state = BHClassificationRetryState(consecutive_failures=3)
        assert state.has_fallen_back is True

    def test_bh_state_has_not_fallen_back_at_2_failures(self) -> None:
        """has_fallen_back is False at 2 consecutive failures (still retrying)."""
        state = BHClassificationRetryState(consecutive_failures=2)
        assert state.has_fallen_back is False

    def test_bh_state_decision_at_1_failure_speaks_retry_1(self) -> None:
        """State with 1 failure produces decision with spoken_line=BH_RETRY_1."""
        state = BHClassificationRetryState(consecutive_failures=1)
        assert state.decision.spoken_line == BH_RETRY_1

    def test_bh_state_decision_at_3_failures_is_silent(self) -> None:
        """State with 3 failures produces silent decision."""
        state = BHClassificationRetryState(consecutive_failures=3)
        assert state.decision.is_silent is True

    # ── 3. BH cluster: retry edges structure ─────────────────────────────

    def test_bh_cluster_has_retry_1_self_loop_edge(self) -> None:
        """BH cluster has a retry-1 self-loop edge labeled 'Retry 1 - Not Understood'
        with transition_speech=BH_RETRY_1."""
        cluster = build_business_hours_cluster(routing_entry_node_id="routing_resolve_route")
        retry_1_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Retry 1 - Not Understood" in (e.data.label or "")
        ]
        assert len(retry_1_edges) == 1
        edge = retry_1_edges[0]
        assert edge.source == edge.target  # self-loop
        assert edge.data.transition_speech == BH_RETRY_1

    def test_bh_cluster_has_retry_2_self_loop_edge(self) -> None:
        """BH cluster has a retry-2 self-loop edge labeled 'Retry 2 - Still Not Understood'
        with transition_speech=BH_RETRY_2."""
        cluster = build_business_hours_cluster(routing_entry_node_id="routing_resolve_route")
        retry_2_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Retry 2 - Still Not Understood" in (e.data.label or "")
        ]
        assert len(retry_2_edges) == 1
        edge = retry_2_edges[0]
        assert edge.source == edge.target  # self-loop
        assert edge.data.transition_speech == BH_RETRY_2

    def test_bh_cluster_has_retry_3_silent_edge_to_routing(self) -> None:
        """BH cluster has a retry-3 edge labeled 'Retry 3 - Silent Route' with
        transition_speech='' targeting routing."""
        routing_entry = "routing_resolve_route"
        cluster = build_business_hours_cluster(routing_entry_node_id=routing_entry)
        retry_3_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Retry 3 - Silent Route" in (e.data.label or "")
        ]
        assert len(retry_3_edges) == 1
        edge = retry_3_edges[0]
        assert edge.data.transition_speech == ""
        assert edge.target == routing_entry

    # ── 4. Silent-transition classifier: BH retry-3 ─────────────────────

    def test_bh_retry_3_edge_classified_as_retry_3(self) -> None:
        """The BH retry-3 edge is classified as SilentTransitionType.RETRY_3."""
        routing_entry = "routing_resolve_route"
        cluster = build_business_hours_cluster(routing_entry_node_id=routing_entry)
        retry_3_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Retry 3 - Silent Route" in (e.data.label or "")
        ]
        assert len(retry_3_edges) == 1
        classification = classify_silent_transition(retry_3_edges[0])
        assert classification == SilentTransitionType.RETRY_3

    def test_bh_retry_3_edge_is_silent(self) -> None:
        """The BH retry-3 edge passes is_silent_transition() check."""
        routing_entry = "routing_resolve_route"
        cluster = build_business_hours_cluster(routing_entry_node_id=routing_entry)
        retry_3_edges = [
            e for e in cluster.edges
            if e.data is not None
            and "Retry 3 - Silent Route" in (e.data.label or "")
        ]
        assert len(retry_3_edges) == 1
        assert is_silent_transition(retry_3_edges[0]) is True

    # ── 5. Full graph: BH retry-3 targets routing resolve node ───────────

    def test_full_graph_has_bh_retry_3_silent_edge(self) -> None:
        """The assembled graph contains the BH retry-3 silent edge targeting
        the routing resolve node."""
        wg = build_switchboard_graph()
        routing = build_routing_cluster()
        retry_3_edges = [
            e for e in wg.edges
            if "Retry 3 - Silent Route" in (e.label or "")
            and e.transition_speech == ""
            and e.target == routing.resolve_route_id
        ]
        assert len(retry_3_edges) >= 1, (
            "Expected at least one BH retry-3 silent edge targeting routing resolve"
        )

    # ── 6. E2E scenario walkthrough: BH ──────────────────────────────────

    def test_bh_e2e_walkthrough_three_failures(self) -> None:
        """E2E: BH caller fails classification 3 times. Retry 1 spoken, Retry 2
        spoken, then silent transition to Routing (no speech)."""
        state = BHClassificationRetryState()

        # Failure 1: speak BH_RETRY_1
        state = state.record_failure()
        decision = state.decision
        assert decision.spoken_line == BH_RETRY_1
        assert decision.is_silent is False

        # Failure 2: speak BH_RETRY_2
        state = state.record_failure()
        decision = state.decision
        assert decision.spoken_line == BH_RETRY_2
        assert decision.is_silent is False

        # Failure 3: silent transition to Routing
        state = state.record_failure()
        decision = state.decision
        assert decision.spoken_line is None
        assert decision.is_silent is True
        assert decision.silent_transition is SILENT_TO_ROUTING

    def test_bh_e2e_reset_after_success(self) -> None:
        """If classification succeeds, the state resets and retry count restarts."""
        state = BHClassificationRetryState()
        state = state.record_failure()
        assert state.decision.spoken_line == BH_RETRY_1

        # Success resets
        state = state.reset()
        assert state.consecutive_failures == 0

        # Next failure starts from 1 again
        state = state.record_failure()
        assert state.decision.spoken_line == BH_RETRY_1


# ---------------------------------------------------------------------------
# POC-08 After Hours: two retries then silent route
# ---------------------------------------------------------------------------


class TestPOC08TwoRetriesThenSilentRouteAH:
    """POC-08 After Hours: two retries then silent route.

    Requirements: 20.10 (Req 8.6, 8.7)
    """

    # ── 1. AH retry machine — pure logic ─────────────────────────────────

    def test_ah_retry_1_speaks_ah_retry_1_line(self) -> None:
        """ah_classification_retry(1) speaks the AH_RETRY_1 line."""
        decision = ah_classification_retry(1)
        assert decision.spoken_line == AH_RETRY_1

    def test_ah_retry_1_is_not_silent(self) -> None:
        """ah_classification_retry(1) is NOT silent (it speaks)."""
        decision = ah_classification_retry(1)
        assert decision.is_silent is False

    def test_ah_retry_1_has_no_silent_transition(self) -> None:
        """ah_classification_retry(1) has silent_transition=None."""
        decision = ah_classification_retry(1)
        assert decision.silent_transition is None

    def test_ah_retry_2_speaks_ah_retry_2_line(self) -> None:
        """ah_classification_retry(2) speaks the AH_RETRY_2 line."""
        decision = ah_classification_retry(2)
        assert decision.spoken_line == AH_RETRY_2

    def test_ah_retry_2_is_not_silent(self) -> None:
        """ah_classification_retry(2) is NOT silent (it speaks)."""
        decision = ah_classification_retry(2)
        assert decision.is_silent is False

    def test_ah_retry_2_has_no_silent_transition(self) -> None:
        """ah_classification_retry(2) has silent_transition=None."""
        decision = ah_classification_retry(2)
        assert decision.silent_transition is None

    def test_ah_retry_3_spoken_line_is_none(self) -> None:
        """ah_classification_retry(3) speaks nothing (spoken_line=None)."""
        decision = ah_classification_retry(3)
        assert decision.spoken_line is None

    def test_ah_retry_3_is_silent(self) -> None:
        """ah_classification_retry(3) is silent (is_silent=True)."""
        decision = ah_classification_retry(3)
        assert decision.is_silent is True

    def test_ah_retry_3_silent_transition_is_silent_to_routing(self) -> None:
        """ah_classification_retry(3) has silent_transition=SILENT_TO_ROUTING."""
        decision = ah_classification_retry(3)
        assert decision.silent_transition is SILENT_TO_ROUTING

    def test_ah_beyond_3_stays_silent(self) -> None:
        """ah_classification_retry(5) is still silent (beyond 3rd)."""
        decision = ah_classification_retry(5)
        assert decision.is_silent is True
        assert decision.silent_transition is SILENT_TO_ROUTING

    def test_ah_max_retries_is_2(self) -> None:
        """AH_CLASSIFICATION_MAX_RETRIES is 2 (two spoken retries before silent)."""
        assert AH_CLASSIFICATION_MAX_RETRIES == 2

    # ── 2. AHClassificationRetryState tracks consecutive failures ────────

    def test_ah_state_initial_has_zero_failures(self) -> None:
        """Fresh AHClassificationRetryState has consecutive_failures=0."""
        state = AHClassificationRetryState()
        assert state.consecutive_failures == 0

    def test_ah_state_record_failure_increments(self) -> None:
        """record_failure() returns a new state with incremented count."""
        state = AHClassificationRetryState()
        state1 = state.record_failure()
        assert state1.consecutive_failures == 1
        state2 = state1.record_failure()
        assert state2.consecutive_failures == 2

    def test_ah_state_reset_clears_failures(self) -> None:
        """reset() returns a state with consecutive_failures=0."""
        state = AHClassificationRetryState(consecutive_failures=3)
        assert state.reset().consecutive_failures == 0

    def test_ah_state_has_fallen_back_after_3_failures(self) -> None:
        """has_fallen_back is True after 3 consecutive failures."""
        state = AHClassificationRetryState(consecutive_failures=3)
        assert state.has_fallen_back is True

    def test_ah_state_has_not_fallen_back_at_2_failures(self) -> None:
        """has_fallen_back is False at 2 consecutive failures (still retrying)."""
        state = AHClassificationRetryState(consecutive_failures=2)
        assert state.has_fallen_back is False

    def test_ah_state_decision_at_1_failure_speaks_retry_1(self) -> None:
        """State with 1 failure produces decision with spoken_line=AH_RETRY_1."""
        state = AHClassificationRetryState(consecutive_failures=1)
        assert state.decision.spoken_line == AH_RETRY_1

    def test_ah_state_decision_at_3_failures_is_silent(self) -> None:
        """State with 3 failures produces silent decision."""
        state = AHClassificationRetryState(consecutive_failures=3)
        assert state.decision.is_silent is True

    # ── 3. AH cluster: retry edges structure ─────────────────────────────

    def test_ah_cluster_has_retry_1_edge(self) -> None:
        """AH cluster has EDGE_AH_RETRY_1 with transition_speech=AH_RETRY_1."""
        cluster = build_after_hours_cluster()
        retry_1_edges = [e for e in cluster.edges if e.id == EDGE_AH_RETRY_1]
        assert len(retry_1_edges) == 1
        edge = retry_1_edges[0]
        assert edge.data.transition_speech == AH_RETRY_1

    def test_ah_cluster_retry_1_is_self_loop(self) -> None:
        """EDGE_AH_RETRY_1 is a self-loop from AH Intent → AH Intent."""
        cluster = build_after_hours_cluster()
        retry_1_edges = [e for e in cluster.edges if e.id == EDGE_AH_RETRY_1]
        assert len(retry_1_edges) == 1
        edge = retry_1_edges[0]
        assert edge.source == NODE_AH_INTENT
        assert edge.target == NODE_AH_INTENT

    def test_ah_cluster_has_retry_2_edge(self) -> None:
        """AH cluster has EDGE_AH_RETRY_2 with transition_speech=AH_RETRY_2."""
        cluster = build_after_hours_cluster()
        retry_2_edges = [e for e in cluster.edges if e.id == EDGE_AH_RETRY_2]
        assert len(retry_2_edges) == 1
        edge = retry_2_edges[0]
        assert edge.data.transition_speech == AH_RETRY_2

    def test_ah_cluster_retry_2_is_self_loop(self) -> None:
        """EDGE_AH_RETRY_2 is a self-loop from AH Intent → AH Intent."""
        cluster = build_after_hours_cluster()
        retry_2_edges = [e for e in cluster.edges if e.id == EDGE_AH_RETRY_2]
        assert len(retry_2_edges) == 1
        edge = retry_2_edges[0]
        assert edge.source == NODE_AH_INTENT
        assert edge.target == NODE_AH_INTENT

    def test_ah_cluster_has_retry_3_silent_edge(self) -> None:
        """AH cluster has EDGE_AH_RETRY_3_SILENT with transition_speech='' (silent)."""
        cluster = build_after_hours_cluster()
        retry_3_edges = [e for e in cluster.edges if e.id == EDGE_AH_RETRY_3_SILENT]
        assert len(retry_3_edges) == 1
        edge = retry_3_edges[0]
        assert edge.data.transition_speech == ""

    def test_ah_cluster_retry_3_targets_routing(self) -> None:
        """EDGE_AH_RETRY_3_SILENT targets the routing entry node (not self-loop)."""
        cluster = build_after_hours_cluster()
        retry_3_edges = [e for e in cluster.edges if e.id == EDGE_AH_RETRY_3_SILENT]
        assert len(retry_3_edges) == 1
        edge = retry_3_edges[0]
        assert edge.source == NODE_AH_INTENT
        # target is routing entry, not AH Intent
        assert edge.target != NODE_AH_INTENT

    # ── 4. Silent-transition classifier: AH retry-3 ─────────────────────

    def test_ah_retry_3_edge_classified_as_retry_3(self) -> None:
        """The AH retry-3 edge is classified as SilentTransitionType.RETRY_3."""
        cluster = build_after_hours_cluster()
        retry_3_edges = [e for e in cluster.edges if e.id == EDGE_AH_RETRY_3_SILENT]
        assert len(retry_3_edges) == 1
        classification = classify_silent_transition(retry_3_edges[0])
        assert classification == SilentTransitionType.RETRY_3

    def test_ah_retry_3_edge_is_silent(self) -> None:
        """The AH retry-3 edge passes is_silent_transition() check."""
        cluster = build_after_hours_cluster()
        retry_3_edges = [e for e in cluster.edges if e.id == EDGE_AH_RETRY_3_SILENT]
        assert len(retry_3_edges) == 1
        assert is_silent_transition(retry_3_edges[0]) is True

    # ── 5. Full graph: AH retry-3 targets routing resolve node ───────────

    def test_full_graph_has_ah_retry_3_silent_edge(self) -> None:
        """The assembled graph contains the AH retry-3 silent edge from AH Intent
        to the routing resolve node."""
        wg = build_switchboard_graph()
        routing = build_routing_cluster()
        retry_3_edges = [
            e for e in wg.edges
            if e.source == NODE_AH_INTENT
            and e.target == routing.resolve_route_id
            and e.transition_speech == ""
            and "3rd failure" in (e.label or "").lower()
        ]
        assert len(retry_3_edges) >= 1, (
            "Expected at least one AH retry-3 silent edge from ah_intent to "
            "routing resolve"
        )

    # ── 6. E2E scenario walkthrough: AH ──────────────────────────────────

    def test_ah_e2e_walkthrough_three_failures(self) -> None:
        """E2E: AH caller fails classification 3 times. Retry 1 spoken, Retry 2
        spoken, then silent transition to Routing (no speech)."""
        state = AHClassificationRetryState()

        # Failure 1: speak AH_RETRY_1
        state = state.record_failure()
        decision = state.decision
        assert decision.spoken_line == AH_RETRY_1
        assert decision.is_silent is False

        # Failure 2: speak AH_RETRY_2
        state = state.record_failure()
        decision = state.decision
        assert decision.spoken_line == AH_RETRY_2
        assert decision.is_silent is False

        # Failure 3: silent transition to Routing
        state = state.record_failure()
        decision = state.decision
        assert decision.spoken_line is None
        assert decision.is_silent is True
        assert decision.silent_transition is SILENT_TO_ROUTING

    def test_ah_e2e_reset_after_success(self) -> None:
        """If classification succeeds, the state resets and retry count restarts."""
        state = AHClassificationRetryState()
        state = state.record_failure()
        assert state.decision.spoken_line == AH_RETRY_1

        # Success resets
        state = state.reset()
        assert state.consecutive_failures == 0

        # Next failure starts from 1 again
        state = state.record_failure()
        assert state.decision.spoken_line == AH_RETRY_1

    # ── 7. Full graph integration: both BH and AH retry-3 edges present ──

    def test_full_graph_both_bh_and_ah_retry_3_edges_target_routing(self) -> None:
        """The assembled graph contains BOTH BH retry-3 and AH retry-3 silent
        edges targeting the same routing resolve node."""
        wg = build_switchboard_graph()
        routing = build_routing_cluster()

        # BH retry-3 (identified by label)
        bh_retry_3 = [
            e for e in wg.edges
            if "Retry 3 - Silent Route" in (e.label or "")
            and e.transition_speech == ""
            and e.target == routing.resolve_route_id
        ]

        # AH retry-3 (identified by source=ah_intent + label)
        ah_retry_3 = [
            e for e in wg.edges
            if e.source == NODE_AH_INTENT
            and e.target == routing.resolve_route_id
            and e.transition_speech == ""
            and "3rd failure" in (e.label or "").lower()
        ]

        assert len(bh_retry_3) >= 1, "BH retry-3 silent edge not found in graph"
        assert len(ah_retry_3) >= 1, "AH retry-3 silent edge not found in graph"
