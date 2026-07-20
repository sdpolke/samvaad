"""Full switchboard workflow graph assembler (Req 1.1, 1.8, 19.1–19.3).

Imports all cluster builders, wires cross-cluster edges, validates the assembled
graph with :class:`~api.services.workflow.workflow_graph.WorkflowGraph`, and
validates tool scoping with :func:`validate_tool_scoping`.

The result is a single directed graph from an inbound trigger/startCall entry
(NO outbound dial), with ledger fields as context variables, node tool references,
and edges carrying ``condition`` + ``transition_speech``.

Design references:
- ``design.md`` → "Phases as node clusters" and "Assemble the complete graph"
- ``requirements.md`` → Requirements 1.1, 1.8, 2.1, 2.2, 3.1, 19.1, 19.2, 19.3

Requirements: 1.1, 1.8, 2.1, 2.2, 3.1, 19.1, 19.2, 19.3.
"""

from __future__ import annotations

from api.services.switchboard.clusters.after_hours import (
    build_after_hours_cluster,
)
from api.services.switchboard.clusters.authentication import (
    build_authentication_cluster,
)
from api.services.switchboard.clusters.business_hours import (
    build_business_hours_cluster,
)
from api.services.switchboard.clusters.global_node import build_global_node
from api.services.switchboard.clusters.greeting import (
    EDGE_PATH_A,
    EDGE_ROUTING_REQUEST,
    EDGE_TRIGGER_TO_START,
    TRIGGER_NODE_ID,
    build_greeting_cluster,
)
from api.services.switchboard.clusters.routing import build_routing_cluster
from api.services.switchboard.clusters.scheduling import build_scheduling_cluster
from api.services.switchboard.clusters.tool_scoping import validate_tool_scoping
from api.services.workflow.dto import (
    EdgeDataDTO,
    EndCallNodeData,
    Position,
    ReactFlowDTO,
    RFEdgeDTO,
    RFNodeDTO,
)
from api.services.workflow.workflow_graph import WorkflowGraph

# ---------------------------------------------------------------------------
# End/Goodbye node for AH restricted-connect decline
# ---------------------------------------------------------------------------

END_GOODBYE_NODE_ID = "end_goodbye"

_END_GOODBYE_PROMPT = (
    "Speak a polite goodbye. Thank the caller for contacting SpinSci and "
    "wish them well."
)


def _build_end_goodbye_node() -> RFNodeDTO:
    """Build the terminal end/goodbye node for restricted-connect decline."""
    return RFNodeDTO(
        id=END_GOODBYE_NODE_ID,
        type="endCall",
        position=Position(x=1200, y=600),
        data=EndCallNodeData(
            name="End Goodbye",
            prompt=_END_GOODBYE_PROMPT,
            add_global_prompt=False,
        ),
    )


# ---------------------------------------------------------------------------
# Cross-cluster edge builders
# ---------------------------------------------------------------------------


def _replace_greeting_placeholder_edges(
    greeting_edges: list[RFEdgeDTO],
    greeting_collect_node_id: str,
    bh_intent_classify_id: str,
    ah_intent_node_id: str,
) -> list[RFEdgeDTO]:
    """Replace Greeting cluster placeholder edges with properly-targeted versions.

    The Greeting cluster emits Path A and ROUTING REQUEST edges with self-loop
    placeholder targets. This function replaces those with edges that route to
    Business Hours (after_hours=false) or After Hours (after_hours=true).

    Returns the full list of greeting edges with replacements applied.
    """
    result: list[RFEdgeDTO] = []

    for edge in greeting_edges:
        if edge.id == EDGE_PATH_A:
            # Replace with TWO edges: one to BH (after_hours=false), one to AH (after_hours=true)
            result.append(
                RFEdgeDTO(
                    id="edge_greeting_path_a_to_bh",
                    source=greeting_collect_node_id,
                    target=bh_intent_classify_id,
                    data=EdgeDataDTO(
                        label="Path A → Business Hours",
                        condition=(
                            "It is currently business hours (after_hours is "
                            "false) AND the caller gave a routing signal (an "
                            "intent, specialty, provider, scan type, or "
                            "appointment action; a name alone does not count)."
                        ),
                        transition_speech=edge.data.transition_speech,
                        transition_speech_type=edge.data.transition_speech_type,
                    ),
                )
            )
            result.append(
                RFEdgeDTO(
                    id="edge_greeting_path_a_to_ah",
                    source=greeting_collect_node_id,
                    target=ah_intent_node_id,
                    data=EdgeDataDTO(
                        label="Path A → After Hours",
                        condition=(
                            "It is currently after hours (after_hours is true) "
                            "AND the caller gave a routing signal (an intent, "
                            "specialty, provider, scan type, or appointment "
                            "action; a name alone does not count)."
                        ),
                        transition_speech=edge.data.transition_speech,
                        transition_speech_type=edge.data.transition_speech_type,
                    ),
                )
            )
        elif edge.id == EDGE_ROUTING_REQUEST:
            # Replace with TWO edges: routing-request fallback to BH or AH
            result.append(
                RFEdgeDTO(
                    id="edge_greeting_routing_request_to_bh",
                    source=greeting_collect_node_id,
                    target=bh_intent_classify_id,
                    data=EdgeDataDTO(
                        label="ROUTING REQUEST → Business Hours",
                        condition=(
                            "It is currently business hours (after_hours is "
                            "false) AND no routing signal could be captured: the "
                            "caller was understood but gave no usable signal — "
                            "including an unsure caller who says they don't know, "
                            "asks for help, or gives only chit-chat or a name — "
                            "or three not-understood turns occurred."
                        ),
                        transition_speech=edge.data.transition_speech,
                        transition_speech_type=edge.data.transition_speech_type,
                    ),
                )
            )
            result.append(
                RFEdgeDTO(
                    id="edge_greeting_routing_request_to_ah",
                    source=greeting_collect_node_id,
                    target=ah_intent_node_id,
                    data=EdgeDataDTO(
                        label="ROUTING REQUEST → After Hours",
                        condition=(
                            "It is currently after hours (after_hours is true) "
                            "AND no routing signal could be captured: the caller "
                            "was understood but gave no usable signal — including "
                            "an unsure caller who says they don't know, asks for "
                            "help, or gives only chit-chat or a name — or three "
                            "not-understood turns occurred."
                        ),
                        transition_speech=edge.data.transition_speech,
                        transition_speech_type=edge.data.transition_speech_type,
                    ),
                )
            )
        else:
            # Keep original edge unchanged
            result.append(edge)

    return result


