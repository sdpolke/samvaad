"""E2E acceptance scenario tests: POC-14, POC-15, POC-16

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes. They do NOT use a live LLM or TTS pipeline; instead they:

1. Drive the pure logic functions (classify_appointment_action,
   appointment_action_consequences, auth_required, may_proceed_to_routing,
   build_scheduling_engine_input, visit_type_applies_to_action).
2. Invoke the mock connector tools (scheduling_handoff, scheduling_engine).
3. Walk through complete E2E scenarios: existing patient cancel/list/confirm
   from Greeting through Scheduling Engine.

Scenarios:
  POC-14 — existing-patient cancel.
  POC-15 — existing-patient list upcoming appointments.
  POC-16 — existing-patient confirm appointment.

Requirements: 20.16 (POC-14), 20.17 (POC-15), 20.18 (POC-16)
"""

from __future__ import annotations

import pytest

from api.services.switchboard.auth import (
    PATIENT_VERIFIED_SUCCESS,
    auth_required,
    is_patient_verified_resolved,
    may_proceed_to_routing,
    patient_verified_from_dob,
)
from api.services.switchboard.business_hours import (
    AppointmentAction,
    appointment_action_consequences,
    classify_appointment_action,
    is_manage_action,
)
from api.services.switchboard.ledger import CallStateLedger, reduce_ledger
from api.services.switchboard.scheduling import (
    build_scheduling_engine_input,
    visit_type_applies_to_action,
)
from api.services.switchboard.tools import get_connector_tool


# ---------------------------------------------------------------------------
# POC-14 Pure logic: classify_appointment_action for cancel
# ---------------------------------------------------------------------------


class TestPOC14ClassifyCancel:
    """POC-14 Pure logic: classify_appointment_action recognizes cancel speech.

    Requirements: 20.16 (Req 7.6, 7.7, 12.1, Property 11)
    """

    def test_classify_cancel_direct(self) -> None:
        """classify_appointment_action recognizes 'I need to cancel my appointment'."""
        result = classify_appointment_action("I need to cancel my appointment")
        assert result == AppointmentAction.CANCEL

    def test_classify_cancel_call_off(self) -> None:
        """classify_appointment_action recognizes 'call off my visit'."""
        result = classify_appointment_action("I want to call off my visit")
        assert result == AppointmentAction.CANCEL

    def test_classify_cancel_drop(self) -> None:
        """classify_appointment_action recognizes 'drop my appointment'."""
        result = classify_appointment_action("I need to drop my appointment")
        assert result == AppointmentAction.CANCEL

    def test_classify_cancel_get_rid_of(self) -> None:
        """classify_appointment_action recognizes 'get rid of my appointment'."""
        result = classify_appointment_action("I want to get rid of my appointment")
        assert result == AppointmentAction.CANCEL

    def test_cancel_is_manage_action(self) -> None:
        """is_manage_action(CANCEL) -> True."""
        assert is_manage_action(AppointmentAction.CANCEL) is True


# ---------------------------------------------------------------------------
# POC-15 Pure logic: classify_appointment_action for list
# ---------------------------------------------------------------------------


class TestPOC15ClassifyList:
    """POC-15 Pure logic: classify_appointment_action recognizes list speech.

    Requirements: 20.17 (Req 7.6, 7.7, 12.1, Property 11)
    """

    def test_classify_list_direct(self) -> None:
        """classify_appointment_action recognizes 'list my appointments'."""
        result = classify_appointment_action("Can you list my appointments?")
        assert result == AppointmentAction.LIST

    def test_classify_list_what_appointment(self) -> None:
        """classify_appointment_action recognizes 'what appointments do I have'."""
        result = classify_appointment_action("What appointments do I have?")
        assert result == AppointmentAction.LIST

    def test_classify_list_which_appointment(self) -> None:
        """classify_appointment_action recognizes 'which appointment is coming up'."""
        result = classify_appointment_action("Which appointment do I have next?")
        assert result == AppointmentAction.LIST

    def test_classify_list_do_i_have(self) -> None:
        """classify_appointment_action recognizes 'do I have any visits'."""
        result = classify_appointment_action("Do I have any upcoming visits?")
        assert result == AppointmentAction.LIST

    def test_classify_list_any_appointment(self) -> None:
        """classify_appointment_action recognizes 'any appointments scheduled'."""
        result = classify_appointment_action("Are there any appointments for me?")
        assert result == AppointmentAction.LIST

    def test_classify_list_upcoming(self) -> None:
        """classify_appointment_action recognizes 'upcoming appointments'."""
        result = classify_appointment_action("I want to check my upcoming visits")
        assert result == AppointmentAction.LIST

    def test_classify_list_my_appointments(self) -> None:
        """classify_appointment_action recognizes 'my appointments'."""
        result = classify_appointment_action("Tell me about my appointments")
        assert result == AppointmentAction.LIST

    def test_list_is_manage_action(self) -> None:
        """is_manage_action(LIST) -> True."""
        assert is_manage_action(AppointmentAction.LIST) is True


