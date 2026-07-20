"""E2E acceptance scenario tests: POC-06 / POC-07

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes.  They do NOT use a live LLM or TTS pipeline; instead they:

1. Build the graph via ``build_switchboard_graph()`` and verify its structure.
2. Trace the pure logic functions (auth outcome, greeting, ledger reducer) through
   each scenario.
3. Assert the observable outcomes: auth connect-decision, verbatim scripts,
   graph structure, turn-1 post-state.

Scenarios:
  POC-06  — caller refuses to authenticate; switchboard speaks "No problem. I'll
             connect you now." and TRANSFERS (never hangs up)
  POC-07  — cold start, no ANI match (0 records); turn 1 is silent; welcome audio
             plays; turn 2 branches on greeting_ani_match_count

Requirements: 20.8, 20.9
"""

from __future__ import annotations


from api.services.switchboard.auth import (
    AuthOutcome,
    AuthTerminal,
    auth_fail_route_line,
    auth_outcome_connects,
    next_terminal_after_auth,
    should_speak_fail_route_line,
)
from api.services.switchboard.scripts import AUTH_FAIL_ROUTE
from api.services.switchboard.clusters.authentication import (
    AUTH_NODE_IDS,
    build_authentication_cluster,
)
from api.services.switchboard.clusters.greeting import (
    START_CALL_NODE_ID,
    build_greeting_cluster,
)
from api.services.switchboard.graph import build_switchboard_graph
from api.services.switchboard.greeting import (
    AniLookupResult,
    build_turn1_post_state,
    ready_to_handoff,
    select_greeting,
)
from api.services.switchboard.ledger import CallStateLedger
from api.services.switchboard.scripts import (
    GREETING_SCRIPT_2_PRIME_PERSONALIZED,
    GREETING_SCRIPT_4_STANDARD_IN_HOURS,
)


# ---------------------------------------------------------------------------
# POC-06: Auth refusal still connects (never hangup)
# ---------------------------------------------------------------------------


