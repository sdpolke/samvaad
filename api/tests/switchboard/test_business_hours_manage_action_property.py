"""Property-based test for manage-action consequences (task 8.6).

Covers Property 12 — Manage-action consequences
(Requirements 7.8, 12.2, 13.7).

The property verifies that for any ledger whose appointment_action is cancel,
reschedule, list, or confirm, the switchboard sets patient_status=existing, asks
no new/existing question, requires authentication after specialty is confirmed,
and Scheduling Init sets no visit_type.
"""

# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences

from __future__ import annotations

from typing import Optional

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.business_hours import (
    PATIENT_STATUS_EXISTING,
    AppointmentAction,
    appointment_action_consequences,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: any of the four manage actions
_manage_action = st.sampled_from(
    [
        AppointmentAction.CANCEL,
        AppointmentAction.RESCHEDULE,
        AppointmentAction.LIST,
        AppointmentAction.CONFIRM,
    ]
)

# Strategy: various patient_status inputs (manage actions must ignore these)
_any_patient_status: st.SearchStrategy[Optional[str]] = st.one_of(
    st.none(),
    st.just("existing"),
    st.just("new"),
    st.just(""),
    st.just("   "),
    st.just("\t"),
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "Zs")),
        min_size=0,
        max_size=20,
    ),
)

# Strategy: known patient_status values (non-empty, non-whitespace)
_known_patient_status = st.sampled_from(["existing", "new", "returning", "vip"])

# Strategy: unknown patient_status values (None or blank)
_unknown_patient_status: st.SearchStrategy[Optional[str]] = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),
    st.just("\t\n"),
)


# ===========================================================================
# Property 12: Manage-action consequences
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences
@given(
    action=_manage_action,
    patient_status=_any_patient_status,
)
@example(action=AppointmentAction.CANCEL, patient_status=None)
@example(action=AppointmentAction.RESCHEDULE, patient_status="existing")
@example(action=AppointmentAction.LIST, patient_status="new")
@example(action=AppointmentAction.CONFIRM, patient_status="   ")
@settings(max_examples=200)
def test_property_12_manage_action_sets_patient_status_existing(
    action: AppointmentAction,
    patient_status: Optional[str],
) -> None:
    """Manage actions always set patient_status to "existing" (Req 7.8, 12.2).

    **Validates: Requirements 7.8, 12.2, 13.7**

    For any manage action (cancel/reschedule/list/confirm), regardless of the
    prior patient_status on the ledger, the consequence sets patient_status to
    "existing". The manage-action caller is always treated as an existing patient.
    """
    result = appointment_action_consequences(action, patient_status)

    assert result.patient_status == PATIENT_STATUS_EXISTING, (
        f"VIOLATION of Req 7.8/12.2: manage action did not set patient_status=existing.\n"
        f"Action: {action.value}\n"
        f"Input patient_status: {patient_status!r}\n"
        f"Got patient_status: {result.patient_status!r}"
    )


# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences
@given(
    action=_manage_action,
    patient_status=_any_patient_status,
)
@example(action=AppointmentAction.CANCEL, patient_status=None)
@example(action=AppointmentAction.RESCHEDULE, patient_status="new")
@example(action=AppointmentAction.LIST, patient_status="existing")
@example(action=AppointmentAction.CONFIRM, patient_status="")
@settings(max_examples=200)
def test_property_12_manage_action_skips_new_existing_question(
    action: AppointmentAction,
    patient_status: Optional[str],
) -> None:
    """Manage actions never ask the new/existing question (Req 7.8, 12.2).

    **Validates: Requirements 7.8, 12.2, 13.7**

    For any manage action, ask_new_or_existing must be False and the
    new_existing_question must be None. The switchboard SHALL NOT ask the caller
    whether they are new or existing when the action is a manage action.
    """
    result = appointment_action_consequences(action, patient_status)

    assert result.ask_new_or_existing is False, (
        f"VIOLATION of Req 7.8/12.2: manage action asked new/existing.\n"
        f"Action: {action.value}\n"
        f"Input patient_status: {patient_status!r}"
    )
    assert result.new_existing_question is None, (
        f"VIOLATION: new_existing_question should be None for manage action.\n"
        f"Action: {action.value}\n"
        f"Got: {result.new_existing_question!r}"
    )


# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences
@given(
    action=_manage_action,
    patient_status=_any_patient_status,
)
@example(action=AppointmentAction.CANCEL, patient_status=None)
@example(action=AppointmentAction.RESCHEDULE, patient_status="existing")
@example(action=AppointmentAction.LIST, patient_status="new")
@example(action=AppointmentAction.CONFIRM, patient_status="   ")
@settings(max_examples=200)
def test_property_12_manage_action_requires_specialty_before_auth(
    action: AppointmentAction,
    patient_status: Optional[str],
) -> None:
    """Manage actions require confirmed specialty before authentication (Req 7.8, 12.2).

    **Validates: Requirements 7.8, 12.2, 13.7**

    For any manage action, require_specialty_before_auth must be True — the
    switchboard requires that specialty is confirmed before entering Authentication.
    """
    result = appointment_action_consequences(action, patient_status)

    assert result.require_specialty_before_auth is True, (
        f"VIOLATION of Req 7.8/12.2: manage action did not require specialty before auth.\n"
        f"Action: {action.value}\n"
        f"Input patient_status: {patient_status!r}"
    )


# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences
@given(
    action=_manage_action,
    patient_status=_any_patient_status,
)
@example(action=AppointmentAction.CANCEL, patient_status=None)
@example(action=AppointmentAction.RESCHEDULE, patient_status="existing")
@example(action=AppointmentAction.LIST, patient_status="new")
@example(action=AppointmentAction.CONFIRM, patient_status="")
@settings(max_examples=200)
def test_property_12_manage_action_does_not_set_visit_type(
    action: AppointmentAction,
    patient_status: Optional[str],
) -> None:
    """Manage actions never set visit_type on the switchboard (Req 13.7).

    **Validates: Requirements 7.8, 12.2, 13.7**

    For any manage action, set_visit_type_on_switchboard must be False. When
    appointment_action is cancel/reschedule/list/confirm, Scheduling Init SHALL NOT
    ask sick vs wellness and SHALL pass appointment_action and ledger context directly.
    """
    result = appointment_action_consequences(action, patient_status)

    assert result.set_visit_type_on_switchboard is False, (
        f"VIOLATION of Req 13.7: manage action set visit_type on switchboard.\n"
        f"Action: {action.value}\n"
        f"Input patient_status: {patient_status!r}"
    )


# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences
@given(
    action=_manage_action,
    patient_status=_any_patient_status,
)
@example(action=AppointmentAction.CANCEL, patient_status=None)
@example(action=AppointmentAction.RESCHEDULE, patient_status="new")
@example(action=AppointmentAction.LIST, patient_status="existing")
@example(action=AppointmentAction.CONFIRM, patient_status="random_value")
@settings(max_examples=200)
def test_property_12_manage_action_all_consequences_combined(
    action: AppointmentAction,
    patient_status: Optional[str],
) -> None:
    """All manage-action consequences hold simultaneously (Req 7.8, 12.2, 13.7).

    **Validates: Requirements 7.8, 12.2, 13.7**

    Comprehensive check: for any manage action with any patient_status input, ALL
    five consequence invariants hold at once:
    1. patient_status == "existing"
    2. ask_new_or_existing == False
    3. new_existing_question is None
    4. require_specialty_before_auth == True
    5. set_visit_type_on_switchboard == False
    """
    result = appointment_action_consequences(action, patient_status)

    assert result.patient_status == PATIENT_STATUS_EXISTING
    assert result.ask_new_or_existing is False
    assert result.new_existing_question is None
    assert result.require_specialty_before_auth is True
    assert result.set_visit_type_on_switchboard is False
    assert result.appointment_action == action


# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences
@given(patient_status=_unknown_patient_status)
@example(patient_status=None)
@example(patient_status="")
@example(patient_status="   ")
@settings(max_examples=200)
def test_property_12_create_with_unknown_status_asks_new_existing(
    patient_status: Optional[str],
) -> None:
    """Create with unknown patient_status DOES ask the new/existing question (contrast).

    **Validates: Requirements 7.8, 12.2, 13.7**

    This is the contrast case: when the action is create and patient_status is
    unknown (None/blank), the switchboard asks the new/existing question. This
    demonstrates that the manage-action path is distinct from the create path.
    """
    result = appointment_action_consequences(AppointmentAction.CREATE, patient_status)

    assert result.ask_new_or_existing is True, (
        f"Create with unknown patient_status should ask new/existing.\n"
        f"Input patient_status: {patient_status!r}"
    )
    assert result.new_existing_question is not None
    # Create does NOT require specialty before auth
    assert result.require_specialty_before_auth is False
    # visit_type is still not set on switchboard (even for create)
    assert result.set_visit_type_on_switchboard is False


# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences
@given(patient_status=_known_patient_status)
@example(patient_status="existing")
@example(patient_status="new")
@settings(max_examples=200)
def test_property_12_create_with_known_status_does_not_ask(
    patient_status: str,
) -> None:
    """Create with known patient_status does NOT re-ask new/existing.

    **Validates: Requirements 7.8, 12.2, 13.7**

    When the action is create but patient_status is already known (populated), the
    switchboard does not re-ask the new/existing question — it carries the known
    status forward.
    """
    result = appointment_action_consequences(AppointmentAction.CREATE, patient_status)

    assert result.ask_new_or_existing is False, (
        f"Create with known patient_status should NOT ask new/existing.\n"
        f"Input patient_status: {patient_status!r}"
    )
    assert result.new_existing_question is None
    # The known patient_status is preserved for create
    assert result.patient_status == patient_status
    # Create does NOT require specialty before auth
    assert result.require_specialty_before_auth is False
    # visit_type is still not set on switchboard
    assert result.set_visit_type_on_switchboard is False


# Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences
@given(action=st.sampled_from(list(AppointmentAction)))
@settings(max_examples=200)
def test_property_12_visit_type_never_set_on_switchboard(
    action: AppointmentAction,
) -> None:
    """set_visit_type_on_switchboard is always False for any action (Req 12.4, 13.7).

    **Validates: Requirements 7.8, 12.2, 13.7**

    Regardless of whether the action is create or a manage action, the switchboard
    never sets visit_type — it is always deferred to Scheduling Init downstream.
    """
    result = appointment_action_consequences(action, None)

    assert result.set_visit_type_on_switchboard is False, (
        f"visit_type should never be set on switchboard.\n"
        f"Action: {action.value}"
    )
