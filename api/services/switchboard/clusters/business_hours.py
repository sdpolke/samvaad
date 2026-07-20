"""Business Hours cluster builder for the SpinSci switchboard workflow graph.

Assembles the Business Hours phase as a set of nodes and edges using the workflow
engine DTOs (:mod:`api.services.workflow.dto`). The pure decision logic lives in
:mod:`api.services.switchboard.business_hours`; this module only wires it into
node prompts, edge conditions, and extraction variables for the graph.

The cluster contains:
1. **Intent Classify** (``agentNode``): classifies the caller's intent from speech
   (Req 7.1). Extraction variables: ``intent``, ``appointment_action``,
   ``specialty``, ``patient_status``, ``provider_name``, ``location``,
   ``scan_type``.
2. **Directory/FAQ Lookup** (``agentNode``): performs provider/directory or FAQ
   lookups with speech prefix rules (Req 7.2-7.4). Tools: ``directory_lookup``,
   ``faq_kb``. Triage is never used as a directory specialty (Req 4.4).
3. **Scheduling Gate** (``agentNode``): asks "Are you a new or existing patient?"
   when ``appointment_action=create`` and ``patient_status`` is unknown (Req 7.5).
   Requires confirmed ``specialty`` before auth (Req 7.9, 12.3). Extraction:
   ``patient_status``, ``specialty``.
4. **Search Trouble** (``agentNode``): speaks the BH_SEARCH_TROUBLE line when a
   directory/provider search returns no match (Req 7.13).

Edges encode:
- Entry from Greeting cluster → BH Intent Classify
- Intent Classify → Directory/FAQ Lookup (lookup needed)
- Intent Classify → Scheduling Gate (intent=Scheduling)
- Directory/FAQ Lookup → Search Trouble (no match)
- Records silent-skip → Routing cluster (Req 7.10, ``transition_speech=""``)
- Retry edges: Intent Classify → itself (BH_RETRY_1 / BH_RETRY_2, Req 7.11)
- Silent retry-3 → Routing cluster (Req 7.12, ``transition_speech=""``)
- Scheduling Gate → Authentication cluster (auth required, silent)
- Intent Classify → Authentication cluster (non-Records non-Scheduling needing auth)

Export:
    :func:`build_business_hours_cluster` returns a :class:`BusinessHoursCluster`
    dataclass exposing node IDs for cross-cluster wiring.

Design references:
- ``design.md`` → "Business Hours cluster (Req 7, Req 11, Req 12)"
- ``requirements.md`` → Requirements 7.1-7.5, 7.9-7.13, 4.4, 11.1, 11.3, 11.4,
  12.3, 12.5

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.9, 7.10, 7.13, 4.4, 11.1, 11.3, 11.4,
12.3, 12.5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from api.services.switchboard import scripts
from api.services.switchboard.business_hours import (
    RECORDS_INTENT,
)
from api.services.switchboard.tools.base import ToolCluster
from api.services.switchboard.tools.registry import tools_for_cluster
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
# Stable node & edge IDs
# ---------------------------------------------------------------------------
# These are deterministic (no UUID suffix) so that (a) the assembled/registered
# template is stable across deployments, and (b) the silent-transition
# classifier (``api/services/switchboard/transitions.py``) can identify silent
# and auth-entry edges by ID rather than by brittle human-readable label text.
# The Business Hours cluster is instantiated exactly once per graph, so stable
# IDs cannot collide (matching the After Hours / Authentication clusters).

NODE_BH_INTENT_CLASSIFY = "bh_intent_classify"
NODE_BH_LOOKUP = "bh_lookup"
NODE_BH_SCHEDULING_GATE = "bh_scheduling_gate"
NODE_BH_SEARCH_TROUBLE = "bh_search_trouble"

EDGE_BH_GREETING_TO_BH = "bh_edge_greeting_to_bh"
EDGE_BH_CLASSIFY_TO_LOOKUP = "bh_edge_classify_to_lookup"
EDGE_BH_CLASSIFY_TO_SCHEDULING_GATE = "bh_edge_classify_to_scheduling_gate"
EDGE_BH_LOOKUP_TO_SEARCH_TROUBLE = "bh_edge_lookup_to_search_trouble"
EDGE_BH_LOOKUP_TO_ROUTING = "bh_edge_lookup_to_routing"
EDGE_BH_RECORDS_SKIP_AUTH = "bh_edge_records_skip_auth"
EDGE_BH_RETRY_1 = "bh_edge_retry_1"
EDGE_BH_RETRY_2 = "bh_edge_retry_2"
EDGE_BH_RETRY_3_SILENT_ROUTE = "bh_edge_retry_3_silent_route"
EDGE_BH_SCHEDULING_GATE_TO_AUTH = "bh_edge_scheduling_gate_to_auth"
EDGE_BH_CLASSIFY_TO_AUTH = "bh_edge_classify_to_auth"
EDGE_BH_SEARCH_TROUBLE_TO_ROUTING = "bh_edge_search_trouble_to_routing"


# ---------------------------------------------------------------------------
# Tool UUID helpers
# ---------------------------------------------------------------------------

def _tool_uuids_for_cluster(cluster: ToolCluster) -> list[str]:
    """Return the tool function names (used as UUIDs) for the given cluster."""
    return [tool.function_name for tool in tools_for_cluster(cluster)]


def _bh_lookup_tool_names() -> list[str]:
    """Return tool names scoped to the BH lookup node (directory_lookup, faq_kb)."""
    tools = tools_for_cluster(ToolCluster.BUSINESS_HOURS)
    return [t.function_name for t in tools if t.name in ("directory_lookup", "faq_kb")]


# ---------------------------------------------------------------------------
# Extraction variable definitions
# ---------------------------------------------------------------------------

_INTENT_CLASSIFY_EXTRACTION_VARS: list[ExtractionVariableDTO] = [
    ExtractionVariableDTO(
        name="intent",
        type=VariableType.string,
        prompt=(
            "The caller's classified intent. One of: Scheduling, Referrals, "
            "Triage, Billing, mychart, Paging, Directory, Pharmacy, General, "
            "Records."
        ),
    ),
    ExtractionVariableDTO(
        name="appointment_action",
        type=VariableType.string,
        prompt=(
            "The scheduling action when intent=Scheduling. One of: create, "
            "cancel, reschedule, list, confirm. Null if intent is not Scheduling."
        ),
    ),
    ExtractionVariableDTO(
        name="specialty",
        type=VariableType.string,
        prompt=(
            "The medical specialty or department the caller needs. Normalize to "
            "a standard specialty name. Triage is NEVER a directory specialty "
            "(Req 4.4)."
        ),
    ),
    ExtractionVariableDTO(
        name="patient_status",
        type=VariableType.string,
        prompt="Whether the caller is a 'new' or 'existing' patient, if stated.",
    ),
    ExtractionVariableDTO(
        name="provider_name",
        type=VariableType.string,
        prompt="The provider/doctor name the caller mentioned, if any.",
    ),
    ExtractionVariableDTO(
        name="location",
        type=VariableType.string,
        prompt="The location/city/site the caller mentioned, if any.",
    ),
    ExtractionVariableDTO(
        name="scan_type",
        type=VariableType.string,
        prompt=(
            "The type of scan if the caller mentioned one. One of: MRI/CT, "
            "Mammo/Dexa, PET/Nuclear, US/Fluoro."
        ),
    ),
]

_SCHEDULING_GATE_EXTRACTION_VARS: list[ExtractionVariableDTO] = [
    ExtractionVariableDTO(
        name="patient_status",
        type=VariableType.string,
        prompt="Whether the caller is a 'new' or 'existing' patient.",
    ),
    ExtractionVariableDTO(
        name="specialty",
        type=VariableType.string,
        prompt=(
            "Confirm the specialty for the scheduling request. Required before "
            "authentication for manage actions (Req 7.9, 12.3)."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Node prompts
# ---------------------------------------------------------------------------

_INTENT_CLASSIFY_PROMPT: str = """\
You are classifying the caller's intent during business hours at SpinSci.

