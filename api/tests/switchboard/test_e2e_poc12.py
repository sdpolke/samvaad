"""E2E acceptance scenario tests: POC-12

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes. They do NOT use a live LLM or TTS pipeline; instead they:

1. Drive the pure logic functions (resolve_visit_type, determine_visit_type,
   resolve_disambiguation_answer, visit_type_applies_to_action,
   classify_appointment_action, auth_required, build_scheduling_engine_input).
2. Invoke the mock connector tools (scheduling_engine with visit_type for create).
3. Walk through a complete E2E scenario: existing patient create with wellness +
   symptom disambiguation from Greeting through Scheduling Engine.

Scenarios:
  POC-12 — Wellness + symptom disambiguation. Caller says "I need a physical
            because my hand hurts" → Scheduling Init asks wellness vs sick for
            hand → sets visit_type from answer → Engine proceeds.
            Validates Property P28.

Requirements: 20.14 (Req 13.2, 13.4, 13.5, 13.6)
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
    classify_appointment_action,
)
from api.services.switchboard.ledger import CallStateLedger, reduce_ledger
from api.services.switchboard.scheduling import (
    SchedulingInputError,
    VisitReasonSignals,
    VisitType,
    VisitTypeOutcome,
    build_scheduling_engine_input,
    determine_visit_type,
    resolve_disambiguation_answer,
    resolve_visit_type,
    visit_type_applies_to_action,
)
from api.services.switchboard import scripts
from api.services.switchboard.tools import get_connector_tool


# ---------------------------------------------------------------------------
# POC-12 Pure logic: visit-type resolution cases
# ---------------------------------------------------------------------------


class TestPOC12VisitTypeResolution:
    """POC-12 Pure logic: resolve_visit_type and determine_visit_type.

    Requirements: 20.14 (Req 13.2, 13.4, 13.5, 13.6; Property P28)
    """

    def test_wellness_signal_only_resolves_wellness(self) -> None:
        """Wellness signal only → RESOLVED, visit_type=wellness."""
        signals = VisitReasonSignals(has_wellness_signal=True, has_symptom_signal=False)
        assert resolve_visit_type(signals) == VisitType.WELLNESS

        decision = determine_visit_type(signals)
        assert decision.outcome == VisitTypeOutcome.RESOLVED
        assert decision.visit_type == VisitType.WELLNESS
        assert decision.question is None
        assert decision.must_ask is False

    def test_symptom_signal_only_resolves_sick(self) -> None:
        """Symptom signal only → RESOLVED, visit_type=sick."""
        signals = VisitReasonSignals(has_wellness_signal=False, has_symptom_signal=True)
        assert resolve_visit_type(signals) == VisitType.SICK

        decision = determine_visit_type(signals)
        assert decision.outcome == VisitTypeOutcome.RESOLVED
        assert decision.visit_type == VisitType.SICK
        assert decision.question is None
        assert decision.must_ask is False

    def test_both_signals_ask_disambiguation(self) -> None:
        """Both wellness + symptom signals → ASK_DISAMBIGUATION (POC-12 scenario)."""
        signals = VisitReasonSignals(has_wellness_signal=True, has_symptom_signal=True)
        # resolve_visit_type returns wellness (both-indicated default)
        assert resolve_visit_type(signals) == VisitType.WELLNESS

        decision = determine_visit_type(signals)
        assert decision.outcome == VisitTypeOutcome.ASK_DISAMBIGUATION
        assert decision.visit_type == VisitType.WELLNESS
        assert decision.question == scripts.SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION
        assert decision.must_ask is True

    def test_neither_signal_ask_reason(self) -> None:
        """Neither signal → ASK_REASON."""
        signals = VisitReasonSignals(has_wellness_signal=False, has_symptom_signal=False)
        assert resolve_visit_type(signals) is None

        decision = determine_visit_type(signals)
        assert decision.outcome == VisitTypeOutcome.ASK_REASON
        assert decision.visit_type is None
        assert decision.question == scripts.SCHED_INIT_VISIT_REASON
        assert decision.must_ask is True


# ---------------------------------------------------------------------------
# POC-12 Pure logic: disambiguation answer resolution
# ---------------------------------------------------------------------------


class TestPOC12DisambiguationAnswer:
    """POC-12 Pure logic: resolve_disambiguation_answer (Req 13.5).

    Requirements: 20.14 (Req 13.5; Property P28)
    """

    def test_wellness_answer_resolves_wellness(self) -> None:
        """answer_is_wellness=True, answer_is_symptom=False → wellness."""
        result = resolve_disambiguation_answer(
            answer_is_wellness=True, answer_is_symptom=False
        )
        assert result == VisitType.WELLNESS

    def test_symptom_answer_resolves_sick(self) -> None:
        """answer_is_wellness=False, answer_is_symptom=True → sick."""
        result = resolve_disambiguation_answer(
            answer_is_wellness=False, answer_is_symptom=True
        )
        assert result == VisitType.SICK

    def test_both_indicated_defaults_to_wellness(self) -> None:
        """answer_is_wellness=True, answer_is_symptom=True → wellness (Req 13.5)."""
        result = resolve_disambiguation_answer(
            answer_is_wellness=True, answer_is_symptom=True
        )
        assert result == VisitType.WELLNESS

    def test_neither_indicated_defaults_to_wellness(self) -> None:
        """answer_is_wellness=False, answer_is_symptom=False → wellness (safe default)."""
        result = resolve_disambiguation_answer(
            answer_is_wellness=False, answer_is_symptom=False
        )
        assert result == VisitType.WELLNESS


# ---------------------------------------------------------------------------
# POC-12 Pure logic: visit_type applies only to create
# ---------------------------------------------------------------------------


class TestPOC12VisitTypeAppliesToCreate:
    """POC-12 Pure logic: visit_type_applies_to_action(CREATE) → True.

    Requirements: 20.14 (Req 13.7; Property P28)
    """

    def test_visit_type_applies_to_create(self) -> None:
        """visit_type_applies_to_action(CREATE) → True."""
        assert visit_type_applies_to_action(AppointmentAction.CREATE) is True

    def test_visit_type_does_not_apply_to_manage_actions(self) -> None:
        """visit_type_applies_to_action returns False for all manage actions."""
        for action in (
            AppointmentAction.CANCEL,
            AppointmentAction.RESCHEDULE,
            AppointmentAction.LIST,
            AppointmentAction.CONFIRM,
        ):
            assert visit_type_applies_to_action(action) is False, (
                f"Expected False for manage action {action.value}"
            )


# ---------------------------------------------------------------------------
# POC-12 Pure logic: appointment_action classification for create
# ---------------------------------------------------------------------------


class TestPOC12ClassifyCreate:
    """POC-12 Pure logic: classify_appointment_action recognizes create speech.

    Requirements: 20.14 (Req 7.6, 12.1; Property P11)
    """

    def test_classify_create_need_physical(self) -> None:
        """classify_appointment_action recognizes 'I need a physical because my hand hurts'."""
        result = classify_appointment_action(
            "I need a physical because my hand hurts"
        )
        assert result == AppointmentAction.CREATE

    def test_classify_create_book_appointment(self) -> None:
        """classify_appointment_action recognizes 'I'd like to book an appointment'."""
        result = classify_appointment_action("I'd like to book an appointment")
        assert result == AppointmentAction.CREATE

    def test_classify_create_schedule(self) -> None:
        """classify_appointment_action recognizes 'I want to schedule a visit'."""
        result = classify_appointment_action("I want to schedule a visit")
        assert result == AppointmentAction.CREATE


