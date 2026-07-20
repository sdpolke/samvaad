"""Property-based test for Scheduling Engine input completeness (task 13.4).

Covers Property 30 — Scheduling Engine input completeness
(Requirements 14.2, 12.8).

THE Scheduling_Engine SHALL receive at minimum `specialty`, verified `patient_id`,
and `appointment_action` for all actions, `visit_type` for `create`, and
`location`/`provider_name`/`existing_appointment_date` when known.

WHEN handing off a Scheduling call, THE Switchboard SHALL pass the full
Call_State_Ledger including `specialty`, `location`, `provider_name`,
`appointment_action`, verification status, and call summary.
"""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.business_hours import AppointmentAction
from api.services.switchboard.ledger import CallStateLedger
from api.services.switchboard.scheduling import (
    SchedulingInputError,
    VisitType,
    build_scheduling_engine_input,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All five appointment action values.
_appointment_actions = st.sampled_from(list(AppointmentAction))

#: Manage actions only (everything except CREATE).
_manage_actions = st.sampled_from(
    [a for a in AppointmentAction if a is not AppointmentAction.CREATE]
)

#: Both visit types.
_visit_types = st.sampled_from(list(VisitType))

#: Non-empty string strategy for mandatory fields (specialty, patient_id).
_nonempty_str = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

#: Optional non-empty string for location, provider_name, existing_appointment_date.
_optional_known_str = st.one_of(st.none(), st.text(min_size=1, max_size=50))

#: Patient verified values (null / Success / Fail / N/A).
_patient_verified = st.sampled_from([None, "Success", "Fail", "N/A"])


# ===========================================================================
# Property 30: Scheduling Engine input completeness
# ===========================================================================


# ---------------------------------------------------------------------------
# 30a: For ALL five appointment_action values, the output always contains
#      specialty, patient_id, and appointment_action
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    action=_appointment_actions,
    specialty=_nonempty_str,
    patient_id=_nonempty_str,
    patient_verified=_patient_verified,
    visit_type=_visit_types,
    location=_optional_known_str,
    provider_name=_optional_known_str,
    existing_appointment_date=_optional_known_str,
)
@example(
    action=AppointmentAction.CREATE,
    specialty="Cardiology",
    patient_id="12345",
    patient_verified="Success",
    visit_type=VisitType.SICK,
    location="Chicago",
    provider_name="Dr. Smith",
    existing_appointment_date=None,
)
@example(
    action=AppointmentAction.CANCEL,
    specialty="Neurology",
    patient_id="99999",
    patient_verified="N/A",
    visit_type=VisitType.WELLNESS,
    location=None,
    provider_name=None,
    existing_appointment_date="2025-03-15",
)
@example(
    action=AppointmentAction.RESCHEDULE,
    specialty="Dermatology",
    patient_id="00001",
    patient_verified="Success",
    visit_type=VisitType.SICK,
    location="Austin",
    provider_name=None,
    existing_appointment_date="2025-04-01",
)
@example(
    action=AppointmentAction.LIST,
    specialty="General",
    patient_id="55555",
    patient_verified=None,
    visit_type=VisitType.WELLNESS,
    location=None,
    provider_name="Dr. Jones",
    existing_appointment_date=None,
)
@example(
    action=AppointmentAction.CONFIRM,
    specialty="Orthopedics",
    patient_id="77777",
    patient_verified="Fail",
    visit_type=VisitType.SICK,
    location="Dallas",
    provider_name="Dr. Lee",
    existing_appointment_date="2025-06-10",
)
@settings(max_examples=200)
def test_all_actions_always_have_mandatory_fields(
    action: AppointmentAction,
    specialty: str,
    patient_id: str,
    patient_verified: str | None,
    visit_type: VisitType,
    location: str | None,
    provider_name: str | None,
    existing_appointment_date: str | None,
) -> None:
    """For ALL five actions, the output always contains specialty, patient_id, appointment_action.

    **Validates: Requirements 14.2, 12.8**

    The Scheduling Engine input must always carry `specialty`, `patient_id`, and
    `appointment_action` regardless of which of the five actions is being performed.
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=action.value,
        specialty=specialty,
        patient_id=patient_id,
        patient_verified=patient_verified,
        location=location,
        provider_name=provider_name,
        existing_appointment_date=existing_appointment_date,
    )

    # For create, pass visit_type; for manage, it's ignored anyway
    vt = visit_type if action is AppointmentAction.CREATE else visit_type
    result = build_scheduling_engine_input(ledger, visit_type=vt)

    # Mandatory fields are always present
    assert result.appointment_action == action, (
        f"Expected action={action.value}, got {result.appointment_action.value}"
    )
    assert result.specialty == specialty.strip(), (
        f"Expected specialty={specialty.strip()!r}, got {result.specialty!r}"
    )
    assert result.patient_id == patient_id.strip(), (
        f"Expected patient_id={patient_id.strip()!r}, got {result.patient_id!r}"
    )


# ---------------------------------------------------------------------------
# 30b: For `create` action, visit_type is required and included in the output
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    specialty=_nonempty_str,
    patient_id=_nonempty_str,
    visit_type=_visit_types,
    patient_verified=_patient_verified,
    location=_optional_known_str,
    provider_name=_optional_known_str,
)
@example(
    specialty="Cardiology",
    patient_id="12345",
    visit_type=VisitType.SICK,
    patient_verified="Success",
    location=None,
    provider_name=None,
)
@example(
    specialty="Internal Med",
    patient_id="67890",
    visit_type=VisitType.WELLNESS,
    patient_verified="N/A",
    location="Houston",
    provider_name="Dr. Adams",
)
@settings(max_examples=200)
def test_create_action_includes_visit_type(
    specialty: str,
    patient_id: str,
    visit_type: VisitType,
    patient_verified: str | None,
    location: str | None,
    provider_name: str | None,
) -> None:
    """For `create` action, visit_type is required and included in the output.

    **Validates: Requirements 14.2, 12.8**

    When the appointment_action is `create`, the scheduling engine input must
    include a resolved visit_type (sick or wellness).
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=AppointmentAction.CREATE.value,
        specialty=specialty,
        patient_id=patient_id,
        patient_verified=patient_verified,
        location=location,
        provider_name=provider_name,
    )

    result = build_scheduling_engine_input(ledger, visit_type=visit_type)

    assert result.visit_type is visit_type, (
        f"For create, visit_type must be {visit_type.value!r}, got "
        f"{result.visit_type.value if result.visit_type else None!r}"
    )
    # visit_type must appear in the payload dict
    payload = result.to_payload()
    assert "visit_type" in payload, "visit_type must appear in the create payload"
    assert payload["visit_type"] == visit_type.value


