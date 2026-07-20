"""Unit tests for the switchboard backend connector tools (task 15.1 →
Requirements 16.1, 16.2, 1.7).

These focused example tests verify the 11 connector tools are registered, their
switchboard-side contracts validate, the PoC mock backends return valid outputs,
per-cluster scoping is correct (so transfer/route_metadata are Routing-only), and
no SpinSci wire format is hardcoded (tools default to an unbound credential/
endpoint seam).
"""

from __future__ import annotations

import pytest

import api.services.telephony.call_transfer_manager as transfer_manager_mod
import api.services.telephony.factory as telephony_factory
from api.db import db_client
from api.enums import ToolCategory
from api.services.switchboard.tools import (
    CONNECTOR_TOOLS,
    SwitchboardCallContext,
    ToolCluster,
    get_connector_tool,
    get_connector_tools,
    tools_for_cluster,
)

EXPECTED_TOOL_NAMES = {
    "patient_lookup",
    "directory_lookup",
    "faq_kb",
    "dob_validation",
    "identity_verify",
    "routing_intent_resolution",
    "route_metadata_resolution",
    "transfer",
    "hangup",
    "scheduling_handoff",
    "scheduling_engine",
}


class TestRegistry:
    def test_all_eleven_tools_registered(self) -> None:
        assert set(CONNECTOR_TOOLS) == EXPECTED_TOOL_NAMES
        assert len(get_connector_tools()) == 11

    def test_get_connector_tool_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_connector_tool("nonexistent_tool")


class TestScoping:
    def test_transfer_and_metadata_are_routing_only(self) -> None:
        # Gate-by-scoping: these capabilities cannot exist before Routing.
        for name in ("transfer", "route_metadata_resolution", "routing_intent_resolution"):
            tool = get_connector_tool(name)
            assert tool.clusters == frozenset({ToolCluster.ROUTING})

    def test_patient_lookup_scoped_to_greeting_and_auth(self) -> None:
        tool = get_connector_tool("patient_lookup")
        assert tool.is_scoped_to(ToolCluster.GREETING)
        assert tool.is_scoped_to(ToolCluster.AUTHENTICATION)
        assert not tool.is_scoped_to(ToolCluster.ROUTING)

    def test_tools_for_cluster_routing(self) -> None:
        names = {t.name for t in tools_for_cluster(ToolCluster.ROUTING)}
        assert names == {
            "routing_intent_resolution",
            "route_metadata_resolution",
            "transfer",
            "hangup",
        }

    def test_tools_for_cluster_scheduling(self) -> None:
        names = {t.name for t in tools_for_cluster(ToolCluster.SCHEDULING)}
        assert names == {"scheduling_handoff", "scheduling_engine"}


class TestContractsAndSeam:
    def test_no_hardcoded_spinsci_wire_format(self) -> None:
        # Every tool defaults to an unbound credential/endpoint seam (Req 16.2).
        for tool in get_connector_tools():
            assert tool.binding.endpoint is None
            assert tool.binding.credential_key is None
            assert tool.binding.is_bound is False

    def test_function_schema_shape(self) -> None:
        schema = get_connector_tool("patient_lookup").to_function_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "patient_lookup"
        assert "phone" in schema["function"]["parameters"]["properties"]
        assert "phone" in schema["function"]["parameters"]["required"]

    def test_tool_definition_is_http_api_with_binding(self) -> None:
        definition = get_connector_tool("directory_lookup").to_tool_definition()
        assert definition["type"] == ToolCategory.HTTP_API.value
        assert definition["config"]["url"] == ""
        assert definition["config"]["credential_uuid"] is None
        assert definition["config"]["field_mapping"] == {}
        param_names = {p["name"] for p in definition["config"]["parameters"]}
        assert "query" in param_names

    def test_sensitive_fields_registered_for_masking(self) -> None:
        # DOB / patient identifiers must be registered for masking.
        assert "provided_dob" in get_connector_tool("dob_validation").sensitive_fields
        assert "dob_on_file" in get_connector_tool("patient_lookup").sensitive_fields

    def test_invoke_rejects_unknown_field(self) -> None:
        # extra="forbid" on the contract validates untrusted input at the boundary.
        with pytest.raises(Exception):
            get_connector_tool("faq_kb").input_model.model_validate(
                {"question": "hi", "unexpected": "x"}
            )


