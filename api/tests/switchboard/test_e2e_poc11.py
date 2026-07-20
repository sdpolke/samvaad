"""E2E acceptance scenario tests: POC-11

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes. They do NOT use a live LLM or TTS pipeline; instead they:

1. Drive the pure logic functions (classify_appointment_action,
   appointment_action_consequences, auth_required, may_proceed_to_routing,
   build_scheduling_engine_input, visit_type_applies_to_action).
2. Invoke the mock connector tools (scheduling_handoff, scheduling_engine).
3. Assert graph structure (scheduling cluster edges, tool scoping).
4. Walk through a complete E2E scenario: existing patient reschedule from
   Greeting through Scheduling Engine.

Scenarios:
  POC-11 — existing-patient reschedule. The Switchboard confirms specialty,
            authenticates, hands off to Scheduling_Init without a visit type,
            and the Scheduling_Engine locates the appointment and offers new slots.
            Validates Properties P12, P30.

Requirements: 20.13 (Req 7.8, 12.2, 13.7, 14.2)
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
    appointment_action_consequences,
    classify_appointment_action,
    is_manage_action,
)
from api.services.switchboard.clusters.scheduling import build_scheduling_cluster
from api.services.switchboard.graph import build_switchboard_graph
from api.services.switchboard.ledger import CallStateLedger, reduce_ledger, should_ask
from api.services.switchboard.scheduling import (
    build_scheduling_engine_input,
    visit_type_applies_to_action,
)
from api.services.switchboard.tools import get_connector_tool


# ---------------------------------------------------------------------------
# POC-11 Pure logic: classify_appointment_action for reschedule
# ---------------------------------------------------------------------------


class TestPOC11ClassifyReschedule:
    """POC-11 Pure logic: classify_appointment_action recognizes reschedule speech.

    Requirements: 20.13 (Req 7.6, 7.7, 12.1, Property 11)
    """

    def test_classify_reschedule_direct(self) -> None:
        """classify_appointment_action recognizes 'I'd like to reschedule my appointment'."""
        result = classify_appointment_action("I'd like to reschedule my appointment")
        assert result == AppointmentAction.RESCHEDULE

    def test_classify_reschedule_move(self) -> None:
        """classify_appointment_action recognizes 'move my appointment'."""
        result = classify_appointment_action("I need to move my appointment")
        assert result == AppointmentAction.RESCHEDULE

    def test_classify_reschedule_change(self) -> None:
        """classify_appointment_action recognizes 'change my appointment'."""
        result = classify_appointment_action("Can I change my appointment time?")
        assert result == AppointmentAction.RESCHEDULE

    def test_reschedule_is_manage_action(self) -> None:
        """is_manage_action(RESCHEDULE) → True."""
        assert is_manage_action(AppointmentAction.RESCHEDULE) is True


# ---------------------------------------------------------------------------
# POC-11 Pure logic: appointment_action_consequences for reschedule
# ---------------------------------------------------------------------------


class TestPOC11ManageActionConsequences:
    """POC-11 Pure logic: appointment_action_consequences for reschedule (Property P12).

    Requirements: 20.13 (Req 7.8, 12.2, 13.7)
    """

    def test_consequences_patient_status_existing(self) -> None:
        """Reschedule consequence: patient_status=existing."""
        cons = appointment_action_consequences(AppointmentAction.RESCHEDULE)
        assert cons.patient_status == "existing"

    def test_consequences_no_new_or_existing_question(self) -> None:
        """Reschedule consequence: ask_new_or_existing=False."""
        cons = appointment_action_consequences(AppointmentAction.RESCHEDULE)
        assert cons.ask_new_or_existing is False

    def test_consequences_require_specialty_before_auth(self) -> None:
        """Reschedule consequence: require_specialty_before_auth=True."""
        cons = appointment_action_consequences(AppointmentAction.RESCHEDULE)
        assert cons.require_specialty_before_auth is True

    def test_consequences_no_visit_type_on_switchboard(self) -> None:
        """Reschedule consequence: set_visit_type_on_switchboard=False."""
        cons = appointment_action_consequences(AppointmentAction.RESCHEDULE)
        assert cons.set_visit_type_on_switchboard is False


