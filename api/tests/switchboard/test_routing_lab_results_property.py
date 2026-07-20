"""Property-based test for lab-results routing (task 11.7).

Covers Property 26 — Lab results route to General
(Requirement 11.5).

WHEN the caller requests lab results, the Switchboard SHALL route to General
rather than Records — regardless of the intent, patient_status, or
appointment_action.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.auth import Intent
from api.services.switchboard.business_hours import AppointmentAction
from api.services.switchboard.routing import RouteDestination, resolve_route

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All Intent enum values, including None (unresolved).
_intents = st.sampled_from([*list(Intent), None])

#: Patient status values: None, "new", "existing", and some casing variants.
_patient_statuses = st.sampled_from([None, "new", "existing", "New", "EXISTING", " new "])

#: Appointment actions: enum values, raw strings, and None.
_appointment_actions = st.sampled_from(
    [*list(AppointmentAction), None, "create", "cancel", "reschedule", "list", "confirm"]
)


# ===========================================================================
# Property 26: Lab results route to General
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 26: Lab results route to General
@given(
    intent=_intents,
    patient_status=_patient_statuses,
    appointment_action=_appointment_actions,
)
@example(intent=Intent.RECORDS, patient_status=None, appointment_action=None)
@example(intent=Intent.SCHEDULING, patient_status="new", appointment_action=AppointmentAction.CREATE)
@example(intent=Intent.GENERAL, patient_status=None, appointment_action=None)
@example(intent=None, patient_status=None, appointment_action=None)
@settings(max_examples=200)
def test_lab_results_always_routes_to_general(
    intent: Intent | None,
    patient_status: str | None,
    appointment_action: AppointmentAction | str | None,
) -> None:
    """When requests_lab_results=True, result is ALWAYS RouteDestination.GENERAL.

    **Validates: Requirements 11.5**

    WHEN the caller requests lab results, THE Switchboard SHALL route to General
    rather than Records, regardless of the classified intent, patient_status, or
    appointment_action.
    """
    # Feature: spinsci-switchboard-poc, Property 26: Lab results route to General

    result = resolve_route(
        intent=intent,
        patient_status=patient_status,
        appointment_action=appointment_action,
        requests_lab_results=True,
    )
    assert result is RouteDestination.GENERAL, (
        f"Expected GENERAL when requests_lab_results=True, got {result} "
        f"(intent={intent}, patient_status={patient_status!r}, "
        f"appointment_action={appointment_action})"
    )


# Feature: spinsci-switchboard-poc, Property 26: Lab results route to General
@given(
    patient_status=_patient_statuses,
    appointment_action=_appointment_actions,
)
@example(patient_status=None, appointment_action=None)
@example(patient_status="new", appointment_action=AppointmentAction.CREATE)
@example(patient_status="existing", appointment_action=AppointmentAction.LIST)
@settings(max_examples=200)
def test_lab_results_overrides_records_intent(
    patient_status: str | None,
    appointment_action: AppointmentAction | str | None,
) -> None:
    """When intent is RECORDS and requests_lab_results=True, result is GENERAL not RECORDS.

    **Validates: Requirements 11.5**

    In particular, even when the classified intent would normally route to Records,
    the lab-results signal overrides it to General.
    """
    # Feature: spinsci-switchboard-poc, Property 26: Lab results route to General

    result = resolve_route(
        intent=Intent.RECORDS,
        patient_status=patient_status,
        appointment_action=appointment_action,
        requests_lab_results=True,
    )
    assert result is RouteDestination.GENERAL, (
        f"Expected GENERAL (not RECORDS) when intent=RECORDS and "
        f"requests_lab_results=True, got {result} "
        f"(patient_status={patient_status!r}, appointment_action={appointment_action})"
    )


# Feature: spinsci-switchboard-poc, Property 26: Lab results route to General
@given(
    intent=_intents,
    patient_status=_patient_statuses,
    appointment_action=_appointment_actions,
)
@example(intent=Intent.SCHEDULING, patient_status="new", appointment_action=AppointmentAction.CREATE)
@example(intent=Intent.BILLING, patient_status=None, appointment_action=None)
@example(intent=Intent.DIRECTORY, patient_status=None, appointment_action=None)
@settings(max_examples=200)
def test_lab_results_takes_precedence_over_all_routing(
    intent: Intent | None,
    patient_status: str | None,
    appointment_action: AppointmentAction | str | None,
) -> None:
    """Lab-results signal takes precedence over all other routing decisions.

    **Validates: Requirements 11.5**

    The lab-results check is the FIRST precedence rule in resolve_route: it is
    evaluated before new-patient-create (Req 12.7), before intent-based routing,
    and before the fallback (Req 11.6). Therefore when requests_lab_results=True,
    the result is always GENERAL — even for inputs that would otherwise route to
    SCHEDULING_NEW_INTAKE, FALLBACK, or any other destination.
    """
    # Feature: spinsci-switchboard-poc, Property 26: Lab results route to General

    result = resolve_route(
        intent=intent,
        patient_status=patient_status,
        appointment_action=appointment_action,
        requests_lab_results=True,
    )
    assert result is RouteDestination.GENERAL, (
        f"Expected GENERAL (lab-results precedence), got {result} "
        f"(intent={intent}, patient_status={patient_status!r}, "
        f"appointment_action={appointment_action})"
    )