# ---------------------------------------------------------------------------
# POC-12 Pure logic: auth gate for Scheduling/existing
# ---------------------------------------------------------------------------


class TestPOC12AuthGate:
    """POC-12 Pure logic: auth gate for existing-patient create.

    Requirements: 20.14 (Req 9.2, 9.3)
    """

    def test_auth_required_scheduling_existing(self) -> None:
        """auth_required('Scheduling', 'existing') → True."""
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
# POC-12 Pure logic: scheduling engine input with visit_type for create
# ---------------------------------------------------------------------------


class TestPOC12SchedulingEngineInput:
    """POC-12 Pure logic: build_scheduling_engine_input for create with visit_type (Property P30).

    Requirements: 20.14 (Req 14.2, 12.8, 13.2)
    """

    def test_engine_input_requires_visit_type_for_create(self) -> None:
        """build_scheduling_engine_input raises if visit_type is None for create."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        with pytest.raises(SchedulingInputError, match="visit_type is required"):
            build_scheduling_engine_input(ledger, visit_type=None)

    def test_engine_input_succeeds_with_visit_type_wellness(self) -> None:
        """build_scheduling_engine_input succeeds for create with visit_type=WELLNESS."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=VisitType.WELLNESS)
        assert result.appointment_action == AppointmentAction.CREATE
        assert result.specialty == "primary_care"
        assert result.patient_id == "mock-patient-5558675309"
        assert result.visit_type == VisitType.WELLNESS

    def test_engine_payload_includes_visit_type(self) -> None:
        """Payload from build_scheduling_engine_input for create includes visit_type key."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=VisitType.WELLNESS)
        payload = result.to_payload()
        assert payload["visit_type"] == "wellness"
        assert payload["appointment_action"] == "create"
        assert payload["specialty"] == "primary_care"
        assert payload["patient_id"] == "mock-patient-5558675309"

    def test_engine_input_carries_full_ledger(self) -> None:
        """The engine input carries the full Call State Ledger (Req 12.8)."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=VisitType.SICK)
        assert result.ledger is ledger