# ---------------------------------------------------------------------------
# POC-11 Pure logic: visit_type does not apply to reschedule
# ---------------------------------------------------------------------------


class TestPOC11VisitTypeNotApplicable:
    """POC-11 Pure logic: visit_type_applies_to_action(RESCHEDULE) is False.

    Requirements: 20.13 (Req 13.7, Property P30)
    """

    def test_visit_type_not_applicable_to_reschedule(self) -> None:
        """visit_type_applies_to_action(RESCHEDULE) → False (manage action)."""
        assert visit_type_applies_to_action(AppointmentAction.RESCHEDULE) is False


# ---------------------------------------------------------------------------
# POC-11 Pure logic: auth gate for Scheduling/existing
# ---------------------------------------------------------------------------


class TestPOC11AuthGate:
    """POC-11 Pure logic: auth gate for existing-patient reschedule.

    Requirements: 20.13 (Req 9.2, 9.3)
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
# POC-11 Pure logic: build_scheduling_engine_input for reschedule
# ---------------------------------------------------------------------------


class TestPOC11SchedulingEngineInput:
    """POC-11 Pure logic: build_scheduling_engine_input for reschedule (Property P30).

    Requirements: 20.13 (Req 14.2, 12.8, 13.7)
    """

    def test_engine_input_succeeds_without_visit_type(self) -> None:
        """build_scheduling_engine_input succeeds for reschedule without visit_type."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="reschedule",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=None)
        assert result.appointment_action == AppointmentAction.RESCHEDULE
        assert result.specialty == "primary_care"
        assert result.patient_id == "mock-patient-5558675309"
        assert result.visit_type is None

    def test_engine_payload_excludes_visit_type(self) -> None:
        """Payload from build_scheduling_engine_input for reschedule has no visit_type key."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="reschedule",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=None)
        payload = result.to_payload()
        assert "visit_type" not in payload
        assert payload["appointment_action"] == "reschedule"
        assert payload["specialty"] == "primary_care"
        assert payload["patient_id"] == "mock-patient-5558675309"

    def test_engine_input_includes_existing_appointment_date(self) -> None:
        """existing_appointment_date is passed through when known on the ledger."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="reschedule",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
            existing_appointment_date="2026-01-10",
        )
        result = build_scheduling_engine_input(ledger, visit_type=None)
        assert result.existing_appointment_date == "2026-01-10"
        payload = result.to_payload()
        assert payload["existing_appointment_date"] == "2026-01-10"

    def test_engine_input_carries_full_ledger(self) -> None:
        """The engine input carries the full Call State Ledger (Req 12.8)."""
        ledger = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="reschedule",
            patient_verified="Success",
            patient_id="mock-patient-5558675309",
            specialty="primary_care",
        )
        result = build_scheduling_engine_input(ledger, visit_type=None)
        assert result.ledger is ledger


# ---------------------------------------------------------------------------
# POC-11 Mock connector tools: scheduling_engine and scheduling_handoff
# ---------------------------------------------------------------------------


class TestPOC11ConnectorTools:
    """POC-11 Mock connector tools: scheduling_engine and scheduling_handoff.

    Requirements: 20.13 (Req 14.2, 12.8)
    """

    async def test_scheduling_engine_returns_slots_for_reschedule(self) -> None:
        """Scheduling Engine mock returns action_result='slots_offered' for reschedule."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "reschedule",
                # No visit_type — reschedule is a manage action
            }
        )
        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1
        for slot in result.slots:
            assert slot.slot_id
            assert slot.start

    async def test_scheduling_engine_reschedule_with_existing_date(self) -> None:
        """Scheduling Engine mock handles reschedule with existing_appointment_date."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5558675309",
                "appointment_action": "reschedule",
                "existing_appointment_date": "2026-01-10",
            }
        )
        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1

    async def test_scheduling_handoff_surfaces_reschedule_context(self) -> None:
        """Scheduling handoff surfaces specialty and appointment_action=reschedule."""
        handoff_tool = get_connector_tool("scheduling_handoff")
        result = await handoff_tool.invoke(
            {
                "ledger": {
                    "specialty": "primary_care",
                    "appointment_action": "reschedule",
                    "patient_status": "existing",
                    "patient_id": "mock-patient-5558675309",
                    "patient_verified": "Success",
                }
            }
        )
        assert result.appointment_action == "reschedule"
        assert result.specialty == "primary_care"
        assert result.ready is True


