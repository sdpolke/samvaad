"""Property-based test for speech and prompt preservation (task 11.2).

Covers Property 7 — Speech and prompt preservation (Requirements 12.1, 12.3,
12.4).

For all edges and nodes, serializing and instantiating the switchboard
preserves every empty ``transition_speech`` as empty (silent transitions stay
silent), preserves every node prompt and edge ``transition_speech`` value
unchanged, and preserves each node's ``add_global_prompt`` value unchanged —
across the full pipeline:
``serialize_switchboard_template_json()`` (inlined against a perturbed DTO,
since that function only ever assembles the real unperturbed switchboard
graph internally) -> reload into a ``ReactFlowDTO`` ->
``reconcile_tool_references(...)``.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 7: Speech and
  prompt preservation"
- ``requirements.md`` -> Requirements 12.1, 12.3, 12.4

Requirements: 12.1, 12.3, 12.4.
"""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from api.services.switchboard.clusters.tool_scoping import validate_tool_scoping
from api.services.switchboard.enablement.reconcile import reconcile_tool_references
from api.services.switchboard.graph import build_switchboard_reactflow_dto
from api.services.workflow.dto import EdgeDataDTO, ReactFlowDTO, RFEdgeDTO, RFNodeDTO
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.switchboard.enablement._pipeline_helpers import (
    build_default_name_to_uuid,
)

# ---------------------------------------------------------------------------
# Real assembled switchboard DTO — perturbations are built on top of this so
# the property exercises the actual switchboard shape rather than an invented
# graph (per the design's "Generators" guidance), matching the pattern
# established in test_registrar_roundtrip_property.py (task 2.2).
# ---------------------------------------------------------------------------

_BASE_DTO: ReactFlowDTO = build_switchboard_reactflow_dto()

#: agentNode ids are unconstrained on outgoing edges (no `max_outgoing`) and
#: are where `prompt` / `add_global_prompt` perturbations are anchored, since
#: `agentNode` is the node type that always carries both fields for a
#: mid-call step.
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
# Strategies — structure-preserving perturbations that add silent/verbatim
# edges and perturb node prompt / add_global_prompt values.
# ---------------------------------------------------------------------------

_st_extra_edge_spec = st.tuples(
    st.sampled_from(_AGENT_NODE_IDS),
    st.sampled_from(_EXTRA_EDGE_TARGET_IDS),
    st.sampled_from(["silent_empty", "silent_none", "verbatim"]),
)

_st_global_prompt_toggle_spec = st.sampled_from(_AGENT_NODE_IDS)

_st_verbatim_prompt_spec = st.tuples(
    st.sampled_from(_AGENT_NODE_IDS),
    st.integers(min_value=0, max_value=2**31 - 1),
)

_st_perturbation = st.fixed_dictionaries(
    {
        "shuffle_seed": st.integers(min_value=0, max_value=2**31 - 1),
        "extra_edges": st.lists(_st_extra_edge_spec, max_size=4),
        "add_global_prompt_false_node_ids": st.lists(
            _st_global_prompt_toggle_spec, max_size=4, unique=True
        ),
        "verbatim_prompts": st.lists(_st_verbatim_prompt_spec, max_size=4),
    }
)