class TestPOC06AuthRefusalStillConnects:
    """POC-06: caller refuses to authenticate; switchboard speaks AUTH_FAIL_ROUTE
    and TRANSFERS the caller — it never hangs up for refusal alone.

    Requirements: 20.8 (Req 9.7, 9.12, AC-11)
    """

    # ── 1. Verbatim fail/refusal line ────────────────────────────────────

    def test_auth_fail_route_line_equals_constant(self) -> None:
        """auth_fail_route_line() returns the verbatim AUTH_FAIL_ROUTE constant."""
        assert auth_fail_route_line() == AUTH_FAIL_ROUTE

    def test_auth_fail_route_exact_wording(self) -> None:
        """AUTH_FAIL_ROUTE is exactly the mandated verbatim line (Req 9.7, Appendix C).
        Note: uses curly apostrophe (U+2019) per Appendix C fidelity rules."""
        assert AUTH_FAIL_ROUTE == "No problem. I\u2019ll connect you now."

    # ── 2. Every outcome connects (never hangs up) ───────────────────────

    def test_auth_outcome_connects_success(self) -> None:
        """auth_outcome_connects(SUCCESS) is True."""
        assert auth_outcome_connects(AuthOutcome.SUCCESS) is True

    def test_auth_outcome_connects_failed(self) -> None:
        """auth_outcome_connects(FAILED) is True — failure still connects."""
        assert auth_outcome_connects(AuthOutcome.FAILED) is True

    def test_auth_outcome_connects_refused(self) -> None:
        """auth_outcome_connects(REFUSED) is True — refusal still connects."""
        assert auth_outcome_connects(AuthOutcome.REFUSED) is True

    def test_auth_outcome_connects_attempts_exhausted(self) -> None:
        """auth_outcome_connects(ATTEMPTS_EXHAUSTED) is True."""
        assert auth_outcome_connects(AuthOutcome.ATTEMPTS_EXHAUSTED) is True

    # ── 3. Every outcome terminals to TRANSFER, never HANGUP ─────────────

    def test_next_terminal_success_is_transfer(self) -> None:
        """next_terminal_after_auth(SUCCESS) == AuthTerminal.TRANSFER."""
        assert next_terminal_after_auth(AuthOutcome.SUCCESS) is AuthTerminal.TRANSFER

    def test_next_terminal_failed_is_transfer(self) -> None:
        """next_terminal_after_auth(FAILED) == AuthTerminal.TRANSFER."""
        assert next_terminal_after_auth(AuthOutcome.FAILED) is AuthTerminal.TRANSFER

    def test_next_terminal_refused_is_transfer(self) -> None:
        """next_terminal_after_auth(REFUSED) == AuthTerminal.TRANSFER."""
        assert next_terminal_after_auth(AuthOutcome.REFUSED) is AuthTerminal.TRANSFER

    def test_next_terminal_attempts_exhausted_is_transfer(self) -> None:
        """next_terminal_after_auth(ATTEMPTS_EXHAUSTED) == AuthTerminal.TRANSFER."""
        assert (
            next_terminal_after_auth(AuthOutcome.ATTEMPTS_EXHAUSTED)
            is AuthTerminal.TRANSFER
        )

    def test_no_outcome_maps_to_hangup(self) -> None:
        """No AuthOutcome value maps next_terminal_after_auth to HANGUP."""
        for outcome in AuthOutcome:
            assert next_terminal_after_auth(outcome) is not AuthTerminal.HANGUP, (
                f"Outcome {outcome!r} should never terminal to HANGUP"
            )

    # ── 4. should_speak_fail_route_line for each outcome ─────────────────

    def test_speak_fail_line_for_refused(self) -> None:
        """should_speak_fail_route_line(REFUSED) is True."""
        assert should_speak_fail_route_line(AuthOutcome.REFUSED) is True

    def test_speak_fail_line_for_failed(self) -> None:
        """should_speak_fail_route_line(FAILED) is True."""
        assert should_speak_fail_route_line(AuthOutcome.FAILED) is True

    def test_speak_fail_line_for_attempts_exhausted(self) -> None:
        """should_speak_fail_route_line(ATTEMPTS_EXHAUSTED) is True."""
        assert should_speak_fail_route_line(AuthOutcome.ATTEMPTS_EXHAUSTED) is True

    def test_no_speak_fail_line_for_success(self) -> None:
        """should_speak_fail_route_line(SUCCESS) is False — success skips the line."""
        assert should_speak_fail_route_line(AuthOutcome.SUCCESS) is False

    # ── 5. Auth cluster: refusal/fail edges speak AUTH_FAIL_ROUTE ────────

    def test_auth_cluster_fail_edges_use_auth_fail_route_speech(self) -> None:
        """Auth cluster has fail/refusal edges from each auth node whose
        transition_speech equals AUTH_FAIL_ROUTE."""
        cluster = build_authentication_cluster()
        fail_edges = [
            e for e in cluster.edges
            if e.data is not None
            and e.data.transition_speech == AUTH_FAIL_ROUTE
        ]
        assert len(fail_edges) >= len(AUTH_NODE_IDS), (
            f"Expected at least one fail edge per auth node ({len(AUTH_NODE_IDS)}); "
            f"found {len(fail_edges)}"
        )

    def test_auth_cluster_fail_edges_cover_all_auth_nodes(self) -> None:
        """Each auth node has at least one outgoing fail/refusal edge with
        AUTH_FAIL_ROUTE as transition_speech."""
        cluster = build_authentication_cluster()
        fail_speech = AUTH_FAIL_ROUTE
        nodes_with_fail_edge = {
            e.source
            for e in cluster.edges
            if e.data is not None and e.data.transition_speech == fail_speech
        }
        for node_id in AUTH_NODE_IDS:
            assert node_id in nodes_with_fail_edge, (
                f"Auth node {node_id!r} has no fail/refusal edge with AUTH_FAIL_ROUTE"
            )

    # ── 6. Full graph: fail-route edges target routing, not end/hangup ───

    def test_full_graph_fail_route_edges_do_not_target_end_or_hangup(self) -> None:
        """In the assembled graph, edges from auth nodes with AUTH_FAIL_ROUTE speech
        target routing nodes — not any node whose ID contains 'end', 'hangup', or
        'goodbye'."""
        wg = build_switchboard_graph()
        end_like_ids = {
            node_id for node_id in wg.nodes
            if any(
                token in node_id.lower()
                for token in ("end", "hangup", "goodbye")
            )
        }
        auth_node_ids_set = set(AUTH_NODE_IDS)
        for edge in wg.edges:
            if (
                edge.source in auth_node_ids_set
                and edge.data is not None
                and edge.data.transition_speech == AUTH_FAIL_ROUTE
            ):
                assert edge.target not in end_like_ids, (
                    f"Fail-route edge from {edge.source!r} targets an end/hangup "
                    f"node {edge.target!r} — refusal must always connect (transfer)"
                )


# ---------------------------------------------------------------------------
# POC-07: Cold start — turn 1 silent, welcome audio, branch turn 2
# ---------------------------------------------------------------------------