# ---------------------------------------------------------------------------
# POC-11 Graph structure: scheduling cluster edges and tool scoping
# ---------------------------------------------------------------------------


class TestPOC11GraphStructure:
    """POC-11 Graph structure: scheduling cluster and tool scoping.

    Requirements: 20.13 (Req 12.6, 12.8)
    """

    def test_scheduling_init_has_scheduling_handoff_tool(self) -> None:
        """Scheduling Init node is scoped to scheduling_handoff tool."""
        wg = build_switchboard_graph()
        node = wg.nodes["scheduling_init"]
        assert node.tool_uuids is not None
        assert "scheduling_handoff" in node.tool_uuids

    def test_scheduling_engine_has_scheduling_engine_tool(self) -> None:
        """Scheduling Engine node is scoped to scheduling_engine tool."""
        wg = build_switchboard_graph()
        node = wg.nodes["scheduling_engine"]
        assert node.tool_uuids is not None
        assert "scheduling_engine" in node.tool_uuids

    def test_scheduling_cluster_init_to_engine_edge(self) -> None:
        """The scheduling cluster has an Init → Engine edge."""
        cluster = build_scheduling_cluster()
        init_to_engine = [
            e for e in cluster.edges
            if e.source == cluster.scheduling_init_id
            and e.target == cluster.scheduling_engine_id
        ]
        assert len(init_to_engine) == 1


# ---------------------------------------------------------------------------
# POC-11 E2E scenario walkthrough: existing patient reschedule from Greeting
# through Scheduling Engine
# ---------------------------------------------------------------------------