# ---------------------------------------------------------------------------
# POC-12 Mock connector tools: scheduling_engine with visit_type for create
# ---------------------------------------------------------------------------


class TestPOC12ConnectorTools:
    """POC-12 Mock connector tools: scheduling_engine with visit_type for create.

    Requirements: 20.14 (Req 14.2)
    """

    async def test_scheduling_engine_returns_slots_for_create_with_visit_type(
        self,
    ) -> None:
        """Scheduling Engine mock returns action_result='slots_offered' for create with visit_type."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "create",
                "visit_type": "wellness",
            }
        )
        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1
        for slot in result.slots:
            assert slot.slot_id
            assert slot.start

    async def test_scheduling_engine_create_with_sick_visit_type(self) -> None:
        """Scheduling Engine mock handles create with visit_type=sick."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "create",
                "visit_type": "sick",
            }
        )
        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1


# ---------------------------------------------------------------------------
# POC-12 E2E scenario walkthrough: wellness-vs-sick disambiguation from
# Greeting through Scheduling Engine
# ---------------------------------------------------------------------------


class TestPOC12E2EScenarioWalkthrough:
    """POC-12 E2E scenario: wellness-vs-sick disambiguation.

    Scripted trace:
      1. Greeting phase: after_hours=False, ANI lookup done
      2. Business Hours: intent=Scheduling, appointment_action=create,
         patient_status=existing
      3. Specialty confirmed (e.g. "primary_care")
      4. Authentication: auth required → DOB match → patient_verified=Success
      5. Scheduling Init: visit reason signals have BOTH wellness + symptom →
         determine_visit_type returns ASK_DISAMBIGUATION with the mandated question
      6. Caller answers "the physical" (wellness) →
         resolve_disambiguation_answer(wellness=True, symptom=False) →
         VisitType.WELLNESS
      7. Build engine input with visit_type=WELLNESS → succeeds, payload includes
         visit_type="wellness"
      8. Scheduling Engine invoked with visit_type → returns slots

    Requirements: 20.14 (Req 13.2, 13.4, 13.5, 13.6, 14.2, POC-12)
    """

    async def test_e2e_poc12_wellness_vs_sick_disambiguation(self) -> None:
        """E2E POC-12: full disambiguation scenario from Greeting to Scheduling Engine.

        Validates Property P28:
        - Both wellness + symptom signals → ASK_DISAMBIGUATION
        - Disambiguation question is the mandated verbatim line
        - Caller wellness answer → visit_type=WELLNESS
        - Engine input includes visit_type for create
        - Engine returns slots_offered
        """
        # ── Step 1: Greeting phase (ANI lookup, after_hours=False) ────────
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

        # ── Step 2: Business Hours — classify create intent ───────────────
        # Caller says: "I need a physical because my hand hurts"
        action = classify_appointment_action(
            "I need a physical because my hand hurts"
        )
        assert action == AppointmentAction.CREATE

        # Update ledger with BH decisions
        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Scheduling",
                "patient_status": "existing",
                "appointment_action": action.value,
            },
        )
        assert ledger.intent == "Scheduling"
        assert ledger.patient_status == "existing"
        assert ledger.appointment_action == "create"

        # visit_type is NOT set on the switchboard (Req 12.4)
        assert ledger.visit_type is None
        # But visit_type DOES apply to create actions
        assert visit_type_applies_to_action(action) is True

        # ── Step 3: Specialty confirmed ───────────────────────────────────
        ledger = reduce_ledger(ledger, {"specialty": "primary_care"})
        assert ledger.specialty == "primary_care"

        # ── Step 4: Authentication ────────────────────────────────────────
        # Auth is required for Scheduling/existing
        assert auth_required(ledger.intent, ledger.patient_status) is True

        # Gate is CLOSED while patient_verified is None
        assert ledger.patient_verified is None
        assert is_patient_verified_resolved(ledger.patient_verified) is False
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        # DOB match → patient_verified=Success
        verified_value = patient_verified_from_dob(dob_match=True)
        assert verified_value == PATIENT_VERIFIED_SUCCESS

        ledger = reduce_ledger(ledger, {"patient_verified": verified_value})
        assert ledger.patient_verified == "Success"

        # Gate is now OPEN
        assert is_patient_verified_resolved(ledger.patient_verified) is True
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

        # ── Step 5: Scheduling Init — visit reason has BOTH signals ───────
        # The caller said "I need a physical because my hand hurts":
        #   - "physical" = wellness signal
        #   - "my hand hurts" = symptom signal
        signals = VisitReasonSignals(
            has_wellness_signal=True, has_symptom_signal=True
        )
        assert signals.reason_known is True

        # determine_visit_type with both signals → ASK_DISAMBIGUATION
        decision = determine_visit_type(signals)
        assert decision.outcome == VisitTypeOutcome.ASK_DISAMBIGUATION
        assert decision.must_ask is True
        assert decision.question == scripts.SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION
        # The default resolution (if both remain) is wellness
        assert decision.visit_type == VisitType.WELLNESS

        # ── Step 6: Caller answers "the physical" (wellness) ──────────────
        # The disambiguation question was asked; caller answered indicating wellness
        resolved_type = resolve_disambiguation_answer(
            answer_is_wellness=True, answer_is_symptom=False
        )
        assert resolved_type == VisitType.WELLNESS

        # ── Step 7: Build engine input with visit_type=WELLNESS ───────────
        engine_input = build_scheduling_engine_input(
            ledger, visit_type=resolved_type
        )
        assert engine_input.appointment_action == AppointmentAction.CREATE
        assert engine_input.specialty == "primary_care"
        assert engine_input.patient_id == "mock-patient-5558675309"
        assert engine_input.visit_type == VisitType.WELLNESS

        # Payload includes visit_type
        payload = engine_input.to_payload()
        assert payload["visit_type"] == "wellness"
        assert payload["appointment_action"] == "create"
        assert payload["specialty"] == "primary_care"
        assert payload["patient_id"] == "mock-patient-5558675309"

        # ── Step 8: Scheduling Engine invoked with visit_type → slots ─────
        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": engine_input.specialty,
                "patient_id": engine_input.patient_id,
                "appointment_action": engine_input.appointment_action.value,
                "visit_type": engine_input.visit_type.value,
            }
        )
        assert engine_result.action_result == "slots_offered"
        assert len(engine_result.slots) >= 1
        for slot in engine_result.slots:
            assert slot.slot_id
            assert slot.start

        # ── Complete scenario summary ────────────────────────────────────
        # POC-12 validated:
        # - Create classified correctly (Property P11) ✓
        # - visit_type applies to create (Req 13.7) ✓
        # - Auth required and gate works (Property P13) ✓
        # - Both signals → ASK_DISAMBIGUATION (Req 13.4, Property P28) ✓
        # - Disambiguation question is the mandated verbatim line ✓
        # - Caller wellness answer → visit_type=WELLNESS (Req 13.5) ✓
        # - Engine input includes visit_type for create (Req 14.2, P30) ✓
        # - Engine returns slots_offered for create with visit_type ✓

    async def test_e2e_poc12_disambiguation_symptom_answer(self) -> None:
        """E2E POC-12 variant: caller answers the disambiguation with symptom.

        Same setup as the main scenario but the caller answers "for my hand"
        (symptom) instead of "the physical" (wellness).
        """
        # Setup: ledger with authenticated existing patient + create action
        ledger = CallStateLedger(
            after_hours=False,
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
            greeting_ani_lookup_done=True,
        )

        # Both signals present → disambiguation
        signals = VisitReasonSignals(
            has_wellness_signal=True, has_symptom_signal=True
        )
        decision = determine_visit_type(signals)
        assert decision.outcome == VisitTypeOutcome.ASK_DISAMBIGUATION

        # Caller answers "for my hand" (symptom) → sick
        resolved_type = resolve_disambiguation_answer(
            answer_is_wellness=False, answer_is_symptom=True
        )
        assert resolved_type == VisitType.SICK

        # Build engine input with visit_type=SICK
        engine_input = build_scheduling_engine_input(
            ledger, visit_type=resolved_type
        )
        assert engine_input.visit_type == VisitType.SICK

        # Payload includes visit_type=sick
        payload = engine_input.to_payload()
        assert payload["visit_type"] == "sick"

        # Engine returns slots
        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": engine_input.specialty,
                "patient_id": engine_input.patient_id,
                "appointment_action": engine_input.appointment_action.value,
                "visit_type": engine_input.visit_type.value,
            }
        )
        assert engine_result.action_result == "slots_offered"
        assert len(engine_result.slots) >= 1