def _apply_perturbation(base_dto: ReactFlowDTO, spec: dict) -> ReactFlowDTO:
    """Build a structure-preserving perturbation of ``base_dto``.

    Reorders nodes/edges, adds extra silent (empty ``transition_speech``) and
    verbatim edges between existing agentNode/endCall nodes, sets
    ``add_global_prompt=False`` on a subset of existing agentNode nodes, and
    sets a distinctive verbatim ``prompt`` on a (possibly overlapping) subset
    of existing agentNode nodes — never inventing a new node type, edge
    field, or schema.
    """
    rng = random.Random(spec["shuffle_seed"])

    false_global_prompt_ids: set[str] = set(spec["add_global_prompt_false_node_ids"])

    verbatim_prompt_by_node: dict[str, str] = {}
    for node_id, seed in spec["verbatim_prompts"]:
        verbatim_prompt_by_node[node_id] = (
            f"VERBATIM_PROMPT_{seed}: this exact mandated line must be "
            "reproduced without modification."
        )

    new_nodes: list[RFNodeDTO] = []
    for node in base_dto.nodes:
        data_update: dict = {}
        if node.id in false_global_prompt_ids and hasattr(
            node.data, "add_global_prompt"
        ):
            data_update["add_global_prompt"] = False
        if node.id in verbatim_prompt_by_node and hasattr(node.data, "prompt"):
            data_update["prompt"] = verbatim_prompt_by_node[node.id]

        if not data_update:
            new_nodes.append(node)
            continue

        updated_data = node.data.model_copy(update=data_update)
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
        edge_id = f"pbt_speech_extra_edge_{idx}_{source}_{target}"
        if edge_kind == "silent_empty":
            transition_speech = ""
            label = "PBT silent extra edge (empty)"
        elif edge_kind == "silent_none":
            transition_speech = None
            label = "PBT silent extra edge (none)"
        else:
            transition_speech = (
                f"VERBATIM_EDGE_SPEECH_{idx}: spoken exactly as written."
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
                        "speech-preservation testing."
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


def _node_prompts(nodes) -> dict[str, str | None]:
    return {n.id: getattr(n.data, "prompt", None) for n in nodes}


def _node_add_global_prompts(nodes) -> dict[str, bool | None]:
    return {n.id: getattr(n.data, "add_global_prompt", None) for n in nodes}


def _edge_transition_speech(edges) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for edge in edges:
        data = getattr(edge, "data", None)
        speech = getattr(data, "transition_speech", None) if data is not None else (
            getattr(edge, "transition_speech", None)
        )
        result[edge.id] = speech
    return result


# ---------------------------------------------------------------------------
# Property 7: Speech and prompt preservation
# ---------------------------------------------------------------------------


# Feature: switchboard-frontend-enablement, Property 7: Speech and prompt preservation
@given(spec=_st_perturbation)
@settings(max_examples=100)
def test_speech_and_prompt_preservation_across_pipeline(spec: dict) -> None:
    """Every empty ``transition_speech`` stays empty, every node prompt and
    edge ``transition_speech`` value is unchanged, and every node's
    ``add_global_prompt`` value is unchanged after
    ``serialize_switchboard_template_json`` -> reload ->
    ``reconcile_tool_references``.

    ``serialize_switchboard_template_json()`` only ever assembles the real,
    unperturbed switchboard graph internally (it calls
    ``build_switchboard_reactflow_dto()`` with no way to inject a custom
    starting DTO), so this test inlines the equivalent of that function's
    body (``WorkflowGraph`` + ``validate_tool_scoping`` validation, then
    ``model_dump(mode="json")``) applied to the perturbed DTO instead, then
    continues the same reload -> reconcile chain
    ``run_full_pipeline()``/``_pipeline_helpers.py`` uses for the real graph.

    **Validates: Requirements 12.1, 12.3, 12.4**
    """
    # Feature: switchboard-frontend-enablement, Property 7: Speech and prompt preservation

    perturbed_dto = _apply_perturbation(_BASE_DTO, spec)

    # Sanity: the perturbation is structure-preserving, so it must still pass
    # the same Graph_Validator checks the real switchboard graph passes.
    WorkflowGraph(perturbed_dto)
    assert validate_tool_scoping(perturbed_dto.nodes) == []

    before_prompts = _node_prompts(perturbed_dto.nodes)
    before_add_global_prompts = _node_add_global_prompts(perturbed_dto.nodes)
    before_edge_speech = _edge_transition_speech(perturbed_dto.edges)

    # Inline serialize_switchboard_template_json()'s body against the
    # perturbed DTO (it cannot itself accept a custom starting DTO).
    template_json = perturbed_dto.model_dump(mode="json")

    # Reload.
    reloaded_dto = ReactFlowDTO.model_validate(template_json)

    # Reconcile tool references (name-strings -> real UUIDs).
    name_to_uuid = build_default_name_to_uuid(reloaded_dto)
    reconciled_dto = reconcile_tool_references(reloaded_dto, name_to_uuid)

    after_prompts = _node_prompts(reconciled_dto.nodes)
    after_add_global_prompts = _node_add_global_prompts(reconciled_dto.nodes)
    after_edge_speech = _edge_transition_speech(reconciled_dto.edges)

    # Every node prompt is unchanged (Req 12.3, verbatim node prompts).
    assert after_prompts == before_prompts

    # Every node's add_global_prompt is unchanged (Req 12.4).
    assert after_add_global_prompts == before_add_global_prompts

    # Every edge's transition_speech (silent or verbatim) is unchanged
    # (Req 12.3).
    assert after_edge_speech == before_edge_speech

    # Every empty transition_speech stays empty (Req 12.1).
    for edge_id, before_speech in before_edge_speech.items():
        if not before_speech:
            assert not after_edge_speech[edge_id]