# ---------------------------------------------------------------------------
# POC-16 Pure logic: classify_appointment_action for confirm
# ---------------------------------------------------------------------------


class TestPOC16ClassifyConfirm:
    """POC-16 Pure logic: classify_appointment_action recognizes confirm speech.

    Requirements: 20.18 (Req 7.6, 7.7, 12.1, Property 11)
    """

    def test_classify_confirm_direct(self) -> None:
        """classify_appointment_action recognizes 'confirm my appointment'."""
        result = classify_appointment_action("I'd like to confirm my appointment")
        assert result == AppointmentAction.CONFIRM

    def test_classify_confirm_verify(self) -> None:
        """classify_appointment_action recognizes 'verify my appointment'."""
        result = classify_appointment_action("Can you verify my appointment?")
        assert result == AppointmentAction.CONFIRM

    def test_classify_confirm_still_on(self) -> None:
        """classify_appointment_action recognizes 'is my appointment still on'."""
        result = classify_appointment_action("Is my appointment still on?")
        assert result == AppointmentAction.CONFIRM

    def test_classify_confirm_still_scheduled(self) -> None:
        """classify_appointment_action recognizes 'still scheduled'."""
        result = classify_appointment_action("Am I still scheduled for Thursday?")
        assert result == AppointmentAction.CONFIRM

    def test_classify_confirm_double_check(self) -> None:
        """classify_appointment_action recognizes 'double-check'."""
        result = classify_appointment_action("I want to double-check my visit")
        assert result == AppointmentAction.CONFIRM

    def test_classify_confirm_make_sure(self) -> None:
        """classify_appointment_action recognizes 'make sure'."""
        result = classify_appointment_action("Just want to make sure I still have my appointment")
        assert result == AppointmentAction.CONFIRM

    def test_confirm_is_manage_action(self) -> None:
        """is_manage_action(CONFIRM) -> True."""
        assert is_manage_action(AppointmentAction.CONFIRM) is True


# ---------------------------------------------------------------------------
# POC-14/15/16 Pure logic: appointment_action_consequences for all three
# ---------------------------------------------------------------------------


class TestPOC14_15_16ManageActionConsequences:
    """Pure logic: appointment_action_consequences for cancel/list/confirm (Property P12).

    Requirements: 20.16, 20.17, 20.18 (Req 7.8, 12.2, 13.7)
    """

    @pytest.mark.parametrize("action", [
        AppointmentAction.CANCEL,
        AppointmentAction.LIST,
        AppointmentAction.CONFIRM,
    ])
    def test_consequences_patient_status_existing(self, action: AppointmentAction) -> None:
        """Manage-action consequence: patient_status=existing."""
        cons = appointment_action_consequences(action)
        assert cons.patient_status == "existing"

    @pytest.mark.parametrize("action", [
        AppointmentAction.CANCEL,
        AppointmentAction.LIST,
        AppointmentAction.CONFIRM,
    ])
    def test_consequences_no_new_or_existing_question(self, action: AppointmentAction) -> None:
        """Manage-action consequence: ask_new_or_existing=False."""
        cons = appointment_action_consequences(action)
        assert cons.ask_new_or_existing is False

    @pytest.mark.parametrize("action", [
        AppointmentAction.CANCEL,
        AppointmentAction.LIST,
        AppointmentAction.CONFIRM,
    ])
    def test_consequences_require_specialty_before_auth(self, action: AppointmentAction) -> None:
        """Manage-action consequence: require_specialty_before_auth=True."""
        cons = appointment_action_consequences(action)
        assert cons.require_specialty_before_auth is True

    @pytest.mark.parametrize("action", [
        AppointmentAction.CANCEL,
        AppointmentAction.LIST,
        AppointmentAction.CONFIRM,
    ])
    def test_consequences_no_visit_type_on_switchboard(self, action: AppointmentAction) -> None:
        """Manage-action consequence: set_visit_type_on_switchboard=False."""
        cons = appointment_action_consequences(action)
        assert cons.set_visit_type_on_switchboard is False


