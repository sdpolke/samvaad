"""Serialization helpers for the switchboard ``ReactFlowDTO``.

Wraps ``build_switchboard_reactflow_dto()`` with validation
(``WorkflowGraph`` + ``validate_tool_scoping``) and produces the
``template_json`` consumed by the Template_Registrar.

Design references:
- ``design.md`` → "Template_Registrar", "Serialization seam (minimal refactor)"
- ``requirements.md`` → Requirements 1.1, 1.6

Requirements: 1.1, 1.6.
"""

from __future__ import annotations

from loguru import logger

from api.services.switchboard.clusters.tool_scoping import validate_tool_scoping
from api.services.switchboard.graph import build_switchboard_reactflow_dto
from api.services.workflow.workflow_graph import WorkflowGraph


def serialize_switchboard_template_json() -> dict:
    """Assemble, validate, and serialize the switchboard graph as ``template_json``.

    Calls :func:`build_switchboard_reactflow_dto` to assemble the raw
    ``ReactFlowDTO``, validates it through
    :class:`~api.services.workflow.workflow_graph.WorkflowGraph` and
    :func:`validate_tool_scoping`, and returns
    ``dto.model_dump(mode="json")`` — preserving node ids, node types, edge
    ``condition``/``transition_speech`` values, ``extraction_variables``, and
    node ``tool_uuids`` name-string references (Req 1.1, 1.5).

    Returns:
        The switchboard ``ReactFlow_Definition`` as a JSON-serializable dict,
        suitable for storing as a ``WorkflowTemplates.template_json`` value.

    Raises:
        SwitchboardTemplateInvalid: If the assembled DTO fails
            ``WorkflowGraph`` validation or ``validate_tool_scoping``
            (Req 1.6). Carries the collected validation error messages.
    """
    # Imported lazily to avoid a module-level circular import: registrar.py
    # imports this module's function, and this exception is defined in
    # registrar.py per the design.
    from api.services.switchboard.enablement.registrar import (
        SwitchboardTemplateInvalid,
    )

    dto = build_switchboard_reactflow_dto()

    validation_errors: list[str] = []

    try:
        WorkflowGraph(dto)
    except ValueError as exc:
        graph_errors = exc.args[0] if exc.args else []
        validation_errors.extend(str(error) for error in graph_errors)

    validation_errors.extend(validate_tool_scoping(dto.nodes))

    if validation_errors:
        logger.error(
            "Switchboard template_json failed validation: {}", validation_errors
        )
        raise SwitchboardTemplateInvalid(validation_errors)

    return dto.model_dump(mode="json")


__all__ = ["serialize_switchboard_template_json"]
