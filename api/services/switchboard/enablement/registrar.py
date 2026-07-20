"""Template_Registrar: register the switchboard graph as a workflow template.

Serializes the assembled switchboard ``ReactFlowDTO`` into ``template_json``
and create-or-updates the ``spinsci-switchboard`` catalog entry via
``WorkflowTemplateClient``.

Design references:
- ``design.md`` → "Template_Registrar"
- ``requirements.md`` → Requirements 1.1, 1.2, 1.3, 1.4, 1.6

Requirements: 1.1, 1.2, 1.3, 1.4, 1.6.
"""

from __future__ import annotations

from loguru import logger

from api.db.models import WorkflowTemplates
from api.db.workflow_template_client import WorkflowTemplateClient
from api.services.switchboard.enablement.serialize import (
    serialize_switchboard_template_json,
)

#: Stable catalog key. Never changes across registrations so repeated runs
#: update the same row instead of creating duplicates (Req 1.2, 1.3, 1.4).
SWITCHBOARD_TEMPLATE_NAME = "spinsci-switchboard"

SWITCHBOARD_TEMPLATE_DESCRIPTION = "SpinSci AI Virtual Switchboard (inbound)."


class SwitchboardTemplateInvalid(Exception):
    """Raised when the serialized switchboard ``template_json`` fails
    Graph_Validator validation (Req 1.6).

    Carries the collected validation error messages so callers can report
    them without re-deriving them from a generic exception.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            "Switchboard template_json failed validation: " + "; ".join(errors)
        )


async def register_switchboard_template(
    template_client: WorkflowTemplateClient | None = None,
) -> WorkflowTemplates:
    """Serialize build_switchboard_reactflow_dto() to template_json and
    create-or-update the catalog entry keyed by SWITCHBOARD_TEMPLATE_NAME.

    Raises SwitchboardTemplateInvalid if the serialized template_json fails
    Graph_Validator validation (Req 1.6).

    Args:
        template_client: The ``WorkflowTemplateClient`` to use. Defaults to a
            new instance, but tests may inject an in-memory fake to exercise
            idempotence without a real database.

    Returns:
        The created or updated ``WorkflowTemplates`` row.

    Raises:
        SwitchboardTemplateInvalid: If the assembled graph fails validation
            (Req 1.6). Nothing is written to the catalog in this case.
    """
    client = template_client or WorkflowTemplateClient()

    # Validates via WorkflowGraph + validate_tool_scoping before returning;
    # raises SwitchboardTemplateInvalid on failure (Req 1.1, 1.6).
    template_json = serialize_switchboard_template_json()

    existing = await client.get_workflow_template_by_name(SWITCHBOARD_TEMPLATE_NAME)

    if existing is None:
        logger.info(
            "Registering new switchboard workflow template: {}",
            SWITCHBOARD_TEMPLATE_NAME,
        )
        return await client.create_workflow_template(
            template_name=SWITCHBOARD_TEMPLATE_NAME,
            template_description=SWITCHBOARD_TEMPLATE_DESCRIPTION,
            template_json=template_json,
        )

    logger.info(
        "Updating existing switchboard workflow template: {} (id={})",
        SWITCHBOARD_TEMPLATE_NAME,
        existing.id,
    )
    return await client.update_workflow_template(
        template_id=existing.id,
        template_json=template_json,
    )


__all__ = [
    "SWITCHBOARD_TEMPLATE_DESCRIPTION",
    "SWITCHBOARD_TEMPLATE_NAME",
    "SwitchboardTemplateInvalid",
    "register_switchboard_template",
]
