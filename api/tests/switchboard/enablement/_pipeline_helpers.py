"""Test-support helper chaining the full serialize -> reload -> reconcile pipeline.

This module is **not** a test module (no `test_` functions, no assertions) —
it is a small support seam used by property tests (see task 11.2,
``test_speech_preservation_property.py``) that need to exercise the full
enablement pipeline end to end:

``serialize_switchboard_template_json()`` -> reload into a ``ReactFlowDTO``
-> ``reconcile_tool_references(...)``.

No new production transformation is introduced here (per Design
"Silent-transition / verbatim / global-prompt preservation" — the existing
``model_dump(mode="json")`` serialization from task 2 and the reconciler's
``tool_uuids``-only rewrite from task 4 already satisfy preservation); this
helper only wires those two existing pieces together for tests.

Design references:
- ``design.md`` -> "Serialization seam (minimal refactor)", "Template_Registrar",
  "Tool-reference reconciler"
- ``requirements.md`` -> Requirements 12.1, 12.3, 12.4
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from api.services.switchboard.enablement.reconcile import reconcile_tool_references
from api.services.switchboard.enablement.serialize import (
    serialize_switchboard_template_json,
)
from api.services.workflow.dto import ReactFlowDTO

# Fixed namespace UUID so synthetic tool UUIDs are deterministic/reproducible
# across test runs (uuid.uuid5 is deterministic given the same namespace +
# name, unlike uuid.uuid4).
_SYNTHETIC_TOOL_UUID_NAMESPACE = uuid.UUID("d3f1b1f0-6c1a-4f6e-9c8b-4b6a1f0c9e2d")


@dataclass(frozen=True)
class PipelineResult:
    """Result of running the full serialize -> reload -> reconcile pipeline.

    Attributes:
        pre_reconciliation_dto: The ``ReactFlowDTO`` reloaded from
            ``template_json`` (name-string ``tool_uuids``), before
            reconciliation.
        reconciled_dto: The ``ReactFlowDTO`` returned by
            ``reconcile_tool_references`` (real-UUID ``tool_uuids``).
        name_to_uuid: The connector-name -> synthetic-UUID mapping used to
            reconcile ``pre_reconciliation_dto`` into ``reconciled_dto``.
    """

    pre_reconciliation_dto: ReactFlowDTO
    reconciled_dto: ReactFlowDTO
    name_to_uuid: dict[str, str]


def _connector_names(dto: ReactFlowDTO) -> set[str]:
    """Collect every connector name referenced across all nodes' ``tool_uuids``."""
    names: set[str] = set()
    for node in dto.nodes:
        tool_uuids = getattr(node.data, "tool_uuids", None)
        if tool_uuids:
            names.update(tool_uuids)
    return names


def build_default_name_to_uuid(dto: ReactFlowDTO) -> dict[str, str]:
    """Build a deterministic ``{connector_name: synthetic_uuid}`` map.

    Covers every connector name-string referenced across all nodes'
    ``tool_uuids`` in ``dto``, using ``uuid.uuid5`` (keyed by connector name)
    so the mapping is reproducible across test runs.

    Args:
        dto: The ``ReactFlowDTO`` whose node ``tool_uuids`` name-strings
            should all resolve.

    Returns:
        A mapping from connector name to a deterministic synthetic UUID
        string.
    """
    return {
        name: str(uuid.uuid5(_SYNTHETIC_TOOL_UUID_NAMESPACE, name))
        for name in _connector_names(dto)
    }


def run_full_pipeline(
    name_to_uuid: dict[str, str] | None = None,
) -> PipelineResult:
    """Chain serialize -> reload -> reconcile over the real switchboard graph.

    Calls ``serialize_switchboard_template_json()``, reloads the resulting
    ``template_json`` into a ``ReactFlowDTO``, builds a default
    ``name_to_uuid`` (if not provided) covering every connector name
    referenced in the reloaded DTO using deterministic synthetic UUIDs, and
    reconciles the DTO via ``reconcile_tool_references``.

    Args:
        name_to_uuid: Optional connector-name -> tool-uuid mapping to use for
            reconciliation. If ``None``, a deterministic default mapping is
            built covering every connector name referenced in the real
            switchboard graph (see :func:`build_default_name_to_uuid`).

    Returns:
        A :class:`PipelineResult` carrying the pre-reconciliation DTO, the
        reconciled DTO, and the ``name_to_uuid`` mapping used.
    """
    template_json = serialize_switchboard_template_json()
    pre_reconciliation_dto = ReactFlowDTO.model_validate(template_json)

    if name_to_uuid is None:
        name_to_uuid = build_default_name_to_uuid(pre_reconciliation_dto)

    reconciled_dto = reconcile_tool_references(pre_reconciliation_dto, name_to_uuid)

    return PipelineResult(
        pre_reconciliation_dto=pre_reconciliation_dto,
        reconciled_dto=reconciled_dto,
        name_to_uuid=name_to_uuid,
    )


__all__ = [
    "PipelineResult",
    "build_default_name_to_uuid",
    "run_full_pipeline",
]
