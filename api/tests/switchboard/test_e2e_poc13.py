"""E2E acceptance scenario tests: POC-13

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes. They do NOT use a live LLM or TTS pipeline; instead they:

1. Drive the pure logic functions (classify_appointment_action,
   build_scheduling_engine_input, should_ask).
2. Invoke the mock connector tools (scheduling_engine with provider_name for
   preferred-provider-unavailable scenario).
3. Walk through a complete E2E scenario: existing patient create with preferred
   provider unavailable, alternative providers offered without re-asking facts.

Scenarios:
  POC-13 — Preferred provider unavailable for visit type. Engine returns that
            the preferred provider cannot see patient for visit type →
            scheduling agent offers alternative provider at same location →
            does not re-ask visit reason or discharge date.
            Validates Properties P3, P30.

Requirements: 20.15 (Req 14.3, 14.4)
"""

from __future__ import annotations


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
from api.services.switchboard.ledger import CallStateLedger, reduce_ledger, should_ask
from api.services.switchboard.scheduling import (
    VisitReasonSignals,
    VisitType,
    build_scheduling_engine_input,
    determine_visit_type,
    resolve_visit_type,
    visit_type_applies_to_action,
)
from api.services.switchboard.tools import get_connector_tool


# ---------------------------------------------------------------------------
# POC-13 Pure logic: classify_appointment_action for create with provider pref
# ---------------------------------------------------------------------------


class TestPOC13ClassifyCreate:
    """POC-13 Pure logic: classify_appointment_action recognizes create with provider preference.

    Requirements: 20.15 (Req 7.6, 12.1; Property P11)
    """

    def test_classify_create_with_provider_preference(self) -> None:
        """classify_appointment_action recognizes 'I want to book with Dr. Smith'."""
        result = classify_appointment_action(
            "I want to book an appointment with Dr. Smith"
        )
        assert result == AppointmentAction.CREATE

    def test_classify_create_schedule_with_specific_doctor(self) -> None:
        """classify_appointment_action recognizes 'schedule with Dr. Jones'."""
        result = classify_appointment_action(
            "I want to schedule an appointment with Dr. Jones"
        )
        assert result == AppointmentAction.CREATE

    def test_classify_create_book_with_preferred_provider(self) -> None:
        """classify_appointment_action recognizes 'book appointment with my usual doctor'."""
        result = classify_appointment_action(
            "Can I book an appointment with my usual doctor?"
        )
        assert result == AppointmentAction.CREATE


# ---------------------------------------------------------------------------
# POC-13 Pure logic: build_scheduling_engine_input includes provider_name
# ---------------------------------------------------------------------------


