"""Property-based test for template serialization round-trip (task 2.2).

Covers Property 1 — Template serialization round-trip (Requirements 1.1, 1.5).

For all nodes and edges in the switchboard graph, serializing the assembled
``ReactFlowDTO`` into ``template_json`` and loading it back through the
Graph_Validator (``WorkflowGraph``) reconstructs a graph with the same node
ids, node types, edge ``condition``/``transition_speech`` values,
``extraction_variables``, and node ``tool_uuids`` references.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 1: Template
  serialization round-trip"
- ``requirements.md`` -> Requirements 1.1, 1.5

Requirements: 1.1, 1.5.
"""

from __future__ import annotations

import random
import string
from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from api.services.switchboard.clusters.tool_scoping import validate_tool_scoping
from api.services.switchboard.graph import build_switchboard_reactflow_dto
from api.services.workflow.dto import (
    EdgeDataDTO,
    ExtractionVariableDTO,
    ReactFlowDTO,
    RFEdgeDTO,
    RFNodeDTO,
    VariableType,
)
from api.services.workflow.workflow_graph import WorkflowGraph

# ---------------------------------------------------------------------------
# Real assembled switchboard DTO — perturbations are built on top of this so
# the property exercises the actual switchboard shape rather than an invented
# graph (per the design's "Generators" guidance).
# ---------------------------------------------------------------------------

_BASE_DTO: ReactFlowDTO = build_switchboard_reactflow_dto()

#: agentNode ids are unconstrained on outgoing edges (no `max_outgoing`) and
#: support `extraction_variables`, so perturbations that add edges/variables
#: are anchored to this set to stay structure-preserving.
_AGENT_NODE_IDS: list[str] = sorted(
    n.id for n in _BASE_DTO.nodes if n.type == "agentNode"
)

#: agentNode/endCall targets have no `max_incoming` constraint, so adding an
#: extra incoming edge to one never violates `WorkflowGraph` cardinality
#: rules (startCall/trigger/globalNode forbid incoming edges entirely).
_EXTRA_EDGE_TARGET_IDS: list[str] = sorted(
    n.id for n in _BASE_DTO.nodes if n.type in ("agentNode", "endCall")
)

assert _AGENT_NODE_IDS, "Expected at least one agentNode in the switchboard graph"
assert _EXTRA_EDGE_TARGET_IDS, "Expected at least one agentNode/endCall node"


# ---------------------------------------------------------------------------
# Strategies — structure-preserving perturbations
# ---------------------------------------------------------------------------

_st_var_name_seed = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=10)

_st_extra_variable_spec = st.tuples(
    st.sampled_from(_AGENT_NODE_IDS),
    _st_var_name_seed,
    st.sampled_from(list(VariableType)),
)

_st_extra_edge_spec = st.tuples(
    st.sampled_from(_AGENT_NODE_IDS),
    st.sampled_from(_EXTRA_EDGE_TARGET_IDS),
    st.sampled_from(["silent_empty", "silent_none", "verbatim"]),
)

_st_perturbation = st.fixed_dictionaries(
    {
        "shuffle_seed": st.integers(min_value=0, max_value=2**31 - 1),
        "extra_variables": st.lists(_st_extra_variable_spec, max_size=4),
        "extra_edges": st.lists(_st_extra_edge_spec, max_size=4),
    }
)


def _apply_perturbation(base_dto: ReactFlowDTO, spec: dict) -> ReactFlowDTO:
    """Build a structure-preserving perturbation of ``base_dto``.

    Reorders nodes/edges, appends extraction variables to existing agentNode
    nodes, and adds extra silent/verbatim edges between existing agentNode/
    endCall nodes — never inventing a new node type, edge field, or schema.
    """
    rng = random.Random(spec["shuffle_seed"])

    # Group extra variables by target node id, giving each a name that can't
    # collide with any real switchboard variable name (e.g. "intent").
    extra_vars_by_node: dict[str, list[ExtractionVariableDTO]] = {}
    for idx, (node_id, name_seed, var_type) in enumerate(spec["extra_variables"]):
        var_name = f"pbt_extra_{idx}_{name_seed}"
        extra_vars_by_node.setdefault(node_id, []).append(
            ExtractionVariableDTO(
                name=var_name,
                type=var_type,
                prompt="PBT-added extraction variable for round-trip testing.",
            )
        )

    new_nodes: list[RFNodeDTO] = []
    for node in base_dto.nodes:
        extra = extra_vars_by_node.get(node.id)
        if not extra:
            new_nodes.append(node)
            continue
        existing = list(getattr(node.data, "extraction_variables", None) or [])
        updated_data = node.data.model_copy(
            update={
                "extraction_enabled": True,
                "extraction_variables": existing + extra,
            }
        )
        new_nodes.append(
            RFNodeDTO(
                id=node.id,
                type=node.type,
                position=node.position,
                data=updated_data,
            )
        )

    new_edges: list[RFEdgeDTO] = list(base_dto.edges)
    for idx, (source, target, edge_kind) in enumerate(spec["extra_edges"]):
        edge_id = f"pbt_extra_edge_{idx}_{source}_{target}"
        if edge_kind == "silent_empty":
            transition_speech = ""
            label = "PBT silent extra edge (empty)"
        elif edge_kind == "silent_none":
            transition_speech = None
            label = "PBT silent extra edge (none)"
        else:
            transition_speech = (
                "This is a verbatim PBT test line spoken exactly as written."
            )
            label = "PBT verbatim extra edge"
        new_edges.append(
            RFEdgeDTO(
                id=edge_id,
                source=source,
                target=target,
                data=EdgeDataDTO(
                    label=label,
                    condition=(
                        f"PBT-added {edge_kind} transition condition for "
                        "round-trip testing."
                    ),
                    transition_speech=transition_speech,
                    transition_speech_type="text" if transition_speech else None,
                ),
            )
        )

    rng.shuffle(new_nodes)
    rng.shuffle(new_edges)

    return ReactFlowDTO(nodes=new_nodes, edges=new_edges)


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def _node_type_map(nodes) -> dict[str, str]:
    return {n.id: n.type for n in nodes}