Listen to the caller's statement and classify their need into exactly ONE of these intents:
- Scheduling (create, cancel, reschedule, list, or confirm an appointment)
- Referrals
- Triage (nurse advice line — NEVER use Triage as a directory specialty)
- Billing
- mychart (MyChart support)
- Paging
- Directory (provider/department lookup)
- Pharmacy
- General
- Records (medical records)

When the intent is Scheduling, also determine the appointment_action from the caller's \
speech. Map to exactly one of: create, cancel, reschedule, list, confirm. NEVER default \
to 'create' when the caller expressed cancel, reschedule, list, or confirm (Req 7.7).

Extract the specialty, provider_name, location, patient_status, and scan_type if the \
caller mentions them. Triage is NEVER used as a directory specialty (Req 4.4).

Handling an unsure caller: if the caller spoke intelligibly but their need is vague or \
uncertain — they don't know which specialty, provider, or department they need, say \
they're not sure, or just ask for help (e.g. "I don't know my specialty", "I'm not \
sure who I need") — classify the intent as General so they are connected to someone \
who can help. This is NOT a not-understood turn; do NOT re-ask with a "didn't catch \
that" line.

Only treat a turn as not-understood (letting the retry mechanism re-ask) when it was \
genuinely unintelligible: silence, background noise, or speech that could not be made \
out at all. If you could make out the caller's words, never treat it as not-understood \
— classify General instead."""

