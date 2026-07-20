"""Unit tests for the silent-transition classifier (transitions.py).

Validates that:
- The classifier correctly identifies all known silent transitions.
- The ``is_silent_transition`` predicate works for empty/None/non-empty speech.
- The ``validate_silent_edges`` function catches violations.
- Edges from actual cluster builders are classified correctly.

Requirements: 1.5, 3.3, 3.4, 7.10, 8.3.
"""

from __future__ import annotations


from api.services.switchboard.clusters.after_hours import (
    EDGE_AH_HOTWORD_TO_ROUTING,
    EDGE_AH_RESTRICTED_CONNECT_TO_AUTH,
    EDGE_AH_RETRY_3_SILENT,
    build_after_hours_cluster,
)
from api.services.switchboard.clusters.authentication import (
    build_authentication_cluster,
)
from api.services.switchboard.clusters.business_hours import (
    EDGE_BH_CLASSIFY_TO_AUTH,
    EDGE_BH_RECORDS_SKIP_AUTH,
    EDGE_BH_RETRY_3_SILENT_ROUTE,
    EDGE_BH_SCHEDULING_GATE_TO_AUTH,
    build_business_hours_cluster,
)
from api.services.switchboard.transitions import (
    SilentTransitionType,
    classify_silent_transition,
    get_known_stable_silent_edge_ids,
    get_silent_edge_ids,
    is_silent_transition,
    validate_silent_edges,
)
from api.services.workflow.dto import EdgeDataDTO, RFEdgeDTO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_edge(
    edge_id: str = "test_edge",
    source: str = "src",
    target: str = "tgt",
    label: str = "test label",
    condition: str = "test condition",
    transition_speech: str | None = None,
) -> RFEdgeDTO:
    """Create a test edge with specified properties."""
    return RFEdgeDTO(
        id=edge_id,
        source=source,
        target=target,
        data=EdgeDataDTO(
            label=label,
            condition=condition,
            transition_speech=transition_speech,
        ),
    )


# ---------------------------------------------------------------------------
# Tests: is_silent_transition
# ---------------------------------------------------------------------------


class TestIsSilentTransition:
    """Tests for the is_silent_transition predicate."""

    def test_none_speech_is_silent(self) -> None:
        edge = _make_edge(transition_speech=None)
        assert is_silent_transition(edge) is True

    def test_empty_string_speech_is_silent(self) -> None:
        edge = _make_edge(transition_speech="")
        assert is_silent_transition(edge) is True

    def test_non_empty_speech_is_not_silent(self) -> None:
        edge = _make_edge(transition_speech="Hello there!")
        assert is_silent_transition(edge) is False

    def test_whitespace_only_speech_is_not_silent(self) -> None:
        # A single space is NOT treated as silent — only empty or None
        edge = _make_edge(transition_speech=" ")
        assert is_silent_transition(edge) is False


# ---------------------------------------------------------------------------
# Tests: classify_silent_transition — stable edge IDs
# ---------------------------------------------------------------------------


class TestClassifyStableEdges:
    """Tests for classification of stable (non-dynamic) edge IDs."""

    def test_hotword_to_routing(self) -> None:
        edge = _make_edge(
            edge_id=EDGE_AH_HOTWORD_TO_ROUTING,
            label="Hotword → Routing (silent)",
            transition_speech="",
        )
        assert classify_silent_transition(edge) == SilentTransitionType.HOTWORD

    def test_ah_retry_3_silent(self) -> None:
        edge = _make_edge(
            edge_id=EDGE_AH_RETRY_3_SILENT,
            label="3rd failure → Routing (silent)",
            transition_speech="",
        )
        assert classify_silent_transition(edge) == SilentTransitionType.RETRY_3

    def test_ah_restricted_connect_to_auth(self) -> None:
        edge = _make_edge(
            edge_id=EDGE_AH_RESTRICTED_CONNECT_TO_AUTH,
            label="Caller agreed → Auth (silent)",
            transition_speech="",
        )
        assert (
            classify_silent_transition(edge) == SilentTransitionType.NORMAL_AUTH_ENTRY
        )

    def test_auth_identity_to_routing(self) -> None:
        edge = _make_edge(
            edge_id="auth_e_identity_to_routing",
            label="Auth complete → Routing",
            transition_speech="",
        )
        assert (
            classify_silent_transition(edge) == SilentTransitionType.NORMAL_AUTH_ENTRY
        )

    def test_auth_3_attempts_route(self) -> None:
        edge = _make_edge(
            edge_id="auth_e_phone_3_attempts_route",
            label="3 phone attempts exhausted → Route",
            transition_speech="",
        )
        assert classify_silent_transition(edge) == SilentTransitionType.RETRY_3


# ---------------------------------------------------------------------------
# Tests: classify_silent_transition — Business Hours stable edge IDs
# ---------------------------------------------------------------------------


