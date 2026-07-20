"""Authentication-phase node cluster for the SpinSci switchboard (Req 9).

Builds the Authentication cluster: a set of workflow nodes and edges implementing
the auth flow (Req 9.1): phone → read-back → patient_lookup → DOB → identity →
Routing. Edges model the silent entry from BH/AH, the ANI-reuse conditional skip
of patient_lookup (Req 9.6), the no-record re-prompt (Req 9.10), the 3-attempt
exhaustion route (Req 9.12), auth fail/refusal routing (Req 9.7), and
changed-request return to Business/After Hours (Req 9.8).

Pure decision logic is in :mod:`api.services.switchboard.auth`; verbatim scripts
in :mod:`api.services.switchboard.scripts`. This module only wires them into the
graph structure using the workflow engine DTOs
(:mod:`api.services.workflow.dto`).

Requirements: 9.1, 3.3, 9.7, 9.8, 9.10, 9.12.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.services.switchboard import auth, scripts
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
# Node IDs — stable identifiers used for edge wiring and cross-cluster refs
# ---------------------------------------------------------------------------

AUTH_PHONE_NODE_ID = "auth_phone"
AUTH_READBACK_NODE_ID = "auth_readback"
AUTH_PATIENT_LOOKUP_NODE_ID = "auth_patient_lookup"
AUTH_DOB_NODE_ID = "auth_dob"
AUTH_IDENTITY_NODE_ID = "auth_identity"

#: All node IDs in this cluster, in flow order (Req 9.1).
AUTH_NODE_IDS: tuple[str, ...] = (
    AUTH_PHONE_NODE_ID,
    AUTH_READBACK_NODE_ID,
    AUTH_PATIENT_LOOKUP_NODE_ID,
    AUTH_DOB_NODE_ID,
    AUTH_IDENTITY_NODE_ID,
)

# ---------------------------------------------------------------------------
# Edge IDs
# ---------------------------------------------------------------------------

_EDGE_PHONE_TO_READBACK = "auth_e_phone_to_readback"
_EDGE_READBACK_TO_LOOKUP = "auth_e_readback_to_lookup"
_EDGE_READBACK_TO_DOB_ANI = "auth_e_readback_to_dob_ani"
_EDGE_READBACK_TO_PHONE_INCORRECT = "auth_e_readback_to_phone_incorrect"
_EDGE_LOOKUP_TO_DOB = "auth_e_lookup_to_dob"
_EDGE_LOOKUP_TO_PHONE_NO_RECORD = "auth_e_lookup_to_phone_no_record"
_EDGE_DOB_TO_IDENTITY = "auth_e_dob_to_identity"
_EDGE_IDENTITY_TO_ROUTING = "auth_e_identity_to_routing"
_EDGE_FAIL_TO_ROUTING = "auth_e_fail_to_routing"
_EDGE_CHANGED_REQUEST_BH = "auth_e_changed_request_bh"
_EDGE_CHANGED_REQUEST_AH = "auth_e_changed_request_ah"
_EDGE_PHONE_3_ATTEMPTS_ROUTE = "auth_e_phone_3_attempts_route"

# ---------------------------------------------------------------------------
# Tool UUIDs — resolved from the switchboard tool registry
# ---------------------------------------------------------------------------


def _auth_tool_uuids() -> list[str]:
    """Return the tool UUIDs (names) scoped to the Authentication cluster."""
    return [tool.name for tool in tools_for_cluster(ToolCluster.AUTHENTICATION)]


def _patient_lookup_tool_uuids() -> list[str]:
    """Return tool UUIDs including patient_lookup (scoped to Greeting+Auth)."""
    return ["patient_lookup"]


def _dob_tool_uuids() -> list[str]:
    """Return tool UUIDs for the DOB node (dob_validation)."""
    return ["dob_validation"]


def _identity_tool_uuids() -> list[str]:
    """Return tool UUIDs for the identity node (identity_verify)."""
    return ["identity_verify"]


# ---------------------------------------------------------------------------
# Node prompts — wire pure logic and verbatim scripts into prompts
# ---------------------------------------------------------------------------

_PHONE_PROMPT = (
    "You are collecting the caller's phone number so their record can be looked "
    "up. Ask for it: if {{caller_is_provider}} is true, say: \""
    + scripts.AUTH_PHONE_PROVIDER
    + '" Otherwise say: "'
    + scripts.AUTH_PHONE_PATIENT
    + '"\n\n'
    "Collect a COMPLETE 10-digit US phone number. Count the digits: if the caller "
    "gives fewer or more than 10 digits, or you are unsure of any digit, ask them "
    "to repeat the full 10-digit number and stay on this step — never proceed with "
    "an incomplete number. Extract the number into caller_phone and increment "
    "{{auth_phone_attempts}} each time you ask.\n\n"
    "Stay strictly on this step. Do NOT ask for the caller's date of birth, and "
    "do NOT attempt any patient lookup, records search, or other tool here — the "
    "only actions available to you are this node's flow transitions, and identity "
    "is verified later in the flow. If a previous lookup found no record, simply "
    "ask for a different phone number; do not switch to a different way of "
    "identifying the patient."
)

_READBACK_PROMPT = (
    "Read back the phone number in 3-3-4 period-grouped format. "
    "Use the format: digit.digit.digit. digit.digit.digit. digit.digit.digit.digit. "
    'Then ask: "Is that correct?" '
    "Extract whether the caller confirmed or denied the phone number."
)

_PATIENT_LOOKUP_PROMPT = (
    "This is a silent node. Do NOT produce any spoken output. "
    "Call the patient_lookup tool with the confirmed phone number. "
    "Extract the patient_id and patient record information from the result."
)

_DOB_PROMPT = (
    "Ask for the caller's date of birth. "
    "If {{caller_is_provider}} is true, say: \""
    + scripts.AUTH_DOB_PROVIDER
    + '" Otherwise say: "'
    + scripts.AUTH_DOB_PATIENT
    + '" Call the dob_validation tool with the provided DOB. '
    "Extract the provided_dob from the caller's response."
)

_IDENTITY_PROMPT = (
    "This is a silent node. Do NOT produce any spoken output. "
    "Call the identity_verify tool with the patient_id and verification signals. "
    "Set patient_verified to Success if DOB matched, or Fail otherwise. "
    "Extract the patient_verified value."
)


# ---------------------------------------------------------------------------
# Extraction variables per node
# ---------------------------------------------------------------------------

_PHONE_EXTRACTIONS = [
    ExtractionVariableDTO(
        name="caller_phone",
        type=VariableType.string,
        prompt="The 10-digit phone number the caller provided.",
    ),
    ExtractionVariableDTO(
        name="auth_phone_attempts",
        type=VariableType.number,
        prompt="Running count of phone number attempts (incremented each ask).",
    ),
]

_READBACK_EXTRACTIONS = [
    ExtractionVariableDTO(
        name="phone_confirmed",
        type=VariableType.boolean,
        prompt="Whether the caller confirmed the read-back phone number is correct.",
    ),
]

_PATIENT_LOOKUP_EXTRACTIONS = [
    ExtractionVariableDTO(
        name="patient_id",
        type=VariableType.string,
        prompt="The patient ID returned by the patient_lookup tool.",
    ),
    ExtractionVariableDTO(
        name="patient_record_found",
        type=VariableType.boolean,
        prompt="Whether a patient record was found for the phone number.",
    ),
]

_DOB_EXTRACTIONS = [
    ExtractionVariableDTO(
        name="provided_dob",
        type=VariableType.string,
        prompt="The date of birth provided by the caller.",
    ),
]

_IDENTITY_EXTRACTIONS = [
    ExtractionVariableDTO(
        name="patient_verified",
        type=VariableType.string,
        prompt=(
            "The identity verification result: 'Success' if DOB matched, "
            "'Fail' otherwise."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Cluster result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthenticationClusterResult:
    """The nodes, edges, and exposed IDs returned by :func:`build_authentication_cluster`.

    Attributes:
        nodes: The workflow nodes for this cluster.
        edges: The intra-cluster edges.
        entry_node_id: The first node in the cluster (Phone Number node), used for
            inter-cluster edges targeting this cluster.
        exit_node_id: The last node in the cluster (Identity Verify), which has an
            edge to the Routing cluster.
        all_node_ids: All node IDs in the cluster (for changed-request edge wiring).
    """

    nodes: list[RFNodeDTO]
    edges: list[RFEdgeDTO]
    entry_node_id: str
    exit_node_id: str
    all_node_ids: tuple[str, ...]


# ---------------------------------------------------------------------------
# External cluster node IDs (cross-cluster edge targets)
# These are the well-known IDs that the graph assembler wires into. They are
# declared here as optional parameters so the cluster builder can produce edges
# to external targets when assembling the full graph.
# ---------------------------------------------------------------------------

#: Default external node IDs — must be supplied by the graph assembler or left as
#: placeholder strings that the graph assembler replaces.
ROUTING_ENTRY_NODE_ID = "routing_entry"
BH_INTENT_CLASSIFY_NODE_ID = "bh_intent_classify"
AH_INTENT_NODE_ID = "ah_intent"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_authentication_cluster(
    *,
    routing_entry_node_id: str = ROUTING_ENTRY_NODE_ID,
    bh_intent_classify_node_id: str = BH_INTENT_CLASSIFY_NODE_ID,
    ah_intent_node_id: str = AH_INTENT_NODE_ID,
) -> AuthenticationClusterResult:
    """Build the Authentication phase node cluster (Req 9.1).

    Returns the nodes and edges for the Authentication flow:
    phone → read-back → patient_lookup → DOB → identity → Routing.

    Edges include:
    - Intra-flow edges (phone→readback, readback→lookup, etc.)
    - ANI-reuse conditional edge: readback → DOB directly when
      greeting_ani_lookup_done=true (Req 9.6)
    - No-record edge: lookup → phone (Req 9.10)
    - 3-attempt route edge: phone → routing (Req 9.12)
    - Auth fail/refusal → routing (Req 9.7)
    - Changed-request edges → BH/AH (Req 9.8)
    - Identity → Routing (silent, Req 3.3)

    Silent entry edges (from BH/AH into this cluster) are left for the graph
    assembler to add, since the source nodes live in other clusters. The
    ``entry_node_id`` exposes where those edges should target.

    Args:
        routing_entry_node_id: The Routing cluster entry node ID for exit edges.
        bh_intent_classify_node_id: The Business Hours intent classify node ID
            for changed-request edges (after_hours=false).
        ah_intent_node_id: The After Hours intent node ID for changed-request
            edges (after_hours=true).

    Returns:
        An :class:`AuthenticationClusterResult` with nodes, edges, and exposed IDs.
    """
    # -- Positions (layout for visual builder; no runtime effect) ----------------
    x_base, y_base = 800.0, 400.0
    y_step = 180.0

    # -- Nodes -------------------------------------------------------------------
    nodes: list[RFNodeDTO] = []

    # 1. Phone Number node
    nodes.append(
        RFNodeDTO(
            id=AUTH_PHONE_NODE_ID,
            type="agentNode",
            position=Position(x=x_base, y=y_base),
            data=AgentNodeData(
                name="Auth: Phone Number",
                prompt=_PHONE_PROMPT,
                allow_interrupt=True,
                add_global_prompt=True,
                extraction_enabled=True,
                extraction_prompt="Extract the phone number and track attempts.",
                extraction_variables=_PHONE_EXTRACTIONS,
                tool_uuids=None,
            ),
        )
    )

    # 2. Read-back node
    nodes.append(
        RFNodeDTO(
            id=AUTH_READBACK_NODE_ID,
            type="agentNode",
            position=Position(x=x_base, y=y_base + y_step),
            data=AgentNodeData(
                name="Auth: Phone Read-back",
                prompt=_READBACK_PROMPT,
                allow_interrupt=True,
                add_global_prompt=True,
                extraction_enabled=True,
                extraction_prompt="Extract whether the caller confirmed the phone number.",
                extraction_variables=_READBACK_EXTRACTIONS,
                tool_uuids=None,
            ),
        )
    )

    # 3. Patient Lookup node (silent)
    nodes.append(
        RFNodeDTO(
            id=AUTH_PATIENT_LOOKUP_NODE_ID,
            type="agentNode",
            position=Position(x=x_base, y=y_base + 2 * y_step),
            data=AgentNodeData(
                name="Auth: Patient Lookup",
                prompt=_PATIENT_LOOKUP_PROMPT,
                allow_interrupt=False,
                add_global_prompt=False,
                extraction_enabled=True,
                extraction_prompt="Extract patient_id and whether a record was found.",
                extraction_variables=_PATIENT_LOOKUP_EXTRACTIONS,
                tool_uuids=_patient_lookup_tool_uuids(),
            ),
        )
    )

    # 4. DOB node
    nodes.append(
        RFNodeDTO(
            id=AUTH_DOB_NODE_ID,
            type="agentNode",
            position=Position(x=x_base, y=y_base + 3 * y_step),
            data=AgentNodeData(
                name="Auth: Date of Birth",
                prompt=_DOB_PROMPT,
                allow_interrupt=True,
                add_global_prompt=True,
                extraction_enabled=True,
                extraction_prompt="Extract the date of birth the caller provided.",
                extraction_variables=_DOB_EXTRACTIONS,
                tool_uuids=_dob_tool_uuids(),
            ),
        )
    )

    # 5. Identity Verify node (silent)
    nodes.append(
        RFNodeDTO(
            id=AUTH_IDENTITY_NODE_ID,
            type="agentNode",
            position=Position(x=x_base, y=y_base + 4 * y_step),
            data=AgentNodeData(
                name="Auth: Identity Verify",
                prompt=_IDENTITY_PROMPT,
                allow_interrupt=False,
                add_global_prompt=False,
                extraction_enabled=True,
                extraction_prompt="Extract the patient_verified result.",
                extraction_variables=_IDENTITY_EXTRACTIONS,
                tool_uuids=_identity_tool_uuids(),
            ),
        )
    )

    # -- Edges -------------------------------------------------------------------
    edges: list[RFEdgeDTO] = []

    # Phone Number → Read-back (phone number provided)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_PHONE_TO_READBACK,
            source=AUTH_PHONE_NODE_ID,
            target=AUTH_READBACK_NODE_ID,
            data=EdgeDataDTO(
                label="Phone number provided",
                condition="The caller provided a phone number.",
                transition_speech=None,
            ),
        )
    )

    # Read-back → Patient Lookup (phone confirmed, ANI lookup NOT done)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_READBACK_TO_LOOKUP,
            source=AUTH_READBACK_NODE_ID,
            target=AUTH_PATIENT_LOOKUP_NODE_ID,
            data=EdgeDataDTO(
                label="Phone confirmed, perform lookup",
                condition=(
                    "The caller confirmed the phone number is correct AND "
                    "greeting_ani_lookup_done is false (ANI lookup not already done)."
                ),
                transition_speech="",
            ),
        )
    )

    # Read-back → DOB (phone confirmed, ANI lookup already done — skip lookup, Req 9.6)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_READBACK_TO_DOB_ANI,
            source=AUTH_READBACK_NODE_ID,
            target=AUTH_DOB_NODE_ID,
            data=EdgeDataDTO(
                label="Phone confirmed, ANI reuse (skip lookup)",
                condition=(
                    "The caller confirmed the phone number is correct AND "
                    "greeting_ani_lookup_done is true (reuse Greeting ANI result, "
                    "Req 9.6)."
                ),
                transition_speech="",
            ),
        )
    )

    # Read-back → Phone Number (phone incorrect, re-ask)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_READBACK_TO_PHONE_INCORRECT,
            source=AUTH_READBACK_NODE_ID,
            target=AUTH_PHONE_NODE_ID,
            data=EdgeDataDTO(
                label="Phone number incorrect",
                condition="The caller said the phone number is incorrect.",
                transition_speech=None,
            ),
        )
    )

    # Patient Lookup → DOB (record found)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_LOOKUP_TO_DOB,
            source=AUTH_PATIENT_LOOKUP_NODE_ID,
            target=AUTH_DOB_NODE_ID,
            data=EdgeDataDTO(
                label="Patient record found",
                condition="A patient record was found for the phone number.",
                transition_speech="",
            ),
        )
    )

    # Patient Lookup → Phone Number (no record found — speak AUTH_NO_RECORD, Req 9.10)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_LOOKUP_TO_PHONE_NO_RECORD,
            source=AUTH_PATIENT_LOOKUP_NODE_ID,
            target=AUTH_PHONE_NODE_ID,
            data=EdgeDataDTO(
                label="No record found",
                condition=(
                    "No patient record was found for the phone number AND "
                    "phone attempts have not been exhausted."
                ),
                transition_speech=scripts.AUTH_NO_RECORD,
            ),
        )
    )

    # DOB → Identity Verify (DOB provided)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_DOB_TO_IDENTITY,
            source=AUTH_DOB_NODE_ID,
            target=AUTH_IDENTITY_NODE_ID,
            data=EdgeDataDTO(
                label="DOB provided",
                condition="The caller provided their date of birth.",
                transition_speech="",
            ),
        )
    )

    # Identity Verify → Routing (verified/fail/na — silent, Req 3.3)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_IDENTITY_TO_ROUTING,
            source=AUTH_IDENTITY_NODE_ID,
            target=routing_entry_node_id,
            data=EdgeDataDTO(
                label="Auth complete → Routing",
                condition=(
                    "Identity verification is complete (patient_verified is "
                    "Success, Fail, or N/A)."
                ),
                transition_speech="",
            ),
        )
    )

    # Auth fail/refusal → Routing (any auth node, Req 9.7)
    # Modeled as an edge from each node that can detect refusal → Routing
    # with AUTH_FAIL_ROUTE as transition_speech.
    _auth_fail_speech = auth.auth_fail_route_line()
    for node_id in AUTH_NODE_IDS:
        edges.append(
            RFEdgeDTO(
                id=f"auth_e_fail_{node_id}",
                source=node_id,
                target=routing_entry_node_id,
                data=EdgeDataDTO(
                    label="Auth refusal/fail → Route",
                    condition=(
                        "The caller refuses to authenticate, or explicitly asks "
                        "to be connected without authenticating."
                    ),
                    transition_speech=_auth_fail_speech,
                ),
            )
        )

    # Changed-request → Business Hours Intent Classify (after_hours=false, Req 9.8)
    _changed_request_speech = scripts.AUTH_CHANGED_REQUEST
    for node_id in AUTH_NODE_IDS:
        edges.append(
            RFEdgeDTO(
                id=f"auth_e_changed_bh_{node_id}",
                source=node_id,
                target=bh_intent_classify_node_id,
                data=EdgeDataDTO(
                    label="Changed request → Business Hours",
                    condition=(
                        "The caller changes their request AND it is currently "
                        "business hours (after_hours is false)."
                    ),
                    transition_speech=_changed_request_speech,
                ),
            )
        )

    # Changed-request → After Hours Intent (after_hours=true, Req 9.8)
    for node_id in AUTH_NODE_IDS:
        edges.append(
            RFEdgeDTO(
                id=f"auth_e_changed_ah_{node_id}",
                source=node_id,
                target=ah_intent_node_id,
                data=EdgeDataDTO(
                    label="Changed request → After Hours",
                    condition=(
                        "The caller changes their request AND it is currently "
                        "after hours (after_hours is true)."
                    ),
                    transition_speech=_changed_request_speech,
                ),
            )
        )

    # 3-attempt route edge: Phone Number → Routing (Req 9.12)
    edges.append(
        RFEdgeDTO(
            id=_EDGE_PHONE_3_ATTEMPTS_ROUTE,
            source=AUTH_PHONE_NODE_ID,
            target=routing_entry_node_id,
            data=EdgeDataDTO(
                label="3 phone attempts exhausted → Route",
                condition=(
                    f"The caller has used all {auth.AUTH_MAX_PHONE_ATTEMPTS} "
                    "phone number attempts without a matching record."
                ),
                transition_speech="",
            ),
        )
    )

    return AuthenticationClusterResult(
        nodes=nodes,
        edges=edges,
        entry_node_id=AUTH_PHONE_NODE_ID,
        exit_node_id=AUTH_IDENTITY_NODE_ID,
        all_node_ids=AUTH_NODE_IDS,
    )


__all__ = [
    "AUTH_PHONE_NODE_ID",
    "AUTH_READBACK_NODE_ID",
    "AUTH_PATIENT_LOOKUP_NODE_ID",
    "AUTH_DOB_NODE_ID",
    "AUTH_IDENTITY_NODE_ID",
    "AUTH_NODE_IDS",
    "ROUTING_ENTRY_NODE_ID",
    "BH_INTENT_CLASSIFY_NODE_ID",
    "AH_INTENT_NODE_ID",
    "AuthenticationClusterResult",
    "build_authentication_cluster",
]
