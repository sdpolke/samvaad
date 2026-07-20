"""Switchboard-side input/output contracts for the 11 connector tools (Req 16.1).

These Pydantic models are the **switchboard-side** shapes from the design's
"Backend connector tools — input/output contracts" table. They describe only what
the switchboard sends and expects back — never SpinSci's wire schema, which is
supplied externally and reached through each tool's
:class:`~api.services.switchboard.tools.base.ConnectorBinding` (Req 16.2).

Each capability has an ``*Input`` and an ``*Output`` model. Field names use the
Call State Ledger vocabulary (Appendix D) so tool inputs/outputs map directly onto
ledger fields (e.g. ``patient_id``, ``department_id``, ``selected_id``,
``patient_verified``, ``appointment_action``, ``visit_type``).

Requirements: 16.1, 16.2.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Contract(BaseModel):
    """Base for all connector contracts: forbid unknown fields at the boundary."""

    model_config = ConfigDict(extra="forbid")


# ===========================================================================
# patient_lookup  — Greeting, Authentication
# ===========================================================================


class PatientLookupInput(_Contract):
    """Look a patient up by ANI (turn-1 Greeting) or a confirmed phone number."""

    phone: str = Field(
        description="The caller ANI or the phone number confirmed during Authentication.",
    )


class PatientLookupOutput(_Contract):
    """Patient-lookup result. ``dob_on_file`` is opaque — never spoken to the caller."""

    patient_id: Optional[str] = Field(
        default=None, description="Resolved patient identifier, or null on no match."
    )
    match_count: int = Field(
        default=0, ge=0, description="Number of matching patient records."
    )
    name: Optional[str] = Field(
        default=None, description="Patient name on file for a single match."
    )
    dob_on_file: Optional[str] = Field(
        default=None,
        description="Opaque DOB-on-file token used only for DOB validation; never spoken.",
    )


# ===========================================================================
# directory_lookup  — Business / After Hours
# ===========================================================================


class DirectoryMatch(_Contract):
    """A single directory match returned by ``directory_lookup``."""

    department_name: str = Field(description="Matched department name.")
    department_id: str = Field(description="Matched department identifier.")
    selected_id: int = Field(description="Numeric record identifier (Req 15.3).")


class DirectoryLookupInput(_Contract):
    """Directory search over a specialty / provider / location query."""

    query: str = Field(description="Specialty, provider, or location search text.")


class DirectoryLookupOutput(_Contract):
    """Directory-lookup result: the top match plus all candidate matches."""

    department_name: Optional[str] = Field(
        default=None, description="Resolved department name for the top match."
    )
    department_id: Optional[str] = Field(
        default=None, description="Resolved department identifier for the top match."
    )
    selected_id: Optional[int] = Field(
        default=None, description="Numeric record identifier for the top match (Req 15.3)."
    )
    matches: list[DirectoryMatch] = Field(
        default_factory=list, description="All candidate matches for the query."
    )


# ===========================================================================
# faq_kb  — Business / After Hours
# ===========================================================================


class FaqKbInput(_Contract):
    """A free-text FAQ / knowledge-base question."""

    question: str = Field(description="The caller's question text.")


class FaqKbOutput(_Contract):
    """FAQ / knowledge-base answer text."""

    answer: str = Field(description="Answer text for the question.")


# ===========================================================================
# dob_validation  — Authentication
# ===========================================================================


class DobValidationInput(_Contract):
    """Validate a caller-provided DOB against the patient's DOB on file."""

    provided_dob: str = Field(description="The DOB the caller provided.")
    patient_id: str = Field(description="The patient whose DOB is validated.")


class DobValidationOutput(_Contract):
    """DOB-validation result: whether the provided DOB matches the record."""

    match: bool = Field(description="True when the provided DOB matches the record.")


# ===========================================================================
# identity_verify  — Authentication
# ===========================================================================


class IdentityVerifyInput(_Contract):
    """Resolve identity verification from a patient id and verification signals."""

    patient_id: str = Field(description="The patient being verified.")
    verification_signals: dict[str, Any] = Field(
        default_factory=dict,
        description="Opaque verification signals (e.g. DOB match) used to decide.",
    )


class IdentityVerifyOutput(_Contract):
    """Identity-verification result mapped to the ledger ``patient_verified`` value."""

    patient_verified: str = Field(
        description="Verification outcome: 'Success' or 'Fail'.",
    )


# ===========================================================================
# routing_intent_resolution  — Routing (step 1 of the sequential chain)
# ===========================================================================


class RoutingIntentResolutionInput(_Contract):
    """Resolve the candidate route listing from department/intent context."""

    department_name: Optional[str] = Field(
        default=None, description="Resolved department name, when known."
    )
    department_id: Optional[str] = Field(
        default=None, description="Resolved department identifier, when known."
    )
    intent: Optional[str] = Field(
        default=None, description="Internal intent classification label."
    )


class RoutingIntentResolutionOutput(_Contract):
    """The route listing: exact routing-intent strings, consumed verbatim (Req 10.2)."""

    route_listing: list[str] = Field(
        default_factory=list,
        description="Exact routing-intent strings; never fabricated, used verbatim.",
    )


# ===========================================================================
# route_metadata_resolution  — Routing (step 2 of the sequential chain)
# ===========================================================================


