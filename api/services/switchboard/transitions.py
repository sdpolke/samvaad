"""Silent-transition classifier for the SpinSci switchboard graph.

Identifies which edge transitions in the switchboard graph must be silent
(empty ``transition_speech``) and classifies them by trigger type. This module
is pure, side-effect-free, and independently testable.

Silent-transition cases (Property 5, design.md):
1. **Normal auth entry** (Req 3.3): edges from BH/AH → Authentication entry.
2. **Records auth-skip** (Req 7.10): edge from BH Intent Classify → Routing
   when intent=Records.
3. **New-patient create auth-skip**: edge for new-patient Scheduling create
   that skips auth and routes directly.
4. **Retry-3 route** (Req 7.12, 8.7): edges from BH/AH Intent → Routing on
   the 3rd consecutive classification failure.
5. **Hotword route** (Req 8.3): edge from AH Intent → Routing when a hotword
   is detected. Sets ``patient_verified=N/A``.

Requirements: 1.5, 3.3, 3.4, 7.10, 8.3.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from api.services.switchboard.clusters.after_hours import (
    EDGE_AH_HOTWORD_TO_ROUTING,
    EDGE_AH_RESTRICTED_CONNECT_TO_AUTH,
    EDGE_AH_RETRY_3_SILENT,
)
from api.services.switchboard.clusters.business_hours import (
    EDGE_BH_CLASSIFY_TO_AUTH,
    EDGE_BH_RECORDS_SKIP_AUTH,
    EDGE_BH_RETRY_3_SILENT_ROUTE,
    EDGE_BH_SCHEDULING_GATE_TO_AUTH,
)
from api.services.workflow.dto import RFEdgeDTO


# ---------------------------------------------------------------------------
# Silent transition type classification
# ---------------------------------------------------------------------------


class SilentTransitionType(str, Enum):
    """Classification of silent transition triggers.

    Each member represents a specific scenario where an edge transition must be
    silent (empty ``transition_speech``).
    """

    NORMAL_AUTH_ENTRY = "normal_auth_entry"
    """Normal auth entry (Req 3.3): BH/AH → Authentication cluster entry."""

    RECORDS_SKIP = "records_skip"
    """Records auth-skip (Req 7.10): BH Intent Classify → Routing, silent."""

    NEW_CREATE_SKIP = "new_create_skip"
    """New-patient create auth-skip: skips auth, routes directly, silent."""

    RETRY_3 = "retry_3"
    """Retry-3 route (Req 7.12, 8.7): 3rd failure → Routing, silent."""

    HOTWORD = "hotword"
    """Hotword route (Req 8.3): AH Intent → Routing on hotword, silent."""


# ---------------------------------------------------------------------------
# Stable edge IDs known to be silent
# ---------------------------------------------------------------------------
# All clusters assign deterministic edge IDs, so silent/auth-entry transitions
# are matched directly by ID. Business Hours edge IDs are imported as constants;
# the Authentication cluster's identity→routing and 3-attempt→routing edges use
# private-but-stable string IDs mirrored here.

_STABLE_SILENT_EDGE_IDS: dict[str, SilentTransitionType] = {
    # After Hours: hotword → routing (Req 8.3)
    EDGE_AH_HOTWORD_TO_ROUTING: SilentTransitionType.HOTWORD,
    # After Hours: retry-3 → routing (Req 8.7)
    EDGE_AH_RETRY_3_SILENT: SilentTransitionType.RETRY_3,
    # After Hours: restricted-connect → auth entry (silent, Req 8.9)
    EDGE_AH_RESTRICTED_CONNECT_TO_AUTH: SilentTransitionType.NORMAL_AUTH_ENTRY,
    # Authentication: identity → routing (Req 3.3)
    "auth_e_identity_to_routing": SilentTransitionType.NORMAL_AUTH_ENTRY,
    # Authentication: 3-attempt phone exhaustion → routing (Req 9.12)
    "auth_e_phone_3_attempts_route": SilentTransitionType.RETRY_3,
    # Business Hours: Records intent → routing, skip auth (Req 7.10)
    EDGE_BH_RECORDS_SKIP_AUTH: SilentTransitionType.RECORDS_SKIP,
    # Business Hours: retry-3 → routing (Req 7.12)
    EDGE_BH_RETRY_3_SILENT_ROUTE: SilentTransitionType.RETRY_3,
    # Business Hours: scheduling gate → auth entry (silent)
    EDGE_BH_SCHEDULING_GATE_TO_AUTH: SilentTransitionType.NORMAL_AUTH_ENTRY,
    # Business Hours: non-scheduling intent → auth entry (silent)
    EDGE_BH_CLASSIFY_TO_AUTH: SilentTransitionType.NORMAL_AUTH_ENTRY,
}


def classify_silent_transition(edge: RFEdgeDTO) -> Optional[SilentTransitionType]:
    """Classify whether an edge is a known silent transition and which type.

    Classification keys off **stable edge IDs** only. Every cluster (Greeting,
    Business Hours, After Hours, Authentication) assigns deterministic edge IDs,
    so silent/auth-entry transitions are identified structurally rather than by
    parsing human-readable label text (which is presentation, not behavior).

    Note: Authentication fail/refusal edges intentionally carry non-empty
    ``transition_speech`` (they speak a line before routing), so they are not
    silent transitions and are deliberately absent from the table.

    Args:
        edge: The workflow edge to classify.

    Returns:
        The :class:`SilentTransitionType` if the edge is a known silent
        transition, or ``None`` if it is not recognized as a silent trigger.
    """
    return _STABLE_SILENT_EDGE_IDS.get(edge.id)


def is_silent_transition(edge: RFEdgeDTO) -> bool:
    """Return True when an edge has empty/None ``transition_speech``.

    An edge is considered silent if its ``transition_speech`` is either:
    - ``None``
    - An empty string ``""``

    Note: ``None`` may represent "no speech specified" (the default), while
    ``""`` explicitly means "silent transition". For the purposes of this
    classifier, both are treated as silent, but edges with ``None`` may be
    transitional placeholders. The stricter check (empty string only) is used
    in :func:`validate_silent_edges`.

    Args:
        edge: The workflow edge to check.

    Returns:
        ``True`` if the edge's ``transition_speech`` is empty or None.
    """
    speech = edge.data.transition_speech if edge.data else None
    return speech is None or speech == ""


def validate_silent_edges(edges: list[RFEdgeDTO]) -> list[str]:
    """Validate that edges expected to be silent actually have empty speech.

    Examines all provided edges, identifies those that are classified as known
    silent transitions (via :func:`classify_silent_transition`), and checks that
    their ``transition_speech`` is indeed empty (``""`` or ``None``).

    Args:
        edges: The list of workflow edges to validate.

    Returns:
        A list of violation descriptions. Empty list means all silent edges
        are correctly configured.
    """
    violations: list[str] = []

    for edge in edges:
        classification = classify_silent_transition(edge)
        if classification is not None:
            # This edge SHOULD be silent — verify it actually is
            speech = edge.data.transition_speech if edge.data else None
            if speech is not None and speech != "":
                violations.append(
                    f"Edge '{edge.id}' (label: '{edge.data.label}') is classified "
                    f"as {classification.value} but has non-empty "
                    f"transition_speech: '{speech}'"
                )

    return violations


def get_silent_edge_ids(edges: list[RFEdgeDTO]) -> set[str]:
    """Return the set of edge IDs that must be silent.

    Scans the provided edges and returns the IDs of those classified as known
    silent transitions. All switchboard clusters now assign stable edge IDs, so
    this is equivalent to intersecting the edge list with the known silent-ID
    table; it accepts the edge list so callers can validate an assembled graph
    directly.

    Args:
        edges: The list of workflow edges (typically from an assembled graph).

    Returns:
        A set of edge IDs that should have empty ``transition_speech``.
    """
    silent_ids: set[str] = set()

    for edge in edges:
        if classify_silent_transition(edge) is not None:
            silent_ids.add(edge.id)

    return silent_ids


def get_known_stable_silent_edge_ids() -> set[str]:
    """Return the set of stable edge IDs known to be silent.

    These are the deterministic edge IDs from the Business Hours, After Hours,
    and Authentication clusters that must always carry empty ``transition_speech``.

    Returns:
        A set of stable edge IDs that must always be silent.
    """
    return set(_STABLE_SILENT_EDGE_IDS.keys())


__all__ = [
    "SilentTransitionType",
    "classify_silent_transition",
    "get_known_stable_silent_edge_ids",
    "get_silent_edge_ids",
    "is_silent_transition",
    "validate_silent_edges",
]