_DIRECTORY_FAQ_LOOKUP_PROMPT: str = """\
You perform provider/directory lookups or FAQ knowledge-base lookups for the caller.

Speech prefix rules (GATE-LOOKUP-SPEECH):
- For the FIRST provider/directory lookup on this turn: say NOTHING before invoking \
the lookup tool (silent — Req 7.2).
- For an FAQ lookup: say "Let me check that for you." THEN invoke the faq_kb tool \
on the same turn (Req 7.3).
- For any OTHER lookup (non-first directory or non-FAQ): say "One moment." THEN \
invoke the tool on the same turn (Req 7.4).

IMPORTANT: Triage is NEVER used as a directory specialty (Req 4.4). If the caller \
asks to be connected to Triage, route through the Triage intent path, NOT a \
directory search for "Triage".

Invoke the lookup tool on the SAME turn as the prefix speech — never defer to a \
later turn.

One lookup per request: call the lookup tool at most ONCE for the caller's \
current request. As soon as a tool result comes back, STOP calling tools and \
transition:
- If the result contains a matching department, provider, or FAQ answer, take \
the "Lookup Complete" transition to Routing.
- If the result is empty (no match) OR the tool returned status "error", take \
the "No Match Found" transition to Search Trouble. Treat a tool error exactly \
like "no match".
Never call the lookup tool a second time for the same request, and never re-call \
it after receiving a result."""

_SCHEDULING_GATE_PROMPT: str = f"""\
You are the scheduling gate at SpinSci during business hours.

When appointment_action is 'create' and patient_status is unknown (null/empty), \
ask the caller: "{scripts.BH_SCHEDULING_GATE}"

For manage actions (cancel, reschedule, list, confirm):
- Skip the new/existing question — the caller is treated as an existing patient \
(patient_status=existing).
- A confirmed specialty is REQUIRED before proceeding to authentication (Req 7.9, 12.3).

If the caller has already stated whether they are new or existing, do NOT re-ask. \
Carry the known patient_status forward.

Extract patient_status and specialty from the caller's response."""

_SEARCH_TROUBLE_PROMPT: str = f"""\
The directory or provider search returned no matching record.

Speak the following line EXACTLY (verbatim, no modifications):
"{scripts.BH_SEARCH_TROUBLE}"

Then wait for the caller's response. If they want to be connected, transition to \
routing. If they want to try again, transition back to lookup."""