class TestPOC13SchedulingEngineInputWithProvider:
    """POC-13 Pure logic: build_scheduling_engine_input includes provider_name (Property P30).

    Requirements: 20.15 (Req 14.2, 14.3, 12.8)
    """

    def test_engine_input_includes_provider_name_when_known(self) -> None:
        """build_scheduling_engine_input includes provider_name in result when set on ledger."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
            provider_name="Dr. Smith",
        )
        result = build_scheduling_engine_input(ledger, visit_type=VisitType.WELLNESS)
        assert result.provider_name == "Dr. Smith"

    def test_engine_payload_includes_provider_name(self) -> None:
        """Payload from build_scheduling_engine_input includes provider_name key when known."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
            provider_name="Dr. Smith",
        )
        result = build_scheduling_engine_input(ledger, visit_type=VisitType.WELLNESS)
        payload = result.to_payload()
        assert payload["provider_name"] == "Dr. Smith"
        assert payload["appointment_action"] == "create"
        assert payload["specialty"] == "primary_care"
        assert payload["visit_type"] == "wellness"

    def test_engine_payload_excludes_provider_name_when_unknown(self) -> None:
        """Payload omits provider_name key when not set on the ledger."""
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
        assert "provider_name" not in payload

    def test_engine_input_carries_full_ledger(self) -> None:
        """The engine input carries the full Call State Ledger (Req 12.8)."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
            provider_name="Dr. Smith",
        )
        result = build_scheduling_engine_input(ledger, visit_type=VisitType.WELLNESS)
        assert result.ledger is ledger


# ---------------------------------------------------------------------------
# POC-13 Pure logic: should_ask returns False for populated fields (Property P3)
# ---------------------------------------------------------------------------


class TestPOC13NeverReAskPopulatedFields:
    """POC-13 Pure logic: should_ask returns False for already-populated fields (Property P3).

    The "no re-ask" property: once a field is populated on the ledger,
    should_ask returns False, meaning the switchboard never re-collects it.
    This validates that when the preferred provider is unavailable,
    the scheduling agent does NOT re-ask visit_reason, visit_type, specialty,
    or provider_name.

    Requirements: 20.15 (Req 15.4, REQ-SCHED-12, AC-18; Property P3)
    """

    def test_should_ask_visit_type_false_when_set(self) -> None:
        """should_ask('visit_type', ledger) is False after visit_type is set."""
        ledger = CallStateLedger(visit_type="wellness")
        assert should_ask("visit_type", ledger) is False

    def test_should_ask_visit_reason_false_when_set(self) -> None:
        """should_ask('visit_reason', ledger) is False after visit_reason is set."""
        ledger = CallStateLedger(visit_reason="annual physical")
        assert should_ask("visit_reason", ledger) is False

    def test_should_ask_specialty_false_when_set(self) -> None:
        """should_ask('specialty', ledger) is False after specialty is set."""
        ledger = CallStateLedger(specialty="primary_care")
        assert should_ask("specialty", ledger) is False

    def test_should_ask_provider_name_false_when_set(self) -> None:
        """should_ask('provider_name', ledger) is False after provider_name is set."""
        ledger = CallStateLedger(provider_name="Dr. Smith")
        assert should_ask("provider_name", ledger) is False

    def test_should_ask_patient_id_false_when_set(self) -> None:
        """should_ask('patient_id', ledger) is False after patient_id is set."""
        ledger = CallStateLedger(patient_id="mock-patient-5558675309")
        assert should_ask("patient_id", ledger) is False

    def test_all_poc13_fields_not_reasked_after_population(self) -> None:
        """All fields relevant to POC-13 return should_ask=False when populated."""
        ledger = CallStateLedger(
            visit_type="wellness",
            visit_reason="annual checkup",
            specialty="primary_care",
            provider_name="Dr. Smith",
            patient_id="mock-patient-5558675309",
            appointment_action="create",
        )
        for field in (
            "visit_type",
            "visit_reason",
            "specialty",
            "provider_name",
            "patient_id",
            "appointment_action",
        ):
            assert should_ask(field, ledger) is False, (
                f"Expected should_ask('{field}', ledger) to be False"
            )


# ---------------------------------------------------------------------------
# POC-13 Mock connector tools: scheduling_engine with preferred provider
# ---------------------------------------------------------------------------


class TestPOC13ConnectorTools:
    """POC-13 Mock connector tools: scheduling_engine returns alternatives when preferred provider given.

    When a provider_name is supplied for a create action, the mock engine
    simulates "preferred provider unavailable" by returning alternative_offered
    with slots from DIFFERENT providers (not the preferred one).

    Requirements: 20.15 (Req 14.3, 14.4, REQ-SCHED-12, AC-18)
    """

    async def test_scheduling_engine_preferred_provider_returns_alternatives(
        self,
    ) -> None:
        """Engine returns action_result='alternative_offered' when provider_name is given."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "create",
                "visit_type": "wellness",
                "provider_name": "Dr. Smith",
            }
        )
        assert result.action_result == "alternative_offered"
        assert len(result.slots) >= 1

    async def test_alternative_slots_have_different_providers(self) -> None:
        """Alternative slots have provider names different from the preferred provider."""
        engine_tool = get_connector_tool("scheduling_engine")
        preferred = "Dr. Smith"
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "create",
                "visit_type": "wellness",
                "provider_name": preferred,
            }
        )
        # Each slot's provider_name must NOT be the preferred provider
        for slot in result.slots:
            assert slot.provider_name != preferred, (
                f"Slot {slot.slot_id} should offer an alternative, not the preferred provider"
            )

    async def test_scheduling_engine_no_provider_returns_slots_offered(self) -> None:
        """Engine returns action_result='slots_offered' when NO provider_name is given (backward compat)."""
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

    async def test_scheduling_engine_reschedule_with_provider_returns_alternatives(
        self,
    ) -> None:
        """Engine returns alternatives for reschedule with preferred provider too."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "reschedule",
                "provider_name": "Dr. Jones",
            }
        )
        assert result.action_result == "alternative_offered"
        assert len(result.slots) >= 1
        for slot in result.slots:
            assert slot.provider_name != "Dr. Jones"


# ---------------------------------------------------------------------------
# POC-13 E2E scenario walkthrough: preferred provider unavailable,
# alternative offered without re-asking already-collected facts
# ---------------------------------------------------------------------------


class TestPOC13E2EScenarioWalkthrough:
    """POC-13 E2E scenario: preferred provider unavailable, alternative without re-ask.

    Scripted trace:
      1. Greeting phase: after_hours=False, ANI lookup done
      2. Business Hours: intent=Scheduling, appointment_action=create,
         patient_status=existing, specialty=primary_care, provider_name=Dr. Smith
      3. Authentication: auth required → DOB match → patient_verified=Success
      4. Scheduling Init: visit_type=wellness (reason is clear — wellness signal)
      5. Build engine input with provider_name=Dr. Smith → payload includes it
      6. Scheduling Engine: preferred provider unavailable → alternatives offered
      7. Verify: no field is re-asked (should_ask returns False for all
         already-populated fields)

    Requirements: 20.15 (Req 14.3, 14.4, REQ-SCHED-12, AC-18, POC-13)
    """

    async def test_e2e_poc13_preferred_provider_unavailable(self) -> None:
        """E2E POC-13: preferred provider unavailable, alternative offered without re-ask.

        Validates Properties P3, P30:
        - P3: Never re-ask a populated field (should_ask returns False)
        - P30: Engine input completeness (specialty, patient_id, appointment_action,
                visit_type for create, provider_name when known)
        """
        # ── Step 1: Greeting phase (ANI lookup, after_hours=False) ────────
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

        # ── Step 2: Business Hours — classify create intent with provider ─
        # Caller says: "I want to book an appointment with Dr. Smith"
        action = classify_appointment_action(
            "I want to book an appointment with Dr. Smith"
        )
        assert action == AppointmentAction.CREATE

        # Update ledger with BH decisions including preferred provider
        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Scheduling",
                "patient_status": "existing",
                "appointment_action": action.value,
                "specialty": "primary_care",
                "provider_name": "Dr. Smith",
                "visit_reason": "annual checkup",
            },
        )
        assert ledger.intent == "Scheduling"
        assert ledger.patient_status == "existing"
        assert ledger.appointment_action == "create"
        assert ledger.specialty == "primary_care"
        assert ledger.provider_name == "Dr. Smith"
        assert ledger.visit_reason == "annual checkup"

        # visit_type is NOT set on the switchboard (Req 12.4)
        assert ledger.visit_type is None
        assert visit_type_applies_to_action(action) is True

        # ── Step 3: Authentication ────────────────────────────────────────
        assert auth_required(ledger.intent, ledger.patient_status) is True

        # Gate closed
        assert ledger.patient_verified is None
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        # DOB match → patient_verified=Success
        verified_value = patient_verified_from_dob(dob_match=True)
        assert verified_value == PATIENT_VERIFIED_SUCCESS

        ledger = reduce_ledger(ledger, {"patient_verified": verified_value})
        assert ledger.patient_verified == "Success"

        # Gate open
        assert is_patient_verified_resolved(ledger.patient_verified) is True
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

        # ── Step 4: Scheduling Init — visit_type resolved from clear reason ─
        # "annual checkup" is a clear wellness signal → resolves directly
        signals = VisitReasonSignals(
            has_wellness_signal=True, has_symptom_signal=False
        )
        assert signals.reason_known is True
        assert resolve_visit_type(signals) == VisitType.WELLNESS

        decision = determine_visit_type(signals)
        assert decision.must_ask is False
        assert decision.visit_type == VisitType.WELLNESS

        # Set visit_type on ledger
        ledger = reduce_ledger(ledger, {"visit_type": decision.visit_type.value})
        assert ledger.visit_type == "wellness"

        # ── Step 5: Build engine input — includes provider_name (P30) ─────
        engine_input = build_scheduling_engine_input(
            ledger, visit_type=VisitType.WELLNESS
        )
        assert engine_input.appointment_action == AppointmentAction.CREATE
        assert engine_input.specialty == "primary_care"
        assert engine_input.patient_id == "mock-patient-5558675309"
        assert engine_input.visit_type == VisitType.WELLNESS
        assert engine_input.provider_name == "Dr. Smith"

        # Payload includes provider_name
        payload = engine_input.to_payload()
        assert payload["provider_name"] == "Dr. Smith"
        assert payload["visit_type"] == "wellness"
        assert payload["appointment_action"] == "create"
        assert payload["specialty"] == "primary_care"
        assert payload["patient_id"] == "mock-patient-5558675309"

        # ── Step 6: Scheduling Engine — preferred provider unavailable ────
        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": engine_input.specialty,
                "patient_id": engine_input.patient_id,
                "appointment_action": engine_input.appointment_action.value,
                "visit_type": engine_input.visit_type.value,
                "provider_name": engine_input.provider_name,
            }
        )
        # Engine reports preferred provider is unavailable and offers alternatives
        assert engine_result.action_result == "alternative_offered"
        assert len(engine_result.slots) >= 1

        # Alternative slots are from DIFFERENT providers (not Dr. Smith)
        for slot in engine_result.slots:
            assert slot.provider_name != "Dr. Smith", (
                f"Slot {slot.slot_id} should be from an alternative provider"
            )
            assert slot.slot_id
            assert slot.start

        # ── Step 7: Verify no re-ask (Property P3) ───────────────────────
        # After the engine returns alternatives, the scheduling agent must NOT
        # re-ask any facts already collected. Verify via should_ask:
        assert should_ask("visit_type", ledger) is False, "visit_type already set"
        assert should_ask("visit_reason", ledger) is False, "visit_reason already set"
        assert should_ask("specialty", ledger) is False, "specialty already set"
        assert should_ask("provider_name", ledger) is False, "provider_name already set"
        assert should_ask("patient_id", ledger) is False, "patient_id already set"
        assert should_ask("appointment_action", ledger) is False, (
            "appointment_action already set"
        )

        # ── Complete scenario summary ────────────────────────────────────
        # POC-13 validated:
        # - Create classified correctly (Property P11) ✓
        # - Specialty and provider_name collected during BH ✓
        # - Auth required → gate closed → DOB match → gate open ✓
        # - Visit reason clear → visit_type=wellness resolved (no re-ask) ✓
        # - Engine input includes provider_name (Property P30) ✓
        # - Engine returns alternative_offered (preferred unavailable) ✓
        # - Alternative slots are from different providers ✓
        # - No facts re-asked: should_ask=False for all populated fields (P3) ✓

    async def test_e2e_poc13_no_reask_after_alternative_offered(self) -> None:
        """E2E POC-13 variant: verify comprehensive no-reask after alternative offered.

        Sets up a fully-populated ledger simulating a call where all facts have
        been collected, then verifies that after the engine offers alternatives,
        none of the already-collected fields would be re-asked.
        """
        # Setup: fully-populated ledger after authentication and scheduling init
        ledger = CallStateLedger(
            after_hours=False,
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
            provider_name="Dr. Smith",
            visit_reason="annual wellness exam",
            visit_type="wellness",
            greeting_ani_lookup_done=True,
            greeting_ani_match_count=1,
            caller_name="Bob Wilson",
        )

        # Invoke engine with preferred provider
        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "create",
                "visit_type": "wellness",
                "provider_name": "Dr. Smith",
            }
        )
        assert engine_result.action_result == "alternative_offered"

        # After alternatives are offered, verify NO field is re-asked (P3, AC-18)
        fields_never_reasked = [
            "visit_type",
            "visit_reason",
            "specialty",
            "provider_name",
            "patient_id",
            "appointment_action",
            "intent",
            "patient_status",
            "patient_verified",
            "caller_name",
        ]
        for field in fields_never_reasked:
            assert should_ask(field, ledger) is False, (
                f"should_ask('{field}') must be False — facts must not be re-asked "
                f"after alternative provider is offered (AC-18)"
            )