# ---------------------------------------------------------------------------
# 30c: For manage actions, visit_type is NEVER included even if passed
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    action=_manage_actions,
    specialty=_nonempty_str,
    patient_id=_nonempty_str,
    visit_type=_visit_types,
    patient_verified=_patient_verified,
    location=_optional_known_str,
    provider_name=_optional_known_str,
    existing_appointment_date=_optional_known_str,
)
@example(
    action=AppointmentAction.CANCEL,
    specialty="Oncology",
    patient_id="11111",
    visit_type=VisitType.SICK,
    patient_verified="Success",
    location=None,
    provider_name=None,
    existing_appointment_date="2025-01-20",
)
@example(
    action=AppointmentAction.RESCHEDULE,
    specialty="Pediatrics",
    patient_id="22222",
    visit_type=VisitType.WELLNESS,
    patient_verified="N/A",
    location="Memphis",
    provider_name="Dr. Park",
    existing_appointment_date=None,
)
@example(
    action=AppointmentAction.LIST,
    specialty="ENT",
    patient_id="33333",
    visit_type=VisitType.SICK,
    patient_verified=None,
    location=None,
    provider_name=None,
    existing_appointment_date=None,
)
@example(
    action=AppointmentAction.CONFIRM,
    specialty="Urology",
    patient_id="44444",
    visit_type=VisitType.WELLNESS,
    patient_verified="Fail",
    location="Denver",
    provider_name="Dr. Kim",
    existing_appointment_date="2025-07-04",
)
@settings(max_examples=200)
def test_manage_actions_never_include_visit_type(
    action: AppointmentAction,
    specialty: str,
    patient_id: str,
    visit_type: VisitType,
    patient_verified: str | None,
    location: str | None,
    provider_name: str | None,
    existing_appointment_date: str | None,
) -> None:
    """For manage actions (cancel/reschedule/list/confirm), visit_type is NEVER included.

    **Validates: Requirements 14.2, 12.8**

    Even if a visit_type is passed to the builder, manage actions never carry it.
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=action.value,
        specialty=specialty,
        patient_id=patient_id,
        patient_verified=patient_verified,
        location=location,
        provider_name=provider_name,
        existing_appointment_date=existing_appointment_date,
    )

    result = build_scheduling_engine_input(ledger, visit_type=visit_type)

    assert result.visit_type is None, (
        f"Manage action {action.value!r} must NEVER have visit_type, "
        f"got {result.visit_type!r}"
    )
    # visit_type must NOT appear in the payload dict
    payload = result.to_payload()
    assert "visit_type" not in payload, (
        f"Manage action {action.value!r} payload must not contain visit_type"
    )


# ---------------------------------------------------------------------------
# 30d: location, provider_name, existing_appointment_date are included ONLY
#      when known (non-None, non-empty)
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    action=_appointment_actions,
    specialty=_nonempty_str,
    patient_id=_nonempty_str,
    visit_type=_visit_types,
    location=_optional_known_str,
    provider_name=_optional_known_str,
    existing_appointment_date=_optional_known_str,
)
@example(
    action=AppointmentAction.CREATE,
    specialty="Rheumatology",
    patient_id="88888",
    visit_type=VisitType.SICK,
    location=None,
    provider_name=None,
    existing_appointment_date=None,
)
@example(
    action=AppointmentAction.CANCEL,
    specialty="Gastro",
    patient_id="99999",
    visit_type=VisitType.WELLNESS,
    location="Orlando",
    provider_name="Dr. White",
    existing_appointment_date="2025-08-15",
)
@settings(max_examples=200)
def test_optional_fields_included_only_when_known(
    action: AppointmentAction,
    specialty: str,
    patient_id: str,
    visit_type: VisitType,
    location: str | None,
    provider_name: str | None,
    existing_appointment_date: str | None,
) -> None:
    """location, provider_name, existing_appointment_date are included ONLY when known.

    **Validates: Requirements 14.2, 12.8**

    When a field is None or blank on the ledger, it must not appear in the engine
    input. When it holds a non-empty value, it must be present.
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=action.value,
        specialty=specialty,
        patient_id=patient_id,
        location=location,
        provider_name=provider_name,
        existing_appointment_date=existing_appointment_date,
    )

    vt = visit_type if action is AppointmentAction.CREATE else None
    result = build_scheduling_engine_input(ledger, visit_type=vt)

    def _is_known(value: str | None) -> bool:
        return value is not None and bool(value.strip())

    # location
    if _is_known(location):
        assert result.location is not None, "Known location must be in result"
        assert result.location == location.strip()
    else:
        assert result.location is None, "Unknown location must be None in result"

    # provider_name
    if _is_known(provider_name):
        assert result.provider_name is not None, "Known provider_name must be in result"
        assert result.provider_name == provider_name.strip()
    else:
        assert result.provider_name is None, "Unknown provider_name must be None in result"

    # existing_appointment_date
    if _is_known(existing_appointment_date):
        assert result.existing_appointment_date is not None, (
            "Known existing_appointment_date must be in result"
        )
        assert result.existing_appointment_date == existing_appointment_date.strip()
    else:
        assert result.existing_appointment_date is None, (
            "Unknown existing_appointment_date must be None in result"
        )