# ---------------------------------------------------------------------------
# Cluster result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BusinessHoursCluster:
    """The assembled Business Hours cluster: nodes, edges, and exposed node IDs.

    Node IDs are exposed for cross-cluster edge wiring (the graph assembler
    connects edges from/to these IDs).
    """

    nodes: list[RFNodeDTO]
    edges: list[RFEdgeDTO]

    #: Entry point — the Intent Classify node. Greeting cluster edges target this.
    intent_classify_id: str

    #: The Directory/FAQ Lookup node.
    lookup_id: str

    #: The Scheduling Gate node.
    scheduling_gate_id: str

    #: The Search Trouble node.
    search_trouble_id: str


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_business_hours_cluster(
    *,
    greeting_exit_node_id: Optional[str] = None,
    auth_entry_node_id: Optional[str] = None,
    routing_entry_node_id: Optional[str] = None,
) -> BusinessHoursCluster:
    """Build the Business Hours node cluster for the switchboard workflow graph.

    Returns a :class:`BusinessHoursCluster` with all nodes, internal edges, and
    cross-cluster edges (when target node IDs are provided).

    Args:
        greeting_exit_node_id: The Greeting cluster's exit node ID. When provided,
            an entry edge from Greeting → Intent Classify is created.
        auth_entry_node_id: The Authentication cluster's entry node ID. When
            provided, edges from Scheduling Gate → Auth and Intent Classify → Auth
            are created.
        routing_entry_node_id: The Routing cluster's entry node ID. When provided,
            Records silent-skip, retry-3 silent, and other routing edges are
            created.

    Returns:
        A :class:`BusinessHoursCluster` with nodes, edges, and exposed IDs.
    """
    # --- Node IDs (stable) ---
    intent_classify_id = NODE_BH_INTENT_CLASSIFY
    lookup_id = NODE_BH_LOOKUP
    scheduling_gate_id = NODE_BH_SCHEDULING_GATE
    search_trouble_id = NODE_BH_SEARCH_TROUBLE

    # --- Build nodes ---
    lookup_tool_uuids = _bh_lookup_tool_names()

    intent_classify_node = RFNodeDTO(
        id=intent_classify_id,
        type="agentNode",
        position=Position(x=400, y=300),
        data=AgentNodeData(
            name="BH Intent Classify",
            prompt=_INTENT_CLASSIFY_PROMPT,
            allow_interrupt=True,
            add_global_prompt=True,
            extraction_enabled=True,
            extraction_prompt=(
                "Extract the caller's intent classification, appointment action "
                "(if scheduling), specialty, patient status, provider name, "
                "location, and scan type from their utterance."
            ),
            extraction_variables=_INTENT_CLASSIFY_EXTRACTION_VARS,
            tool_uuids=None,  # No tools on classify — tools are on the lookup node
        ),
    )

    lookup_node = RFNodeDTO(
        id=lookup_id,
        type="agentNode",
        position=Position(x=700, y=200),
        data=AgentNodeData(
            name="BH Directory/FAQ Lookup",
            prompt=_DIRECTORY_FAQ_LOOKUP_PROMPT,
            allow_interrupt=False,
            add_global_prompt=True,
            extraction_enabled=False,
            tool_uuids=lookup_tool_uuids,
        ),
    )

    scheduling_gate_node = RFNodeDTO(
        id=scheduling_gate_id,
        type="agentNode",
        position=Position(x=700, y=400),
        data=AgentNodeData(
            name="BH Scheduling Gate",
            prompt=_SCHEDULING_GATE_PROMPT,
            allow_interrupt=True,
            add_global_prompt=True,
            extraction_enabled=True,
            extraction_prompt=(
                "Extract whether the caller is new or existing, and confirm the "
                "specialty for the scheduling request."
            ),
            extraction_variables=_SCHEDULING_GATE_EXTRACTION_VARS,
            tool_uuids=None,
        ),
    )

    search_trouble_node = RFNodeDTO(
        id=search_trouble_id,
        type="agentNode",
        position=Position(x=1000, y=200),
        data=AgentNodeData(
            name="BH Search Trouble",
            prompt=_SEARCH_TROUBLE_PROMPT,
            allow_interrupt=True,
            add_global_prompt=False,  # Verbatim line — no global persona perturbation
            extraction_enabled=False,
            tool_uuids=None,
        ),
    )

    nodes: list[RFNodeDTO] = [
        intent_classify_node,
        lookup_node,
        scheduling_gate_node,
        search_trouble_node,
    ]

    # --- Build edges ---
    edges: list[RFEdgeDTO] = []

    # Entry edge: Greeting → BH Intent Classify
    if greeting_exit_node_id:
        edges.append(
            RFEdgeDTO(
                id=EDGE_BH_GREETING_TO_BH,
                source=greeting_exit_node_id,
                target=intent_classify_id,
                data=EdgeDataDTO(
                    label="To Business Hours",
                    condition=(
                        "after_hours is false AND caller provided intent, "
                        "specialty, provider, or specific request (Path A)"
                    ),
                    transition_speech=scripts.GREETING_PATH_A_STANDARD,
                    transition_speech_type="text",
                ),
            )
        )

    # Intent Classify → Directory/FAQ Lookup (condition: lookup needed)
    edges.append(
        RFEdgeDTO(
            id=EDGE_BH_CLASSIFY_TO_LOOKUP,
            source=intent_classify_id,
            target=lookup_id,
            data=EdgeDataDTO(
                label="Lookup Needed",
                condition=(
                    "The caller needs a directory/provider lookup or an "
                    "FAQ/knowledge-base answer (e.g. intent is Directory, or "
                    "they asked a question that needs a lookup)."
                ),
                transition_speech=None,
            ),
        )
    )

    # Intent Classify → Scheduling Gate (condition: intent=Scheduling)
    edges.append(
        RFEdgeDTO(
            id=EDGE_BH_CLASSIFY_TO_SCHEDULING_GATE,
            source=intent_classify_id,
            target=scheduling_gate_id,
            data=EdgeDataDTO(
                label="Scheduling Intent",
                condition=(
                    "The intent is Scheduling (an appointment_action such as "
                    "create, cancel, reschedule, list, or confirm is present)."
                ),
                transition_speech=None,
            ),
        )
    )

    # Directory/FAQ Lookup → Search Trouble (condition: no match found)
    edges.append(
        RFEdgeDTO(
            id=EDGE_BH_LOOKUP_TO_SEARCH_TROUBLE,
            source=lookup_id,
            target=search_trouble_id,
            data=EdgeDataDTO(
                label="No Match Found",
                condition=(
                    "The directory or provider search returned no matching record, "
                    "OR the lookup tool call returned status 'error' (treat a tool "
                    "error identically to no match — never retry the tool)."
                ),
                transition_speech=None,
            ),
        )
    )

    # Directory/FAQ Lookup → Routing (condition: lookup returned a result).
    # Without this edge the lookup node has no success/onward transition, so a
    # successful (or mocked) lookup leaves the LLM with nothing to do but call
    # the lookup tool again — an infinite tool-call loop. On a match, hand off to
    # Routing, which resolves the destination and either transfers (connect) or
    # speaks the info-only Directory goodbye.
    if routing_entry_node_id:
        edges.append(
            RFEdgeDTO(
                id=EDGE_BH_LOOKUP_TO_ROUTING,
                source=lookup_id,
                target=routing_entry_node_id,
                data=EdgeDataDTO(
                    label="Lookup Complete",
                    condition=(
                        "The lookup returned a result (a matching department, "
                        "provider, or FAQ answer). Do NOT call the lookup tool "
                        "again — proceed to Routing to connect the caller or "
                        "deliver the directory outcome."
                    ),
                    transition_speech=None,
                ),
            )
        )

    # Records silent-skip edge: Intent Classify → Routing cluster entry
    # (condition: intent=Records, transition_speech="" — silent, Req 7.10)
    if routing_entry_node_id:
        edges.append(
            RFEdgeDTO(
                id=EDGE_BH_RECORDS_SKIP_AUTH,
                source=intent_classify_id,
                target=routing_entry_node_id,
                data=EdgeDataDTO(
                    label="Records Skip Auth",
                    condition=(
                        f"The intent is '{RECORDS_INTENT}'. Skip authentication "
                        "and go straight to Routing (silent)."
                    ),
                    transition_speech="",
                    transition_speech_type="text",
                ),
            )
        )

    # Retry edge 1: Intent Classify → Intent Classify (1st failure, BH_RETRY_1)
    edges.append(
        RFEdgeDTO(
            id=EDGE_BH_RETRY_1,
            source=intent_classify_id,
            target=intent_classify_id,
            data=EdgeDataDTO(
                label="Retry 1 - Not Understood",
                condition=(
                    "The caller's turn was genuinely unintelligible — silence, "
                    "background noise, or speech that could not be made out at "
                    "all — and this is the FIRST such not-understood turn. Do "
                    "NOT take this for an intelligible but vague/unsure caller "
                    "(classify General instead). Stay here and re-ask."
                ),
                transition_speech=scripts.BH_RETRY_1,
                transition_speech_type="text",
            ),
        )
    )

    # Retry edge 2: Intent Classify → Intent Classify (2nd failure, BH_RETRY_2)
    edges.append(
        RFEdgeDTO(
            id=EDGE_BH_RETRY_2,
            source=intent_classify_id,
            target=intent_classify_id,
            data=EdgeDataDTO(
                label="Retry 2 - Still Not Understood",
                condition=(
                    "The caller's turn was genuinely unintelligible — silence, "
                    "background noise, or speech that could not be made out at "
                    "all — and this is the SECOND consecutive such not-understood "
                    "turn. Do NOT take this for an intelligible but vague/unsure "
                    "caller (classify General instead). Stay here and re-ask."
                ),
                transition_speech=scripts.BH_RETRY_2,
                transition_speech_type="text",
            ),
        )
    )

    # Silent retry-3 edge: Intent Classify → Routing cluster entry
    # (condition: 3rd consecutive failure, transition_speech="" — silent, Req 7.12)
    if routing_entry_node_id:
        edges.append(
            RFEdgeDTO(
                id=EDGE_BH_RETRY_3_SILENT_ROUTE,
                source=intent_classify_id,
                target=routing_entry_node_id,
                data=EdgeDataDTO(
                    label="Retry 3 - Silent Route",
                    condition=(
                        "The intent could not be classified on the THIRD "
                        "consecutive turn. Go to Routing silently, with no filler."
                    ),
                    transition_speech="",
                    transition_speech_type="text",
                ),
            )
        )

    # Scheduling Gate → Authentication cluster entry
    # (condition: auth required, transition_speech="" — silent)
    if auth_entry_node_id:
        edges.append(
            RFEdgeDTO(
                id=EDGE_BH_SCHEDULING_GATE_TO_AUTH,
                source=scheduling_gate_id,
                target=auth_entry_node_id,
                data=EdgeDataDTO(
                    label="Auth Required After Scheduling Gate",
                    condition=(
                        "Scheduling gate complete — patient_status and specialty "
                        "confirmed, authentication is required before routing"
                    ),
                    transition_speech="",
                    transition_speech_type="text",
                ),
            )
        )

    # Intent Classify → Authentication cluster entry
    # (condition: non-Records non-Scheduling intent requiring auth, silent)
    if auth_entry_node_id:
        edges.append(
            RFEdgeDTO(
                id=EDGE_BH_CLASSIFY_TO_AUTH,
                source=intent_classify_id,
                target=auth_entry_node_id,
                data=EdgeDataDTO(
                    label="Auth Required (Non-Scheduling)",
                    condition=(
                        "The intent needs authentication before routing "
                        "(Referrals, Triage, Billing, MyChart, Paging, "
                        "Directory-connect, Pharmacy, or General) and is neither "
                        "Records nor a new-patient create."
                    ),
                    transition_speech="",
                    transition_speech_type="text",
                ),
            )
        )

    # Search Trouble → Routing (when caller wants to be connected)
    if routing_entry_node_id:
        edges.append(
            RFEdgeDTO(
                id=EDGE_BH_SEARCH_TROUBLE_TO_ROUTING,
                source=search_trouble_id,
                target=routing_entry_node_id,
                data=EdgeDataDTO(
                    label="Connect After Search Trouble",
                    condition=(
                        "Caller agreed to be connected with someone who can help "
                        "after search trouble"
                    ),
                    transition_speech=None,
                ),
            )
        )

    return BusinessHoursCluster(
        nodes=nodes,
        edges=edges,
        intent_classify_id=intent_classify_id,
        lookup_id=lookup_id,
        scheduling_gate_id=scheduling_gate_id,
        search_trouble_id=search_trouble_id,
    )


__all__ = [
    # Stable node IDs
    "NODE_BH_INTENT_CLASSIFY",
    "NODE_BH_LOOKUP",
    "NODE_BH_SCHEDULING_GATE",
    "NODE_BH_SEARCH_TROUBLE",
    # Stable edge IDs
    "EDGE_BH_GREETING_TO_BH",
    "EDGE_BH_CLASSIFY_TO_LOOKUP",
    "EDGE_BH_CLASSIFY_TO_SCHEDULING_GATE",
    "EDGE_BH_LOOKUP_TO_SEARCH_TROUBLE",
    "EDGE_BH_LOOKUP_TO_ROUTING",
    "EDGE_BH_RECORDS_SKIP_AUTH",
    "EDGE_BH_RETRY_1",
    "EDGE_BH_RETRY_2",
    "EDGE_BH_RETRY_3_SILENT_ROUTE",
    "EDGE_BH_SCHEDULING_GATE_TO_AUTH",
    "EDGE_BH_CLASSIFY_TO_AUTH",
    "EDGE_BH_SEARCH_TROUBLE_TO_ROUTING",
    # Cluster
    "BusinessHoursCluster",
    "build_business_hours_cluster",
]
