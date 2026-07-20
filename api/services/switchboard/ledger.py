"""Call State Ledger for the SpinSci switchboard (Appendix D, Requirement 15).

The Call State Ledger is the single shared session record for a call. There is
exactly one ledger per call (Req 2.1) and it is threaded across every phase
transition, mapping directly onto the workflow engine's extraction/gathered
context variables (Req 1.6). Each field here corresponds to a workflow context
variable whose type is one of the engine's :class:`VariableType` values
(``string`` / ``number`` / ``boolean``).

Design references:
- ``design.md`` → Data Models → "Call State Ledger → workflow context variables"
- ``requirements.md`` → Requirement 15 (15.1 field set, 15.2 specialty
  normalization, 15.3 numeric-only ``selected_id``)

This module holds only the ledger model, its field→``VariableType`` registry,
and the ``specialty`` normalization seam. Schedule/session configuration lives
in ``config.py`` and the after-hours evaluator in ``schedule.py``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.services.workflow.dto import VariableType


def normalize_specialty(value: Optional[str]) -> Optional[str]:
    """Normalization seam for the ``specialty`` ledger field (Req 15.2).

    The switchboard normalizes ``specialty`` when a specialty is required so that
    caller phrasing maps onto SpinSci's directory/scheduling catalog. For now this
    is a conservative pass-through that only trims surrounding whitespace and
    collapses blank strings to ``None``; later tasks extend it with the real
    specialty synonym/canonicalization mapping without changing this signature.

    Args:
        value: The raw specialty string as captured from the caller, or ``None``.

    Returns:
        The normalized specialty string, or ``None`` when no meaningful value was
        provided.
    """
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class CallStateLedger(BaseModel):
    """The single per-call state record (Appendix D / Requirement 15.1).

    All fields are optional and default to empty/false-y values because a fresh
    ledger starts mostly empty and is populated as the conversation progresses.
    No field is ever dropped on a phase transition (Req 2.2); collection nodes
    guard on these fields so a populated value is never re-asked (Req 15.4).

    Field types map onto the workflow engine's :class:`VariableType`; see
    :data:`LEDGER_VARIABLE_TYPES` for the field→type registry used by the graph
    builder to emit ``ExtractionVariableDTO`` definitions.
    """

    # ── string fields ────────────────────────────────────────────────────────
    caller_name: Optional[str] = Field(
        default=None, description="Caller's name as provided during Greeting."
    )
    intent: Optional[str] = Field(
        default=None,
        description=(
            "Internal intent classification label. Distinct from the transient "
            "routing-intent string produced during Routing; never overwritten by it."
        ),
    )
    patient_status: Optional[str] = Field(
        default=None, description="One of null / new / existing."
    )
    provider_name: Optional[str] = Field(
        default=None, description="Requested provider name."
    )
    specialty: Optional[str] = Field(
        default=None,
        description="Requested specialty; normalized when required (Req 15.2).",
    )
    scan_type: Optional[str] = Field(
        default=None,
        description="MRI/CT · Mammo/Dexa · PET/Nuclear · US/Fluoro.",
    )
    location: Optional[str] = Field(
        default=None, description="City / address / site."
    )
    department_name: Optional[str] = Field(
        default=None, description="Department name resolved by directory lookup."
    )
    department_id: Optional[str] = Field(
        default=None, description="Department identifier resolved by directory lookup."
    )
    patient_verified: Optional[str] = Field(
        default=None, description="One of null / Success / Fail / N/A."
    )
    appointment_action: Optional[str] = Field(
        default=None,
        description="One of create / cancel / reschedule / list / confirm.",
    )
    existing_appointment_date: Optional[str] = Field(
        default=None,
        description="Optional; used for cancel / reschedule.",
    )
    visit_type: Optional[str] = Field(
        default=None,
        description="sick / wellness. Set in Scheduling Init only (create only).",
    )
    visit_reason: Optional[str] = Field(
        default=None, description="Reason for visit; derives visit_type."
    )
    preferred_provider_id: Optional[str] = Field(
        default=None, description="Caller/Engine preferred provider identifier."
    )
    preferred_date: Optional[str] = Field(
        default=None, description="Caller preferred date."
    )
    patient_id: Optional[str] = Field(
        default=None, description="Patient identifier resolved by patient lookup."
    )
    ah_intent_selection: Optional[str] = Field(
        default=None,
        description=(
            "After-hours selection: 'Hospital or Physician' · "
            "'Afterhours Answering Service'."
        ),
    )

    # ── number fields ────────────────────────────────────────────────────────
    selected_id: Optional[int] = Field(
        default=None,
        description="Numeric record identifier only (Req 15.3).",
    )
    greeting_ani_match_count: Optional[int] = Field(
        default=None,
        description="ANI match count from turn-1 lookup (personalized ⇔ == 1).",
    )

    # ── boolean fields ───────────────────────────────────────────────────────
    caller_is_provider: Optional[bool] = Field(
        default=None,
        description="Set during After Hours paging; unknown (None) until then.",
    )
    after_hours: bool = Field(
        default=False,
        description="Set at call start from the America/Chicago schedule.",
    )
    greeting_ani_lookup_done: bool = Field(
        default=False,
        description="Turn-1 ANI lookup completion flag; starts false.",
    )

    @field_validator("selected_id", mode="before")
    @classmethod
    def _validate_selected_id_numeric(cls, value: object) -> Optional[int]:
        """Enforce that ``selected_id`` is a numeric record identifier (Req 15.3).

        Accepts ``None``, integers, and integer-valued strings/floats; rejects any
        non-numeric or fractional value so a non-numeric directory id can never be
        stored on the ledger.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            # bool is an int subclass in Python; reject it explicitly.
            raise ValueError("selected_id must be a numeric record identifier")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            raise ValueError("selected_id must be a whole numeric record identifier")
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit() or (
                stripped.startswith("-") and stripped[1:].isdigit()
            ):
                return int(stripped)
            logger.debug("Rejected non-numeric selected_id: {!r}", value)
            raise ValueError("selected_id must be a numeric record identifier")
        raise ValueError("selected_id must be a numeric record identifier")

    @field_validator("specialty", mode="before")
    @classmethod
    def _normalize_specialty(cls, value: Optional[str]) -> Optional[str]:
        """Apply the :func:`normalize_specialty` seam on assignment (Req 15.2)."""
        return normalize_specialty(value)


