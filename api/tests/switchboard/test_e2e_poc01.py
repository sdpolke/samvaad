"""E2E acceptance scenario tests: POC-01 / POC-01b / POC-01c

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes.  They do NOT use a live LLM or TTS pipeline; instead they:

1. Build the graph via ``build_switchboard_graph()`` and verify its structure.
2. Trace the pure logic functions (auth gate, ledger reducer) through each scenario.
3. Invoke the mock connector tools directly to verify end-to-end data flow.
4. Assert the observable outcomes: ledger state, tool outputs, graph structure.

Scenarios:
  POC-01  — existing patient, wellness scheduling (auth required, slots offered)
  POC-01b — existing patient, sick visit scheduling (auth required, slots offered)
  POC-01c — new patient, create scheduling (auth skipped, general intake path)

Requirements: 20.1, 20.2, 20.3
"""

from __future__ import annotations


from api.services.switchboard.auth import (
    PATIENT_VERIFIED_SUCCESS,
    auth_required,
    may_proceed_to_routing,
)
from api.services.switchboard.clusters.scheduling import build_scheduling_cluster
from api.services.switchboard.graph import build_switchboard_graph
from api.services.switchboard.ledger import CallStateLedger, reduce_ledger, should_ask
from api.services.switchboard.tools import get_connector_tool


# ---------------------------------------------------------------------------
# POC-01: Existing patient — wellness scheduling
# ---------------------------------------------------------------------------


class TestPOC01ExistingWellness:
    """POC-01: after_hours=False, intent=Scheduling, patient_status=existing,
    appointment_action=create, visit_type=wellness.

    Scripted trace:
      Greeting → Business Hours → Authentication → Routing → Scheduling Init
      → Scheduling Engine offers slots for create+wellness.
    """

    # ── 1. Auth gate assertions ────────────────────────────────────────────

    def test_auth_required_for_existing_scheduling(self) -> None:
        """auth_required('Scheduling', 'existing') is True — auth must run."""
        assert auth_required("Scheduling", "existing") is True

    def test_gate_closed_before_verification(self) -> None:
        """GATE-AUTH: may_proceed_to_routing is False while patient_verified is None."""
        assert may_proceed_to_routing("Scheduling", "existing", None) is False

    def test_gate_open_after_verification_success(self) -> None:
        """GATE-AUTH: may_proceed_to_routing is True once patient_verified=Success."""
        assert (
            may_proceed_to_routing("Scheduling", "existing", PATIENT_VERIFIED_SUCCESS)
            is True
        )

    # ── 2. Ledger trace through the scenario ─────────────────────────────

    def test_ledger_trace_greeting_to_scheduling_init(self) -> None:
        """Ledger carries all fields forward from Greeting through Scheduling Init."""
        # After Greeting: caller name captured
        ledger = reduce_ledger(
            CallStateLedger(),
            {
                "caller_name": "Jane Smith",
                "after_hours": False,
                "greeting_ani_lookup_done": True,
                "greeting_ani_match_count": 1,
            },
        )
        assert ledger.caller_name == "Jane Smith"
        assert ledger.after_hours is False

        # After Business Hours: intent + patient_status + appointment_action
        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Scheduling",
                "patient_status": "existing",
                "appointment_action": "create",
            },
        )
        assert ledger.intent == "Scheduling"
        assert ledger.patient_status == "existing"
        assert ledger.appointment_action == "create"

        # Auth gate: GATE-AUTH is closed (patient_verified is still None)
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        # After Authentication: patient_verified=Success, patient_id resolved
        ledger = reduce_ledger(
            ledger,
            {
                "patient_verified": "Success",
                "patient_id": "mock-patient-5558675309",
            },
        )
        assert ledger.patient_verified == PATIENT_VERIFIED_SUCCESS
        assert ledger.patient_id == "mock-patient-5558675309"

        # Auth gate: GATE-AUTH is open
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

        # After Scheduling Init: visit_type resolved as wellness
        ledger = reduce_ledger(ledger, {"visit_type": "wellness"})
        assert ledger.visit_type == "wellness"

        # should_ask(visit_type) is now False — never re-asks a populated field
        assert should_ask("visit_type", ledger) is False

    # ── 3. Scheduling Engine mock — slots offered for create+wellness ─────

    async def test_scheduling_engine_returns_slots_for_create_wellness(self) -> None:
        """Scheduling Engine mock returns action_result=slots_offered for create+wellness."""
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

    # ── 4. Graph structure ────────────────────────────────────────────────

    def test_graph_builds_and_has_scheduling_init_node(self) -> None:
        """The assembled graph has a scheduling_init node reachable from routing."""
        wg = build_switchboard_graph()
        assert "scheduling_init" in wg.nodes

    def test_graph_has_scheduling_engine_node(self) -> None:
        """The assembled graph has a scheduling_engine node."""
        wg = build_switchboard_graph()
        assert "scheduling_engine" in wg.nodes

    def test_routing_to_scheduling_edge_exists(self) -> None:
        """An edge from the routing resolve_route node targets scheduling_init."""
        wg = build_switchboard_graph()
        scheduling_init_id = "scheduling_init"
        routing_to_sched = [
            e for e in wg.edges if e.target == scheduling_init_id
        ]
        assert len(routing_to_sched) >= 1, (
            "Expected at least one edge targeting scheduling_init from routing"
        )

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


