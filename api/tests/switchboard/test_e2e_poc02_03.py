"""E2E acceptance scenario tests: POC-02 / POC-03

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes.  They do NOT use a live LLM or TTS pipeline; instead they:

1. Build the graph via ``build_switchboard_graph()`` and verify its structure.
2. Trace the pure logic functions (auth gate, after-hours decision logic) through
   each scenario.
3. Assert the observable outcomes: auth skip, graph structure, verbatim script
   lines, and connect-decision logic.

Scenarios:
  POC-02  — business-hours Records call (auth skipped, silent BH→Routing, E_RECORDS)
  POC-03  — after-hours restricted-service scheduling (INFORM/ASK, agree→Auth+Route,
             decline/timeout → no auth or routing)

Requirements: 20.4, 20.5
"""

from __future__ import annotations


from api.services.switchboard.after_hours import (
    ConnectResponse,
    RestrictedServiceConnectDecision,
    restricted_service_connect_decision,
    restricted_service_offer_line,
)
from api.services.switchboard.auth import (
    auth_required,
    may_proceed_to_routing,
    PATIENT_VERIFIED_SUCCESS,
)
from api.services.switchboard.clusters.after_hours import (
    NODE_AH_RESTRICTED_CONNECT,
    EDGE_AH_RESTRICTED_CONNECT_TO_AUTH,
    EDGE_AH_RESTRICTED_CONNECT_TO_END,
    build_after_hours_cluster,
)
from api.services.switchboard.graph import build_switchboard_graph
from api.services.switchboard.scripts import (
    AH_RESTRICTED_SERVICE_SCHEDULING,
    E_RECORDS,
)


# ---------------------------------------------------------------------------
# POC-02: Records in hours — auth skipped, silent route, E_RECORDS terminal line
# ---------------------------------------------------------------------------


class TestPOC02RecordsInHours:
    """POC-02: after_hours=False, intent=Records.

    Scripted trace:
      Greeting → Business Hours → Routing (silent, no auth) → speaks E_RECORDS

    Requirements: 20.4
    """

    # ── 1. Auth gate: Records always skips auth ──────────────────────────

    def test_auth_not_required_for_records_no_patient_status(self) -> None:
        """auth_required('Records', None) is False — Records always skips auth."""
        assert auth_required("Records", None) is False

    def test_auth_not_required_for_records_existing_patient(self) -> None:
        """auth_required('Records', 'existing') is False — even existing patient."""
        assert auth_required("Records", "existing") is False

    # ── 2. GATE-AUTH: may proceed to routing without any verification ─────

    def test_gate_open_for_records_no_patient_status(self) -> None:
        """GATE-AUTH: may_proceed_to_routing is True for Records with no patient_status."""
        assert may_proceed_to_routing("Records", None, None) is True

    def test_gate_open_for_records_existing_no_verification(self) -> None:
        """GATE-AUTH: may_proceed_to_routing is True for Records/existing even with
        patient_verified=None — auth was never required."""
        assert may_proceed_to_routing("Records", "existing", None) is True

    # ── 3. Verbatim transfer line ─────────────────────────────────────────

    def test_e_records_exact_wording(self) -> None:
        """E_RECORDS is the exact mandated verbatim transfer line (Appendix E)."""
        assert E_RECORDS == "Let me get you over to the Records department. One moment."

    # ── 4. Graph: BH→Routing silent edge for Records ─────────────────────

    def test_graph_has_records_silent_routing_edge(self) -> None:
        """The assembled graph has a silent-transition edge whose condition mentions
        Records, confirming the BH→Routing silent skip for Records."""
        wg = build_switchboard_graph()
        # Find edges with empty transition_speech whose condition mentions "Records"
        records_silent_edges = [
            e for e in wg.edges
            if e.data is not None
            and e.data.transition_speech == ""
            and "records" in (e.data.condition or "").lower()
        ]
        assert len(records_silent_edges) >= 1, (
            "Expected at least one silent edge with 'Records' in its condition "
            "(BH→Routing skip for Records)"
        )

    # ── 5. Lab results → General, not Records (auth required) ────────────

    def test_auth_required_for_general_existing_patient(self) -> None:
        """auth_required('General', 'existing') is True.

        Lab results route to General (not Records), and General requires auth.
        This ensures the Records skip does NOT bleed into General.
        """
        assert auth_required("General", "existing") is True


# ---------------------------------------------------------------------------
# POC-03: After-hours restricted service (scheduling) — INFORM/ASK/agree path
# ---------------------------------------------------------------------------