# Registry mapping each ledger field name to its workflow :class:`VariableType`.
# The graph builder consumes this to emit ``ExtractionVariableDTO`` definitions
# (Req 1.6). All 23 Appendix D fields are present.
LEDGER_VARIABLE_TYPES: dict[str, VariableType] = {
    # string fields
    "caller_name": VariableType.string,
    "intent": VariableType.string,
    "patient_status": VariableType.string,
    "provider_name": VariableType.string,
    "specialty": VariableType.string,
    "scan_type": VariableType.string,
    "location": VariableType.string,
    "department_name": VariableType.string,
    "department_id": VariableType.string,
    "patient_verified": VariableType.string,
    "appointment_action": VariableType.string,
    "existing_appointment_date": VariableType.string,
    "visit_type": VariableType.string,
    "visit_reason": VariableType.string,
    "preferred_provider_id": VariableType.string,
    "preferred_date": VariableType.string,
    "patient_id": VariableType.string,
    "ah_intent_selection": VariableType.string,
    # number fields
    "selected_id": VariableType.number,
    "greeting_ani_match_count": VariableType.number,
    # boolean fields
    "caller_is_provider": VariableType.boolean,
    "after_hours": VariableType.boolean,
    "greeting_ani_lookup_done": VariableType.boolean,
}


#: The set of valid ledger field names (all 23 Appendix D fields). Derived from
#: :data:`LEDGER_VARIABLE_TYPES` so the two can never drift apart.
LEDGER_FIELD_NAMES: frozenset[str] = frozenset(LEDGER_VARIABLE_TYPES)


