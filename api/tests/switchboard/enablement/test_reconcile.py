"""Unit tests for the greeting pre_call_fetch binding and unresolved reference.

Covers:
- The greeting ``startCall`` node's patient-lookup capability
  (``pre_call_fetch``) binds to the provisioned ``patient_lookup`` tool_uuid
  after reconciliation (Req 5.3).
- A node naming a connector that was not provisioned for the organization
  raises ``UnresolvedToolReference``, carrying the offending ``node_id`` and
  ``connector_name`` (Req 5.4).

Design references:
- ``design.md`` -> "Tool-reference reconciler"
- ``requirements.md`` -> Requirements 5.3, 5.4
"""

from __future__ import annotations

import uuid

import pytest

from api.services.switchboard.clusters.greeting import START_CALL_NODE_ID
from api.services.switchboard.graph import build_switchboard_reactflow_dto
from api.services.switchboard.enablement.reconcile import (
    UnresolvedToolReference,
    reconcile_tool_references,
)


def _collect_connector_names(dto) -> set[str]:
    """Collect every connector name-string referenced across all node tool_uuids."""
    names: set[str] = set()
    for node in dto.nodes:
        tool_uuids = getattr(node.data, "tool_uuids", None)
        if tool_uuids:
            names.update(tool_uuids)
    return names


def _build_full_name_to_uuid(dto) -> dict[str, str]:
    """Build a name_to_uuid map covering every connector name in the real graph."""
    return {name: str(uuid.uuid4()) for name in _collect_connector_names(dto)}


async def test_greeting_start_call_binds_patient_lookup_tool_uuid():
    """Req 5.3: the greeting startCall node's patient-lookup pre_call_fetch
    binds to the provisioned patient_lookup tool_uuid.

    Resolving the greeting startCall node's tool_uuids (which name-references
    "patient_lookup") through name_to_uuid is the Req 5.3 binding — there is
    no separate pre_call_fetch-only reference field.
    """
    dto = build_switchboard_reactflow_dto()
    name_to_uuid = _build_full_name_to_uuid(dto)
    patient_lookup_uuid = name_to_uuid["patient_lookup"]

    reconciled = reconcile_tool_references(dto, name_to_uuid)

    greeting_start_call_nodes = [
        node for node in reconciled.nodes if node.id == START_CALL_NODE_ID
    ]
    assert len(greeting_start_call_nodes) == 1
    greeting_node = greeting_start_call_nodes[0]

    assert greeting_node.data.tool_uuids is not None
    assert patient_lookup_uuid in greeting_node.data.tool_uuids
    # No connector name-string should remain on the reconciled node.
    assert "patient_lookup" not in greeting_node.data.tool_uuids


async def test_greeting_start_call_node_id_is_stable():
    """Sanity check: the greeting startCall node is identified by the exact,
    stable id exported from greeting.py, confirming the id used in the
    binding assertion above matches the real graph's node."""
    dto = build_switchboard_reactflow_dto()

    assert any(node.id == START_CALL_NODE_ID for node in dto.nodes)
    assert START_CALL_NODE_ID == "greeting_start_call"


async def test_unresolved_tool_reference_raised_for_missing_connector():
    """Req 5.4: a node naming an unprovisioned connector raises
    UnresolvedToolReference, carrying the node_id/connector_name that
    triggered it.

    Omits "patient_lookup" from the name_to_uuid map even though it is
    actually referenced (by the greeting startCall node) in the real graph.
    """
    dto = build_switchboard_reactflow_dto()
    name_to_uuid = _build_full_name_to_uuid(dto)
    del name_to_uuid["patient_lookup"]

    with pytest.raises(UnresolvedToolReference) as exc_info:
        reconcile_tool_references(dto, name_to_uuid)

    assert exc_info.value.connector_name == "patient_lookup"
    assert exc_info.value.node_id == START_CALL_NODE_ID


async def test_unresolved_tool_reference_for_arbitrary_omitted_connector():
    """Req 5.4: omitting any other connector actually referenced by some node
    in the real graph also raises UnresolvedToolReference with the correct
    node_id/connector_name."""
    dto = build_switchboard_reactflow_dto()
    name_to_uuid = _build_full_name_to_uuid(dto)

    # Pick a connector name other than patient_lookup that's actually used,
    # to confirm the reconciler isn't special-casing patient_lookup.
    other_name = next(
        name for name in name_to_uuid if name != "patient_lookup"
    )
    del name_to_uuid[other_name]

    # Find a node that actually references the omitted connector, so we know
    # exactly which node_id should be reported in the raised exception.
    expected_node_id = next(
        node.id
        for node in dto.nodes
        if getattr(node.data, "tool_uuids", None)
        and other_name in node.data.tool_uuids
    )

    with pytest.raises(UnresolvedToolReference) as exc_info:
        reconcile_tool_references(dto, name_to_uuid)

    assert exc_info.value.connector_name == other_name
    assert exc_info.value.node_id == expected_node_id