def _variable_type_value(var_type) -> str:
    return var_type.value if hasattr(var_type, "value") else var_type


def _extraction_variables_map(nodes) -> dict[str, tuple | None]:
    result: dict[str, tuple | None] = {}
    for n in nodes:
        variables = getattr(n.data, "extraction_variables", None)
        if variables is None:
            result[n.id] = None
        else:
            result[n.id] = tuple(
                (v.name, _variable_type_value(v.type), v.prompt) for v in variables
            )
    return result


def _tool_uuids_map(nodes) -> dict[str, tuple | None]:
    result: dict[str, tuple | None] = {}
    for n in nodes:
        tool_uuids = getattr(n.data, "tool_uuids", None)
        result[n.id] = tuple(tool_uuids) if tool_uuids is not None else None
    return result


def _edge_attr(edge, attr: str):
    """Read ``attr`` from an edge's nested ``.data`` (RFEdgeDTO) or directly
    (WorkflowGraph's ``Edge``, which also exposes ``.data``)."""
    data = getattr(edge, "data", None)
    if data is not None:
        return getattr(data, attr)
    return getattr(edge, attr)


def _edge_multiset(edges) -> Counter:
    return Counter(
        (
            edge.source,
            edge.target,
            _edge_attr(edge, "condition"),
            _edge_attr(edge, "transition_speech"),
        )
        for edge in edges
    )


# ---------------------------------------------------------------------------
# Property 1: Template serialization round-trip
# ---------------------------------------------------------------------------


# Feature: switchboard-frontend-enablement, Property 1: Template serialization round-trip
@given(spec=_st_perturbation)
@settings(max_examples=100)
def test_serialize_then_reload_preserves_graph_shape(spec: dict) -> None:
    """Serializing then reloading a switchboard-derived DTO through
    ``WorkflowGraph`` reconstructs the same node ids, node types, edge
    ``condition``/``transition_speech`` values, ``extraction_variables``, and
    node ``tool_uuids``.

    **Validates: Requirements 1.1, 1.5**
    """
    # Feature: switchboard-frontend-enablement, Property 1: Template serialization round-trip

    perturbed_dto = _apply_perturbation(_BASE_DTO, spec)

    # Sanity: the perturbation is structure-preserving, so it must still pass
    # the same Graph_Validator checks the real switchboard graph passes.
    WorkflowGraph(perturbed_dto)
    assert validate_tool_scoping(perturbed_dto.nodes) == []

    before_node_types = _node_type_map(perturbed_dto.nodes)
    before_extraction = _extraction_variables_map(perturbed_dto.nodes)
    before_tools = _tool_uuids_map(perturbed_dto.nodes)
    before_edges = _edge_multiset(perturbed_dto.edges)

    # Serialize (as the Template_Registrar does) then reload.
    template_json = perturbed_dto.model_dump(mode="json")
    reloaded_dto = ReactFlowDTO.model_validate(template_json)

    # Load it back through the Graph_Validator.
    reloaded_graph = WorkflowGraph(reloaded_dto)

    # Same node ids.
    assert set(reloaded_graph.nodes.keys()) == set(before_node_types.keys())

    # Same node types.
    after_node_types = {
        node_id: node.node_type for node_id, node in reloaded_graph.nodes.items()
    }
    assert after_node_types == before_node_types

    # Same extraction_variables per node.
    after_extraction: dict[str, tuple | None] = {}
    for node_id, node in reloaded_graph.nodes.items():
        variables = node.extraction_variables
        if variables is None:
            after_extraction[node_id] = None
        else:
            after_extraction[node_id] = tuple(
                (v.name, _variable_type_value(v.type), v.prompt) for v in variables
            )
    assert after_extraction == before_extraction

    # Same tool_uuids per node.
    after_tools = {
        node_id: (tuple(node.tool_uuids) if node.tool_uuids is not None else None)
        for node_id, node in reloaded_graph.nodes.items()
    }
    assert after_tools == before_tools

    # Same edge condition/transition_speech values (order-independent).
    after_edges = _edge_multiset(reloaded_graph.edges)
    assert after_edges == before_edges
