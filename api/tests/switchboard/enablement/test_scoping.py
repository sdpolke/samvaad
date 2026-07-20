"""Edge-case tests for UUID-aware gate-by-scoping rejection (Task 5.3).

Covers:
- A non-Routing node listing ``transfer``/``route_metadata_resolution`` is
  rejected with a gate-by-scoping violation (Req 11.3).
- An unresolvable tool identity fails closed and is rejected regardless of
  node type (Req 11.5).
- The allowed control case: a Routing node listing a routing-only tool
  produces no violation.
- The ``build_uuid_to_connector_name`` helper correctly extracts
  ``definition["switchboard"]["connector_name"]`` and omits entries missing
  the marker.

Design references:
- ``design.md`` -> "Gate-by-scoping preservation"
- ``requirements.md`` -> Requirements 11.3, 11.5

Requirements: 11.3, 11.5.
"""

from __future__ import annotations

from api.services.switchboard.enablement.scoping import (
    build_uuid_to_connector_name,
    validate_uuid_tool_scoping,
)
from api.services.workflow.dto import Position, RFNodeDTO


def _agent_node(node_id: str, tool_uuids: list[str]) -> RFNodeDTO:
    """Build a minimal agentNode RFNodeDTO carrying the given tool_uuids."""
    return RFNodeDTO(
        id=node_id,
        type="agentNode",
        position=Position(x=0, y=0),
        data={
            "name": node_id,
            "prompt": "Do something.",
            "tool_uuids": tool_uuids,
        },
    )


class TestNonRoutingNodeWithTransferRejected:
    """Req 11.3: a non-Routing node listing ``transfer`` is rejected."""

    def test_non_routing_node_with_transfer_is_a_violation(self):
        uuid_to_connector_name = {"tool-uuid-1": "transfer"}
        node = _agent_node("authentication_verify_identity", ["tool-uuid-1"])

        violations = validate_uuid_tool_scoping([node], uuid_to_connector_name)

        assert len(violations) == 1
        assert "authentication_verify_identity" in violations[0]
        assert "transfer" in violations[0]


class TestNonRoutingNodeWithRouteMetadataResolutionRejected:
    """Req 11.3: a non-Routing node listing ``route_metadata_resolution`` is
    rejected."""

    def test_non_routing_node_with_route_metadata_resolution_is_a_violation(self):
        uuid_to_connector_name = {"tool-uuid-2": "route_metadata_resolution"}
        node = _agent_node("greeting_start_call", ["tool-uuid-2"])

        violations = validate_uuid_tool_scoping([node], uuid_to_connector_name)

        assert len(violations) == 1
        assert "greeting_start_call" in violations[0]
        assert "route_metadata_resolution" in violations[0]


class TestRoutingNodeWithRoutingOnlyToolIsAllowed:
    """Control case: a Routing node (id starts with ``routing_``) listing a
    resolvable routing-only tool produces NO violation."""

    def test_routing_node_with_transfer_has_no_violation(self):
        uuid_to_connector_name = {"tool-uuid-3": "transfer"}
        node = _agent_node("routing_transfer_decision", ["tool-uuid-3"])

        violations = validate_uuid_tool_scoping([node], uuid_to_connector_name)

        assert violations == []

    def test_routing_node_with_route_metadata_resolution_has_no_violation(self):
        uuid_to_connector_name = {"tool-uuid-4": "route_metadata_resolution"}
        node = _agent_node("routing_resolve_destination", ["tool-uuid-4"])

        violations = validate_uuid_tool_scoping([node], uuid_to_connector_name)

        assert violations == []


class TestUnresolvableToolIdentityFailsClosed:
    """Req 11.5: an unresolvable tool identity is always a violation,
    regardless of whether the node is a Routing node."""

    def test_non_routing_node_with_unresolvable_uuid_is_a_violation(self):
        uuid_to_connector_name: dict[str, str] = {}
        node = _agent_node("greeting_start_call", ["unresolvable-tool-uuid"])

        violations = validate_uuid_tool_scoping([node], uuid_to_connector_name)

        assert len(violations) == 1
        assert "greeting_start_call" in violations[0]
        assert "unresolvable-tool-uuid" in violations[0]

    def test_routing_node_with_unresolvable_uuid_is_still_a_violation(self):
        """Fail-closed applies even on a Routing node: an unresolved tool
        identity cannot positively confirm the invariant holds, so it is a
        violation regardless of node type."""
        uuid_to_connector_name: dict[str, str] = {}
        node = _agent_node("routing_transfer_decision", ["unresolvable-tool-uuid"])

        violations = validate_uuid_tool_scoping([node], uuid_to_connector_name)

        assert len(violations) == 1
        assert "routing_transfer_decision" in violations[0]
        assert "unresolvable-tool-uuid" in violations[0]


class TestBuildUuidToConnectorName:
    """Unit test for the ``build_uuid_to_connector_name`` helper."""

    def test_extracts_connector_name_from_switchboard_marker(self):
        tool_definitions = {
            "uuid-a": {
                "switchboard": {"connector_name": "patient_lookup"},
            },
            "uuid-b": {
                "switchboard": {"connector_name": "transfer"},
            },
        }

        result = build_uuid_to_connector_name(tool_definitions)

        assert result == {"uuid-a": "patient_lookup", "uuid-b": "transfer"}

    def test_skips_entries_missing_the_switchboard_marker(self):
        tool_definitions = {
            "uuid-a": {"switchboard": {"connector_name": "patient_lookup"}},
            "uuid-missing-switchboard": {"type": "http_api"},
            "uuid-missing-connector-name": {"switchboard": {}},
        }

        result = build_uuid_to_connector_name(tool_definitions)

        assert result == {"uuid-a": "patient_lookup"}
        assert "uuid-missing-switchboard" not in result
        assert "uuid-missing-connector-name" not in result

    def test_empty_input_produces_empty_map(self):
        assert build_uuid_to_connector_name({}) == {}