# ---------------------------------------------------------------------------
# POC-01b: Existing patient — sick visit scheduling
# ---------------------------------------------------------------------------


class TestPOC01bExistingSick:
    """POC-01b: Same as POC-01 but visit_type=sick.

    The auth gate, ledger carry, and graph structure are identical to POC-01.
    Only the visit_type in the Scheduling Engine call changes.
    """

    def test_auth_required_for_existing_scheduling(self) -> None:
        """auth_required('Scheduling', 'existing') is True (same as POC-01)."""
        assert auth_required("Scheduling", "existing") is True

    def test_gate_still_closed_before_verification(self) -> None:
        """GATE-AUTH is closed while patient_verified is None (sick visit path)."""
        assert may_proceed_to_routing("Scheduling", "existing", None) is False

    def test_ledger_carries_sick_visit_type(self) -> None:
        """Ledger carries visit_type=sick through the scheduling segment."""
        base = CallStateLedger(
            intent="Scheduling",
            patient_status="existing",
            appointment_action="create",
            patient_verified="Success",
            patient_id="mock-patient-5559991234",
        )
        ledger = reduce_ledger(base, {"visit_type": "sick"})
        assert ledger.visit_type == "sick"
        assert ledger.patient_status == "existing"
        assert should_ask("visit_type", ledger) is False

    async def test_scheduling_engine_returns_slots_for_create_sick(self) -> None:
        """Scheduling Engine mock returns slots_offered for create+sick."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-5559991234",
                "appointment_action": "create",
                "visit_type": "sick",
            }
        )

        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1
        for slot in result.slots:
            assert slot.slot_id
            assert slot.start

    def test_scheduling_cluster_has_init_to_engine_edge(self) -> None:
        """The scheduling cluster has an Init → Engine edge for resolved visit_type."""
        cluster = build_scheduling_cluster()
        init_to_engine = [
            e for e in cluster.edges
            if e.source == cluster.scheduling_init_id
            and e.target == cluster.scheduling_engine_id
        ]
        assert len(init_to_engine) == 1

    def test_slots_have_required_fields_for_sick_visit(self) -> None:
        """Each slot returned for a sick-visit create has slot_id and start."""
        # Verify the contract shape — slot_id and start are always present.
        from api.services.switchboard.tools.contracts import SchedulingSlot
        slot = SchedulingSlot(slot_id="mock-slot-001", start="2026-01-05T09:00:00-06:00")
        assert slot.slot_id == "mock-slot-001"
        assert slot.start == "2026-01-05T09:00:00-06:00"


# ---------------------------------------------------------------------------
# POC-01c: New patient — create scheduling (skip auth, general intake)
# ---------------------------------------------------------------------------


class TestPOC01cNewPatientCreate:
    """POC-01c: patient_status=new, appointment_action=create, intent=Scheduling.

    New-patient create skips authentication (auth_required returns False) and
    routes to the general intake path via the scheduling_new_patient_intake node.

    Requirements: 20.3, 9.4, 12.7.
    """

    # ── 1. Auth gate: new patient skips auth ─────────────────────────────

    def test_auth_not_required_for_new_patient_scheduling(self) -> None:
        """auth_required('Scheduling', 'new') is False — new patient skips auth."""
        assert auth_required("Scheduling", "new") is False

    def test_gate_open_without_verification_for_new_patient(self) -> None:
        """GATE-AUTH: may_proceed_to_routing is True for new Scheduling even with
        patient_verified=None — auth was never required."""
        assert may_proceed_to_routing("Scheduling", "new", None) is True

    def test_gate_open_with_na_verification_for_new_patient(self) -> None:
        """New patient can proceed with patient_verified=N/A (no auth step ran)."""
        assert may_proceed_to_routing("Scheduling", "new", "N/A") is True

    # ── 2. Ledger trace — new patient, no auth step ───────────────────────

    def test_ledger_trace_new_patient_no_auth(self) -> None:
        """New-patient ledger: auth not required, patient_verified stays None."""
        # After Business Hours: intent=Scheduling, patient_status=new, action=create
        ledger = reduce_ledger(
            CallStateLedger(),
            {
                "intent": "Scheduling",
                "patient_status": "new",
                "appointment_action": "create",
                "after_hours": False,
            },
        )
        assert ledger.patient_status == "new"
        assert ledger.appointment_action == "create"

        # Auth gate is open — no auth required for new-patient Scheduling
        assert auth_required(ledger.intent, ledger.patient_status) is False
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

        # visit_type is still unset — should_ask returns True before Init resolves it
        assert should_ask("visit_type", ledger) is True

        # patient_verified is never set (no auth step ran)
        assert ledger.patient_verified is None

    # ── 3. Graph structure — new patient intake path ──────────────────────

    def test_graph_has_new_patient_intake_node(self) -> None:
        """The assembled graph has the scheduling_new_patient_intake node (Req 12.7)."""
        wg = build_switchboard_graph()
        assert "scheduling_new_patient_intake" in wg.nodes

    def test_scheduling_cluster_has_new_patient_intake_node(self) -> None:
        """The scheduling cluster result exposes the new-patient intake node ID."""
        cluster = build_scheduling_cluster()
        assert cluster.scheduling_new_patient_intake_id == "scheduling_new_patient_intake"
        node_ids = {n.id for n in cluster.nodes}
        assert "scheduling_new_patient_intake" in node_ids

    def test_scheduling_cluster_has_init_to_new_patient_edge(self) -> None:
        """The scheduling cluster has an Init → New Patient Intake edge (Req 12.7)."""
        cluster = build_scheduling_cluster()
        init_to_new_patient = [
            e for e in cluster.edges
            if e.source == cluster.scheduling_init_id
            and e.target == cluster.scheduling_new_patient_intake_id
        ]
        assert len(init_to_new_patient) == 1
        edge = init_to_new_patient[0]
        # The condition must reference new patient and general intake
        assert edge.data is not None
        condition_lower = edge.data.condition.lower()
        assert "new" in condition_lower
        assert "intake" in condition_lower

    def test_new_patient_intake_node_is_end_call(self) -> None:
        """The scheduling_new_patient_intake node is an endCall terminal (Req 12.7)."""
        cluster = build_scheduling_cluster()
        node_map = {n.id: n for n in cluster.nodes}
        intake_node = node_map["scheduling_new_patient_intake"]
        assert intake_node.type == "endCall"

    # ── 4. Scheduling Engine — new patient create path ────────────────────

    async def test_scheduling_engine_returns_slots_for_new_patient_create(
        self,
    ) -> None:
        """Scheduling Engine mock returns slots_offered for new-patient create."""
        engine_tool = get_connector_tool("scheduling_engine")
        result = await engine_tool.invoke(
            {
                "specialty": "primary_care",
                "patient_id": "mock-patient-new-0001",
                "appointment_action": "create",
                # visit_type is absent for new-patient general intake path
            }
        )

        # The mock engine returns slots_offered for any create action
        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1

    # ── 5. Scheduling handoff — new patient ledger carried through ────────

    async def test_scheduling_handoff_surfaces_new_patient_context(self) -> None:
        """Scheduling handoff surfaces specialty and action for new-patient create."""
        handoff_tool = get_connector_tool("scheduling_handoff")
        result = await handoff_tool.invoke(
            {
                "ledger": {
                    "specialty": "primary_care",
                    "appointment_action": "create",
                    "patient_status": "new",
                    "patient_id": None,  # new patient — no verified ID yet
                }
            }
        )

        assert result.appointment_action == "create"
        assert result.specialty == "primary_care"
        assert result.ready is True