def reduce_ledger(
    current: CallStateLedger, updates: Mapping[str, Any]
) -> CallStateLedger:
    """Merge ``updates`` onto the full prior ledger and return a new ledger.

    This is the switchboard's pure state reducer (Req 2.1, 2.2). On every phase
    transition the *entire* ledger is carried forward: the returned ledger holds
    every field the ``current`` ledger held, with only the fields explicitly
    present in ``updates`` changed. No field is ever dropped or reset by a
    transition, and there is always exactly one ledger for the call.

    The function is side-effect-free: ``current`` is never mutated and a brand
    new :class:`CallStateLedger` is returned. Field validators (numeric
    ``selected_id``, ``specialty`` normalization) run on the merged result so the
    reduced ledger is always valid.

    Args:
        current: The ledger held by the phase being left. Not mutated.
        updates: The fields the entered phase sets/changes. Keys must be valid
            ledger field names (see :data:`LEDGER_FIELD_NAMES`); a value of
            ``None`` explicitly clears that field, while any field absent from
            ``updates`` is carried forward unchanged.

    Returns:
        A new :class:`CallStateLedger` merging ``updates`` onto ``current``.

    Raises:
        KeyError: If ``updates`` contains a key that is not a ledger field.
    """
    unknown = set(updates) - LEDGER_FIELD_NAMES
    if unknown:
        raise KeyError(f"Unknown ledger field(s) in update: {sorted(unknown)}")

    merged: dict[str, Any] = current.model_dump()
    merged.update(updates)
    return CallStateLedger.model_validate(merged)


def _is_populated(value: Any) -> bool:
    """Return whether a ledger value counts as a meaningful, populated value.

    ``None`` is never populated. A string is populated only when it holds
    non-whitespace text (so ``""``/``"   "`` count as unset). Numbers and
    booleans are populated whenever they are present — ``0`` and ``False`` are
    meaningful values, not "empty" — matching the ledger's field semantics.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def should_ask(field: str, ledger: CallStateLedger) -> bool:
    """Return whether a collection node should still ask the caller for ``field``.

    Implements the never-re-ask predicate (Req 2.3, 15.4): the switchboard asks
    for a field only while it is empty/unset. Because the full ledger travels on
    every transition (:func:`reduce_ledger`), a downstream node always sees prior
    values and skips a question once the field is populated.

    Args:
        field: A ledger field name; must be one of the 23 Appendix D fields
            (see :data:`LEDGER_FIELD_NAMES`).
        ledger: The current call-state ledger.

    Returns:
        ``False`` when the target field already holds a meaningful value,
        ``True`` when it is empty/unset and must still be collected.

    Raises:
        KeyError: If ``field`` is not a valid ledger field name.
    """
    if field not in LEDGER_FIELD_NAMES:
        raise KeyError(f"Unknown ledger field: {field!r}")
    return not _is_populated(getattr(ledger, field))


class RoutingResolution(BaseModel):
    """Transient result of routing resolution, separate from ``ledger.intent``.

    The routing intent is a transient value produced by
    ``routing_intent_resolution`` and consumed by ``route_metadata_resolution``
    (Req 2.4, REQ-LEDGER-03). It is deliberately **not** written back onto the
    ledger's ``intent`` classification label. This container keeps the two
    distinct: it snapshots the ledger's ``intent`` (``ledger_intent``) alongside
    the transient ``routing_intent`` without ever mutating the ledger.

    The model is frozen so a resolved routing intent cannot be silently altered.
    """

    model_config = ConfigDict(frozen=True)

    ledger_intent: Optional[str] = Field(
        default=None,
        description="Snapshot of the ledger's internal `intent` classification label.",
    )
    routing_intent: str = Field(
        description="Transient routing-intent string returned by route listing.",
    )


def resolve_routing(
    ledger: CallStateLedger, routing_intent: str
) -> RoutingResolution:
    """Attach a routing intent to a call without touching ``ledger.intent``.

    Produces a :class:`RoutingResolution` carrying the transient
    ``routing_intent`` separately from the ledger's internal ``intent`` label
    (Req 2.4). The ``ledger`` is not mutated: its ``intent`` is only snapshotted
    onto the returned container, guaranteeing the routing intent is never written
    back onto the classification label.

    Args:
        ledger: The current call-state ledger. Not mutated.
        routing_intent: The exact routing-intent string produced by
            ``routing_intent_resolution``.

    Returns:
        A frozen :class:`RoutingResolution` holding the ledger intent snapshot
        and the transient routing intent.
    """
    return RoutingResolution(
        ledger_intent=ledger.intent, routing_intent=routing_intent
    )


__all__ = [
    "CallStateLedger",
    "LEDGER_VARIABLE_TYPES",
    "LEDGER_FIELD_NAMES",
    "RoutingResolution",
    "normalize_specialty",
    "reduce_ledger",
    "resolve_routing",
    "should_ask",
]
