"""Integration tests for the mocked Scheduling Engine contracts (Req 14.3–14.9).

Exercises the scheduling_engine_backend mock with concrete inputs for all five
appointment actions, validating that the switchboard-side contract shapes are
correct and the mock provides stable responses for downstream integration.

Requirements: 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9.
"""

from __future__ import annotations


from api.services.switchboard.tools.backends import scheduling_engine_backend
from api.services.switchboard.tools.contracts import SchedulingEngineToolInput


class TestCreateAvailability:
    """Create action returns offered slots with correct shape (Req 14.3)."""

    async def test_create_returns_slots_offered(self) -> None:
        """Create with a valid specialty and patient_id yields slots_offered."""
        request = SchedulingEngineToolInput(
            specialty="dermatology",
            patient_id="mock-patient-1234567890",
            appointment_action="create",
            visit_type="sick",
        )
        result = await scheduling_engine_backend(request)

        assert result.action_result == "slots_offered"
        assert len(result.slots) == 2
        for slot in result.slots:
            assert slot.slot_id
            assert slot.start
            assert slot.provider_name

    async def test_create_wellness_visit_type(self) -> None:
        """Create with visit_type='wellness' also returns slots_offered."""
        request = SchedulingEngineToolInput(
            specialty="family-medicine",
            patient_id="mock-patient-9876543210",
            appointment_action="create",
            visit_type="wellness",
        )
        result = await scheduling_engine_backend(request)

        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1

    async def test_create_with_provider_name_appears_on_slots(self) -> None:
        """When provider_name is supplied, engine offers alternatives (POC-13, AC-18)."""
        request = SchedulingEngineToolInput(
            specialty="cardiology",
            patient_id="mock-patient-5551234567",
            appointment_action="create",
            visit_type="sick",
            provider_name="Dr. Smith",
        )
        result = await scheduling_engine_backend(request)

        assert result.action_result == "alternative_offered"
        for slot in result.slots:
            # Alternative providers — NOT the preferred one
            assert slot.provider_name != "Dr. Smith"


class TestRescheduleAvailability:
    """Reschedule returns slots without re-asking specialty/location (Req 14.4, 14.6)."""

    async def test_reschedule_returns_slots_offered(self) -> None:
        """Reschedule with existing_appointment_date yields slots_offered directly."""
        request = SchedulingEngineToolInput(
            specialty="orthopedics",
            patient_id="mock-patient-5559998877",
            appointment_action="reschedule",
            existing_appointment_date="2026-01-03T14:00:00-06:00",
        )
        result = await scheduling_engine_backend(request)

        assert result.action_result == "slots_offered"
        assert len(result.slots) == 2
        for slot in result.slots:
            assert slot.slot_id
            assert slot.start
            assert slot.provider_name

    async def test_reschedule_does_not_require_visit_type(self) -> None:
        """Reschedule does not need visit_type — alternative-without-re-ask (Req 14.6)."""
        request = SchedulingEngineToolInput(
            specialty="neurology",
            patient_id="mock-patient-5550001234",
            appointment_action="reschedule",
            existing_appointment_date="2026-02-10T08:00:00-06:00",
        )
        # visit_type is None — the mock should still produce slots without error.
        assert request.visit_type is None
        result = await scheduling_engine_backend(request)

        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1


class TestCancel:
    """Cancel action returns cancelled status with details (Req 14.5)."""

    async def test_cancel_returns_cancelled(self) -> None:
        """Cancel yields action_result='cancelled' and appointment_details with status."""
        request = SchedulingEngineToolInput(
            specialty="cardiology",
            patient_id="mock-patient-5550005678",
            appointment_action="cancel",
            existing_appointment_date="2026-01-10T11:00:00-06:00",
        )
        result = await scheduling_engine_backend(request)

        assert result.action_result == "cancelled"
        assert result.appointment_details is not None
        assert result.appointment_details["status"] == "cancelled"
        assert result.slots == []


class TestList:
    """List action returns listed status with appointment_details (Req 14.7)."""

    async def test_list_returns_listed(self) -> None:
        """List yields action_result='listed' and populated appointment_details."""
        request = SchedulingEngineToolInput(
            specialty="dermatology",
            patient_id="mock-patient-5553334444",
            appointment_action="list",
        )
        result = await scheduling_engine_backend(request)

        assert result.action_result == "listed"
        assert result.appointment_details is not None


class TestConfirm:
    """Confirm action returns confirmed status with details (Req 14.8)."""

    async def test_confirm_returns_confirmed(self) -> None:
        """Confirm yields action_result='confirmed' and populated appointment_details."""
        request = SchedulingEngineToolInput(
            specialty="dermatology",
            patient_id="mock-patient-5551112222",
            appointment_action="confirm",
        )
        result = await scheduling_engine_backend(request)

        assert result.action_result == "confirmed"
        assert result.appointment_details is not None
        assert result.appointment_details["status"] == "confirmed"