# ---------------------------------------------------------------------------
# 30e: The full CallStateLedger is carried on the result (Req 12.8)
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    action=_appointment_actions,
    specialty=_nonempty_str,
    patient_id=_nonempty_str,
    visit_type=_visit_types,
    patient_verified=_patient_verified,
    location=_optional_known_str,
    provider_name=_optional_known_str,
    existing_appointment_date=_optional_known_str,
)
@example(
    action=AppointmentAction.CREATE,
    specialty="Allergy",
    patient_id="10001",
    visit_type=VisitType.WELLNESS,
    patient_verified="Success",
    location="San Diego",
    provider_name="Dr. Patel",
    existing_appointment_date=None,
)
@example(
    action=AppointmentAction.LIST,
    specialty="Pulmonology",
    patient_id="20002",
    visit_type=VisitType.SICK,
    patient_verified=None,
    location=None,
    provider_name=None,
    existing_appointment_date=None,
)
@settings(max_examples=200)
def test_full_ledger_carried_on_result(
    action: AppointmentAction,
    specialty: str,
    patient_id: str,
    visit_type: VisitType,
    patient_verified: str | None,
    location: str | None,
    provider_name: str | None,
    existing_appointment_date: str | None,
) -> None:
    """The full CallStateLedger is carried on the result (Req 12.8).

    **Validates: Requirements 14.2, 12.8**

    The Scheduling Engine handoff must pass the complete Call State Ledger
    including specialty, location, provider_name, appointment_action, verification
    status, and all other ledger fields.
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=action.value,
        specialty=specialty,
        patient_id=patient_id,
        patient_verified=patient_verified,
        location=location,
        provider_name=provider_name,
        existing_appointment_date=existing_appointment_date,
    )

    vt = visit_type if action is AppointmentAction.CREATE else None
    result = build_scheduling_engine_input(ledger, visit_type=vt)

    # The full ledger is the exact same instance passed in
    assert result.ledger is ledger, (
        "The full CallStateLedger must be carried on the SchedulingEngineInput (Req 12.8)"
    )
    # Verify key ledger fields are accessible through result.ledger
    assert result.ledger.appointment_action == action.value
    assert result.ledger.patient_verified == patient_verified
    assert result.ledger.location == location
    assert result.ledger.provider_name == provider_name


# ---------------------------------------------------------------------------
# 30f: Missing mandatory fields raise SchedulingInputError
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    action=_appointment_actions,
    patient_id=_nonempty_str,
    visit_type=_visit_types,
)
@example(
    action=AppointmentAction.CREATE,
    patient_id="12345",
    visit_type=VisitType.SICK,
)
@example(
    action=AppointmentAction.CANCEL,
    patient_id="99999",
    visit_type=VisitType.WELLNESS,
)
@settings(max_examples=200)
def test_missing_specialty_raises_error(
    action: AppointmentAction,
    patient_id: str,
    visit_type: VisitType,
) -> None:
    """Missing specialty raises SchedulingInputError.

    **Validates: Requirements 14.2, 12.8**

    specialty is mandatory for all appointment actions.
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=action.value,
        specialty=None,
        patient_id=patient_id,
    )

    with pytest.raises(SchedulingInputError):
        build_scheduling_engine_input(ledger, visit_type=visit_type)


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    action=_appointment_actions,
    specialty=_nonempty_str,
    visit_type=_visit_types,
)
@example(
    action=AppointmentAction.CREATE,
    specialty="Cardiology",
    visit_type=VisitType.WELLNESS,
)
@example(
    action=AppointmentAction.RESCHEDULE,
    specialty="ENT",
    visit_type=VisitType.SICK,
)
@settings(max_examples=200)
def test_missing_patient_id_raises_error(
    action: AppointmentAction,
    specialty: str,
    visit_type: VisitType,
) -> None:
    """Missing patient_id raises SchedulingInputError.

    **Validates: Requirements 14.2, 12.8**

    A verified patient_id is mandatory for all appointment actions.
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=action.value,
        specialty=specialty,
        patient_id=None,
    )

    with pytest.raises(SchedulingInputError):
        build_scheduling_engine_input(ledger, visit_type=visit_type)


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    specialty=_nonempty_str,
    patient_id=_nonempty_str,
)
@example(specialty="Cardiology", patient_id="12345")
@settings(max_examples=200)
def test_missing_appointment_action_raises_error(
    specialty: str,
    patient_id: str,
) -> None:
    """Missing appointment_action raises SchedulingInputError.

    **Validates: Requirements 14.2, 12.8**

    appointment_action is mandatory for all handoffs.
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=None,
        specialty=specialty,
        patient_id=patient_id,
    )

    with pytest.raises(SchedulingInputError):
        build_scheduling_engine_input(ledger, visit_type=VisitType.SICK)


# ---------------------------------------------------------------------------
# 30g: Missing visit_type for create raises SchedulingInputError
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness
@given(
    specialty=_nonempty_str,
    patient_id=_nonempty_str,
    patient_verified=_patient_verified,
)
@example(specialty="Cardiology", patient_id="12345", patient_verified="Success")
@example(specialty="Neurology", patient_id="67890", patient_verified=None)
@settings(max_examples=200)
def test_missing_visit_type_for_create_raises_error(
    specialty: str,
    patient_id: str,
    patient_verified: str | None,
) -> None:
    """Missing visit_type for create action raises SchedulingInputError.

    **Validates: Requirements 14.2, 12.8**

    For a `create` action, Scheduling Init must resolve visit_type before the
    Engine handoff. Missing visit_type for create is an error.
    """
    # Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness

    ledger = CallStateLedger(
        appointment_action=AppointmentAction.CREATE.value,
        specialty=specialty,
        patient_id=patient_id,
        patient_verified=patient_verified,
    )

    with pytest.raises(SchedulingInputError):
        build_scheduling_engine_input(ledger, visit_type=None)