class TestPOC03AfterHoursRestrictedScheduling:
    """POC-03: after_hours=True, caller requests scheduling (restricted after hours).

    Scripted trace (agree path):
      Greeting → After Hours → AH Restricted Connect (INFORM/ASK) →
      caller agrees → Authentication → After-hours Routing

    Scripted trace (decline/timeout path):
      Greeting → After Hours → AH Restricted Connect (INFORM/ASK) →
      caller declines (or times out) → End/Goodbye  (no auth, no routing)

    Requirements: 20.5
    """

    # ── 1. AH_RESTRICTED_SERVICE_SCHEDULING verbatim content ────────────

    def test_ah_restricted_service_scheduling_contains_closed(self) -> None:
        """AH_RESTRICTED_SERVICE_SCHEDULING mentions 'closed' (offices are closed)."""
        assert "closed" in AH_RESTRICTED_SERVICE_SCHEDULING.lower()

    def test_ah_restricted_service_scheduling_contains_connect_or_someone(self) -> None:
        """AH_RESTRICTED_SERVICE_SCHEDULING offers to connect the caller ('connect'
        or 'someone')."""
        lower = AH_RESTRICTED_SERVICE_SCHEDULING.lower()
        assert "connect" in lower or "someone" in lower

    # ── 2. restricted_service_offer_line for scheduling ──────────────────

    def test_restricted_service_offer_line_scheduling_returns_scheduling_script(
        self,
    ) -> None:
        """restricted_service_offer_line(scheduling=True) returns
        AH_RESTRICTED_SERVICE_SCHEDULING verbatim."""
        assert (
            restricted_service_offer_line(scheduling=True)
            == AH_RESTRICTED_SERVICE_SCHEDULING
        )

    # ── 3. Connect-decision: agree → proceed to auth+route ───────────────

    def test_agreed_within_window_proceeds_to_auth_and_route(self) -> None:
        """Caller agreed within 10 s → proceed_to_auth_and_route=True (Req 8.9)."""
        decision = restricted_service_connect_decision(
            ConnectResponse.AGREED, elapsed_seconds=5.0
        )
        assert isinstance(decision, RestrictedServiceConnectDecision)
        assert decision.proceed_to_auth_and_route is True
        assert decision.end_restricted_flow is False

    def test_declined_ends_flow_no_auth_or_routing(self) -> None:
        """Caller declined → end_restricted_flow=True, no auth/routing (Req 8.10)."""
        decision = restricted_service_connect_decision(ConnectResponse.DECLINED)
        assert decision.end_restricted_flow is True
        assert decision.proceed_to_auth_and_route is False

    def test_unintelligible_treated_as_decline(self) -> None:
        """Unintelligible response → end_restricted_flow=True (Req 8.11)."""
        decision = restricted_service_connect_decision(ConnectResponse.UNINTELLIGIBLE)
        assert decision.end_restricted_flow is True
        assert decision.proceed_to_auth_and_route is False

    def test_agreed_but_timed_out_ends_flow(self) -> None:
        """Agreed but timed_out=True → end_restricted_flow=True (Req 8.11, timeout
        overrides the AGREED response)."""
        decision = restricted_service_connect_decision(
            ConnectResponse.AGREED, timed_out=True
        )
        assert decision.end_restricted_flow is True
        assert decision.proceed_to_auth_and_route is False

    def test_agreed_but_elapsed_exceeds_window_ends_flow(self) -> None:
        """Agreed but elapsed_seconds > 10 → timeout derived → end_restricted_flow=True."""
        decision = restricted_service_connect_decision(
            ConnectResponse.AGREED, elapsed_seconds=11.0
        )
        assert decision.end_restricted_flow is True
        assert decision.proceed_to_auth_and_route is False

    # ── 4. AH cluster structure: INFORM/ASK node + agree/decline edges ───

    def test_ah_cluster_has_restricted_connect_node(self) -> None:
        """The After Hours cluster contains the AH Restricted Connect (INFORM/ASK) node."""
        cluster = build_after_hours_cluster()
        node_ids = {n.id for n in cluster.nodes}
        assert NODE_AH_RESTRICTED_CONNECT in node_ids

    def test_ah_cluster_has_agree_edge_to_auth(self) -> None:
        """The After Hours cluster has an edge from Restricted Connect to Auth
        for the agree path (Req 8.9)."""
        cluster = build_after_hours_cluster()
        agree_edges = [
            e for e in cluster.edges
            if e.id == EDGE_AH_RESTRICTED_CONNECT_TO_AUTH
        ]
        assert len(agree_edges) == 1
        edge = agree_edges[0]
        assert edge.source == NODE_AH_RESTRICTED_CONNECT
        # The agree edge must be silent (no spoken filler on the transition)
        assert edge.data is not None
        assert edge.data.transition_speech == ""

    def test_ah_cluster_has_decline_edge_to_end(self) -> None:
        """The After Hours cluster has an edge from Restricted Connect to End/Goodbye
        for the decline/timeout path (Req 8.10, 8.11)."""
        cluster = build_after_hours_cluster()
        decline_edges = [
            e for e in cluster.edges
            if e.id == EDGE_AH_RESTRICTED_CONNECT_TO_END
        ]
        assert len(decline_edges) == 1
        edge = decline_edges[0]
        assert edge.source == NODE_AH_RESTRICTED_CONNECT
        # Condition must mention declining or timeout
        assert edge.data is not None
        condition_lower = edge.data.condition.lower()
        assert "declin" in condition_lower or "timeout" in condition_lower or "seconds" in condition_lower

    # ── 5. After agree: auth still runs for Scheduling/existing ──────────

    def test_auth_required_for_scheduling_after_ah_agree(self) -> None:
        """After AH agree, auth_required('Scheduling', 'existing') is True —
        authentication still runs before routing (Req 8.9)."""
        assert auth_required("Scheduling", "existing") is True

    def test_gate_open_after_auth_success_for_scheduling_existing(self) -> None:
        """After successful auth, may_proceed_to_routing is True for Scheduling/existing."""
        assert (
            may_proceed_to_routing("Scheduling", "existing", PATIENT_VERIFIED_SUCCESS)
            is True
        )

    # ── 6. Full graph: AH restricted-connect node present ────────────────

    def test_full_graph_has_ah_restricted_connect_node(self) -> None:
        """The assembled switchboard graph contains the AH Restricted Connect node."""
        wg = build_switchboard_graph()
        assert NODE_AH_RESTRICTED_CONNECT in wg.nodes