class TestPOC11E2EScenarioWalkthrough:
    """POC-11 E2E scenario: existing-patient reschedule.

    Scripted trace:
      1. Greeting phase: after_hours=False, ANI lookup done
      2. Business Hours: intent=Scheduling, appointment_action=reschedule →
         patient_status=existing, no new/existing question, require specialty
         before auth, no visit_type on switchboard
      3. Specialty confirmed before auth
      4. Authentication: auth required for Scheduling/existing → gate closed →
         DOB match → patient_verified=Success → gate open
      5. Scheduling handoff with full ledger
      6. Scheduling Init does NOT set visit_type (manage action, Req 13.7)
      7. Scheduling Engine receives: specialty, patient_id,
         appointment_action=reschedule, NO visit_type,
         existing_appointment_date when known → returns slots_offered

    Requirements: 20.13 (Req 7.8, 9.2, 12.2, 12.8, 13.7, 14.2, POC-11)
    """

    async def test_e2e_poc11_existing_patient_reschedule(self) -> None:
        """E2E POC-11: full reschedule scenario from Greeting to Scheduling Engine.

        Validates Properties P12, P30:
        - P12: manage-action consequences (patient_status=existing, no new/existing,
          specialty before auth, no visit_type on switchboard)
        - P30: engine-input completeness (reschedule without visit_type succeeds,
          existing_appointment_date passed through)
        """
        # ── Step 1: Greeting phase (ANI lookup, after_hours=False) ────────
        ledger = CallStateLedger(after_hours=False)
        ledger = reduce_ledger(
            ledger,
            {
                "caller_name": "John Doe",
                "greeting_ani_lookup_done": True,
                "greeting_ani_match_count": 1,
                "patient_id": "mock-patient-5558675309",
            },
        )
        assert ledger.after_hours is False
        assert ledger.greeting_ani_lookup_done is True
        assert ledger.patient_id == "mock-patient-5558675309"

        # ── Step 2: Business Hours — classify reschedule intent ───────────
        action = classify_appointment_action(
            "I'd like to reschedule my appointment"
        )
        assert action == AppointmentAction.RESCHEDULE
        assert is_manage_action(action) is True

        # Apply manage-action consequences (Property P12)
        cons = appointment_action_consequences(action)
        assert cons.patient_status == "existing"
        assert cons.ask_new_or_existing is False
        assert cons.require_specialty_before_auth is True
        assert cons.set_visit_type_on_switchboard is False

        # Update ledger with BH decisions
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
        assert ledger.appointment_action == "reschedule"

        # visit_type is NOT set on the switchboard (Req 12.4, 13.7)
        assert ledger.visit_type is None
        assert visit_type_applies_to_action(action) is False

        # ── Step 3: Specialty confirmed before auth ───────────────────────
        # For manage actions, specialty is required before auth (Req 7.8)
        assert cons.require_specialty_before_auth is True
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

        # ── Step 5: Scheduling handoff with full ledger ───────────────────
        handoff_tool = get_connector_tool("scheduling_handoff")
        handoff_result = await handoff_tool.invoke(
            {"ledger": ledger.model_dump()}
        )
        assert handoff_result.specialty == "primary_care"
        assert handoff_result.appointment_action == "reschedule"
        assert handoff_result.ready is True

        # ── Step 6: Scheduling Init does NOT set visit_type (Req 13.7) ────
        # For manage actions, Scheduling Init skips sick/wellness entirely.
        # visit_type_applies_to_action(RESCHEDULE) is False — no visit_type set.
        assert visit_type_applies_to_action(AppointmentAction.RESCHEDULE) is False
        assert ledger.visit_type is None
        # should_ask("visit_type", ledger) is True but irrelevant — Init
        # never asks it for manage actions (the action skips the question).
        assert should_ask("visit_type", ledger) is True

        # ── Step 7: Scheduling Engine — reschedule without visit_type ─────
        # Add existing_appointment_date (known for reschedule)
        ledger = reduce_ledger(
            ledger, {"existing_appointment_date": "2026-01-10"}
        )

        # Build engine input — must succeed without visit_type (Property P30)
        engine_input = build_scheduling_engine_input(ledger, visit_type=None)
        assert engine_input.appointment_action == AppointmentAction.RESCHEDULE
        assert engine_input.specialty == "primary_care"
        assert engine_input.patient_id == "mock-patient-5558675309"
        assert engine_input.visit_type is None
        assert engine_input.existing_appointment_date == "2026-01-10"

        # Payload has no visit_type key
        payload = engine_input.to_payload()
        assert "visit_type" not in payload
        assert payload["existing_appointment_date"] == "2026-01-10"

        # Invoke the engine mock
        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": engine_input.specialty,
                "patient_id": engine_input.patient_id,
                "appointment_action": engine_input.appointment_action.value,
                "existing_appointment_date": engine_input.existing_appointment_date,
            }
        )
        assert engine_result.action_result == "slots_offered"
        assert len(engine_result.slots) >= 1
        for slot in engine_result.slots:
            assert slot.slot_id
            assert slot.start

        # ── Complete scenario summary ────────────────────────────────────
        # POC-11 validated:
        # - Reschedule classified as a manage action (Property P12) ✓
        # - patient_status=existing, no new/existing question ✓
        # - Specialty confirmed before auth ✓
        # - Auth required → gate closed → DOB match → gate open ✓
        # - Scheduling handoff surfaces specialty+action ✓
        # - Scheduling Init does NOT set visit_type (Req 13.7) ✓
        # - Engine input succeeds without visit_type (Property P30) ✓
        # - Engine returns slots_offered for reschedule ✓
        # - existing_appointment_date passed through ✓