# ---------------------------------------------------------------------------
# POC-14/15/16 Pure logic: visit_type does not apply to cancel/list/confirm
# ---------------------------------------------------------------------------


class TestPOC14_15_16VisitTypeNotApplicable:
    """Pure logic: visit_type_applies_to_action returns False for cancel/list/confirm.

    Requirements: 20.16, 20.17, 20.18 (Req 13.7, Property P30)
    """

    @pytest.mark.parametrize("action", [
        AppointmentAction.CANCEL,
        AppointmentAction.LIST,
        AppointmentAction.CONFIRM,
    ])
    def test_visit_type_not_applicable(self, action: AppointmentAction) -> None:
        """visit_type_applies_to_action(action) -> False for manage actions."""
        assert visit_type_applies_to_action(action) is False


# ---------------------------------------------------------------------------
# POC-14/15/16 Pure logic: auth gate for Scheduling/existing
# ---------------------------------------------------------------------------


class TestPOC14_15_16AuthGate:
    """Pure logic: auth gate for existing-patient cancel/list/confirm.

    Requirements: 20.16, 20.17, 20.18 (Req 9.2, 9.3)
    """

    def test_auth_required_scheduling_existing(self) -> None:
        """auth_required('Scheduling', 'existing') -> True."""
        assert auth_required("Scheduling", "existing") is True

    def test_gate_closed_before_verification(self) -> None:
        """GATE-AUTH: may_proceed_to_routing is False while patient_verified is None."""
        assert may_proceed_to_routing("Scheduling", "existing", None) is False

    def test_gate_open_after_success(self) -> None:
        """GATE-AUTH: may_proceed_to_routing is True once patient_verified=Success."""
        assert (
            may_proceed_to_routing("Scheduling", "existing", PATIENT_VERIFIED_SUCCESS)
            is True
        )


# ---------------------------------------------------------------------------
# POC-14/15/16 Pure logic: build_scheduling_engine_input for cancel/list/confirm
# ---------------------------------------------------------------------------


class TestPOC14_15_16SchedulingEngineInput:
    """Pure logic: build_scheduling_engine_input for cancel/list/confirm (Property P30).

    Requirements: 20.16, 20.17, 20.18 (Req 14.2, 12.8, 13.7)
    """

    @pytest.mark.parametrize("action_str,action_enum", [
        ("cancel", AppointmentAction.CANCEL),
        ("list", AppointmentAction.LIST),
        ("confirm", AppointmentAction.CONFIRM),
    ])
    def test_engine_input_succeeds_without_visit_type(
        self, action_str: str, action_enum: AppointmentAction
    ) -> None:
        """build_scheduling_engine_input succeeds for manage actions without visit_type."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action=action_str,
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=None)
        assert result.appointment_action == action_enum
        assert result.specialty == "primary_care"
        assert result.patient_id == "mock-patient-5558675309"
        assert result.visit_type is None

    @pytest.mark.parametrize("action_str", ["cancel", "list", "confirm"])
    def test_engine_payload_excludes_visit_type(self, action_str: str) -> None:
        """Payload from build_scheduling_engine_input for manage actions has no visit_type key."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action=action_str,
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=None)
        payload = result.to_payload()
        assert "visit_type" not in payload
        assert payload["appointment_action"] == action_str
        assert payload["specialty"] == "primary_care"
        assert payload["patient_id"] == "mock-patient-5558675309"

    def test_cancel_engine_input_includes_existing_appointment_date(self) -> None:
        """existing_appointment_date is passed through for cancel when known."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="cancel",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
            existing_appointment_date="2026-02-15",
        )
        result = build_scheduling_engine_input(ledger, visit_type=None)
        assert result.existing_appointment_date == "2026-02-15"
        payload = result.to_payload()
        assert payload["existing_appointment_date"] == "2026-02-15"

    @pytest.mark.parametrize("action_str", ["cancel", "list", "confirm"])
    def test_engine_input_carries_full_ledger(self, action_str: str) -> None:
        """The engine input carries the full Call State Ledger (Req 12.8)."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action=action_str,
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=None)
        assert result.ledger is ledger