class TestPOC07ColdStartGreeting:
    """POC-07: call cold-starts with no ANI match (0 records). Turn 1 is silent.
    Welcome audio plays. Turn 2 speaks the non-personalized in-hours greeting.

    Requirements: 20.9 (Req 6.1, 6.2, 6.3, 6.4, 6.5, Property 6, 7)
    """

    # ── 1. build_turn1_post_state for various ANI outcomes ───────────────

    def test_turn1_post_state_success_zero_matches(self) -> None:
        """build_turn1_post_state(success(0)) records done=True, match_count=0."""
        state = build_turn1_post_state(AniLookupResult.success(0))
        assert state == {
            "greeting_ani_lookup_done": True,
            "greeting_ani_match_count": 0,
        }

    def test_turn1_post_state_failure(self) -> None:
        """build_turn1_post_state(failure()) records done=True, match_count=0
        (failure = no matches, no error field)."""
        state = build_turn1_post_state(AniLookupResult.failure())
        assert state == {
            "greeting_ani_lookup_done": True,
            "greeting_ani_match_count": 0,
        }

    def test_turn1_post_state_timeout(self) -> None:
        """build_turn1_post_state(timeout()) records done=True, match_count=0
        (timeout treated as zero matches, Req 6.3)."""
        state = build_turn1_post_state(AniLookupResult.timeout())
        assert state == {
            "greeting_ani_lookup_done": True,
            "greeting_ani_match_count": 0,
        }

    def test_turn1_post_state_success_one_match(self) -> None:
        """build_turn1_post_state(success(1)) records done=True, match_count=1."""
        state = build_turn1_post_state(AniLookupResult.success(1))
        assert state == {
            "greeting_ani_lookup_done": True,
            "greeting_ani_match_count": 1,
        }

    # ── 2. Turn 1 is silent — no speech key in post state ────────────────

    def test_turn1_post_state_contains_no_speech_key(self) -> None:
        """The turn-1 post state contains no 'speech' or 'spoken_line' key."""
        state = build_turn1_post_state(AniLookupResult.success(0))
        assert "speech" not in state
        assert "spoken_line" not in state

    def test_turn1_post_state_failure_contains_no_speech_key(self) -> None:
        """Failure post state contains no speech key either."""
        state = build_turn1_post_state(AniLookupResult.failure())
        assert "speech" not in state
        assert "spoken_line" not in state

    # ── 3. select_greeting for cold-start / no-match scenario ────────────

    def test_select_greeting_in_hours_zero_matches(self) -> None:
        """select_greeting(after_hours=False, 0) returns GREETING_SCRIPT_4 (standard)."""
        script = select_greeting(after_hours=False, greeting_ani_match_count=0)
        assert script == GREETING_SCRIPT_4_STANDARD_IN_HOURS

    def test_select_greeting_in_hours_one_match_is_personalized(self) -> None:
        """select_greeting(after_hours=False, 1) returns the personalized script."""
        script = select_greeting(after_hours=False, greeting_ani_match_count=1)
        assert script == GREETING_SCRIPT_2_PRIME_PERSONALIZED

    # ── 4. Personalization placeholder present in personalized script ─────

    def test_personalized_script_contains_first_name_placeholder(self) -> None:
        """GREETING_SCRIPT_2_PRIME_PERSONALIZED contains the {FirstName} placeholder
        (single-brace token, authored verbatim per Req 18.1)."""
        assert "{FirstName}" in GREETING_SCRIPT_2_PRIME_PERSONALIZED

    # ── 5. After-hours non-personalized script is different ───────────────

    def test_select_greeting_after_hours_zero_matches_is_different_script(
        self,
    ) -> None:
        """select_greeting(after_hours=True, 0) returns a different (after-hours)
        script from the in-hours standard script."""
        after_hours_script = select_greeting(
            after_hours=True, greeting_ani_match_count=0
        )
        in_hours_script = select_greeting(
            after_hours=False, greeting_ani_match_count=0
        )
        assert after_hours_script != in_hours_script

    def test_select_greeting_after_hours_mentions_closed(self) -> None:
        """The after-hours non-personalized greeting mentions 'closed' (offices
        are currently closed)."""
        script = select_greeting(after_hours=True, greeting_ani_match_count=0)
        assert "closed" in script.lower()

    # ── 6. ready_to_handoff — name alone is insufficient ─────────────────

    def test_ready_to_handoff_name_only_is_false(self) -> None:
        """ready_to_handoff(ledger with only caller_name) is False.
        A name alone is never a sufficient routing signal (Req 6.7)."""
        name_only = CallStateLedger(caller_name="John")
        assert ready_to_handoff(name_only) is False

    def test_ready_to_handoff_with_intent_is_true(self) -> None:
        """ready_to_handoff(ledger with caller_name and intent) is True."""
        with_intent = CallStateLedger(caller_name="John", intent="Scheduling")
        assert ready_to_handoff(with_intent) is True

    def test_ready_to_handoff_empty_ledger_is_false(self) -> None:
        """ready_to_handoff on a completely empty ledger is False."""
        assert ready_to_handoff(CallStateLedger()) is False

    # ── 7. Greeting cluster: startCall node exists with pre_call_fetch ────

    def test_greeting_cluster_has_start_call_node(self) -> None:
        """build_greeting_cluster() produces a startCall node with id=START_CALL_NODE_ID."""
        cluster = build_greeting_cluster()
        node_ids = {n.id for n in cluster.nodes}
        assert START_CALL_NODE_ID in node_ids

    def test_greeting_cluster_start_call_node_has_pre_call_fetch_enabled(
        self,
    ) -> None:
        """The startCall node in the greeting cluster has pre_call_fetch_enabled=True
        (enables the 2-second ANI patient lookup, Req 6.1)."""
        cluster = build_greeting_cluster()
        start_node = next(n for n in cluster.nodes if n.id == START_CALL_NODE_ID)
        assert start_node.data.pre_call_fetch_enabled is True

    # ── 8. Full graph: start_call node is present ─────────────────────────

    def test_full_graph_contains_start_call_node(self) -> None:
        """The assembled switchboard graph contains the greeting startCall node."""
        wg = build_switchboard_graph()
        assert START_CALL_NODE_ID in wg.nodes
