"""Greeting cluster graph builder for the SpinSci switchboard.

Produces the workflow nodes and edges for the Greeting phase:
- ``trigger`` → ``startCall`` → ``agentNode`` (Greeting Collect)
- Path A edge from Greeting Collect to BH/AH output connector
- Path E loop edge (not-understood retry with ROUTING REQUEST fallback)
- ROUTING REQUEST edge (explicit fallback for no-signal callers)

The pure decision logic lives in :mod:`api.services.switchboard.greeting`
(``select_greeting``, ``ready_to_handoff``, ``path_e_response``,
``PathERetryState``). This module wires that logic into node prompts and edge
conditions using the engine's DTO primitives.

The verbatim scripts referenced in prompts are from
:mod:`api.services.switchboard.scripts` (Appendix C).

Design references:
- ``design.md`` → "Greeting cluster (Req 6)"
- ``design.md`` → "Phases as node clusters" (trigger → startCall inbound entry)

Requirements: 1.2, 1.3, 1.4, 3.5, 6.1, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.services.switchboard import scripts
from api.services.switchboard.tools.registry import PATIENT_LOOKUP
from api.services.workflow.dto import (
    AgentNodeData,
    EdgeDataDTO,
    ExtractionVariableDTO,
    Position,
    RFEdgeDTO,
    RFNodeDTO,
    StartCallNodeData,
    TriggerNodeData,
    VariableType,
)

# ---------------------------------------------------------------------------
# Node IDs (stable, exported so other clusters can connect to them)
# ---------------------------------------------------------------------------

TRIGGER_NODE_ID: str = "greeting_trigger"
START_CALL_NODE_ID: str = "greeting_start_call"
GREETING_COLLECT_NODE_ID: str = "greeting_collect"

# ---------------------------------------------------------------------------
# Edge IDs
# ---------------------------------------------------------------------------

EDGE_TRIGGER_TO_START: str = "edge_trigger_to_start_call"
EDGE_START_TO_COLLECT: str = "edge_start_call_to_greeting_collect"
EDGE_PATH_A: str = "edge_greeting_path_a"
EDGE_PATH_E_LOOP: str = "edge_greeting_path_e_loop"
EDGE_ROUTING_REQUEST: str = "edge_greeting_routing_request"

# ---------------------------------------------------------------------------
# Config placeholders (replaced at deploy time with real values)
# ---------------------------------------------------------------------------

#: Placeholder for the pre-call fetch URL that performs the 2s ANI patient lookup.
PRE_CALL_FETCH_URL_PLACEHOLDER: str = (
    "https://api.spinsci.example.com/patient-lookup"
)

#: Placeholder recording ID for the config-driven welcome audio (Req 6.4).
GREETING_RECORDING_ID_PLACEHOLDER: str = "spinsci_welcome_audio_recording"

# ---------------------------------------------------------------------------
# Extraction variables shared across greeting nodes
# ---------------------------------------------------------------------------

GREETING_EXTRACTION_VARIABLES: list[ExtractionVariableDTO] = [
    ExtractionVariableDTO(
        name="caller_name",
        type=VariableType.string,
        prompt="The caller's name as they state it.",
    ),
    ExtractionVariableDTO(
        name="intent",
        type=VariableType.string,
        prompt=(
            "The caller's intent or reason for calling (e.g. scheduling, "
            "referrals, triage, billing, records, pharmacy, general)."
        ),
    ),
    ExtractionVariableDTO(
        name="specialty",
        type=VariableType.string,
        prompt="The medical specialty the caller mentions (e.g. cardiology, orthopedics).",
    ),
    ExtractionVariableDTO(
        name="provider_name",
        type=VariableType.string,
        prompt="The name of a specific provider/doctor the caller requests.",
    ),
    ExtractionVariableDTO(
        name="scan_type",
        type=VariableType.string,
        prompt=(
            "A specific imaging/scan type the caller requests "
            "(MRI/CT, Mammo/Dexa, PET/Nuclear, US/Fluoro)."
        ),
    ),
    ExtractionVariableDTO(
        name="appointment_action",
        type=VariableType.string,
        prompt=(
            "The appointment action the caller wants: create, cancel, "
            "reschedule, list, or confirm."
        ),
    ),
]

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

START_CALL_PROMPT: str = (
    "The welcome greeting is delivered to the caller automatically (as node "
    "greeting audio/text) — do NOT speak a greeting yourself and do NOT repeat "
    "it. The turn-1 ANI patient lookup runs automatically via pre-call fetch.\n\n"
    "Wait for the caller to respond to the greeting. When they do, extract "
    "caller_name, intent, specialty, provider_name, scan_type, and "
    "appointment_action from what they say, then transition to collect their "
    "routing information. Do not speak filler while waiting."
)

GREETING_COLLECT_PROMPT: str = (
    "You are in the Greeting Collect phase. The welcome greeting has already been "
    "delivered to the caller by the previous step — do NOT greet again and do NOT "
    "repeat it. Your only job now is to capture the caller's routing information "
    "(intent, specialty, provider, scan type, or appointment action) and then take "
    "the correct transition.\n\n"
    "Extract caller_name, intent, specialty, provider_name, scan_type, and "
    "appointment_action from what the caller says.\n\n"
    "Deciding which transition to take (choose exactly ONE):\n"
    "- Path A — the caller's utterance contains at least one routing signal: an "
    "intent, a specialty, a provider_name, a scan_type, or an appointment_action. "
    "A caller_name alone is NEVER sufficient to hand off (Req 6.7).\n"
    "- ROUTING REQUEST — the caller was understood but gave NO routing signal. "
    "This INCLUDES a caller who is unsure, says they don't know (e.g. \"I don't "
    "know my specialty\", \"I'm not sure\"), asks for help, or gives only chit-chat "
    "or a name. Also take this after three consecutive not-understood turns.\n"
    "- Path E — ONLY when the caller's turn was genuinely unintelligible: silence, "
    "background noise, or speech that could not be made out at all, AND fewer than "
    "three consecutive not-understood turns have occurred.\n\n"
    "Critical: an intelligible reply that simply lacks a routing signal is NOT "
    "\"not understood\". If you could make out the words, never take Path E — the "
    "caller must never hear \"I didn't catch that\" for something they clearly "
    "said. When in doubt between Path E and ROUTING REQUEST, choose ROUTING "
    "REQUEST.\n\n"
    "The line spoken on each transition is delivered automatically by the "
    "transition itself — do not speak it yourself, and do not emit filler while "
    "deciding."
)

# ---------------------------------------------------------------------------
# Cluster result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GreetingClusterResult:
    """The assembled Greeting cluster: nodes, edges, and exported IDs.

    Attributes:
        nodes: The RFNodeDTO instances for this cluster.
        edges: The RFEdgeDTO instances wiring the cluster internally and to
            output connectors (downstream clusters connect to the Path A / ROUTING
            REQUEST edge targets).
        trigger_node_id: The trigger node ID (graph entry point).
        start_call_node_id: The startCall node ID.
        greeting_collect_node_id: The Greeting Collect agentNode ID (downstream
            clusters connect edges FROM this node).
    """

    nodes: list[RFNodeDTO]
    edges: list[RFEdgeDTO]
    trigger_node_id: str
    start_call_node_id: str
    greeting_collect_node_id: str


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_greeting_cluster(
    *,
    pre_call_fetch_url: str = PRE_CALL_FETCH_URL_PLACEHOLDER,
    greeting_recording_id: str | None = None,
    greeting_text: str = scripts.GREETING_SCRIPT_4_STANDARD_IN_HOURS,
    patient_lookup_tool_uuid: str = PATIENT_LOOKUP.name,
) -> GreetingClusterResult:
    """Build the Greeting phase node cluster and return its graph elements.

    Creates the trigger → startCall → Greeting Collect nodes with the correct
    prompts, extraction variables, tool scoping, and edge conditions.

    Args:
        pre_call_fetch_url: The endpoint URL for the 2-second ANI patient lookup
            pre-call fetch. Defaults to the placeholder URL.
        greeting_recording_id: The recording ID for the config-driven welcome
            audio. Defaults to a placeholder.
        patient_lookup_tool_uuid: The tool UUID for the patient_lookup connector
            tool. Defaults to the tool's registered name.

    Returns:
        A :class:`GreetingClusterResult` containing nodes, edges, and the
        exported node IDs for downstream cluster connections.
    """
    # -- Nodes ---------------------------------------------------------------

    trigger_node = RFNodeDTO(
        id=TRIGGER_NODE_ID,
        type="trigger",
        position=Position(x=0, y=0),
        data=TriggerNodeData(
            name="Inbound Trigger",
            enabled=True,
        ),
    )

    start_call_node = RFNodeDTO(
        id=START_CALL_NODE_ID,
        type="startCall",
        position=Position(x=0, y=150),
        data=StartCallNodeData(
            name="Greeting Start",
            prompt=START_CALL_PROMPT,
            # Deterministic spoken greeting (Req 6.4): play the config-driven
            # welcome audio when a recording is provided, otherwise speak a text
            # greeting via TTS. A configured greeting makes the engine speak on
            # turn 1 and wait for the caller, instead of falling through to an
            # immediate LLM generation that transitions without greeting.
            greeting_type="audio" if greeting_recording_id else "text",
            greeting=None if greeting_recording_id else greeting_text,
            greeting_recording_id=greeting_recording_id,
            # 2s-bound ANI lookup via pre-call fetch (Req 6.1)
            pre_call_fetch_enabled=True,
            pre_call_fetch_url=pre_call_fetch_url,
            # Extraction for ledger fields the caller may provide on turn 1
            extraction_enabled=True,
            extraction_variables=GREETING_EXTRACTION_VARIABLES,
            # Scoped tool: patient_lookup only (Req 1.7)
            tool_uuids=[patient_lookup_tool_uuid],
            allow_interrupt=True,
        ),
    )

    greeting_collect_node = RFNodeDTO(
        id=GREETING_COLLECT_NODE_ID,
        type="agentNode",
        position=Position(x=0, y=350),
        data=AgentNodeData(
            name="Greeting Collect",
            prompt=GREETING_COLLECT_PROMPT,
            extraction_enabled=True,
            extraction_variables=GREETING_EXTRACTION_VARIABLES,
            allow_interrupt=True,
        ),
    )

    nodes: list[RFNodeDTO] = [trigger_node, start_call_node, greeting_collect_node]

    # -- Edges ---------------------------------------------------------------

    # trigger → startCall (unconditional inbound entry)
    edge_trigger_to_start = RFEdgeDTO(
        id=EDGE_TRIGGER_TO_START,
        source=TRIGGER_NODE_ID,
        target=START_CALL_NODE_ID,
        data=EdgeDataDTO(
            label="Inbound call",
            condition="Call received on inbound trigger.",
        ),
    )

    # startCall → Greeting Collect (after welcome audio, agent collects)
    edge_start_to_collect = RFEdgeDTO(
        id=EDGE_START_TO_COLLECT,
        source=START_CALL_NODE_ID,
        target=GREETING_COLLECT_NODE_ID,
        data=EdgeDataDTO(
            label="After welcome audio",
            condition=(
                "Welcome audio has played and pre-call fetch (ANI lookup) "
                "has completed. Transition to collect caller routing information."
            ),
        ),
    )

    # Path A: Greeting Collect → output (BH/AH connector)
    # Condition: caller utterance contains intent/specialty/provider/request
    # transition_speech: Path A ack line (same-turn ack, Req 3.5)
    edge_path_a = RFEdgeDTO(
        id=EDGE_PATH_A,
        source=GREETING_COLLECT_NODE_ID,
        target=GREETING_COLLECT_NODE_ID,  # placeholder target; downstream wires to BH/AH
        data=EdgeDataDTO(
            label="Path A — caller provided signal",
            condition=(
                "The caller's utterance contains at least one routing signal: "
                "an intent, a specialty, a provider name, a scan type, or an "
                "appointment action. A caller_name alone is NOT sufficient."
            ),
            transition_speech=scripts.GREETING_PATH_A_STANDARD,
            transition_speech_type="text",
        ),
    )

    # Path E loop: Greeting Collect → Greeting Collect (not understood)
    edge_path_e_loop = RFEdgeDTO(
        id=EDGE_PATH_E_LOOP,
        source=GREETING_COLLECT_NODE_ID,
        target=GREETING_COLLECT_NODE_ID,
        data=EdgeDataDTO(
            label="Path E — not understood (retry)",
            condition=(
                "The caller's turn was genuinely unintelligible — silence, "
                "background noise, or speech that could not be made out at all — "
                "AND fewer than three consecutive not-understood turns have "
                "occurred. Do NOT take this for an intelligible reply that merely "
                "lacks a routing signal (an unsure caller, 'I don't know', or "
                "chit-chat) — that is the ROUTING REQUEST transition. Stay here "
                "and re-prompt."
            ),
            transition_speech=scripts.GREETING_PATH_E,
            transition_speech_type="text",
        ),
    )

    # ROUTING REQUEST edge: Greeting Collect → output
    # On 3rd consecutive failure OR caller responded but no signal extracted
    edge_routing_request = RFEdgeDTO(
        id=EDGE_ROUTING_REQUEST,
        source=GREETING_COLLECT_NODE_ID,
        target=GREETING_COLLECT_NODE_ID,  # placeholder target; downstream wires to BH/AH
        data=EdgeDataDTO(
            label="ROUTING REQUEST — fallback",
            condition=(
                "The caller was understood but no routing signal (intent, "
                "specialty, provider, scan_type, appointment_action) was "
                "extracted — including a caller who is unsure, says they don't "
                "know, asks for help, or gives only chit-chat or a name — OR "
                "three consecutive not-understood turns have occurred."
            ),
            transition_speech=scripts.GREETING_ROUTING_REQUEST,
            transition_speech_type="text",
        ),
    )

    edges: list[RFEdgeDTO] = [
        edge_trigger_to_start,
        edge_start_to_collect,
        edge_path_a,
        edge_path_e_loop,
        edge_routing_request,
    ]

    return GreetingClusterResult(
        nodes=nodes,
        edges=edges,
        trigger_node_id=TRIGGER_NODE_ID,
        start_call_node_id=START_CALL_NODE_ID,
        greeting_collect_node_id=GREETING_COLLECT_NODE_ID,
    )


__all__ = [
    # Node IDs
    "TRIGGER_NODE_ID",
    "START_CALL_NODE_ID",
    "GREETING_COLLECT_NODE_ID",
    # Edge IDs
    "EDGE_TRIGGER_TO_START",
    "EDGE_START_TO_COLLECT",
    "EDGE_PATH_A",
    "EDGE_PATH_E_LOOP",
    "EDGE_ROUTING_REQUEST",
    # Config placeholders
    "PRE_CALL_FETCH_URL_PLACEHOLDER",
    "GREETING_RECORDING_ID_PLACEHOLDER",
    # Prompts
    "START_CALL_PROMPT",
    "GREETING_COLLECT_PROMPT",
    # Extraction variables
    "GREETING_EXTRACTION_VARIABLES",
    # Result
    "GreetingClusterResult",
    # Builder
    "build_greeting_cluster",
]
