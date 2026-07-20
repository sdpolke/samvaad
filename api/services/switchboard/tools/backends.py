"""Mock backends for the switchboard connector tools (Req 16.1, 16.2).

Because SpinSci supplies the real wire contracts externally (Req 16.2), the PoC
services every connector tool with a deterministic **mock** backend defined here.
Each backend takes a validated switchboard-side input model (see
:mod:`.contracts`) and returns the corresponding output model, so the switchboard
contract is exercised end-to-end without any SpinSci wire assumption. When SpinSci
delivers schemas, these mocks are swapped for an HTTP backend that uses the tool's
:class:`~api.services.switchboard.tools.base.ConnectorBinding` — no contract change.

The ``transfer`` and ``hangup`` backends are **wired to the repository telephony
providers** (task 15.2, Req 16.3, 16.4): :func:`transfer_backend` resolves the
active call's provider through the telephony registry/factory
(:func:`~api.services.telephony.factory.get_telephony_provider_for_run` — never a
provider class directly) and invokes ``transfer_call(destination, ...)`` carrying
the full transfer payload (destination + call summary + verification status +
spoken transfer message). :func:`hangup_backend` likewise resolves the provider
through the factory to confirm live telephony before the call is ended. Both take
a :class:`~api.services.switchboard.tools.base.SwitchboardCallContext` via the
backend's keyword call-context mechanism, so the switchboard-side contracts
(``TransferInput``/``TransferOutput``, ``HangupInput``/``HangupOutput``) stay
unchanged.

The remaining backends are deterministic mocks (no randomness, no real I/O) so
tests are stable.

Requirements: 16.1, 16.2, 16.3, 16.4.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from loguru import logger

from api.services.switchboard.tools.base import SwitchboardCallContext
from api.services.switchboard.tools.contracts import (
    DirectoryLookupInput,
    DirectoryLookupOutput,
    DirectoryMatch,
    DobValidationInput,
    DobValidationOutput,
    FaqKbInput,
    FaqKbOutput,
    HangupInput,
    HangupOutput,
    IdentityVerifyInput,
    IdentityVerifyOutput,
    PatientLookupInput,
    PatientLookupOutput,
    RouteMetadataResolutionInput,
    RouteMetadataResolutionOutput,
    RoutingIntentResolutionInput,
    RoutingIntentResolutionOutput,
    SchedulingEngineToolInput,
    SchedulingEngineToolOutput,
    SchedulingHandoffInput,
    SchedulingHandoffOutput,
    SchedulingSlot,
    TransferInput,
    TransferOutput,
)


def _digits(value: str) -> str:
    """Return only the digit characters of ``value`` (helper for stable mock ids)."""
    return "".join(ch for ch in value if ch.isdigit())


async def patient_lookup_backend(
    request: PatientLookupInput, *, organization_id: Optional[int] = None
) -> PatientLookupOutput:
    """Mock patient lookup: derive a stable single match from the phone digits.

    A phone with 10+ digits yields one match with an opaque DOB-on-file token; a
    shorter/empty value yields no match (``match_count == 0``). Deterministic so
    Authentication's DOB validation can be exercised against the same token.
    """
    digits = _digits(request.phone)
    if len(digits) >= 10:
        return PatientLookupOutput(
            patient_id=f"mock-patient-{digits[-10:]}",
            match_count=1,
            name="Mock Patient",
            dob_on_file=f"dob-token-{digits[-4:]}",
        )
    logger.debug("Mock patient_lookup: no match for phone with {} digits", len(digits))
    return PatientLookupOutput(patient_id=None, match_count=0, name=None, dob_on_file=None)


async def directory_lookup_backend(
    request: DirectoryLookupInput, *, organization_id: Optional[int] = None
) -> DirectoryLookupOutput:
    """Mock directory lookup: return one deterministic department for any query."""
    match = DirectoryMatch(
        department_name=f"{request.query.strip().title()} Department",
        department_id="mock-dept-001",
        selected_id=1001,
    )
    return DirectoryLookupOutput(
        department_name=match.department_name,
        department_id=match.department_id,
        selected_id=match.selected_id,
        matches=[match],
    )


async def faq_kb_backend(
    request: FaqKbInput, *, organization_id: Optional[int] = None
) -> FaqKbOutput:
    """Mock FAQ knowledge base: return a canned answer referencing the question."""
    return FaqKbOutput(
        answer="Our standard clinic hours are Monday through Friday, 8 to 5."
    )


async def dob_validation_backend(
    request: DobValidationInput, *, organization_id: Optional[int] = None
) -> DobValidationOutput:
    """Mock DOB validation: match when the provided DOB echoes the token suffix.

    The mock :func:`patient_lookup_backend` mints DOB tokens as ``dob-token-<4>``;
    this backend treats a provided DOB whose digits end with that suffix (or the
    literal token) as a match, so a paired lookup→validate flow is deterministic.
    """
    provided = _digits(request.provided_dob)
    expected_suffix = _digits(request.patient_id)[-4:]
    match = bool(provided) and provided.endswith(expected_suffix)
    logger.debug("Mock dob_validation: match={}", match)
    return DobValidationOutput(match=match)


async def identity_verify_backend(
    request: IdentityVerifyInput, *, organization_id: Optional[int] = None
) -> IdentityVerifyOutput:
    """Mock identity verify: Success iff a truthy ``dob_match`` signal is present."""
    dob_match = bool(request.verification_signals.get("dob_match"))
    return IdentityVerifyOutput(patient_verified="Success" if dob_match else "Fail")


async def routing_intent_resolution_backend(
    request: RoutingIntentResolutionInput, *, organization_id: Optional[int] = None
) -> RoutingIntentResolutionOutput:
    """Mock route listing: derive exact routing-intent strings from context.

    Returns a small deterministic listing so ``route_metadata_resolution`` can be
    called with one of the **exact** returned strings (Req 10.2, 10.3).
    """
    label = (request.department_name or request.intent or "General").strip()
    listing = [f"{label} Queue", f"{label} Voicemail"]
    return RoutingIntentResolutionOutput(route_listing=listing)


async def route_metadata_resolution_backend(
    request: RouteMetadataResolutionInput, *, organization_id: Optional[int] = None
) -> RouteMetadataResolutionOutput:
    """Mock destination metadata for one exact routing-intent string (Req 10.3)."""
    return RouteMetadataResolutionOutput(
        destination="+15551230000",
        queue_id="mock-queue-001",
        display_name=request.routing_intent,
    )


# ---------------------------------------------------------------------------
# Telephony seam — transfer / hangup  (Req 16.3, 16.4)
# ---------------------------------------------------------------------------
# The two backends below are wired to the repository telephony providers. The
# active call's provider is resolved through the telephony registry/factory
# (get_telephony_provider_for_run) — never by instantiating a provider class
# directly — and transfer_call(destination, ...) is invoked with the full
# transfer payload (destination + call summary + verification status + spoken
# message). Runtime call context arrives via the SwitchboardCallContext keyword
# rather than the switchboard-side contract, which stays unchanged.


async def transfer_backend(
    request: TransferInput,
    *,
    organization_id: Optional[int] = None,
    call_context: Optional[SwitchboardCallContext] = None,
) -> TransferOutput:
    """Transfer the active call via the telephony provider (Req 16.3, 16.4).

    Resolves the provider for the current workflow run through the telephony
    registry/factory (:func:`get_telephony_provider_for_run`), then invokes
    ``transfer_call(request.destination, ...)`` carrying the full transfer payload
    — destination, call summary, verification status, and the spoken transfer
    message (Req 16.3). The provider handles the wire-level transfer; this backend
    only orchestrates resolution and payload delivery, keeping the
    :class:`TransferInput`/:class:`TransferOutput` contract unchanged.

    Without an active-call context (e.g. a graph-build or unit-test invocation
    with no live telephony), the transfer cannot be executed and a deterministic
    ``status="unavailable"`` result is returned rather than raising.
    """
    if call_context is None:
        logger.warning(
            "switchboard transfer invoked without call context; telephony unavailable"
        )
        return TransferOutput(status="unavailable", transfer_id=None)

    # Lazy imports keep the tools package free of DB/telephony import-time coupling.
    from api.db import db_client
    from api.services.telephony.call_transfer_manager import get_call_transfer_manager
    from api.services.telephony.factory import get_telephony_provider_for_run
    from api.services.telephony.transfer_event_protocol import TransferContext

    org_id = call_context.organization_id or organization_id
    workflow_run = await db_client.get_workflow_run_by_id(call_context.workflow_run_id)
    if workflow_run is None:
        logger.error(
            "switchboard transfer: workflow run {} not found",
            call_context.workflow_run_id,
        )
        return TransferOutput(status="failed", transfer_id=None)

    original_call_sid = (workflow_run.gathered_context or {}).get("call_id")

    # No live telephony call to transfer (e.g. a browser/WebRTC test call has no
    # PSTN/SIP call SID). A real transfer is impossible here, but this is NOT a
    # failure — surface a distinct "simulated" status so the graph can speak the
    # prescribed transfer line and end the call cleanly instead of routing to the
    # transfer-error line. Genuine telephony failures below still return "failed".
    if not original_call_sid:
        logger.info(
            "switchboard transfer: no live telephony call (call_id absent) — "
            "returning simulated transfer for non-telephony run {}",
            call_context.workflow_run_id,
        )
        return TransferOutput(status="simulated", transfer_id=None)

    # Provider resolution is org-scoped by the factory, enforcing tenant isolation.
    provider = await get_telephony_provider_for_run(workflow_run, org_id)
    if not provider.supports_transfers() or not provider.validate_config():
        logger.error(
            "switchboard transfer: provider {} does not support transfers or is "
            "misconfigured",
            getattr(provider, "PROVIDER_NAME", type(provider).__name__),
        )
        return TransferOutput(status="failed", transfer_id=None)

    transfer_id = str(uuid.uuid4())
    conference_name = f"transfer-{original_call_sid}"

    # Seed transfer context before the provider call so transfer_id-keyed webhooks
    # can resolve org/credentials without a race (mirrors the engine transfer flow).
    transfer_manager = await get_call_transfer_manager()
    await transfer_manager.store_transfer_context(
        TransferContext(
            transfer_id=transfer_id,
            call_sid=None,
            target_number=request.destination,
            tool_uuid="switchboard.transfer",
            original_call_sid=original_call_sid or "",
            conference_name=conference_name,
            initiated_at=time.time(),
            workflow_run_id=call_context.workflow_run_id,
        )
    )

    logger.info(
        "switchboard transfer via {}: verified={}, transfer_id={}",
        getattr(provider, "PROVIDER_NAME", type(provider).__name__),
        request.patient_verified,
        transfer_id,
    )
    # The transfer payload carries destination + call summary + verification status
    # + spoken transfer message (Req 16.3); providers consume what they need.
    result = await provider.transfer_call(
        destination=request.destination,
        transfer_id=transfer_id,
        conference_name=conference_name,
        call_summary=request.call_summary,
        patient_verified=request.patient_verified,
        spoken_transfer_message=request.spoken_transfer_message,
    )
    status = result.get("status") if isinstance(result, dict) else None
    return TransferOutput(status=status or "initiated", transfer_id=transfer_id)


async def hangup_backend(
    request: HangupInput,
    *,
    organization_id: Optional[int] = None,
    call_context: Optional[SwitchboardCallContext] = None,
) -> HangupOutput:
    """End the active call through the telephony provider (Req 16.4).

    Resolves the active call's provider through the telephony registry/factory
    (:func:`get_telephony_provider_for_run` — never a provider class directly) to
    confirm live telephony before ending the call. The verbatim goodbye line in
    ``request.goodbye_line`` is spoken by the terminal node before this backend
    runs; the wire-level channel teardown is performed by the provider's hangup
    strategy at pipeline teardown. Keeps the :class:`HangupInput`/
    :class:`HangupOutput` contract unchanged.

    Without an active-call context, no telephony is reachable and a deterministic
    ``status="ended"`` acknowledgement is returned rather than raising.
    """
    if call_context is None:
        logger.warning(
            "switchboard hangup invoked without call context; telephony unavailable"
        )
        return HangupOutput(status="ended")

    from api.db import db_client
    from api.services.telephony.factory import get_telephony_provider_for_run

    org_id = call_context.organization_id or organization_id
    workflow_run = await db_client.get_workflow_run_by_id(call_context.workflow_run_id)
    if workflow_run is None:
        logger.error(
            "switchboard hangup: workflow run {} not found",
            call_context.workflow_run_id,
        )
        return HangupOutput(status="ended")

    # Org-scoped resolution enforces tenant isolation on the telephony config.
    provider = await get_telephony_provider_for_run(workflow_run, org_id)
    logger.info(
        "switchboard hangup via {}",
        getattr(provider, "PROVIDER_NAME", type(provider).__name__),
    )
    return HangupOutput(status="ended")


async def scheduling_handoff_backend(
    request: SchedulingHandoffInput, *, organization_id: Optional[int] = None
) -> SchedulingHandoffOutput:
    """Mock scheduling handoff: surface specialty/action from the full ledger."""
    ledger = request.ledger
    return SchedulingHandoffOutput(
        specialty=ledger.get("specialty"),
        appointment_action=ledger.get("appointment_action"),
        ready=bool(ledger.get("specialty")),
    )


async def scheduling_engine_backend(
    request: SchedulingEngineToolInput, *, organization_id: Optional[int] = None
) -> SchedulingEngineToolOutput:
    """Mock Scheduling Engine: offer slots for create/reschedule, else act.

    Deterministic per action so the downstream scheduling segment (task 17) and
    its integration tests can be exercised against a stable engine.

    When ``provider_name`` is supplied for a create/reschedule action, the mock
    simulates a "preferred provider unavailable" scenario (POC-13, REQ-SCHED-12,
    AC-18): the preferred provider cannot see the patient for the visit type, so
    the engine returns ``action_result="alternative_offered"`` with slots from
    **different** providers at the same location, proving alternatives are offered
    without re-asking already-collected facts.
    """
    action = request.appointment_action.strip().lower()
    if action in {"create", "reschedule"}:
        if request.provider_name:
            # Preferred provider unavailable — offer alternative providers at
            # the same location (POC-13, REQ-SCHED-12, AC-18).
            slots = [
                SchedulingSlot(
                    slot_id="mock-alt-slot-001",
                    start="2026-01-05T09:00:00-06:00",
                    provider_name=f"Alt Provider A (not {request.provider_name})",
                ),
                SchedulingSlot(
                    slot_id="mock-alt-slot-002",
                    start="2026-01-05T10:30:00-06:00",
                    provider_name=f"Alt Provider B (not {request.provider_name})",
                ),
            ]
            return SchedulingEngineToolOutput(
                action_result="alternative_offered", slots=slots
            )
        slots = [
            SchedulingSlot(
                slot_id="mock-slot-001",
                start="2026-01-05T09:00:00-06:00",
                provider_name="Mock Provider",
            ),
            SchedulingSlot(
                slot_id="mock-slot-002",
                start="2026-01-05T10:30:00-06:00",
                provider_name="Mock Provider",
            ),
        ]
        return SchedulingEngineToolOutput(action_result="slots_offered", slots=slots)
    if action == "cancel":
        return SchedulingEngineToolOutput(
            action_result="cancelled",
            appointment_details={"status": "cancelled"},
        )
    if action == "list":
        return SchedulingEngineToolOutput(
            action_result="listed",
            appointment_details={"appointments": []},
        )
    # confirm
    return SchedulingEngineToolOutput(
        action_result="confirmed",
        appointment_details={"status": "confirmed"},
    )


__all__ = [
    "patient_lookup_backend",
    "directory_lookup_backend",
    "faq_kb_backend",
    "dob_validation_backend",
    "identity_verify_backend",
    "routing_intent_resolution_backend",
    "route_metadata_resolution_backend",
    "transfer_backend",
    "hangup_backend",
    "scheduling_handoff_backend",
    "scheduling_engine_backend",
]