class TestClassifyBusinessHoursEdges:
    """Tests for classification of Business Hours edges by stable edge ID."""

    def test_records_skip_auth(self) -> None:
        edge = _make_edge(
            edge_id=EDGE_BH_RECORDS_SKIP_AUTH,
            label="Records Skip Auth",
            transition_speech="",
        )
        assert classify_silent_transition(edge) == SilentTransitionType.RECORDS_SKIP

    def test_retry_3_silent_route(self) -> None:
        edge = _make_edge(
            edge_id=EDGE_BH_RETRY_3_SILENT_ROUTE,
            label="Retry 3 - Silent Route",
            transition_speech="",
        )
        assert classify_silent_transition(edge) == SilentTransitionType.RETRY_3

    def test_scheduling_gate_to_auth(self) -> None:
        edge = _make_edge(
            edge_id=EDGE_BH_SCHEDULING_GATE_TO_AUTH,
            label="Auth Required After Scheduling Gate",
            transition_speech="",
        )
        assert (
            classify_silent_transition(edge) == SilentTransitionType.NORMAL_AUTH_ENTRY
        )

    def test_classify_to_auth(self) -> None:
        edge = _make_edge(
            edge_id=EDGE_BH_CLASSIFY_TO_AUTH,
            label="Auth Required (Non-Scheduling)",
            transition_speech="",
        )
        assert (
            classify_silent_transition(edge) == SilentTransitionType.NORMAL_AUTH_ENTRY
        )

    def test_unknown_edge_returns_none(self) -> None:
        edge = _make_edge(
            edge_id="some_unknown_edge_xyz",
            label="Lookup Needed",
            transition_speech=None,
        )
        assert classify_silent_transition(edge) is None


# ---------------------------------------------------------------------------
# Tests: validate_silent_edges
# ---------------------------------------------------------------------------


class TestValidateSilentEdges:
    """Tests for the validate_silent_edges function."""

    def test_no_violations_when_silent_edges_have_empty_speech(self) -> None:
        edges = [
            _make_edge(
                edge_id=EDGE_AH_HOTWORD_TO_ROUTING,
                label="Hotword → Routing (silent)",
                transition_speech="",
            ),
            _make_edge(
                edge_id=EDGE_AH_RETRY_3_SILENT,
                label="3rd failure → Routing (silent)",
                transition_speech="",
            ),
        ]
        violations = validate_silent_edges(edges)
        assert violations == []

    def test_violation_when_silent_edge_has_speech(self) -> None:
        edges = [
            _make_edge(
                edge_id=EDGE_AH_HOTWORD_TO_ROUTING,
                label="Hotword → Routing (silent)",
                transition_speech="Oops, this should be silent!",
            ),
        ]
        violations = validate_silent_edges(edges)
        assert len(violations) == 1
        assert EDGE_AH_HOTWORD_TO_ROUTING in violations[0]
        assert "hotword" in violations[0]

    def test_none_speech_on_silent_edge_passes(self) -> None:
        edges = [
            _make_edge(
                edge_id=EDGE_AH_HOTWORD_TO_ROUTING,
                label="Hotword → Routing (silent)",
                transition_speech=None,
            ),
        ]
        violations = validate_silent_edges(edges)
        assert violations == []

    def test_non_silent_edges_are_ignored(self) -> None:
        edges = [
            _make_edge(
                edge_id="some_normal_edge",
                label="Normal transition",
                transition_speech="Let me transfer you.",
            ),
        ]
        violations = validate_silent_edges(edges)
        assert violations == []


# ---------------------------------------------------------------------------
# Tests: get_silent_edge_ids
# ---------------------------------------------------------------------------


class TestGetSilentEdgeIds:
    """Tests for the get_silent_edge_ids function."""

    def test_returns_classified_edge_ids(self) -> None:
        edges = [
            _make_edge(
                edge_id=EDGE_AH_HOTWORD_TO_ROUTING,
                label="Hotword → Routing (silent)",
                transition_speech="",
            ),
            _make_edge(
                edge_id=EDGE_BH_RECORDS_SKIP_AUTH,
                label="Records Skip Auth",
                transition_speech="",
            ),
            _make_edge(
                edge_id="some_normal_edge",
                label="Normal transition",
                transition_speech="Hello!",
            ),
        ]
        silent_ids = get_silent_edge_ids(edges)
        assert EDGE_AH_HOTWORD_TO_ROUTING in silent_ids
        assert EDGE_BH_RECORDS_SKIP_AUTH in silent_ids
        assert "some_normal_edge" not in silent_ids

    def test_empty_edge_list(self) -> None:
        assert get_silent_edge_ids([]) == set()


# ---------------------------------------------------------------------------
# Tests: get_known_stable_silent_edge_ids
# ---------------------------------------------------------------------------


