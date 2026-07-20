"""Routing-phase node cluster for the SpinSci switchboard workflow graph.

Builds the Routing conversation phase as a set of workflow engine nodes and edges.
The Routing phase resolves the caller's destination (zero speech), speaks *only*
the prescribed Appendix E line on the terminal transfer/hangup turn, and invokes
the telephony transfer/hangup tools.

Nodes:
  1. **Resolve Route** (``agentNode``): zero-speech resolution node. Runs
     ``routing_intent_resolution`` then ``route_metadata_resolution`` with the
     exact string from the listing. No speech, no filler. Silent entry edge
     (``transition_speech=""``).
  2. **Transfer** (``agentNode``): terminal transfer — speaks ONLY the Appendix E
     transfer line selected by the resolved destination. No other speech.
     ``add_global_prompt=false``.
  3. **Hangup/Goodbye** (``endCall``): for Directory info-only goodbye — speaks
     the E_HANGUP line. ``add_global_prompt=false``.
  4. **Transfer Error** (``endCall``): when transfer fails, speaks E_TRANSFER_ERROR.
     ``add_global_prompt=false``.

Edges:
  - Silent entry edge → Resolve Route (``transition_speech=""``, Req 3.4)
  - Resolve Route → Transfer (destination resolved, transfer needed)
  - Resolve Route → Goodbye (Directory info-only, caller just wanted info)
  - Transfer → Transfer Error (transfer failed, Req 10.10)
  - Resolve Route → Scheduling downstream (scheduling existing-patient handoff)

Design references:
- ``design.md`` → "Routing cluster (Req 10, Req 11)"
- ``requirements.md`` → Requirements 10.1–10.4, 10.9, 10.10, 3.4

Requirements: 10.1, 10.2, 10.3, 10.4, 10.9, 10.10, 3.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from api.services.switchboard.routing import (
    DESTINATION_TERMINAL_LINES,
    RouteDestination,
)
from api.services.switchboard.scripts import E_HANGUP, E_TRANSFER_ERROR
from api.services.switchboard.tools.base import ToolCluster
from api.services.switchboard.tools.registry import tools_for_cluster
from api.services.workflow.dto import (
    AgentNodeData,
    EdgeDataDTO,
    EndCallNodeData,
    Position,
    RFEdgeDTO,
    RFNodeDTO,
)


def _node_id(label: str) -> str:
    """Generate a deterministic, human-identifiable node ID for the routing cluster."""
    return f"routing_{label}"


def _edge_id(source_label: str, target_label: str) -> str:
    """Generate a deterministic edge ID from source/target labels."""
    return f"routing_edge_{source_label}_to_{target_label}"


# ---------------------------------------------------------------------------
# Tool UUIDs for the routing cluster
# ---------------------------------------------------------------------------
# In the PoC the tool UUIDs are derived from the tool names (since real ToolModel
# UUIDs don't exist until the graph is assembled with a live DB). The graph
# assembler (task 18.1) replaces these with actual UUIDs at assembly time. For
# the cluster builder we use the tool function_name as the placeholder UUID so
# scoping can be validated structurally.


def _routing_tool_uuids() -> List[str]:
    """Return placeholder tool UUIDs for the Routing cluster's tools."""
    return [tool.function_name for tool in tools_for_cluster(ToolCluster.ROUTING)]


def _resolve_route_tool_uuids() -> List[str]:
    """Tool UUIDs for the Resolve Route node (routing_intent_resolution + route_metadata_resolution)."""
    return ["routing_intent_resolution", "route_metadata_resolution"]


def _transfer_tool_uuids() -> List[str]:
    """Tool UUIDs for the Transfer node (transfer)."""
    return ["transfer"]


# ---------------------------------------------------------------------------
# Node prompts — verbatim, enforcing the zero-speech and prescribed-line rules
# ---------------------------------------------------------------------------

RESOLVE_ROUTE_PROMPT: str = (
    "Emit NO speech. Run routing_intent_resolution to get the route listing. "
    "Then run route_metadata_resolution with the exact string from the listing. "
    "Do not speak any filler, acknowledgment, or stall phrases."
)

TRANSFER_PROMPT: str = (
    "Do NOT speak. The prescribed transfer line has already been delivered on the "
    "transition into this step, so emit no speech of your own. Invoke the transfer "
    "tool with the resolved destination. Then choose the transition based on the "
    "tool result: if the transfer succeeded, was simulated, or reported telephony "
    "unavailable, take the 'Transfer Complete' transition; if it genuinely failed "
    "or returned an error status, take the 'Transfer Failed' transition."
)

TRANSFER_COMPLETE_PROMPT: str = (
    "Do NOT speak. The transfer line has already been delivered and the transfer "
    "has been handed off. End the call."
)

