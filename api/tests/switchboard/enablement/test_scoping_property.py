"""Property-based test for the UUID-aware gate-by-scoping invariant (task 5.2).

Covers Property 6 — Gate-by-scoping invariant (Requirements 11.1, 11.2, 11.4).

``validate_uuid_tool_scoping`` (``enablement/scoping.py``) resolves each
node's ``tool_uuids`` through a ``uuid_to_connector_name`` map and reports a
violation for a given node/tool_uuid entry if and only if:

- the UUID cannot be positively resolved to a known connector identity
  (fail-closed, Req 11.5) — this applies **unconditionally**, on Routing
  nodes as well as non-Routing nodes, per the current implementation; or
- the UUID resolves to a ``ROUTING_ONLY_TOOLS`` connector name (``transfer``
  or ``route_metadata_resolution``) AND the node is not a Routing node
  (Req 11.2, 11.4).

This test generates arbitrary ``uuid_to_connector_name`` resolution maps
(including maps that leave some UUIDs unresolvable and maps that place a
routing-only tool's UUID on a non-Routing node) against the real switchboard
graph's nodes, and asserts the reported violations exactly match that
if-and-only-if rule. It also asserts the real, correctly-scoped switchboard
graph with a complete, correct resolution map has zero violations.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 6: Gate-by-scoping
  invariant"
- ``requirements.md`` -> Requirements 11.1, 11.2, 11.4, 11.5

Requirements: 11.1, 11.2, 11.4.
"""

from __future__ import annotations

import re
import uuid

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.clusters.tool_scoping import ROUTING_ONLY_TOOLS
from api.services.switchboard.enablement.reconcile import reconcile_tool_references
from api.services.switchboard.enablement.scoping import validate_uuid_tool_scoping
from api.services.switchboard.graph import build_switchboard_reactflow_dto
from api.services.workflow.dto import RFNodeDTO

# ---------------------------------------------------------------------------
# Real assembled switchboard graph, reconciled to synthetic (but real-shaped)
# tool UUIDs — the property is exercised against the actual switchboard
# shape, not an invented graph.
# ---------------------------------------------------------------------------

_BASE_DTO = build_switchboard_reactflow_dto()


def _get_node_tool_uuids(node: RFNodeDTO) -> list[str]:
    """Extract a node's tool_uuids, returning an empty list if None."""
    if hasattr(node.data, "tool_uuids") and node.data.tool_uuids is not None:
        return list(node.data.tool_uuids)
    return []


#: The connector name-strings the real switchboard graph references (before
#: reconciliation), e.g. "patient_lookup", "transfer", "route_metadata_resolution".
_CONNECTOR_NAMES: list[str] = sorted(
    {
        name
        for node in _BASE_DTO.nodes
        for name in _get_node_tool_uuids(node)
    }
)

assert _CONNECTOR_NAMES, "Expected the switchboard graph to reference connector tools"
assert ROUTING_ONLY_TOOLS <= set(_CONNECTOR_NAMES), (
    "Expected the switchboard graph to reference both routing-only tools"
)

#: Deterministic synthetic tool_uuid per connector name (real UUID shape,
#: stable across test runs).
_NAME_TO_UUID: dict[str, str] = {
    name: str(uuid.uuid5(uuid.NAMESPACE_DNS, f"switchboard-connector:{name}"))
    for name in _CONNECTOR_NAMES
}

#: The real switchboard nodes with every tool_uuids name-string reconciled to
#: its synthetic real UUID — this is the shape ``validate_uuid_tool_scoping``
#: operates on in production (post-reconciliation).
_RECONCILED_NODES: list[RFNodeDTO] = list(
    reconcile_tool_references(_BASE_DTO, _NAME_TO_UUID).nodes
)

#: Every distinct real tool_uuid that appears on some node's tool_uuids.
_ALL_TOOL_UUIDS: list[str] = sorted(
    {tu for node in _RECONCILED_NODES for tu in _get_node_tool_uuids(node)}
)

assert _ALL_TOOL_UUIDS, "Expected at least one reconciled tool_uuid on the graph"

#: The correct, complete resolution map (tool_uuid -> its real connector
#: name) — i.e. the real, correctly-scoped switchboard graph's resolution.
_CORRECT_UUID_TO_CONNECTOR_NAME: dict[str, str] = {
    uid: name for name, uid in _NAME_TO_UUID.items()
}


def _is_routing_node(node: RFNodeDTO) -> bool:
    return node.id.startswith("routing_")


def _expected_violations(
    nodes: list[RFNodeDTO], uuid_to_connector_name: dict[str, str]
) -> set[tuple[str, str]]:
    """Compute the expected set of (node_id, tool_uuid) violations.

    Mirrors the CONFIRMED actual behavior of ``validate_uuid_tool_scoping``:
    a violation occurs for a node/tool_uuid entry if and only if the UUID is
    unresolvable (unconditionally, regardless of node type — Req 11.5), or
    it resolves to a ``ROUTING_ONLY_TOOLS`` name and the node is not a
    Routing node (Req 11.2, 11.4).
    """
    expected: set[tuple[str, str]] = set()
    for node in nodes:
        tool_uuids = _get_node_tool_uuids(node)
        if not tool_uuids:
            continue
        is_routing = _is_routing_node(node)
        for tool_uuid in tool_uuids:
            resolved_name = uuid_to_connector_name.get(tool_uuid)
            if resolved_name is None:
                expected.add((node.id, tool_uuid))
            elif resolved_name in ROUTING_ONLY_TOOLS and not is_routing:
                expected.add((node.id, tool_uuid))
    return expected