class TestGetKnownStableSilentEdgeIds:
    """Tests for the get_known_stable_silent_edge_ids function."""

    def test_includes_after_hours_edges(self) -> None:
        stable_ids = get_known_stable_silent_edge_ids()
        assert EDGE_AH_HOTWORD_TO_ROUTING in stable_ids
        assert EDGE_AH_RETRY_3_SILENT in stable_ids
        assert EDGE_AH_RESTRICTED_CONNECT_TO_AUTH in stable_ids

    def test_includes_auth_edges(self) -> None:
        stable_ids = get_known_stable_silent_edge_ids()
        assert "auth_e_identity_to_routing" in stable_ids
        assert "auth_e_phone_3_attempts_route" in stable_ids

    def test_returns_nonempty_set(self) -> None:
        stable_ids = get_known_stable_silent_edge_ids()
        assert len(stable_ids) >= 5


# ---------------------------------------------------------------------------
# Integration tests: classifier against actual cluster builds
# ---------------------------------------------------------------------------


class TestClassifierAgainstClusters:
    """Validate the classifier against edges from actual cluster builders."""

    def test_after_hours_cluster_silent_edges(self) -> None:
        """Verify all expected AH silent edges are classified correctly."""
        cluster = build_after_hours_cluster()
        silent_edges = [
            e for e in cluster.edges if classify_silent_transition(e) is not None
        ]

        # Should find: hotword, retry-3, restricted-connect-to-auth
        silent_ids = {e.id for e in silent_edges}
        assert EDGE_AH_HOTWORD_TO_ROUTING in silent_ids
        assert EDGE_AH_RETRY_3_SILENT in silent_ids
        assert EDGE_AH_RESTRICTED_CONNECT_TO_AUTH in silent_ids

        # All classified silent edges should actually have empty transition_speech
        violations = validate_silent_edges(cluster.edges)
        assert violations == []

    def test_authentication_cluster_silent_edges(self) -> None:
        """Verify auth cluster silent edges are classified correctly."""
        cluster = build_authentication_cluster()

        # Identity → Routing should be classified as NORMAL_AUTH_ENTRY
        identity_edge = next(
            (e for e in cluster.edges if e.id == "auth_e_identity_to_routing"),
            None,
        )
        assert identity_edge is not None
        assert (
            classify_silent_transition(identity_edge)
            == SilentTransitionType.NORMAL_AUTH_ENTRY
        )
        assert is_silent_transition(identity_edge)

        # 3-attempt route should be RETRY_3
        three_attempt_edge = next(
            (e for e in cluster.edges if e.id == "auth_e_phone_3_attempts_route"),
            None,
        )
        assert three_attempt_edge is not None
        assert (
            classify_silent_transition(three_attempt_edge) == SilentTransitionType.RETRY_3
        )
        assert is_silent_transition(three_attempt_edge)

        # No violations in the auth cluster
        violations = validate_silent_edges(cluster.edges)
        assert violations == []

    def test_business_hours_cluster_silent_edges(self) -> None:
        """Verify BH cluster dynamic-ID silent edges are classified."""
        cluster = build_business_hours_cluster(
            auth_entry_node_id="auth_phone",
            routing_entry_node_id="routing_resolve_route",
        )

        # Find edges that should be silent
        records_skip = next(
            (e for e in cluster.edges if "Records Skip Auth" in e.data.label),
            None,
        )
        assert records_skip is not None
        assert (
            classify_silent_transition(records_skip) == SilentTransitionType.RECORDS_SKIP
        )
        assert is_silent_transition(records_skip)

        retry_3 = next(
            (e for e in cluster.edges if "Retry 3 - Silent Route" in e.data.label),
            None,
        )
        assert retry_3 is not None
        assert classify_silent_transition(retry_3) == SilentTransitionType.RETRY_3
        assert is_silent_transition(retry_3)

        scheduling_gate_to_auth = next(
            (
                e
                for e in cluster.edges
                if "Auth Required After Scheduling Gate" in e.data.label
            ),
            None,
        )
        assert scheduling_gate_to_auth is not None
        assert (
            classify_silent_transition(scheduling_gate_to_auth)
            == SilentTransitionType.NORMAL_AUTH_ENTRY
        )
        assert is_silent_transition(scheduling_gate_to_auth)

        classify_to_auth = next(
            (
                e
                for e in cluster.edges
                if "Auth Required (Non-Scheduling)" in e.data.label
            ),
            None,
        )
        assert classify_to_auth is not None
        assert (
            classify_silent_transition(classify_to_auth)
            == SilentTransitionType.NORMAL_AUTH_ENTRY
        )
        assert is_silent_transition(classify_to_auth)

        # No violations
        violations = validate_silent_edges(cluster.edges)
        assert violations == []
