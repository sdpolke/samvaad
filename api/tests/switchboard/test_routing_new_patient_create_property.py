"""Property-based test for new-patient create routing (task 11.8).

Covers Property 27 — New-patient create routes to general intake
(Requirement 12.7).

WHEN routing a new-patient ``create`` Scheduling call, THE Switchboard SHALL
route to the general new-patient intake path rather than the specialty
scheduling agent.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.auth import Intent
from api.services.switchboard.business_hours import AppointmentAction
from api.services.switchboard.routing import RouteDestination, resolve_route, is_new_patient_create

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All Intent enum values, including None (unresolved).
_intents = st.sampled_from([*list(Intent), None])

#: Patient status values that are "new" (case variants, with/without whitespace).
_new_patient_statuses = st.sampled_from(["new", "New", "NEW", " new ", " New "])

#: Patient status values that are NOT "new".
_non_new_patient_statuses = st.sampled_from([None, "existing", "Existing", "EXISTING", " existing ", "unknown", ""])

#: Appointment actions that are "create" (enum and raw string variants).
_create_actions = st.sampled_from([AppointmentAction.CREATE, "create", "Create", "CREATE", " create "])

#: Appointment actions that are NOT "create".
_non_create_actions = st.sampled_from(
    [None, AppointmentAction.CANCEL, AppointmentAction.RESCHEDULE,
     AppointmentAction.LIST, AppointmentAction.CONFIRM,
     "cancel", "reschedule", "list", "confirm"]
)

#: All appointment actions: enum values, raw strings, and None.
_all_appointment_actions = st.sampled_from(
    [*list(AppointmentAction), None, "create", "cancel", "reschedule", "list", "confirm"]
)

#: All patient status values (new, existing, None, casing variants).
_all_patient_statuses = st.sampled_from([None, "new", "existing", "New", "EXISTING", " new ", ""])


# ===========================================================================
# Property 27: New-patient create routes to general intake
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake
@given(
    intent=_intents,
    patient_status=_new_patient_statuses,
    appointment_action=_create_actions,
)
@example(intent=Intent.SCHEDULING, patient_status="new", appointment_action=AppointmentAction.CREATE)
@example(intent=None, patient_status="new", appointment_action="create")
@example(intent=Intent.GENERAL, patient_status=" New ", appointment_action=" create ")
@example(intent=Intent.RECORDS, patient_status="NEW", appointment_action="CREATE")
@settings(max_examples=200)
def test_new_patient_create_always_routes_to_scheduling_new_intake(
    intent: Intent | None,
    patient_status: str,
    appointment_action: AppointmentAction | str,
) -> None:
    """When patient_status=new and appointment_action=create, result is SCHEDULING_NEW_INTAKE.

    **Validates: Requirements 12.7**

    For any ledger with patient_status = new and appointment_action = create,
    resolve_route returns SCHEDULING_NEW_INTAKE (the general new-patient intake
    path) rather than SCHEDULING_EXISTING (the specialty scheduling agent),
    regardless of intent, specialty, or other ledger values.
    """
    # Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake

    result = resolve_route(
        intent=intent,
        patient_status=patient_status,
        appointment_action=appointment_action,
        requests_lab_results=False,
    )
    assert result is RouteDestination.SCHEDULING_NEW_INTAKE, (
        f"Expected SCHEDULING_NEW_INTAKE for new-patient create, got {result} "
        f"(intent={intent}, patient_status={patient_status!r}, "
        f"appointment_action={appointment_action})"
    )


# Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake
@given(
    patient_status=_new_patient_statuses,
    appointment_action=_create_actions,
)
@example(patient_status="new", appointment_action=AppointmentAction.CREATE)
@example(patient_status="New", appointment_action="create")
@example(patient_status=" new ", appointment_action=" create ")
@settings(max_examples=200)
def test_is_new_patient_create_true_for_new_and_create(
    patient_status: str,
    appointment_action: AppointmentAction | str,
) -> None:
    """is_new_patient_create returns True for new+create combinations (casing variants).

    **Validates: Requirements 12.7**

    The predicate correctly identifies new-patient create conditions with
    case-insensitive and whitespace-tolerant matching of patient_status and
    appointment_action.
    """
    # Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake

    assert is_new_patient_create(patient_status, appointment_action) is True, (
        f"Expected is_new_patient_create=True for patient_status={patient_status!r}, "
        f"appointment_action={appointment_action}"
    )


# Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake
@given(
    intent=_intents,
    patient_status=_non_new_patient_statuses,
    appointment_action=_create_actions,
)
@example(intent=Intent.SCHEDULING, patient_status="existing", appointment_action=AppointmentAction.CREATE)
@example(intent=Intent.SCHEDULING, patient_status=None, appointment_action="create")
@example(intent=None, patient_status="", appointment_action=AppointmentAction.CREATE)
@settings(max_examples=200)
def test_non_new_patient_does_not_route_to_new_intake(
    intent: Intent | None,
    patient_status: str | None,
    appointment_action: AppointmentAction | str,
) -> None:
    """When patient_status is NOT "new", result is never SCHEDULING_NEW_INTAKE.

    **Validates: Requirements 12.7**

    Even with appointment_action=create, a non-new patient status does not
    trigger the general new-patient intake path.
    """
    # Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake

    result = resolve_route(
        intent=intent,
        patient_status=patient_status,
        appointment_action=appointment_action,
        requests_lab_results=False,
    )
    assert result is not RouteDestination.SCHEDULING_NEW_INTAKE, (
        f"Expected NOT SCHEDULING_NEW_INTAKE for non-new patient, got {result} "
        f"(intent={intent}, patient_status={patient_status!r}, "
        f"appointment_action={appointment_action})"
    )


# Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake
@given(
    intent=_intents,
    patient_status=_new_patient_statuses,
    appointment_action=_non_create_actions,
)
@example(intent=Intent.SCHEDULING, patient_status="new", appointment_action=AppointmentAction.CANCEL)
@example(intent=Intent.SCHEDULING, patient_status="new", appointment_action=None)
@example(intent=None, patient_status="New", appointment_action="reschedule")
@settings(max_examples=200)
def test_non_create_action_does_not_route_to_new_intake(
    intent: Intent | None,
    patient_status: str,
    appointment_action: AppointmentAction | str | None,
) -> None:
    """When appointment_action is NOT "create", result is never SCHEDULING_NEW_INTAKE.

    **Validates: Requirements 12.7**

    Even with patient_status=new, a non-create appointment action does not
    trigger the general new-patient intake path.
    """
    # Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake

    result = resolve_route(
        intent=intent,
        patient_status=patient_status,
        appointment_action=appointment_action,
        requests_lab_results=False,
    )
    assert result is not RouteDestination.SCHEDULING_NEW_INTAKE, (
        f"Expected NOT SCHEDULING_NEW_INTAKE for non-create action, got {result} "
        f"(intent={intent}, patient_status={patient_status!r}, "
        f"appointment_action={appointment_action})"
    )


# Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake
@given(
    intent=_intents,
    patient_status=_new_patient_statuses,
    appointment_action=_create_actions,
)
@example(intent=Intent.SCHEDULING, patient_status="new", appointment_action=AppointmentAction.CREATE)
@example(intent=Intent.RECORDS, patient_status="new", appointment_action="create")
@example(intent=None, patient_status="New", appointment_action="Create")
@settings(max_examples=200)
def test_lab_results_takes_precedence_over_new_patient_create(
    intent: Intent | None,
    patient_status: str,
    appointment_action: AppointmentAction | str,
) -> None:
    """Lab results (requests_lab_results=True) takes precedence over new-patient-create.

    **Validates: Requirements 12.7**

    When requests_lab_results=True, the result is GENERAL even when
    patient_status=new and appointment_action=create. The lab-results check
    is the FIRST precedence rule in resolve_route.
    """
    # Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake

    result = resolve_route(
        intent=intent,
        patient_status=patient_status,
        appointment_action=appointment_action,
        requests_lab_results=True,
    )
    assert result is RouteDestination.GENERAL, (
        f"Expected GENERAL (lab-results precedence) over new-patient-create, got {result} "
        f"(intent={intent}, patient_status={patient_status!r}, "
        f"appointment_action={appointment_action})"
    )