#: Extracts (node_id, tool_uuid) from either violation message shape:
#: "Node '<id>' has tool_uuid '<uuid>' that could not be resolved..."
#: "Node '<id>' has routing-only tool '<name>' (tool_uuid '<uuid>') ..."
_VIOLATION_RE = re.compile(
    r"^Node '([^']+)' has (?:tool_uuid '([^']+)'|routing-only tool '[^']+' \(tool_uuid '([^']+)'\))"
)


def _actual_violations(violations: list[str]) -> set[tuple[str, str]]:
    actual: set[tuple[str, str]] = set()
    for message in violations:
        match = _VIOLATION_RE.match(message)
        assert match, f"Unrecognized violation message shape: {message!r}"
        node_id = match.group(1)
        tool_uuid = match.group(2) or match.group(3)
        actual.add((node_id, tool_uuid))
    return actual


# ---------------------------------------------------------------------------
# Strategy — arbitrary resolution maps over the real graph's tool_uuids.
# ---------------------------------------------------------------------------

#: Each real tool_uuid independently resolves to: its correct connector name,
#: a different (possibly routing-only) connector name, or is left
#: unresolvable (missing from the map, modeled as None here).
_st_resolution_map = st.fixed_dictionaries(
    {
        tool_uuid: st.one_of(st.none(), st.sampled_from(_CONNECTOR_NAMES))
        for tool_uuid in _ALL_TOOL_UUIDS
    }
)

# Forces at least one example where every tool_uuid resolves correctly (the
# real, correctly-scoped switchboard graph) — expect zero violations.
_EXAMPLE_ALL_CORRECT = dict(_CORRECT_UUID_TO_CONNECTOR_NAME)

# Forces at least one example where every tool_uuid is unresolvable — expect
# a violation for every node/tool_uuid entry, regardless of Routing/non-Routing.
_EXAMPLE_ALL_UNRESOLVABLE = {tool_uuid: None for tool_uuid in _ALL_TOOL_UUIDS}

# Forces at least one example where every tool_uuid resolves to a
# routing-only tool ("transfer") — expect a violation on every non-Routing
# node carrying that UUID (Routing nodes remain unaffected).
_ROUTING_ONLY_NAME = sorted(ROUTING_ONLY_TOOLS)[0]
_EXAMPLE_ALL_ROUTING_ONLY = {
    tool_uuid: _ROUTING_ONLY_NAME for tool_uuid in _ALL_TOOL_UUIDS
}


# ---------------------------------------------------------------------------
# Property 6: Gate-by-scoping invariant
# ---------------------------------------------------------------------------


# Feature: switchboard-frontend-enablement, Property 6: Gate-by-scoping invariant
@example(resolution_map=_EXAMPLE_ALL_CORRECT)
@example(resolution_map=_EXAMPLE_ALL_UNRESOLVABLE)
@example(resolution_map=_EXAMPLE_ALL_ROUTING_ONLY)
@given(resolution_map=_st_resolution_map)
@settings(max_examples=100)
def test_validate_uuid_tool_scoping_iff_unresolved_or_routing_only_on_non_routing(
    resolution_map: dict[str, str | None],
) -> None:
    """``validate_uuid_tool_scoping`` reports a violation for a node's
    tool_uuid entry if and only if that UUID is unresolvable, or it resolves
    to a routing-only tool and the node is not a Routing node.

    **Validates: Requirements 11.1, 11.2, 11.4**
    """
    # Feature: switchboard-frontend-enablement, Property 6: Gate-by-scoping invariant

    # A UUID missing from the map (None in our generator) models an
    # unresolvable identity — omit it entirely so `.get()` returns None.
    uuid_to_connector_name = {
        tool_uuid: name
        for tool_uuid, name in resolution_map.items()
        if name is not None
    }

    violations = validate_uuid_tool_scoping(_RECONCILED_NODES, uuid_to_connector_name)

    expected = _expected_violations(_RECONCILED_NODES, uuid_to_connector_name)
    actual = _actual_violations(violations)

    assert actual == expected
    # Every violation corresponds to exactly one (node_id, tool_uuid) pair —
    # no duplicate/merged messages are produced.
    assert len(violations) == len(expected)


def test_correctly_scoped_switchboard_graph_has_no_violations() -> None:
    """The real, correctly-scoped switchboard graph with a complete, correct
    resolution map produces zero gate-by-scoping violations.

    **Validates: Requirements 11.1, 11.2, 11.4**
    """
    violations = validate_uuid_tool_scoping(
        _RECONCILED_NODES, _CORRECT_UUID_TO_CONNECTOR_NAME
    )
    assert violations == []