class RouteMetadataResolutionInput(_Contract):
    """Resolve destination metadata for one exact routing-intent string (Req 10.3)."""

    routing_intent: str = Field(
        description="The exact routing-intent string returned by the listing step.",
    )


class RouteMetadataResolutionOutput(_Contract):
    """Queue/destination metadata for the selected routing intent."""

    destination: str = Field(description="Transfer destination (queue/endpoint).")
    queue_id: Optional[str] = Field(
        default=None, description="Backend queue identifier, when applicable."
    )
    display_name: Optional[str] = Field(
        default=None, description="Human-readable destination name."
    )


# ===========================================================================
# transfer  — Routing  [telephony seam wired in task 15.2]
# ===========================================================================


class TransferInput(_Contract):
    """Transfer payload: destination + call summary + verification + spoken line.

    The spoken transfer message is the verbatim Appendix E line; the backend seam
    (task 15.2) forwards ``destination`` and this payload to the telephony
    provider's ``transfer_call(destination, ...)``.
    """

    destination: str = Field(description="Transfer destination (from route metadata).")
    call_summary: str = Field(
        default="", description="Summary of the call handed to the receiving party."
    )
    patient_verified: Optional[str] = Field(
        default=None,
        description="Verification status carried with the transfer (null/Success/Fail/N/A).",
    )
    spoken_transfer_message: str = Field(
        default="", description="The verbatim line spoken to the caller on transfer."
    )


class TransferOutput(_Contract):
    """Transfer result returned by the telephony seam."""

    status: str = Field(description="Transfer initiation status.")
    transfer_id: Optional[str] = Field(
        default=None, description="Identifier for tracking the transfer."
    )


# ===========================================================================
# hangup  — Routing  [telephony seam wired in task 15.2]
# ===========================================================================


class HangupInput(_Contract):
    """Hangup payload carrying the verbatim goodbye line to speak before ending."""

    goodbye_line: str = Field(description="The verbatim goodbye line spoken before hangup.")


class HangupOutput(_Contract):
    """Hangup acknowledgement result."""

    status: str = Field(default="ended", description="Hangup status.")


# ===========================================================================
# scheduling_handoff  — Scheduling
# ===========================================================================


class SchedulingHandoffInput(_Contract):
    """Hand the full Call State Ledger to Scheduling Init (Req 12.8)."""

    ledger: dict[str, Any] = Field(
        description="The full Call State Ledger passed on the scheduling handoff.",
    )


class SchedulingHandoffOutput(_Contract):
    """Scheduling Init context derived from the handed-off ledger."""

    specialty: Optional[str] = Field(
        default=None, description="Specialty carried into Scheduling Init."
    )
    appointment_action: Optional[str] = Field(
        default=None, description="The appointment action carried into Scheduling Init."
    )
    ready: bool = Field(
        default=True, description="Whether Scheduling Init has the context it needs."
    )


# ===========================================================================
# scheduling_engine  — Scheduling
# ===========================================================================


class SchedulingEngineToolInput(_Contract):
    """Scheduling Engine input (Req 14.2): required fields + create-only visit_type."""

    specialty: str = Field(description="Confirmed specialty (all actions).")
    patient_id: str = Field(description="Verified patient identifier (all actions).")
    appointment_action: str = Field(
        description="create / cancel / reschedule / list / confirm (all actions).",
    )
    visit_type: Optional[str] = Field(
        default=None, description="sick / wellness — present only for a create action."
    )
    location: Optional[str] = Field(default=None, description="Location, when known.")
    provider_name: Optional[str] = Field(
        default=None, description="Requested provider, when known."
    )
    existing_appointment_date: Optional[str] = Field(
        default=None, description="Target appointment date for cancel/reschedule."
    )


class SchedulingSlot(_Contract):
    """A single available appointment slot returned by the Scheduling Engine."""

    slot_id: str = Field(description="Backend slot identifier.")
    start: str = Field(description="Slot start time (ISO 8601).")
    provider_name: Optional[str] = Field(
        default=None, description="Provider offering the slot."
    )


class SchedulingEngineToolOutput(_Contract):
    """Scheduling Engine result: slots (create/reschedule) or an action result."""

    action_result: str = Field(
        description="Outcome of the action (e.g. 'slots_offered', 'cancelled', 'listed').",
    )
    slots: list[SchedulingSlot] = Field(
        default_factory=list,
        description="Available slots for create/reschedule; empty for other actions.",
    )
    appointment_details: Optional[dict[str, Any]] = Field(
        default=None, description="Appointment details for confirm/list/cancel."
    )


__all__ = [
    "PatientLookupInput",
    "PatientLookupOutput",
    "DirectoryMatch",
    "DirectoryLookupInput",
    "DirectoryLookupOutput",
    "FaqKbInput",
    "FaqKbOutput",
    "DobValidationInput",
    "DobValidationOutput",
    "IdentityVerifyInput",
    "IdentityVerifyOutput",
    "RoutingIntentResolutionInput",
    "RoutingIntentResolutionOutput",
    "RouteMetadataResolutionInput",
    "RouteMetadataResolutionOutput",
    "TransferInput",
    "TransferOutput",
    "HangupInput",
    "HangupOutput",
    "SchedulingHandoffInput",
    "SchedulingHandoffOutput",
    "SchedulingEngineToolInput",
    "SchedulingSlot",
    "SchedulingEngineToolOutput",
]