# ---------------------------------------------------------------------------
# POC-14/15/16 Mock connector tools: scheduling_engine and scheduling_handoff
# ---------------------------------------------------------------------------


class TestPOC14_15_16ConnectorTools:
    """Mock connector tools: scheduling_engine and scheduling_handoff for cancel/list/confirm.

    Requirements: 20.16, 20.17, 20.18 (Req 14.2, 12.8)
    """

    async def test_scheduling_engine_returns_cancelled_for_cancel(self) -> None:
        """Scheduling Engine mock returns action_result='cancelled' for cancel."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "cancel",
            }
        )
        assert result.action_result == "cancelled"
        assert result.appointment_details == {"status": "cancelled"}

    async def test_scheduling_engine_returns_listed_for_list(self) -> None:
        """Scheduling Engine mock returns action_result='listed' for list."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "list",
            }
        )
        assert result.action_result == "listed"
        assert result.appointment_details == {"appointments": []}

    async def test_scheduling_engine_returns_confirmed_for_confirm(self) -> None:
        """Scheduling Engine mock returns action_result='confirmed' for confirm."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "confirm",
            }
        )
        assert result.action_result == "confirmed"
        assert result.appointment_details == {"status": "confirmed"}

    @pytest.mark.parametrize("action", ["cancel", "list", "confirm"])
    async def test_scheduling_handoff_surfaces_action_context(self, action: str) -> None:
        """Scheduling handoff surfaces specialty and appointment_action for manage actions."""
        handoff_tool = get_connector_tool("scheduling_handoff")
        result = await handoff_tool.invoke(
            {
                "ledger": {
                    "specialty": "primary_care",
                    "appointment_action": action,
                    "patient_status": "existing",
                    "patient_id": "mock-patient-5558675309",
                    "patient_verified": "Success",
                }
            }
        )
        assert result.appointment_action == action
        assert result.specialty == "primary_care"
        assert result.ready is True


# ---------------------------------------------------------------------------
# POC-14 E2E scenario walkthrough: existing patient cancel
# ---------------------------------------------------------------------------


class TestPOC14E2EScenario:
    """POC-14 E2E scenario: existing-patient cancel.

    Scripted trace:
      1. Greeting phase: after_hours=False, ANI lookup done, patient matched
      2. Business Hours: intent=Scheduling, appointment_action=cancel ->
         patient_status=existing, no new/existing question, require specialty
         before auth, no visit_type on switchboard
      3. Specialty confirmed before auth
      4. Authentication: auth required for Scheduling/existing -> gate closed ->
         DOB match -> patient_verified=Success -> gate open
      5. Scheduling handoff with full ledger
      6. Scheduling Init does NOT set visit_type (manage action, Req 13.7)
      7. Scheduling Engine receives: specialty, patient_id,
         appointment_action=cancel, NO visit_type -> returns cancelled

    Requirements: 20.16 (Req 7.8, 9.2, 12.2, 12.8, 13.7, 14.2, POC-14)
    """

    async def test_e2e_poc14_existing_patient_cancel(self) -> None:
        """E2E POC-14: full cancel scenario from Greeting to Scheduling Engine."""
        # Step 1: Greeting phase (ANI lookup, after_hours=False)
        ledger = CallStateLedger(after_hours=False)
        ledger = reduce_ledger(
            ledger,
            {
                "caller_name": "Jane Smith",
                "greeting_ani_lookup_done": True,
                "greeting_ani_match_count": 1,
                "patient_id": "mock-patient-5558675309",
            },
        )
        assert ledger.after_hours is False
        assert ledger.greeting_ani_lookup_done is True
        assert ledger.patient_id == "mock-patient-5558675309"

        # Step 2: Business Hours — classify cancel intent
        action = classify_appointment_action("I need to cancel my appointment")
        assert action == AppointmentAction.CANCEL
        assert is_manage_action(action) is True

        cons = appointment_action_consequences(action)
        assert cons.patient_status == "existing"
        assert cons.ask_new_or_existing is False
        assert cons.require_specialty_before_auth is True
        assert cons.set_visit_type_on_switchboard is False

        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Scheduling",
                "patient_status": cons.patient_status,
                "appointment_action": action.value,
            },
        )
        assert ledger.intent == "Scheduling"
        assert ledger.patient_status == "existing"
        assert ledger.appointment_action == "cancel"
        assert ledger.visit_type is None
        assert visit_type_applies_to_action(action) is False

        # Step 3: Specialty confirmed before auth
        assert cons.require_specialty_before_auth is True
        ledger = reduce_ledger(ledger, {"specialty": "primary_care"})
        assert ledger.specialty == "primary_care"

        # Step 4: Authentication
        assert auth_required(ledger.intent, ledger.patient_status) is True
        assert ledger.patient_verified is None
        assert is_patient_verified_resolved(ledger.patient_verified) is False
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        verified_value = patient_verified_from_dob(dob_match=True)
        assert verified_value == PATIENT_VERIFIED_SUCCESS
        ledger = reduce_ledger(ledger, {"patient_verified": verified_value})
        assert ledger.patient_verified == "Success"
        assert is_patient_verified_resolved(ledger.patient_verified) is True
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

        # Step 5: Scheduling handoff with full ledger
        handoff_tool = get_connector_tool("scheduling_handoff")
        handoff_result = await handoff_tool.invoke(
            {"ledger": ledger.model_dump()}
        )
        assert handoff_result.specialty == "primary_care"
        assert handoff_result.appointment_action == "cancel"
        assert handoff_result.ready is True

        # Step 6: Scheduling Init does NOT set visit_type (Req 13.7)
        assert visit_type_applies_to_action(AppointmentAction.CANCEL) is False
        assert ledger.visit_type is None

        # Step 7: Scheduling Engine — cancel without visit_type
        ledger = reduce_ledger(
            ledger, {"existing_appointment_date": "2026-02-15"}
        )

        engine_input = build_scheduling_engine_input(ledger, visit_type=None)
        assert engine_input.appointment_action == AppointmentAction.CANCEL
        assert engine_input.specialty == "primary_care"
        assert engine_input.patient_id == "mock-patient-5558675309"
        assert engine_input.visit_type is None
        assert engine_input.existing_appointment_date == "2026-02-15"

        payload = engine_input.to_payload()
        assert "visit_type" not in payload
        assert payload["existing_appointment_date"] == "2026-02-15"

        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": engine_input.specialty,
                "patient_id": engine_input.patient_id,
                "appointment_action": engine_input.appointment_action.value,
                "existing_appointment_date": engine_input.existing_appointment_date,
            }
        )
        assert engine_result.action_result == "cancelled"
        assert engine_result.appointment_details == {"status": "cancelled"}


# ---------------------------------------------------------------------------
# POC-15 E2E scenario walkthrough: existing patient list
# ---------------------------------------------------------------------------


class TestPOC15E2EScenario:
    """POC-15 E2E scenario: existing-patient list upcoming appointments.

    Scripted trace:
      1. Greeting phase: after_hours=False, ANI lookup done, patient matched
      2. Business Hours: intent=Scheduling, appointment_action=list ->
         patient_status=existing, no new/existing question, require specialty
         before auth, no visit_type on switchboard
      3. Specialty confirmed before auth
      4. Authentication: auth required for Scheduling/existing -> gate closed ->
         DOB match -> patient_verified=Success -> gate open
      5. Scheduling handoff with full ledger
      6. Scheduling Init does NOT set visit_type (manage action, Req 13.7)
      7. Scheduling Engine receives: specialty, patient_id,
         appointment_action=list, NO visit_type -> returns listed

    Requirements: 20.17 (Req 7.8, 9.2, 12.2, 12.8, 13.7, 14.2, POC-15)
    """

    async def test_e2e_poc15_existing_patient_list(self) -> None:
        """E2E POC-15: full list scenario from Greeting to Scheduling Engine."""
        # Step 1: Greeting phase
        ledger = CallStateLedger(after_hours=False)
        ledger = reduce_ledger(
            ledger,
            {
                "caller_name": "Bob Wilson",
                "greeting_ani_lookup_done": True,
                "greeting_ani_match_count": 1,
                "patient_id": "mock-patient-5558675309",
            },
        )
        assert ledger.after_hours is False
        assert ledger.greeting_ani_lookup_done is True
        assert ledger.patient_id == "mock-patient-5558675309"

        # Step 2: Business Hours — classify list intent
        action = classify_appointment_action("What appointments do I have coming up?")
        assert action == AppointmentAction.LIST
        assert is_manage_action(action) is True

        cons = appointment_action_consequences(action)
        assert cons.patient_status == "existing"
        assert cons.ask_new_or_existing is False
        assert cons.require_specialty_before_auth is True
        assert cons.set_visit_type_on_switchboard is False

        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Scheduling",
                "patient_status": cons.patient_status,
                "appointment_action": action.value,
            },
        )
        assert ledger.intent == "Scheduling"
        assert ledger.patient_status == "existing"
        assert ledger.appointment_action == "list"
        assert ledger.visit_type is None
        assert visit_type_applies_to_action(action) is False

        # Step 3: Specialty confirmed before auth
        assert cons.require_specialty_before_auth is True
        ledger = reduce_ledger(ledger, {"specialty": "cardiology"})
        assert ledger.specialty == "cardiology"

        # Step 4: Authentication
        assert auth_required(ledger.intent, ledger.patient_status) is True
        assert ledger.patient_verified is None
        assert is_patient_verified_resolved(ledger.patient_verified) is False
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        verified_value = patient_verified_from_dob(dob_match=True)
        assert verified_value == PATIENT_VERIFIED_SUCCESS
        ledger = reduce_ledger(ledger, {"patient_verified": verified_value})
        assert ledger.patient_verified == "Success"
        assert is_patient_verified_resolved(ledger.patient_verified) is True
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

        # Step 5: Scheduling handoff with full ledger
        handoff_tool = get_connector_tool("scheduling_handoff")
        handoff_result = await handoff_tool.invoke(
            {"ledger": ledger.model_dump()}
        )
        assert handoff_result.specialty == "cardiology"
        assert handoff_result.appointment_action == "list"
        assert handoff_result.ready is True

        # Step 6: Scheduling Init does NOT set visit_type (Req 13.7)
        assert visit_type_applies_to_action(AppointmentAction.LIST) is False
        assert ledger.visit_type is None

        # Step 7: Scheduling Engine — list without visit_type
        engine_input = build_scheduling_engine_input(ledger, visit_type=None)
        assert engine_input.appointment_action == AppointmentAction.LIST
        assert engine_input.specialty == "cardiology"
        assert engine_input.patient_id == "mock-patient-5558675309"
        assert engine_input.visit_type is None

        payload = engine_input.to_payload()
        assert "visit_type" not in payload
        assert payload["appointment_action"] == "list"

        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": engine_input.specialty,
                "patient_id": engine_input.patient_id,
                "appointment_action": engine_input.appointment_action.value,
            }
        )
        assert engine_result.action_result == "listed"
        assert engine_result.appointment_details == {"appointments": []}


# ---------------------------------------------------------------------------
# POC-16 E2E scenario walkthrough: existing patient confirm
# ---------------------------------------------------------------------------


class TestPOC16E2EScenario:
    """POC-16 E2E scenario: existing-patient confirm appointment.

    Scripted trace:
      1. Greeting phase: after_hours=False, ANI lookup done, patient matched
      2. Business Hours: intent=Scheduling, appointment_action=confirm ->
         patient_status=existing, no new/existing question, require specialty
         before auth, no visit_type on switchboard
      3. Specialty confirmed before auth
      4. Authentication: auth required for Scheduling/existing -> gate closed ->
         DOB match -> patient_verified=Success -> gate open
      5. Scheduling handoff with full ledger
      6. Scheduling Init does NOT set visit_type (manage action, Req 13.7)
      7. Scheduling Engine receives: specialty, patient_id,
         appointment_action=confirm, NO visit_type -> returns confirmed

    Requirements: 20.18 (Req 7.8, 9.2, 12.2, 12.8, 13.7, 14.2, POC-16)
    """

    async def test_e2e_poc16_existing_patient_confirm(self) -> None:
        """E2E POC-16: full confirm scenario from Greeting to Scheduling Engine."""
        # Step 1: Greeting phase
        ledger = CallStateLedger(after_hours=False)
        ledger = reduce_ledger(
            ledger,
            {
                "caller_name": "Alice Johnson",
                "greeting_ani_lookup_done": True,
                "greeting_ani_match_count": 1,
                "patient_id": "mock-patient-5558675309",
            },
        )
        assert ledger.after_hours is False
        assert ledger.greeting_ani_lookup_done is True
        assert ledger.patient_id == "mock-patient-5558675309"

        # Step 2: Business Hours — classify confirm intent
        action = classify_appointment_action(
            "I want to confirm my appointment is still on"
        )
        assert action == AppointmentAction.CONFIRM
        assert is_manage_action(action) is True

        cons = appointment_action_consequences(action)
        assert cons.patient_status == "existing"
        assert cons.ask_new_or_existing is False
        assert cons.require_specialty_before_auth is True
        assert cons.set_visit_type_on_switchboard is False

        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Scheduling",
                "patient_status": cons.patient_status,
                "appointment_action": action.value,
            },
        )
        assert ledger.intent == "Scheduling"
        assert ledger.patient_status == "existing"
        assert ledger.appointment_action == "confirm"
        assert ledger.visit_type is None
        assert visit_type_applies_to_action(action) is False

        # Step 3: Specialty confirmed before auth
        assert cons.require_specialty_before_auth is True
        ledger = reduce_ledger(ledger, {"specialty": "dermatology"})
        assert ledger.specialty == "dermatology"

        # Step 4: Authentication
        assert auth_required(ledger.intent, ledger.patient_status) is True
        assert ledger.patient_verified is None
        assert is_patient_verified_resolved(ledger.patient_verified) is False
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        verified_value = patient_verified_from_dob(dob_match=True)
        assert verified_value == PATIENT_VERIFIED_SUCCESS
        ledger = reduce_ledger(ledger, {"patient_verified": verified_value})
        assert ledger.patient_verified == "Success"
        assert is_patient_verified_resolved(ledger.patient_verified) is True
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

        # Step 5: Scheduling handoff with full ledger
        handoff_tool = get_connector_tool("scheduling_handoff")
        handoff_result = await handoff_tool.invoke(
            {"ledger": ledger.model_dump()}
        )
        assert handoff_result.specialty == "dermatology"
        assert handoff_result.appointment_action == "confirm"
        assert handoff_result.ready is True

        # Step 6: Scheduling Init does NOT set visit_type (Req 13.7)
        assert visit_type_applies_to_action(AppointmentAction.CONFIRM) is False
        assert ledger.visit_type is None

        # Step 7: Scheduling Engine — confirm without visit_type
        engine_input = build_scheduling_engine_input(ledger, visit_type=None)
        assert engine_input.appointment_action == AppointmentAction.CONFIRM
        assert engine_input.specialty == "dermatology"
        assert engine_input.patient_id == "mock-patient-5558675309"
        assert engine_input.visit_type is None

        payload = engine_input.to_payload()
        assert "visit_type" not in payload
        assert payload["appointment_action"] == "confirm"

        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": engine_input.specialty,
                "patient_id": engine_input.patient_id,
                "appointment_action": engine_input.appointment_action.value,
            }
        )
        assert engine_result.action_result == "confirmed"
        assert engine_result.appointment_details == {"status": "confirmed"}
