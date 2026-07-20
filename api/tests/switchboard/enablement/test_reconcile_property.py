"""Property-based test for tool-reference reconciliation completeness (task 4.2).

Covers Property 4 — Tool-reference reconciliation completeness
(Requirements 5.1, 5.2, 3.3).

For all `name_to_uuid` maps that cover every connector name-string referenced
across the real switchboard graph's node `tool_uuids` (plus perturbed variants
with extra, unreferenced names), reconciling the graph through
`reconcile_tool_references` resolves every node's `tool_uuids` to real
provisioned UUIDs (no connector name-string remains), preserves each node's
resolved connector identities exactly (cluster scoping preserved), and the
reconciled `ReactFlowDTO` still passes `WorkflowGraph` validation.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 4: Tool-reference
  reconciliation completeness"
- ``requirements.md`` -> Requirements 5.1, 5.2, 3.3

Requirements: 5.1, 5.2, 3.3.
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from api.services.switchboard.enablement.reconcile import reconcile_tool_references
from api.services.switchboard.graph import build_switchboard_reactflow_dto
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph

# ---------------------------------------------------------------------------
# Real assembled switchboard DTO — the property exercises the actual
# switchboard shape rather than an invented graph (per the design's
# "Generators" guidance).
# ---------------------------------------------------------------------------

_BASE_DTO: ReactFlowDTO = build_switchboard_reactflow_dto()


def _collect_connector_names(dto: ReactFlowDTO) -> list[str]:
    """Every distinct connector name-string referenced in any node's
    ``tool_uuids`` across the real switchboard DTO."""
    names: set[str] = set()
    for node in dto.nodes:
        tool_uuids = getattr(node.data, "tool_uuids", None)
        if tool_uuids:
            names.update(tool_uuids)
    return sorted(names)


#: The full set of connector name-strings referenced anywhere in the real
#: switchboard graph — every generated `name_to_uuid` map must cover all of
#: these (a superset) so `reconcile_tool_references` never raises
#: `UnresolvedToolReference`.
_CORE_CONNECTOR_NAMES: list[str] = _collect_connector_names(_BASE_DTO)

assert _CORE_CONNECTOR_NAMES, (
    "Expected the switchboard graph to reference at least one connector "
    "tool name via node tool_uuids"
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: Names for unreferenced/extra entries the generated map may carry in
#: addition to the required core names (a superset is still valid input).
#: The fixed prefix guarantees these never collide with a real connector
#: name (e.g. "patient_lookup", "transfer").
_st_extra_name = st.text(
    alphabet=string.ascii_lowercase, min_size=1, max_size=10
).map(lambda s: f"pbt_unreferenced_{s}")


@st.composite
def _st_name_to_uuid_spec(draw: st.DrawFn) -> tuple[list, list[str]]:
    """Draw (uuid_pool, extra_names) where ``uuid_pool`` has exactly one
    unique UUID per core connector name plus one per extra name, so the
    resulting `name_to_uuid` map's values are all distinct and a reverse
    (uuid -> name) map is unambiguous."""
    extra_names = draw(
        st.lists(_st_extra_name, min_size=0, max_size=5, unique=True)
    )
    total = len(_CORE_CONNECTOR_NAMES) + len(extra_names)
    uuid_pool = draw(
        st.lists(st.uuids(), min_size=total, max_size=total, unique=True)
    )
    return uuid_pool, extra_names


# ---------------------------------------------------------------------------
# Property 4: Tool-reference reconciliation completeness
# ---------------------------------------------------------------------------


# Feature: switchboard-frontend-enablement, Property 4: Tool-reference reconciliation completeness
@given(spec=_st_name_to_uuid_spec())
@settings(max_examples=100)
def test_reconcile_tool_references_completeness(
    spec: tuple[list, list[str]],
) -> None:
    """Reconciling the real switchboard graph against a `name_to_uuid` map
    covering all referenced connector names resolves every node's
    `tool_uuids` to real UUIDs, preserves each node's resolved connector
    identities exactly, and the reconciled DTO still passes `WorkflowGraph`
    validation.

    **Validates: Requirements 5.1, 5.2, 3.3**
    """
    # Feature: switchboard-frontend-enablement, Property 4: Tool-reference reconciliation completeness

    uuid_pool, extra_names = spec
    core_uuids = uuid_pool[: len(_CORE_CONNECTOR_NAMES)]
    extra_uuids = uuid_pool[len(_CORE_CONNECTOR_NAMES) :]

    name_to_uuid: dict[str, str] = {
        name: str(u) for name, u in zip(_CORE_CONNECTOR_NAMES, core_uuids)
    }
    for name, u in zip(extra_names, extra_uuids):
        name_to_uuid[name] = str(u)

    # Reverse map restricted to the core names actually resolvable through a
    # node's tool_uuids (the only names reconciliation ever reads).
    uuid_to_name: dict[str, str] = {
        v: k for k, v in name_to_uuid.items() if k in _CORE_CONNECTOR_NAMES
    }

    before_tool_names: dict[str, tuple[str, ...] | None] = {}
    for node in _BASE_DTO.nodes:
        tool_uuids = getattr(node.data, "tool_uuids", None)
        before_tool_names[node.id] = (
            tuple(tool_uuids) if tool_uuids else None
        )

    reconciled_dto = reconcile_tool_references(_BASE_DTO, name_to_uuid)

    valid_uuid_values = set(name_to_uuid.values())

    for node in reconciled_dto.nodes:
        before = before_tool_names[node.id]
        after_tool_uuids = getattr(node.data, "tool_uuids", None)

        if not before:
            # Nodes with no tool references are unaffected.
            assert not after_tool_uuids
            continue

        assert after_tool_uuids is not None
        assert len(after_tool_uuids) == len(before)

        for value in after_tool_uuids:
            # (a) Every resolved entry is a real UUID drawn from the
            # name_to_uuid codomain — no connector name-string remains.
            assert value in valid_uuid_values
            assert value not in _CORE_CONNECTOR_NAMES

        # (b) The node's resolved connector identities equal exactly its
        # pre-reconciliation name-string sequence (cluster scoping
        # preserved) — order and duplicates included, not just the set.
        resolved_names = tuple(uuid_to_name[v] for v in after_tool_uuids)
        assert resolved_names == before

    # (c) The reconciled DTO still passes Graph_Validator validation.
    WorkflowGraph(reconciled_dto)