def _build_routing_to_scheduling_edge(
    routing_resolve_route_id: str,
    scheduling_init_id: str,
) -> RFEdgeDTO:
    """Build the edge from Routing → Scheduling Init (existing-patient handoff)."""
    return RFEdgeDTO(
        id="edge_routing_to_scheduling_init",
        source=routing_resolve_route_id,
        target=scheduling_init_id,
        data=EdgeDataDTO(
            label="Scheduling Handoff (existing patient)",
            condition=(
                "The resolved route indicates scheduling for an existing patient. "
                "Hand off the full Call State Ledger to Scheduling Init."
            ),
            transition_speech=None,
        ),
    )


# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------


def build_switchboard_reactflow_dto() -> ReactFlowDTO:
    """Assemble the complete SpinSci switchboard graph as a ``ReactFlowDTO``.

    Builds all cluster nodes and edges, wires cross-cluster edges, and adds
    the global node and end/goodbye terminal. This is the serialization seam:
    it produces the raw, unvalidated ``ReactFlowDTO`` that
    :func:`build_switchboard_graph` validates, and that the enablement layer's
    ``Template_Registrar`` serializes into ``template_json``.

    Returns:
        The assembled (not yet validated) :class:`ReactFlowDTO`.
    """
    # -----------------------------------------------------------------------
    # 1. Build each cluster
    # -----------------------------------------------------------------------

    # Routing is self-contained — build first so we know its entry node ID.
    routing = build_routing_cluster()

    # Scheduling is self-contained.
    scheduling = build_scheduling_cluster()

    # Business Hours needs routing entry (for Records skip, retry-3 silent).
    # Auth entry will be wired as a separate cross-cluster edge from BH.
    # We pass routing_entry_node_id here but auth_entry_node_id later.
    # Actually the BH builder accepts auth/routing entries — build Auth first
    # to get its entry node.

    # Authentication needs routing entry + BH intent classify + AH intent.
    # But BH intent classify ID is random — so we build BH first (without auth
    # entry), capture its intent_classify_id, then build Auth with it.

    # Build BH first (with routing entry, without auth — we'll add the auth
    # edges from BH manually since BH already creates them when auth_entry is
    # provided, but here we need Auth's entry ID which comes from building Auth).
    # Solution: build BH without auth_entry, build Auth with BH's ID, then
    # note that BH already has its auth edges if we pass auth_entry.
    # BUT BH uses random UUIDs for node IDs. We MUST build it first.

    # Strategy: Build BH with a placeholder, build Auth, then rebuild BH?
    # No — BH only adds auth edges if auth_entry_node_id is provided.
    # Better: build BH with auth entry = Auth's well-known entry ID.
    # Auth has a fixed entry node ID: AUTH_PHONE_NODE_ID = "auth_phone".

    from api.services.switchboard.clusters.authentication import AUTH_PHONE_NODE_ID
    from api.services.switchboard.clusters.after_hours import NODE_AH_INTENT

    bh = build_business_hours_cluster(
        auth_entry_node_id=AUTH_PHONE_NODE_ID,
        routing_entry_node_id=routing.resolve_route_id,
    )

    # After Hours needs routing entry, auth entry, end node.
    ah = build_after_hours_cluster(
        routing_entry_node_id=routing.resolve_route_id,
        auth_entry_node_id=AUTH_PHONE_NODE_ID,
        end_node_id=END_GOODBYE_NODE_ID,
    )

    # Authentication needs routing entry + BH intent classify + AH intent.
    auth = build_authentication_cluster(
        routing_entry_node_id=routing.resolve_route_id,
        bh_intent_classify_node_id=bh.intent_classify_id,
        ah_intent_node_id=NODE_AH_INTENT,
    )

    # Greeting cluster (no external dependencies, but we'll replace placeholder edges).
    greeting = build_greeting_cluster()

    # Global node.
    global_node, _global_node_id = build_global_node()

    # End/goodbye node for AH restricted-connect decline.
    end_goodbye_node = _build_end_goodbye_node()

    # -----------------------------------------------------------------------
    # 2. Wire cross-cluster edges
    # -----------------------------------------------------------------------

    # Filter out the trigger node and trigger→startCall edge. The startCall node
    # (is_start=True) is the inbound telephony entry point; the trigger node is
    # for API-triggered workflows and the engine forbids incoming edges on
    # startCall (max_incoming=0). The design's "trigger→startCall" conceptual
    # link is realized by startCall.is_start=True — no physical edge needed.
    greeting_nodes = [n for n in greeting.nodes if n.id != TRIGGER_NODE_ID]
    greeting_edges_filtered = [
        e for e in greeting.edges if e.id != EDGE_TRIGGER_TO_START
    ]

    # Replace Greeting placeholder edges (Path A → BH/AH, ROUTING REQUEST → BH/AH)
    greeting_edges = _replace_greeting_placeholder_edges(
        greeting_edges=greeting_edges_filtered,
        greeting_collect_node_id=greeting.greeting_collect_node_id,
        bh_intent_classify_id=bh.intent_classify_id,
        ah_intent_node_id=NODE_AH_INTENT,
    )

    # Routing → Scheduling Init edge
    routing_to_scheduling_edge = _build_routing_to_scheduling_edge(
        routing_resolve_route_id=routing.resolve_route_id,
        scheduling_init_id=scheduling.scheduling_init_id,
    )

    # -----------------------------------------------------------------------
    # 3. Assemble ALL nodes and edges into a single ReactFlowDTO
    # -----------------------------------------------------------------------

    all_nodes: list[RFNodeDTO] = []

    # Greeting nodes (excluding the trigger node)
    all_nodes.extend(greeting_nodes)

    # Business Hours nodes
    all_nodes.extend(bh.nodes)

    # After Hours nodes
    all_nodes.extend(ah.nodes)

    # Authentication nodes
    all_nodes.extend(auth.nodes)

    # Routing nodes
    all_nodes.extend(routing.nodes)

    # Scheduling nodes
    all_nodes.extend(scheduling.nodes)

    # Global node
    all_nodes.append(global_node)

    # End/goodbye node
    all_nodes.append(end_goodbye_node)

    all_edges: list[RFEdgeDTO] = []

    # Greeting edges (with replacements applied)
    all_edges.extend(greeting_edges)

    # Business Hours edges (already includes BH→Auth and BH→Routing edges)
    all_edges.extend(bh.edges)

    # After Hours edges (already includes AH→Auth, AH→Routing, AH→End edges)
    all_edges.extend(ah.edges)

    # Authentication edges (already includes Auth→Routing, Auth→BH, Auth→AH edges)
    all_edges.extend(auth.edges)

    # Routing edges (internal only)
    all_edges.extend(routing.edges)

    # Scheduling edges (internal only)
    all_edges.extend(scheduling.edges)

    # Routing → Scheduling cross-cluster edge
    all_edges.append(routing_to_scheduling_edge)

    # -----------------------------------------------------------------------
    # 4. Assemble the ReactFlowDTO
    # -----------------------------------------------------------------------

    return ReactFlowDTO(nodes=all_nodes, edges=all_edges)


