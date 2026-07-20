"""Scheduling-phase node cluster for the SpinSci switchboard workflow graph.

Builds the Scheduling downstream segment as a set of workflow engine nodes and
edges. The Scheduling segment is entered from the Routing cluster's Resolve Route
node after the scheduling_handoff tool passes the full Call State Ledger (Req 12.8).

Nodes:
  1. **Scheduling Init** (``agentNode``): Receives the full ledger via
     ``scheduling_handoff``. For ``create`` actions: determines ``visit_type``
     (sick/wellness) by asking the reason question (SCHED_INIT_VISIT_REASON) when
     unknown, or the disambiguation question
     (SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION) when both wellness and symptom
     signals are present. For manage actions (cancel/reschedule/list/confirm):
     skips sick/wellness entirely and passes the action+context straight to the
     Engine (Req 13.7). New-patient ``create`` routes to the general intake path
     (Req 12.7).
  2. **Scheduling Engine** (``agentNode``): Handles appointment actions against the
     mock backend. For ``create``/``reschedule``: returns bookable slots; offers
     alternatives if preferred provider unavailable (Req 14.3, 14.4). For
     ``cancel``: completes cancellation (Req 14.5). For ``list``: retrieves
     upcoming appointments (Req 14.7). For ``confirm``: retrieves details (Req
     14.8). Urgency escalation for urgent symptoms during sick-visit (Req 14.9).
     Specialty-not-activated fallback: inform caller and offer alternate path (Req
     14.10).
  3. **Scheduling New Patient Intake** (``endCall``): Terminal node for new-patient
     create actions that route to the general intake path (Req 12.7). Speaks the
     E_SCHEDULING_NEW transfer line.
  4. **Scheduling Complete** (``endCall``): Terminal node when the engine action is
     done (booking/cancellation/list/confirm complete).

Edges:
  - Scheduling Init → Scheduling Engine (visit_type resolved for create, or manage
    action ready)
  - Scheduling Init → Scheduling New Patient Intake (new-patient create, Req 12.7)
  - Scheduling Engine → Scheduling Complete (action done)

Design references:
- ``design.md`` → "Scheduling experience (Req 12, 13, 14)"
- ``requirements.md`` → Requirements 12.6, 12.7, 12.8, 13.1–13.7, 14.1–14.10

Requirements: 12.6, 12.7, 12.8, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7,
14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from api.services.switchboard.scripts import (
    E_SCHEDULING_NEW,
    SCHED_INIT_VISIT_REASON,
    SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION,
)
from api.services.workflow.dto import (
    AgentNodeData,
    EdgeDataDTO,
    EndCallNodeData,
    Position,
    RFEdgeDTO,
    RFNodeDTO,
)


def _node_id(label: str) -> str:
    """Generate a deterministic, human-identifiable node ID for the scheduling cluster."""
    return f"scheduling_{label}"


def _edge_id(source_label: str, target_label: str) -> str:
    """Generate a deterministic edge ID from source/target labels."""
    return f"scheduling_edge_{source_label}_to_{target_label}"


# ---------------------------------------------------------------------------
# Tool UUIDs for the scheduling cluster
# ---------------------------------------------------------------------------
# In the PoC the tool UUIDs are derived from the tool names (since real ToolModel
# UUIDs don't exist until the graph is assembled with a live DB). The graph
# assembler (task 18) replaces these with actual UUIDs at assembly time. For the
# cluster builder we use the tool function_name as the placeholder UUID so scoping
# can be validated structurally.


def _scheduling_init_tool_uuids() -> List[str]:
    """Tool UUIDs for the Scheduling Init node (scheduling_handoff only)."""
    return ["scheduling_handoff"]


def _scheduling_engine_tool_uuids() -> List[str]:
    """Tool UUIDs for the Scheduling Engine node (scheduling_engine only)."""
    return ["scheduling_engine"]


# ---------------------------------------------------------------------------
# Node prompts
# ---------------------------------------------------------------------------

SCHEDULING_INIT_PROMPT: str = (
    "You are Scheduling Init. The full Call State Ledger has been passed to you "
    "via the scheduling_handoff tool (Req 12.8).\n\n"
    "For a CREATE action:\n"
    "- If the patient is NEW (patient_status == 'new'), route to the general "
    "intake path (new-patient create, Req 12.7). Do NOT proceed to the Engine.\n"
    "- If the reason for the visit is UNKNOWN (no wellness or symptom signal), "
    f"ask: \"{SCHED_INIT_VISIT_REASON}\" (Req 13.3)\n"
    "- If BOTH a wellness keyword AND a specific symptom are present, ask: "
    f"\"{SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION}\" (Req 13.4)\n"
    "- If the reason is clear (single signal), resolve visit_type directly: "
    "wellness signal → wellness, symptom signal → sick (Req 13.2, 13.6).\n"
    "- Once visit_type is resolved, pass to the Scheduling Engine.\n\n"
    "For MANAGE actions (cancel/reschedule/list/confirm):\n"
    "- Skip sick/wellness entirely (Req 13.7). Pass the action and ledger context "
    "straight to the Scheduling Engine."
)

SCHEDULING_ENGINE_PROMPT: str = (
    "You are the Scheduling Engine. Handle the appointment action using the "
    "scheduling_engine tool.\n\n"
    "For CREATE or RESCHEDULE:\n"
    "- Determine provider availability and return bookable slots.\n"
    "- If the preferred provider is unavailable, offer alternatives without "
    "re-asking already collected facts (Req 14.3, 14.4).\n\n"
    "For CANCEL:\n"
    "- Locate the target appointment and complete the cancellation (Req 14.5).\n\n"
    "For LIST:\n"
    "- Retrieve upcoming appointments for read-back (Req 14.7).\n\n"
    "For CONFIRM:\n"
    "- Retrieve appointment details for read-back (Req 14.8).\n\n"
    "Urgency escalation: If urgent symptoms are detected during a sick-visit "
    "create, escalate immediately (Req 14.9).\n\n"
    "Specialty-not-activated fallback: If the specialty is not activated in the "
    "scheduling system, inform the caller and offer an alternate path (Req 14.10).\n\n"
    "[DEFERRED — SpinSci contract] Running against mock backend."
)

SCHEDULING_NEW_PATIENT_INTAKE_PROMPT: str = (
    f"Speak ONLY: \"{E_SCHEDULING_NEW}\" "
    "This is a new-patient create — route to general intake (Req 12.7)."
)

SCHEDULING_COMPLETE_PROMPT: str = (
    "The scheduling action is complete. Thank the caller and confirm next steps."
)


# ---------------------------------------------------------------------------
# Cluster result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchedulingClusterResult:
    """The output of :func:`build_scheduling_cluster`.

    Attributes:
        nodes: The RF node DTOs for the Scheduling cluster.
        edges: The RF edge DTOs connecting scheduling nodes internally.
        scheduling_init_id: The entry node ID for the cluster (Scheduling Init).
            External edges from the Routing cluster target this node.
        scheduling_engine_id: The Scheduling Engine node ID.
        scheduling_new_patient_intake_id: The new-patient intake terminal node ID.
        scheduling_complete_id: The terminal completion node ID.
    """

    nodes: List[RFNodeDTO]
    edges: List[RFEdgeDTO]
    scheduling_init_id: str
    scheduling_engine_id: str
    scheduling_new_patient_intake_id: str
    scheduling_complete_id: str


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

# Canvas layout positions (purely cosmetic, no runtime effect).
_POS_INIT = Position(x=1200.0, y=400.0)
_POS_ENGINE = Position(x=1400.0, y=550.0)
_POS_NEW_PATIENT = Position(x=1000.0, y=550.0)
_POS_COMPLETE = Position(x=1400.0, y=700.0)


def build_scheduling_cluster() -> SchedulingClusterResult:
    """Build the Scheduling-phase node cluster for the switchboard workflow graph.

    Returns:
        A :class:`SchedulingClusterResult` containing all nodes, internal edges,
        and exposed node IDs for wiring into the assembled graph.
    """
    # -- Node IDs ---------------------------------------------------------------
    scheduling_init_id = _node_id("init")
    scheduling_engine_id = _node_id("engine")
    scheduling_new_patient_intake_id = _node_id("new_patient_intake")
    scheduling_complete_id = _node_id("complete")

    # -- Nodes ------------------------------------------------------------------

    scheduling_init_node = RFNodeDTO(
        id=scheduling_init_id,
        type="agentNode",
        position=_POS_INIT,
        data=AgentNodeData(
            name="Scheduling Init",
            prompt=SCHEDULING_INIT_PROMPT,
            allow_interrupt=False,
            add_global_prompt=False,
            tool_uuids=_scheduling_init_tool_uuids(),
        ),
    )

    scheduling_engine_node = RFNodeDTO(
        id=scheduling_engine_id,
        type="agentNode",
        position=_POS_ENGINE,
        data=AgentNodeData(
            name="Scheduling Engine",
            prompt=SCHEDULING_ENGINE_PROMPT,
            allow_interrupt=False,
            add_global_prompt=False,
            tool_uuids=_scheduling_engine_tool_uuids(),
        ),
    )

    scheduling_new_patient_intake_node = RFNodeDTO(
        id=scheduling_new_patient_intake_id,
        type="endCall",
        position=_POS_NEW_PATIENT,
        data=EndCallNodeData(
            name="Scheduling New Patient Intake",
            prompt=SCHEDULING_NEW_PATIENT_INTAKE_PROMPT,
            add_global_prompt=False,
        ),
    )

    scheduling_complete_node = RFNodeDTO(
        id=scheduling_complete_id,
        type="endCall",
        position=_POS_COMPLETE,
        data=EndCallNodeData(
            name="Scheduling Complete",
            prompt=SCHEDULING_COMPLETE_PROMPT,
            add_global_prompt=False,
        ),
    )

    nodes: List[RFNodeDTO] = [
        scheduling_init_node,
        scheduling_engine_node,
        scheduling_new_patient_intake_node,
        scheduling_complete_node,
    ]

    # -- Internal Edges ---------------------------------------------------------

    # Scheduling Init → Scheduling Engine (visit_type resolved for create, or
    # manage action ready to process)
    edge_init_to_engine = RFEdgeDTO(
        id=_edge_id("init", "engine"),
        source=scheduling_init_id,
        target=scheduling_engine_id,
        data=EdgeDataDTO(
            label="To Engine",
            condition=(
                "Visit type is resolved for a create action (existing patient), "
                "or a manage action (cancel/reschedule/list/confirm) is ready."
            ),
            transition_speech=None,
        ),
    )

    # Scheduling Init → New Patient Intake (new-patient create, Req 12.7)
    edge_init_to_new_patient = RFEdgeDTO(
        id=_edge_id("init", "new_patient_intake"),
        source=scheduling_init_id,
        target=scheduling_new_patient_intake_id,
        data=EdgeDataDTO(
            label="New Patient Create",
            condition=(
                "The appointment action is create and the patient is new "
                "(patient_status == 'new'). Route to general intake path (Req 12.7)."
            ),
            transition_speech=None,
        ),
    )

    # Scheduling Engine → Scheduling Complete (action done)
    edge_engine_to_complete = RFEdgeDTO(
        id=_edge_id("engine", "complete"),
        source=scheduling_engine_id,
        target=scheduling_complete_id,
        data=EdgeDataDTO(
            label="Action Complete",
            condition=(
                "The scheduling action is complete: booking confirmed, "
                "cancellation done, list read back, or confirmation provided."
            ),
            transition_speech=None,
        ),
    )

    edges: List[RFEdgeDTO] = [
        edge_init_to_engine,
        edge_init_to_new_patient,
        edge_engine_to_complete,
    ]

    return SchedulingClusterResult(
        nodes=nodes,
        edges=edges,
        scheduling_init_id=scheduling_init_id,
        scheduling_engine_id=scheduling_engine_id,
        scheduling_new_patient_intake_id=scheduling_new_patient_intake_id,
        scheduling_complete_id=scheduling_complete_id,
    )


__all__ = [
    "SCHEDULING_INIT_PROMPT",
    "SCHEDULING_ENGINE_PROMPT",
    "SCHEDULING_NEW_PATIENT_INTAKE_PROMPT",
    "SCHEDULING_COMPLETE_PROMPT",
    "SchedulingClusterResult",
    "build_scheduling_cluster",
]
