"""After Hours node cluster builder for the SpinSci switchboard graph (Req 8).

Assembles the After Hours phase as a set of workflow-engine nodes and edges,
wiring the pure decision logic from :mod:`api.services.switchboard.after_hours`
and verbatim lines from :mod:`api.services.switchboard.scripts` into the graph
primitives defined in :mod:`api.services.workflow.dto`.

The cluster contains:
1. **AH Intent** (``agentNode``): entry point for after-hours handling — detects
   hotwords, classifies restricted services, Billing/MyChart, paging.
2. **Restricted Connect** (``agentNode``): INFORM → ASK → wait ≤10s for the
   caller's connect decision.
3. **Billing Closed** (``agentNode``): speaks the AH_BILLING_CLOSED line.
4. **MyChart Closed** (``agentNode``): speaks the AH_MYCHART_CLOSED line.
5. **Paging Clarifier** (``agentNode``): asks a paging clarifier option and sets
   ``caller_is_provider`` / ``ah_intent_selection``.

Edges encode the after-hours transitions including the silent hotword route, retry
edges, restricted-connect outcomes, and closed-service paths.

The hotword keyword list is read from configuration via
:func:`~api.services.switchboard.config.load_afterhours_hotwords` — never
hardcoded (Req 21.3).

Design references:
- ``design.md`` → "After Hours cluster (Req 8)" and Properties 31, 32, 33
- ``requirements.md`` → Requirement 8 (8.1–8.11) and Requirement 21 (21.3)

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 21.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.services.switchboard import scripts
from api.services.switchboard.after_hours import (
    RESTRICTED_CONNECT_TIMEOUT_SECONDS,
)
from api.services.switchboard.config import load_afterhours_hotwords
from api.services.workflow.dto import (
    AgentNodeData,
    EdgeDataDTO,
    ExtractionVariableDTO,
    Position,
    RFEdgeDTO,
    RFNodeDTO,
    VariableType,
)


# ---------------------------------------------------------------------------
# Node ID constants — stable identifiers for cross-cluster wiring
# ---------------------------------------------------------------------------

NODE_AH_INTENT = "ah_intent"
NODE_AH_RESTRICTED_CONNECT = "ah_restricted_connect"
NODE_AH_BILLING_CLOSED = "ah_billing_closed"
NODE_AH_MYCHART_CLOSED = "ah_mychart_closed"
NODE_AH_PAGING_CLARIFIER = "ah_paging_clarifier"

# ---------------------------------------------------------------------------
# Edge ID constants
# ---------------------------------------------------------------------------

EDGE_AH_HOTWORD_TO_ROUTING = "ah_hotword_to_routing"
EDGE_AH_INTENT_TO_BILLING_CLOSED = "ah_intent_to_billing_closed"
EDGE_AH_INTENT_TO_MYCHART_CLOSED = "ah_intent_to_mychart_closed"
EDGE_AH_INTENT_TO_PAGING_CLARIFIER = "ah_intent_to_paging_clarifier"
EDGE_AH_INTENT_TO_RESTRICTED_CONNECT = "ah_intent_to_restricted_connect"
EDGE_AH_RESTRICTED_CONNECT_TO_AUTH = "ah_restricted_connect_to_auth"
EDGE_AH_RESTRICTED_CONNECT_TO_END = "ah_restricted_connect_to_end"
EDGE_AH_RETRY_1 = "ah_retry_1"
EDGE_AH_RETRY_2 = "ah_retry_2"
EDGE_AH_RETRY_3_SILENT = "ah_retry_3_silent"


# ---------------------------------------------------------------------------
# Prompt templates for After Hours nodes
# ---------------------------------------------------------------------------

def _build_ah_intent_prompt() -> str:
    """Build the AH Intent node prompt.

    Instructs the LLM to classify the after-hours caller's intent and detect
    hotword keywords. The hotword keyword list is loaded from configuration
    (Req 21.3) and injected into the prompt so the LLM can recognize them.
    """
    hotwords = load_afterhours_hotwords()
    hotword_section = ""
    if hotwords:
        hotword_list = ", ".join(f'"{kw}"' for kw in hotwords)
        hotword_section = (
            f"\n\nHOTWORD DETECTION (URGENT — highest priority):\n"
            f"If the caller mentions any of these keywords, immediately classify "
            f"as a hotword and route urgently: {hotword_list}.\n"
            f"Do NOT ask further questions — route silently to urgent handling."
        )

    return (
        "You are the after-hours virtual assistant for SpinSci. Our offices are "
        "currently closed. Classify the caller's intent into one of the following "
        "categories:\n\n"
        "1. HOTWORD/URGENT — caller mentions an urgent keyword (see below)\n"
        "2. RESTRICTED SERVICE — caller wants scheduling or a service that is "
        "limited after hours\n"
        "3. BILLING — caller wants to reach the billing department\n"
        "4. MYCHART — caller wants MyChart support\n"
        "5. PAGING — caller needs to page a provider or is calling from a "
        "hospital/medical facility\n"
        "6. OTHER — general after-hours inquiry\n\n"
        "Based on the classification, transition to the appropriate next step. "
        "Extract the caller's intent, specialty, provider name, intent selection, "
        "and whether the caller is a provider."
        f"{hotword_section}"
    )


_RESTRICTED_CONNECT_PROMPT = (
    "You have informed the caller that the requested service is limited after "
    "hours. Ask the caller whether they would like to be connected to someone "
    "who can help, even though they won't be from the specific office. Wait up "
    f"to {RESTRICTED_CONNECT_TIMEOUT_SECONDS} seconds for a response.\n\n"
    "If the caller agrees, transition to authentication.\n"
    "If the caller declines, says goodbye, or does not respond within "
    f"{RESTRICTED_CONNECT_TIMEOUT_SECONDS} seconds, end the call politely."
)

_BILLING_CLOSED_PROMPT = (
    "Speak the following line exactly, then end the interaction. Do not offer to "
    "transfer to an in-hours billing department:\n\n"
    f'"{scripts.AH_BILLING_CLOSED}"'
)

_MYCHART_CLOSED_PROMPT = (
    "Speak the following line exactly, then end the interaction. Do not offer to "
    "transfer to an in-hours MyChart department:\n\n"
    f'"{scripts.AH_MYCHART_CLOSED}"'
)

_PAGING_CLARIFIER_PROMPT = (
    "You need to determine whether the caller is a provider/staff member calling "
    "about a patient, or the patient themselves. Ask one of the following "
    "clarifier questions:\n\n"
    f'Option 1: "{scripts.AH_PAGING_CLARIFIER_OPTION_1}"\n'
    f'Option 2: "{scripts.AH_PAGING_CLARIFIER_OPTION_2}"\n'
    f'Option 3: "{scripts.AH_PAGING_CLARIFIER_OPTION_3}"\n\n'
    "Based on the caller's response, set caller_is_provider to true if they are "
    "a provider/staff/hospital, or false if they are the patient. Also set "
    "ah_intent_selection to 'Hospital or Physician' for providers or "
    "'Afterhours Answering Service' for patients."
)


# ---------------------------------------------------------------------------
# Cluster result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AfterHoursClusterResult:
    """The assembled After Hours cluster: nodes, edges, and exposed node IDs.

    Attributes:
        nodes: All ``RFNodeDTO`` instances in this cluster.
        edges: All ``RFEdgeDTO`` instances internal to this cluster, plus edges
            that connect to external cluster entry/exit points (their target IDs
            are placeholders that the graph assembler resolves).
        entry_node_id: The node ID that other clusters target to enter After
            Hours (the AH Intent node).
        exposed_node_ids: Mapping of logical name → node ID for cross-cluster
            wiring by the graph assembler.
    """

    nodes: list[RFNodeDTO]
    edges: list[RFEdgeDTO]
    entry_node_id: str
    exposed_node_ids: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------


def _make_ah_intent_node() -> RFNodeDTO:
    """Build the AH Intent agent node."""
    return RFNodeDTO(
        id=NODE_AH_INTENT,
        type="agentNode",
        position=Position(x=600, y=400),
        data=AgentNodeData(
            name="AH Intent",
            prompt=_build_ah_intent_prompt(),
            allow_interrupt=True,
            add_global_prompt=True,
            extraction_enabled=True,
            extraction_prompt=(
                "Extract the after-hours caller's intent classification, "
                "specialty, provider name, intent selection, and whether the "
                "caller is a provider."
            ),
            extraction_variables=[
                ExtractionVariableDTO(
                    name="intent",
                    type=VariableType.string,
                    prompt="The classified after-hours intent category.",
                ),
                ExtractionVariableDTO(
                    name="specialty",
                    type=VariableType.string,
                    prompt="The medical specialty the caller is requesting.",
                ),
                ExtractionVariableDTO(
                    name="provider_name",
                    type=VariableType.string,
                    prompt="The provider name the caller mentioned.",
                ),
                ExtractionVariableDTO(
                    name="ah_intent_selection",
                    type=VariableType.string,
                    prompt=(
                        "The after-hours intent selection: 'Hospital or Physician' "
                        "or 'Afterhours Answering Service'."
                    ),
                ),
                ExtractionVariableDTO(
                    name="caller_is_provider",
                    type=VariableType.boolean,
                    prompt="Whether the caller is a provider or medical staff.",
                ),
            ],
            tool_uuids=["directory_lookup", "faq_kb"],
        ),
    )


def _make_restricted_connect_node() -> RFNodeDTO:
    """Build the Restricted Connect agent node (INFORM → ASK → wait ≤10s)."""
    return RFNodeDTO(
        id=NODE_AH_RESTRICTED_CONNECT,
        type="agentNode",
        position=Position(x=900, y=400),
        data=AgentNodeData(
            name="AH Restricted Connect",
            prompt=_RESTRICTED_CONNECT_PROMPT,
            allow_interrupt=True,
            add_global_prompt=True,
            extraction_enabled=True,
            extraction_prompt="Extract the caller's connect decision response.",
            extraction_variables=[
                ExtractionVariableDTO(
                    name="connect_response",
                    type=VariableType.string,
                    prompt=(
                        "The caller's response to the connect offer: "
                        "'agreed', 'declined', or 'unintelligible'."
                    ),
                ),
            ],
        ),
    )


def _make_billing_closed_node() -> RFNodeDTO:
    """Build the Billing Closed agent node (Req 8.4)."""
    return RFNodeDTO(
        id=NODE_AH_BILLING_CLOSED,
        type="agentNode",
        position=Position(x=300, y=600),
        data=AgentNodeData(
            name="AH Billing Closed",
            prompt=_BILLING_CLOSED_PROMPT,
            allow_interrupt=False,
            add_global_prompt=False,
        ),
    )


def _make_mychart_closed_node() -> RFNodeDTO:
    """Build the MyChart Closed agent node (Req 8.5)."""
    return RFNodeDTO(
        id=NODE_AH_MYCHART_CLOSED,
        type="agentNode",
        position=Position(x=300, y=750),
        data=AgentNodeData(
            name="AH MyChart Closed",
            prompt=_MYCHART_CLOSED_PROMPT,
            allow_interrupt=False,
            add_global_prompt=False,
        ),
    )


def _make_paging_clarifier_node() -> RFNodeDTO:
    """Build the Paging Clarifier agent node (Req 8.8)."""
    return RFNodeDTO(
        id=NODE_AH_PAGING_CLARIFIER,
        type="agentNode",
        position=Position(x=600, y=750),
        data=AgentNodeData(
            name="AH Paging Clarifier",
            prompt=_PAGING_CLARIFIER_PROMPT,
            allow_interrupt=True,
            add_global_prompt=True,
            extraction_enabled=True,
            extraction_prompt=(
                "Extract whether the caller is a provider/staff and their "
                "intent selection based on the paging clarifier answer."
            ),
            extraction_variables=[
                ExtractionVariableDTO(
                    name="caller_is_provider",
                    type=VariableType.boolean,
                    prompt=(
                        "True if the caller is a provider, hospital staff, or "
                        "calling from a medical facility. False if the caller is "
                        "the patient."
                    ),
                ),
                ExtractionVariableDTO(
                    name="ah_intent_selection",
                    type=VariableType.string,
                    prompt=(
                        "'Hospital or Physician' if the caller is a provider, "
                        "'Afterhours Answering Service' if the caller is the "
                        "patient."
                    ),
                ),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# Edge builders
# ---------------------------------------------------------------------------


def _make_edges(
    *,
    routing_entry_node_id: str = "routing_resolve",
    auth_entry_node_id: str = "auth_phone",
    end_node_id: str = "end_goodbye",
) -> list[RFEdgeDTO]:
    """Build all edges for the After Hours cluster.

    Args:
        routing_entry_node_id: The external Routing cluster entry node ID that
            hotword and retry-3 edges target.
        auth_entry_node_id: The external Authentication cluster entry node ID
            that the restricted-connect agree edge targets.
        end_node_id: The external end/goodbye node ID that the restricted-connect
            decline/timeout edge targets.

    Returns:
        The list of all After Hours cluster edges.
    """
    edges: list[RFEdgeDTO] = []

    # --- Hotword silent-route edge (Req 8.3) ---
    # AH Intent → Routing cluster entry. Silent (transition_speech="").
    # Sets patient_verified=N/A on the routing side.
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_HOTWORD_TO_ROUTING,
            source=NODE_AH_INTENT,
            target=routing_entry_node_id,
            data=EdgeDataDTO(
                label="Hotword → Routing (silent)",
                condition=(
                    "The caller mentioned an urgent hotword keyword. Go to "
                    "Routing immediately and silently, and set patient_verified "
                    "to N/A."
                ),
                transition_speech="",
                transition_speech_type="text",
            ),
        )
    )

    # --- AH Intent → Billing Closed (Req 8.4) ---
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_INTENT_TO_BILLING_CLOSED,
            source=NODE_AH_INTENT,
            target=NODE_AH_BILLING_CLOSED,
            data=EdgeDataDTO(
                label="Intent: Billing (after hours)",
                condition=(
                    "The intent is Billing. The billing department is closed "
                    "after hours."
                ),
            ),
        )
    )

    # --- AH Intent → MyChart Closed (Req 8.5) ---
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_INTENT_TO_MYCHART_CLOSED,
            source=NODE_AH_INTENT,
            target=NODE_AH_MYCHART_CLOSED,
            data=EdgeDataDTO(
                label="Intent: MyChart (after hours)",
                condition=(
                    "The intent is MyChart support. MyChart support is closed "
                    "after hours."
                ),
            ),
        )
    )

    # --- AH Intent → Paging Clarifier (Req 8.8) ---
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_INTENT_TO_PAGING_CLARIFIER,
            source=NODE_AH_INTENT,
            target=NODE_AH_PAGING_CLARIFIER,
            data=EdgeDataDTO(
                label="Paging clarification needed",
                condition=(
                    "The intent is Paging, or it must be clarified whether the "
                    "caller is a provider/staff member or the patient."
                ),
            ),
        )
    )

    # --- AH Intent → Restricted Connect (Req 8.2) ---
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_INTENT_TO_RESTRICTED_CONNECT,
            source=NODE_AH_INTENT,
            target=NODE_AH_RESTRICTED_CONNECT,
            data=EdgeDataDTO(
                label="Restricted service requested",
                condition=(
                    "The caller wants a service that is limited after hours "
                    "(e.g. scheduling). Inform them and ask whether to connect."
                ),
                transition_speech=scripts.AH_RESTRICTED_SERVICE_SCHEDULING,
                transition_speech_type="text",
            ),
        )
    )

    # --- Restricted Connect → Authentication (caller agreed, Req 8.9) ---
    # Silent transition (Req 8.9 → auth entry is silent per design).
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_RESTRICTED_CONNECT_TO_AUTH,
            source=NODE_AH_RESTRICTED_CONNECT,
            target=auth_entry_node_id,
            data=EdgeDataDTO(
                label="Caller agreed → Auth (silent)",
                condition=(
                    "The caller agreed to be connected. Proceed to "
                    "authentication silently."
                ),
                transition_speech="",
                transition_speech_type="text",
            ),
        )
    )

    # --- Restricted Connect → End/Goodbye (declined or timeout, Req 8.10, 8.11) ---
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_RESTRICTED_CONNECT_TO_END,
            source=NODE_AH_RESTRICTED_CONNECT,
            target=end_node_id,
            data=EdgeDataDTO(
                label="Declined/timeout → Goodbye",
                condition=(
                    "The caller declined to be connected, or no intelligible "
                    f"decision was received within {RESTRICTED_CONNECT_TIMEOUT_SECONDS} "
                    "seconds. End the call."
                ),
            ),
        )
    )

    # --- Retry edges (Req 8.6, 8.7) ---
    # Retry 1: AH Intent → AH Intent with AH_RETRY_1 speech
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_RETRY_1,
            source=NODE_AH_INTENT,
            target=NODE_AH_INTENT,
            data=EdgeDataDTO(
                label="Not understood (1st retry)",
                condition=(
                    "The intent was not understood and this is the FIRST "
                    "not-understood turn. Stay here and ask them to repeat."
                ),
                transition_speech=scripts.AH_RETRY_1,
                transition_speech_type="text",
            ),
        )
    )

    # Retry 2: AH Intent → AH Intent with AH_RETRY_2 speech
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_RETRY_2,
            source=NODE_AH_INTENT,
            target=NODE_AH_INTENT,
            data=EdgeDataDTO(
                label="Not understood (2nd retry)",
                condition=(
                    "The intent was not understood and this is the SECOND "
                    "consecutive not-understood turn. Stay here and ask again."
                ),
                transition_speech=scripts.AH_RETRY_2,
                transition_speech_type="text",
            ),
        )
    )

    # Retry 3 (silent): AH Intent → Routing (Req 8.7)
    edges.append(
        RFEdgeDTO(
            id=EDGE_AH_RETRY_3_SILENT,
            source=NODE_AH_INTENT,
            target=routing_entry_node_id,
            data=EdgeDataDTO(
                label="3rd failure → Routing (silent)",
                condition=(
                    "The intent was not understood on the THIRD consecutive "
                    "turn. Go to Routing silently, with no further retries."
                ),
                transition_speech="",
                transition_speech_type="text",
            ),
        )
    )

    return edges


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_after_hours_cluster(
    *,
    routing_entry_node_id: str = "routing_resolve",
    auth_entry_node_id: str = "auth_phone",
    end_node_id: str = "end_goodbye",
) -> AfterHoursClusterResult:
    """Build the After Hours node cluster for the switchboard graph.

    Assembles nodes and edges for the After Hours phase. External cluster entry
    points (Routing, Authentication, end/goodbye) are wired by their IDs; the
    graph assembler (task 18.1) resolves these to the actual nodes when composing
    the full graph.

    The hotword keyword list is read from configuration at build time
    (Req 21.3) and embedded in the AH Intent node's prompt.

    Args:
        routing_entry_node_id: Node ID of the Routing cluster's entry node.
        auth_entry_node_id: Node ID of the Authentication cluster's entry node.
        end_node_id: Node ID of the end/goodbye terminal node.

    Returns:
        An :class:`AfterHoursClusterResult` containing the nodes, edges, entry
        node ID, and a mapping of exposed node IDs for cross-cluster wiring.
    """
    nodes = [
        _make_ah_intent_node(),
        _make_restricted_connect_node(),
        _make_billing_closed_node(),
        _make_mychart_closed_node(),
        _make_paging_clarifier_node(),
    ]

    edges = _make_edges(
        routing_entry_node_id=routing_entry_node_id,
        auth_entry_node_id=auth_entry_node_id,
        end_node_id=end_node_id,
    )

    return AfterHoursClusterResult(
        nodes=nodes,
        edges=edges,
        entry_node_id=NODE_AH_INTENT,
        exposed_node_ids={
            "ah_intent": NODE_AH_INTENT,
            "ah_restricted_connect": NODE_AH_RESTRICTED_CONNECT,
            "ah_billing_closed": NODE_AH_BILLING_CLOSED,
            "ah_mychart_closed": NODE_AH_MYCHART_CLOSED,
            "ah_paging_clarifier": NODE_AH_PAGING_CLARIFIER,
        },
    )


__all__ = [
    # Node IDs
    "NODE_AH_INTENT",
    "NODE_AH_RESTRICTED_CONNECT",
    "NODE_AH_BILLING_CLOSED",
    "NODE_AH_MYCHART_CLOSED",
    "NODE_AH_PAGING_CLARIFIER",
    # Edge IDs
    "EDGE_AH_HOTWORD_TO_ROUTING",
    "EDGE_AH_INTENT_TO_BILLING_CLOSED",
    "EDGE_AH_INTENT_TO_MYCHART_CLOSED",
    "EDGE_AH_INTENT_TO_PAGING_CLARIFIER",
    "EDGE_AH_INTENT_TO_RESTRICTED_CONNECT",
    "EDGE_AH_RESTRICTED_CONNECT_TO_AUTH",
    "EDGE_AH_RESTRICTED_CONNECT_TO_END",
    "EDGE_AH_RETRY_1",
    "EDGE_AH_RETRY_2",
    "EDGE_AH_RETRY_3_SILENT",
    # Result type
    "AfterHoursClusterResult",
    # Builder
    "build_after_hours_cluster",
]
