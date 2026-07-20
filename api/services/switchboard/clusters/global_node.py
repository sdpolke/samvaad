"""Global node builder for the SpinSci switchboard workflow graph.

Builds the single ``globalNode`` that carries the never-narrate-internals persona
and TTS rules for the entire switchboard conversation. The global node is a
floating node (no edges, no incoming/outgoing connections) whose prompt is
prepended to every other prompted node that has ``add_global_prompt=True``.

The persona enforces:
  - Never speak system names, JSON objects, UUIDs, or Call State Ledger field
    names to the caller (Req 4.1, AC-03).
  - Never repeat medication names — refer only to "your prescription" or
    "your medication" (Req 4.2).
  - Never name a specific clinical team that has not been confirmed by the
    caller or routing (Req 4.3).
  - Use short, concise sentences for TTS clarity (Req 5.1).
  - Use periods to introduce pauses between digit groups, e.g. phone numbers
    as "555.123.4567" (Req 5.2).
  - Always sound natural and conversational — no robotic phrasing.
  - Never say internal module names, variable names, or technical identifiers.

Nodes that must emit an exact verbatim line set ``add_global_prompt=False`` so
the persona cannot perturb their wording, protecting Appendix C/E fidelity
(Req 18). Those nodes include:
  - Routing: Transfer, Goodbye, Transfer Error
  - After Hours: Billing Closed, MyChart Closed
  - Business Hours: Search Trouble
  - Authentication: Patient Lookup, Identity Verify (silent nodes)

Design references:
- ``design.md`` → "Global node (Req 4, Req 5)"
- ``requirements.md`` → Requirements 4.1, 4.2, 4.3, 5.1, 5.2

Requirements: 4.1, 4.2, 4.3, 5.1, 5.2.
"""

from __future__ import annotations

from typing import Tuple

from api.services.workflow.dto import (
    GlobalNodeData,
    Position,
    RFNodeDTO,
)

# ---------------------------------------------------------------------------
# Node ID
# ---------------------------------------------------------------------------

GLOBAL_NODE_ID: str = "switchboard_global"

# ---------------------------------------------------------------------------
# Global persona prompt — the never-narrate-internals rules + TTS directives
# ---------------------------------------------------------------------------

GLOBAL_PERSONA_PROMPT: str = (
    "You are a friendly, professional medical office virtual assistant. "
    "Follow these rules strictly on every turn:\n\n"
    "1. NEVER speak system names, JSON objects, UUIDs, or internal Call State "
    "Ledger field names to the caller. These are internal implementation "
    "details and must never be revealed in speech.\n\n"
    "2. NEVER repeat medication names. If a medication is in context, refer to "
    'it only as "your prescription" or "your medication." Do not say the drug '
    "name aloud.\n\n"
    "3. NEVER name a specific clinical team or department that has not been "
    "confirmed by the caller or by the routing system. Do not guess or assume "
    "a team name.\n\n"
    "4. Use short, concise sentences. Each sentence should be easy to follow "
    "when spoken aloud by a text-to-speech engine. Avoid long compound "
    "sentences.\n\n"
    "5. When speaking digit groups (phone numbers, dates, confirmation codes), "
    "use periods between groups to introduce natural pauses. For example, "
    'speak a phone number as "555.123.4567" not "5551234567".\n\n'
    "6. Always sound natural and conversational. Avoid robotic phrasing, "
    "overly formal language, or scripted-sounding cadences.\n\n"
    "7. Never say internal module names, variable names, technical identifiers, "
    "or workflow node names. The caller must never hear anything that sounds "
    "like a developer artifact."
)


# ---------------------------------------------------------------------------
# Canvas position (purely cosmetic)
# ---------------------------------------------------------------------------

_POS_GLOBAL = Position(x=50.0, y=50.0)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_global_node() -> Tuple[RFNodeDTO, str]:
    """Build the single globalNode for the switchboard workflow graph.

    Returns:
        A tuple of (RFNodeDTO, node_id) where the node is type ``globalNode``
        carrying the persona and TTS rules prompt.
    """
    node = RFNodeDTO(
        id=GLOBAL_NODE_ID,
        type="globalNode",
        position=_POS_GLOBAL,
        data=GlobalNodeData(
            name="SpinSci Persona",
            prompt=GLOBAL_PERSONA_PROMPT,
        ),
    )
    return node, GLOBAL_NODE_ID


__all__ = [
    "GLOBAL_NODE_ID",
    "GLOBAL_PERSONA_PROMPT",
    "build_global_node",
]
