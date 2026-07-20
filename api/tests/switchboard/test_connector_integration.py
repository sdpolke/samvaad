"""Integration tests for the mocked SpinSci connector contracts (task 15.4).

These tests exercise multi-step flows through the mock backends to verify that
the switchboard-side contracts chain correctly end-to-end: the output of one
tool feeds verbatim into the next tool's input, and the contracts validate on
both sides of each hop.

Requirements: 16.1, 16.2.
"""

from __future__ import annotations


from api.services.switchboard.tools import get_connector_tool


class TestPatientAuthChainIntegration:
    """Patient lookup → DOB validation → identity verification chain."""

    async def test_lookup_validate_verify_success_chain(self) -> None:
        """Full auth chain with a matching DOB yields patient_verified=Success."""
        # Step 1: patient_lookup — use a 10+ digit phone to get a match.
        lookup_tool = get_connector_tool("patient_lookup")
        lookup_result = await lookup_tool.invoke({"phone": "+1 (555) 867-5309"})

        assert lookup_result.match_count == 1
        assert lookup_result.patient_id is not None
        assert lookup_result.dob_on_file is not None

        # Step 2: dob_validation — feed patient_id from step 1 and a DOB whose
        # digits end with the patient_id suffix's last 4 digits (mock rule).
        # The mock patient_id is "mock-patient-5558675309", last 4 digits: 5309.
        dob_tool = get_connector_tool("dob_validation")
        dob_result = await dob_tool.invoke(
            {
                "provided_dob": "01/05/5309",  # digits end with 5309
                "patient_id": lookup_result.patient_id,
            }
        )

        assert dob_result.match is True

        # Step 3: identity_verify — feed the patient_id and the dob_match signal
        # derived from the DOB validation result.
        verify_tool = get_connector_tool("identity_verify")
        verify_result = await verify_tool.invoke(
            {
                "patient_id": lookup_result.patient_id,
                "verification_signals": {"dob_match": dob_result.match},
            }
        )

        assert verify_result.patient_verified == "Success"

    async def test_lookup_validate_verify_fail_on_wrong_dob(self) -> None:
        """Auth chain with a non-matching DOB yields patient_verified=Fail."""
        # Step 1: patient_lookup
        lookup_result = await get_connector_tool("patient_lookup").invoke(
            {"phone": "5559991234"}
        )
        assert lookup_result.match_count == 1
        assert lookup_result.patient_id is not None

        # Step 2: dob_validation with wrong DOB digits (mock expects suffix 1234,
        # we provide 0000 which does not match).
        dob_result = await get_connector_tool("dob_validation").invoke(
            {
                "provided_dob": "12/31/0000",
                "patient_id": lookup_result.patient_id,
            }
        )
        assert dob_result.match is False

        # Step 3: identity_verify — the dob_match signal is False → Fail.
        verify_result = await get_connector_tool("identity_verify").invoke(
            {
                "patient_id": lookup_result.patient_id,
                "verification_signals": {"dob_match": dob_result.match},
            }
        )
        assert verify_result.patient_verified == "Fail"


class TestRoutingChainIntegration:
    """Directory lookup → routing intent resolution → route metadata resolution chain."""

    async def test_directory_to_routing_to_metadata_chain(self) -> None:
        """Full routing chain uses exact strings from the listing (Req 10.2, 10.3)."""
        # Step 1: directory_lookup — resolve a department from a specialty query.
        dir_tool = get_connector_tool("directory_lookup")
        dir_result = await dir_tool.invoke({"query": "orthopedics"})

        assert dir_result.department_name is not None
        assert dir_result.department_id is not None
        assert isinstance(dir_result.selected_id, int)

        # Step 2: routing_intent_resolution — use the department context from step 1.
        routing_tool = get_connector_tool("routing_intent_resolution")
        routing_result = await routing_tool.invoke(
            {
                "department_name": dir_result.department_name,
                "department_id": dir_result.department_id,
            }
        )

        assert len(routing_result.route_listing) >= 1, "Route listing must not be empty"

        # Step 3: route_metadata_resolution — use the EXACT string from the listing
        # verbatim (Req 10.2, 10.3: never fabricated, used verbatim).
        exact_intent = routing_result.route_listing[0]
        metadata_tool = get_connector_tool("route_metadata_resolution")
        metadata_result = await metadata_tool.invoke({"routing_intent": exact_intent})

        # The metadata display_name echoes the exact intent string back.
        assert metadata_result.display_name == exact_intent
        assert metadata_result.destination, "Destination must be non-empty"
        assert metadata_result.queue_id is not None


class TestSchedulingChainIntegration:
    """Scheduling handoff → scheduling engine chain."""

    async def test_handoff_to_engine_create_flow(self) -> None:
        """Handoff surfaces specialty/action, then engine returns slots for create."""
        # Step 1: scheduling_handoff — pass a full ledger with create intent.
        handoff_tool = get_connector_tool("scheduling_handoff")
        handoff_result = await handoff_tool.invoke(
            {
                "ledger": {
                    "specialty": "dermatology",
                    "appointment_action": "create",
                    "patient_id": "mock-patient-1234567890",
                    "visit_type": "wellness",
                }
            }
        )

        assert handoff_result.specialty == "dermatology"
        assert handoff_result.appointment_action == "create"
        assert handoff_result.ready is True

        # Step 2: scheduling_engine — use the surfaced specialty and action.
        engine_tool = get_connector_tool("scheduling_engine")
        engine_result = await engine_tool.invoke(
            {
                "specialty": handoff_result.specialty,
                "patient_id": "mock-patient-1234567890",
                "appointment_action": handoff_result.appointment_action,
                "visit_type": "wellness",
            }
        )

        assert engine_result.action_result == "slots_offered"
        assert len(engine_result.slots) >= 1
        # Each slot has required fields per the contract.
        for slot in engine_result.slots:
            assert slot.slot_id
            assert slot.start

    async def test_handoff_to_engine_cancel_flow(self) -> None:
        """Handoff surfaces specialty/action, then engine returns cancellation result."""
        # Step 1: scheduling_handoff with cancel intent.
        handoff_result = await get_connector_tool("scheduling_handoff").invoke(
            {
                "ledger": {
                    "specialty": "cardiology",
                    "appointment_action": "cancel",
                    "patient_id": "mock-patient-0000005678",
                }
            }
        )

        assert handoff_result.specialty == "cardiology"
        assert handoff_result.appointment_action == "cancel"
        assert handoff_result.ready is True

        # Step 2: scheduling_engine with cancel action.
        engine_result = await get_connector_tool("scheduling_engine").invoke(
            {
                "specialty": handoff_result.specialty,
                "patient_id": "mock-patient-0000005678",
                "appointment_action": handoff_result.appointment_action,
            }
        )

        assert engine_result.action_result == "cancelled"
        assert engine_result.slots == []
        assert engine_result.appointment_details is not None
        assert engine_result.appointment_details["status"] == "cancelled"