class TestMockBackends:
    async def test_patient_lookup_single_match(self) -> None:
        result = await get_connector_tool("patient_lookup").invoke(
            {"phone": "+1 (555) 123-4567"}
        )
        assert result.match_count == 1
        assert result.patient_id is not None
        assert result.dob_on_file is not None

    async def test_patient_lookup_no_match_short_number(self) -> None:
        result = await get_connector_tool("patient_lookup").invoke({"phone": "123"})
        assert result.match_count == 0
        assert result.patient_id is None

    async def test_dob_validation_matches_lookup_token(self) -> None:
        lookup = await get_connector_tool("patient_lookup").invoke(
            {"phone": "5551234567"}
        )
        # Provided DOB whose digits end with the patient_id suffix validates.
        dob = await get_connector_tool("dob_validation").invoke(
            {"provided_dob": "01/02/4567", "patient_id": lookup.patient_id}
        )
        assert dob.match is True

    async def test_identity_verify_success_on_dob_match(self) -> None:
        result = await get_connector_tool("identity_verify").invoke(
            {"patient_id": "p1", "verification_signals": {"dob_match": True}}
        )
        assert result.patient_verified == "Success"

    async def test_identity_verify_fail_without_signal(self) -> None:
        result = await get_connector_tool("identity_verify").invoke(
            {"patient_id": "p1", "verification_signals": {}}
        )
        assert result.patient_verified == "Fail"

    async def test_routing_chain_uses_exact_string(self) -> None:
        listing = await get_connector_tool("routing_intent_resolution").invoke(
            {"department_name": "Cardiology"}
        )
        assert listing.route_listing, "listing must not be empty"
        exact = listing.route_listing[0]
        metadata = await get_connector_tool("route_metadata_resolution").invoke(
            {"routing_intent": exact}
        )
        assert metadata.display_name == exact
        assert metadata.destination

    async def test_transfer_without_call_context_is_unavailable(self) -> None:
        # No live-call context (graph-build / contextless invoke) => no telephony.
        result = await get_connector_tool("transfer").invoke(
            {
                "destination": "+15551230000",
                "call_summary": "Verified patient, cardiology transfer.",
                "patient_verified": "Success",
                "spoken_transfer_message": "One moment while I connect you.",
            }
        )
        assert result.status == "unavailable"
        assert result.transfer_id is None

    async def test_hangup_without_call_context_returns_ended(self) -> None:
        result = await get_connector_tool("hangup").invoke(
            {"goodbye_line": "Thank you for calling SpinSci. Goodbye."}
        )
        assert result.status == "ended"

    async def test_directory_lookup_returns_numeric_selected_id(self) -> None:
        result = await get_connector_tool("directory_lookup").invoke(
            {"query": "cardiology"}
        )
        assert isinstance(result.selected_id, int)
        assert result.matches

    async def test_scheduling_engine_create_offers_slots(self) -> None:
        result = await get_connector_tool("scheduling_engine").invoke(
            {
                "specialty": "cardiology",
                "patient_id": "p1",
                "appointment_action": "create",
                "visit_type": "wellness",
            }
        )
        assert result.action_result == "slots_offered"
        assert len(result.slots) >= 1

    async def test_scheduling_engine_cancel_returns_action_result(self) -> None:
        result = await get_connector_tool("scheduling_engine").invoke(
            {
                "specialty": "cardiology",
                "patient_id": "p1",
                "appointment_action": "cancel",
            }
        )
        assert result.action_result == "cancelled"
        assert result.slots == []

    async def test_scheduling_handoff_surfaces_specialty(self) -> None:
        result = await get_connector_tool("scheduling_handoff").invoke(
            {"ledger": {"specialty": "cardiology", "appointment_action": "create"}}
        )
        assert result.specialty == "cardiology"
        assert result.appointment_action == "create"
        assert result.ready is True


class _FakeRun:
    """Minimal workflow-run stand-in exposing ``gathered_context.call_id``."""

    def __init__(self, call_id: str = "CA-XYZ") -> None:
        self.gathered_context = {"call_id": call_id}


class _FakeProvider:
    """Fake telephony provider that records the transfer payload it receives."""

    PROVIDER_NAME = "fake"

    def __init__(self) -> None:
        self.transfer_kwargs: dict | None = None

    def supports_transfers(self) -> bool:
        return True

    def validate_config(self) -> bool:
        return True

    async def transfer_call(
        self,
        *,
        destination: str,
        transfer_id: str,
        conference_name: str,
        timeout: int = 30,
        **kwargs,
    ) -> dict:
        self.transfer_kwargs = {
            "destination": destination,
            "transfer_id": transfer_id,
            "conference_name": conference_name,
            **kwargs,
        }
        return {"status": "initiated", "call_sid": "fake-sid"}