GOODBYE_PROMPT: str = (
    f"Speak ONLY: \"{E_HANGUP}\" "
    "Then invoke the hangup tool. Do not add any other speech."
)

TRANSFER_ERROR_PROMPT: str = (
    f"Speak ONLY: \"{E_TRANSFER_ERROR}\" "
    "Then invoke the hangup tool. Do not add any other speech."
)


# ---------------------------------------------------------------------------
# Cluster result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingClusterResult:
    """The output of :func:`build_routing_cluster`.

    Attributes:
        nodes: The RF node DTOs for the Routing cluster.
        edges: The RF edge DTOs connecting routing nodes internally.
        resolve_route_id: The entry node ID for the cluster (Resolve Route).
            External edges from Auth/BH/AH target this node.
        transfer_id: The Transfer node ID (terminal transfer turn).
        goodbye_id: The Goodbye/hangup node ID (Directory info-only).
        transfer_error_id: The Transfer Error node ID.
        transfer_complete_id: The terminal node reached after a successful or
            simulated transfer (speaks nothing; ends the call cleanly).
        scheduling_downstream_edge_source: The node from which a scheduling-
            downstream edge should originate (Resolve Route).
    """

    nodes: List[RFNodeDTO]
    edges: List[RFEdgeDTO]
    resolve_route_id: str
    transfer_id: str
    goodbye_id: str
    transfer_error_id: str
    transfer_complete_id: str
    scheduling_downstream_edge_source: str


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

# Canvas layout positions (purely cosmetic, no runtime effect).
_POS_RESOLVE = Position(x=800.0, y=400.0)
_POS_TRANSFER = Position(x=1000.0, y=550.0)
_POS_GOODBYE = Position(x=600.0, y=550.0)
_POS_TRANSFER_ERROR = Position(x=1000.0, y=700.0)
_POS_TRANSFER_COMPLETE = Position(x=1200.0, y=550.0)