def build_switchboard_graph() -> WorkflowGraph:
    """Build and validate the complete SpinSci switchboard workflow graph.

    Delegates graph assembly to :func:`build_switchboard_reactflow_dto`, then
    validates the result with ``WorkflowGraph`` and validates tool scoping.

    Returns:
        A validated :class:`WorkflowGraph` instance representing the full
        switchboard graph.

    Raises:
        ValueError: If graph validation fails (start node, global node, edge
            cardinality, or referential integrity issues).
        RuntimeError: If tool scoping validation fails (GATE-AUTH structural
            property violated).
    """
    dto = build_switchboard_reactflow_dto()

    # WorkflowGraph validates: single start node, ≤1 global node, edge
    # cardinality, referential integrity. Raises ValueError on failure.
    workflow_graph = WorkflowGraph(dto)

    # Validate tool scoping (GATE-AUTH structural property)
    scoping_violations = validate_tool_scoping(dto.nodes)
    if scoping_violations:
        raise RuntimeError(
            "Tool scoping validation failed (GATE-AUTH structural property "
            "violated):\n" + "\n".join(f"  - {v}" for v in scoping_violations)
        )

    return workflow_graph


__all__ = [
    "END_GOODBYE_NODE_ID",
    "build_switchboard_graph",
    "build_switchboard_reactflow_dto",
]