class _FakeTransferManager:
    """Fake transfer manager recording the seeded transfer context."""

    def __init__(self) -> None:
        self.stored = None

    async def store_transfer_context(self, context) -> None:
        self.stored = context


class TestTelephonyWiring:
    """Wire-through tests for the transfer/hangup telephony seam (Req 16.3, 16.4).

    These verify the backend resolves a provider through the telephony factory
    (never instantiating a provider directly) and forwards the full transfer
    payload — against a fake provider so no real telephony is touched.
    """

    async def test_transfer_invokes_provider_with_full_payload(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = _FakeProvider()
        manager = _FakeTransferManager()
        seen: dict = {}

        async def fake_get_run(run_id: int):
            seen["run_id"] = run_id
            return _FakeRun(call_id="CA-XYZ")

        async def fake_provider_for_run(run, organization_id):
            seen["org"] = organization_id
            return provider

        async def fake_get_manager():
            return manager

        monkeypatch.setattr(db_client, "get_workflow_run_by_id", fake_get_run)
        monkeypatch.setattr(
            telephony_factory, "get_telephony_provider_for_run", fake_provider_for_run
        )
        monkeypatch.setattr(
            transfer_manager_mod, "get_call_transfer_manager", fake_get_manager
        )

        result = await get_connector_tool("transfer").invoke(
            {
                "destination": "+15551230000",
                "call_summary": "Verified patient, cardiology transfer.",
                "patient_verified": "Success",
                "spoken_transfer_message": "One moment while I connect you.",
            },
            call_context=SwitchboardCallContext(
                organization_id=7, workflow_run_id=42
            ),
        )

        assert result.status == "initiated"
        assert result.transfer_id
        # Provider resolved via the factory, org-scoped to the call context.
        assert seen == {"run_id": 42, "org": 7}
        # Transfer payload carries destination + summary + verification + spoken line.
        assert provider.transfer_kwargs is not None
        assert provider.transfer_kwargs["destination"] == "+15551230000"
        assert (
            provider.transfer_kwargs["call_summary"]
            == "Verified patient, cardiology transfer."
        )
        assert provider.transfer_kwargs["patient_verified"] == "Success"
        assert (
            provider.transfer_kwargs["spoken_transfer_message"]
            == "One moment while I connect you."
        )
        assert provider.transfer_kwargs["conference_name"] == "transfer-CA-XYZ"
        # Transfer context seeded before the provider call.
        assert manager.stored is not None
        assert manager.stored.target_number == "+15551230000"
        assert manager.stored.workflow_run_id == 42

    async def test_transfer_failed_when_provider_lacks_support(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _NoTransferProvider(_FakeProvider):
            def supports_transfers(self) -> bool:
                return False

        async def fake_get_run(run_id: int):
            return _FakeRun()

        async def fake_provider_for_run(run, organization_id):
            return _NoTransferProvider()

        monkeypatch.setattr(db_client, "get_workflow_run_by_id", fake_get_run)
        monkeypatch.setattr(
            telephony_factory, "get_telephony_provider_for_run", fake_provider_for_run
        )

        result = await get_connector_tool("transfer").invoke(
            {"destination": "+15551230000"},
            call_context=SwitchboardCallContext(
                organization_id=1, workflow_run_id=2
            ),
        )
        assert result.status == "failed"
        assert result.transfer_id is None

    async def test_hangup_resolves_provider_and_ends(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict = {}

        async def fake_get_run(run_id: int):
            seen["run_id"] = run_id
            return _FakeRun()

        async def fake_provider_for_run(run, organization_id):
            seen["org"] = organization_id
            return _FakeProvider()

        monkeypatch.setattr(db_client, "get_workflow_run_by_id", fake_get_run)
        monkeypatch.setattr(
            telephony_factory, "get_telephony_provider_for_run", fake_provider_for_run
        )

        result = await get_connector_tool("hangup").invoke(
            {"goodbye_line": "Thank you for calling SpinSci. Goodbye."},
            call_context=SwitchboardCallContext(
                organization_id=3, workflow_run_id=9
            ),
        )
        assert result.status == "ended"
        assert seen == {"run_id": 9, "org": 3}