def build_routing_cluster() -> RoutingClusterResult:
    """Build the Routing-phase node cluster for the switchboard workflow graph.

    Returns:
        A :class:`RoutingClusterResult` containing all nodes, internal edges, and
        exposed node IDs for wiring into the assembled graph.
    """
    # -- Node IDs ---------------------------------------------------------------
    resolve_route_id = _node_id("resolve_route")
    transfer_id = _node_id("transfer")
    goodbye_id = _node_id("goodbye")
    transfer_error_id = _node_id("transfer_error")
    transfer_complete_id = _node_id("transfer_complete")

    # -- Nodes ------------------------------------------------------------------

    resolve_route_node = RFNodeDTO(
        id=resolve_route_id,
        type="agentNode",
        position=_POS_RESOLVE,
        data=AgentNodeData(
            name="Resolve Route",
            prompt=RESOLVE_ROUTE_PROMPT,
            allow_interrupt=False,
            add_global_prompt=False,
            tool_uuids=_resolve_route_tool_uuids(),
        ),
    )

    transfer_node = RFNodeDTO(
        id=transfer_id,
        type="agentNode",
        position=_POS_TRANSFER,
        data=AgentNodeData(
            name="Transfer",
            prompt=TRANSFER_PROMPT,
            allow_interrupt=False,
            add_global_prompt=False,
            tool_uuids=_transfer_tool_uuids(),
        ),
    )

    goodbye_node = RFNodeDTO(
        id=goodbye_id,
        type="endCall",
        position=_POS_GOODBYE,
        data=EndCallNodeData(
            name="Goodbye",
            prompt=GOODBYE_PROMPT,
            add_global_prompt=False,
        ),
    )

    transfer_error_node = RFNodeDTO(
        id=transfer_error_id,
        type="endCall",
        position=_POS_TRANSFER_ERROR,
        data=EndCallNodeData(
            name="Transfer Error",
            prompt=TRANSFER_ERROR_PROMPT,
            add_global_prompt=False,
        ),
    )

    transfer_complete_node = RFNodeDTO(
        id=transfer_complete_id,
        type="endCall",
        position=_POS_TRANSFER_COMPLETE,
        data=EndCallNodeData(
            name="Transfer Complete",
            prompt=TRANSFER_COMPLETE_PROMPT,
            add_global_prompt=False,
        ),
    )

    nodes: List[RFNodeDTO] = [
        resolve_route_node,
        transfer_node,
        goodbye_node,
        transfer_error_node,
        transfer_complete_node,
    ]

    # -- Internal Edges ---------------------------------------------------------

    # Resolve Route → Transfer (destination resolved, transfer needed).
    #
    # The prescribed Appendix E transfer line is spoken ON this transition
    # (``transition_speech``) — the same verbatim-safe mechanism the rest of the
    # graph uses for mandated lines — selected by the resolved destination
    # (Req 10.4, 10.5). The Transfer node itself is silent and only invokes the
    # transfer tool. We wire a curated set of destinations (the happy-path +
    # common departments) plus a Fallback edge that covers every other intent
    # with the generic connect line; the verbatim strings come from the pure
    # DESTINATION_TERMINAL_LINES mapping so they never drift from Appendix E.
    #
    # (Only a subset of RouteDestination is enumerated to keep this node's
    # outgoing-edge fan-out modest — a large fan-out of near-identical transition
    # functions stresses tool-call generation. Adding a destination is a one-line
    # entry here.)
    _transfer_edge_specs: list[tuple[str, RouteDestination, str]] = [
        (
            "scheduling_existing",
            RouteDestination.SCHEDULING_EXISTING,
            "The resolved destination is existing-patient Scheduling: intent is "
            "Scheduling and the patient is existing, or the appointment action is "
            "cancel, reschedule, list, or confirm.",
        ),
        (
            "records",
            RouteDestination.RECORDS,
            "The resolved destination is Records (medical records).",
        ),
        (
            "triage",
            RouteDestination.TRIAGE,
            "The resolved destination is Triage (the nurse advice line).",
        ),
        (
            "billing",
            RouteDestination.BILLING,
            "The resolved destination is Billing.",
        ),
        (
            "general",
            RouteDestination.GENERAL,
            "The resolved destination is General, a Directory connect, or a "
            "lab-results request.",
        ),
        (
            "fallback",
            RouteDestination.FALLBACK,
            "No more specific department destination applies (e.g. Referrals, "
            "Pharmacy, Paging, or MyChart, or an unrecognized intent). Use the "
            "general connect line.",
        ),
    ]
    transfer_edges: List[RFEdgeDTO] = [
        RFEdgeDTO(
            id=f"{_edge_id('resolve_route', 'transfer')}_{suffix}",
            source=resolve_route_id,
            target=transfer_id,
            data=EdgeDataDTO(
                label=f"Transfer — {destination.value}",
                condition=condition,
                transition_speech=DESTINATION_TERMINAL_LINES[destination],
                transition_speech_type="text",
            ),
        )
        for suffix, destination, condition in _transfer_edge_specs
    ]

    # Transfer → Transfer Complete (transfer succeeded or was simulated over a
    # non-telephony/WebRTC call). The prescribed line already played on entry, so
    # this transition is silent and the terminal node ends the call cleanly.
    edge_transfer_to_complete = RFEdgeDTO(
        id=_edge_id("transfer", "transfer_complete"),
        source=transfer_id,
        target=transfer_complete_id,
        data=EdgeDataDTO(
            label="Transfer Complete",
            condition=(
                "The transfer tool returned a successful/initiated status, OR a "
                "simulated/unavailable status (no live telephony call to transfer, "
                "e.g. a browser/web test call). End the call cleanly."
            ),
            transition_speech="",
            transition_speech_type="text",
        ),
    )

    # Resolve Route → Goodbye (Directory info-only, caller just wanted info)
    edge_resolve_to_goodbye = RFEdgeDTO(
        id=_edge_id("resolve_route", "goodbye"),
        source=resolve_route_id,
        target=goodbye_id,
        data=EdgeDataDTO(
            label="Directory Info-Only Goodbye",
            condition=(
                "The caller's request was for directory information only and "
                "does not require a transfer connection."
            ),
            transition_speech=None,
        ),
    )

    # Transfer → Transfer Error (transfer genuinely failed, Req 10.10)
    edge_transfer_to_error = RFEdgeDTO(
        id=_edge_id("transfer", "transfer_error"),
        source=transfer_id,
        target=transfer_error_id,
        data=EdgeDataDTO(
            label="Transfer Failed",
            condition=(
                "The transfer tool genuinely failed or returned an error status "
                "(status 'failed'/'error') — NOT a simulated or unavailable "
                "result, which is handled by the Transfer Complete transition."
            ),
            transition_speech=None,
        ),
    )

    edges: List[RFEdgeDTO] = [
        *transfer_edges,
        edge_resolve_to_goodbye,
        edge_transfer_to_complete,
        edge_transfer_to_error,
    ]

    return RoutingClusterResult(
        nodes=nodes,
        edges=edges,
        resolve_route_id=resolve_route_id,
        transfer_id=transfer_id,
        goodbye_id=goodbye_id,
        transfer_error_id=transfer_error_id,
        transfer_complete_id=transfer_complete_id,
        scheduling_downstream_edge_source=resolve_route_id,
    )


__all__ = [
    "RESOLVE_ROUTE_PROMPT",
    "TRANSFER_PROMPT",
    "TRANSFER_COMPLETE_PROMPT",
    "GOODBYE_PROMPT",
    "TRANSFER_ERROR_PROMPT",
    "RoutingClusterResult",
    "build_routing_cluster",
]
