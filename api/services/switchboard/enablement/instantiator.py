"""Template_Instantiator: orchestrate switchboard instantiation.

Provisions connector tools, reconciles tool references, regenerates trigger
identifiers, stamps ``organization_id``, validates the reconciled definition
in memory, persists the workflow, and rolls back atomically on failure.

Steps (Design "Template_Instantiator"):
1. Provision the 11 connector tools for the org (idempotent) — Req 4.
2. Reconcile the template's name-string ``tool_uuids`` to the provisioned
   UUIDs — Req 5.1, 5.2, 5.3, 5.4.
3. Regenerate trigger node identifiers so triggers do not collide — Req 3.2.
4. Stamp the new workflow's ``organization_id`` — Req 3.1, 3.5, 13.1.
5. Validate the reconciled definition through ``WorkflowGraph`` and the
   UUID-aware gate-by-scoping check, in memory, before persisting —
   Req 3.3, 3.4, 11.4.
6. Persist the workflow and sync triggers.
7. On any failure after step (1), roll back exactly the tool rows newly
   created during this run (never reused ones) and raise a structured
   ``SwitchboardInstantiationError`` — Req 3.6.

Design references:
- ``design.md`` -> "Template_Instantiator", "Error Handling"
- ``requirements.md`` -> Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.4

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.4.
"""

from __future__ import annotations

from typing import Sequence

from loguru import logger
from pydantic import ValidationError

from api.db import db_client as _shared_db_client
from api.db.agent_trigger_client import TriggerPathConflictError
from api.db.db_client import DBClient
from api.db.models import WorkflowModel, WorkflowTemplates
from api.enums import ToolStatus
from api.services.switchboard.enablement.provisioner import provision_connector_tools
from api.services.switchboard.enablement.reconcile import (
    UnresolvedToolReference,
    reconcile_tool_references,
)
from api.services.switchboard.enablement.scoping import (
    build_uuid_to_connector_name,
    validate_uuid_tool_scoping,
)
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.duplicate import (
    extract_trigger_paths,
    regenerate_trigger_uuids,
)
from api.services.workflow.workflow_graph import WorkflowGraph


class SwitchboardInstantiationError(Exception):
    """Structured error raised when switchboard instantiation fails.

    Carries a machine-readable ``reason`` and, where applicable, the list of
    underlying error/violation messages (e.g. graph-validation errors,
    gate-by-scoping violations, or an unresolved tool reference message) so a
    route handler can map this to an HTTP 422 response identifying the
    validation/rollback failure (task 12.1 — not this task).
    """

    def __init__(self, reason: str, errors: list[str] | None = None) -> None:
        self.reason = reason
        self.errors = list(errors) if errors else []
        detail = f"{reason}: {'; '.join(self.errors)}" if self.errors else reason
        super().__init__(f"Switchboard instantiation failed ({detail})")


async def instantiate_switchboard(
    *,
    template: WorkflowTemplates,
    organization_id: int,
    user_id: int,
    workflow_name: str,
    db_client: DBClient | None = None,
) -> WorkflowModel:
    """Provision connector tools, reconcile tool references, regenerate
    triggers, stamp ``organization_id``, validate, then persist the workflow.

    Rolls back all tool rows newly created during this run on any failure
    after provisioning (Req 3.6).

    Args:
        template: The ``spinsci-switchboard`` ``WorkflowTemplates`` row whose
            ``template_json`` is the switchboard ``ReactFlow_Definition``
            (connector name-string tool references).
        organization_id: The requesting user's ``selected_organization_id``.
            Every record created by this call is scoped to this organization
            (Req 3.1, 3.5, 13.1).
        user_id: The requesting user, recorded as the creator of provisioned
            tools and the new workflow.
        workflow_name: The user-provided name for the new workflow.
        db_client: The combined DB client (``ToolClient`` + ``WorkflowClient``
            + ``AgentTriggerClient`` methods) to use. Defaults to the shared
            production ``db_client`` singleton; tests inject an in-memory
            fake exposing the same methods.

    Returns:
        The newly created, organization-scoped ``WorkflowModel``.

    Raises:
        SwitchboardInstantiationError: If provisioning, reconciliation,
            trigger regeneration, validation, or persistence fails. Any tool
            row newly created during this run is rolled back before this is
            raised (except for a step-1 provisioning failure itself — see the
            known limitation noted below).
    """
    client = db_client if db_client is not None else _shared_db_client

    # ------------------------------------------------------------------
    # Step 1: provision connector tools (idempotent). Snapshot the org's
    # existing active tool_uuids BEFORE provisioning so we can diff
    # newly-created vs reused tool_uuids afterwards — rollback (step 7) must
    # archive exactly the newly-created rows and never a reused one
    # (Req 3.6).
    # ------------------------------------------------------------------
    try:
        existing_tools_before = await client.get_tools_for_organization(
            organization_id, status=ToolStatus.ACTIVE.value
        )
    except Exception as exc:  # noqa: BLE001 - convert to structured error
        logger.error(
            "Failed to snapshot existing tools before provisioning switchboard "
            "for org {}: {}",
            organization_id,
            exc,
        )
        raise SwitchboardInstantiationError(
            reason="tool_snapshot_failed", errors=[str(exc)]
        ) from exc

    pre_existing_tool_uuids = {tool.tool_uuid for tool in existing_tools_before}

    try:
        name_to_uuid = await provision_connector_tools(
            organization_id=organization_id,
            user_id=user_id,
            tool_client=client,
        )
    except Exception as exc:  # noqa: BLE001 - convert to structured error
        # KNOWN LIMITATION: provision_connector_tools() iterates its 11
        # connector tools sequentially and does not expose which of them it
        # managed to create before raising (e.g. if tool #5 of 11 fails,
        # tools #1-4 it already created are NOT visible to this except-block
        # and are therefore NOT rolled back here). Those tool rows were
        # created *during* step 1 itself, not after it, so there is nothing
        # this call can roll back from -- closing this gap would require
        # provisioner.py to report partial progress to its caller on
        # failure, which is out of scope for this task.
        logger.error(
            "Connector tool provisioning failed for org {}: {}",
            organization_id,
            exc,
        )
        raise SwitchboardInstantiationError(
            reason="tool_provisioning_failed", errors=[str(exc)]
        ) from exc

    created_tool_uuids = [
        tool_uuid
        for tool_uuid in name_to_uuid.values()
        if tool_uuid not in pre_existing_tool_uuids
    ]

    # ------------------------------------------------------------------
    # Steps 2-6 run under a single rollback net: any failure here rolls back
    # exactly the tool rows newly created in step 1 above (Req 3.6).
    # ------------------------------------------------------------------
    try:
        workflow = await _reconcile_validate_and_persist(
            template=template,
            organization_id=organization_id,
            user_id=user_id,
            workflow_name=workflow_name,
            name_to_uuid=name_to_uuid,
            client=client,
        )
    except SwitchboardInstantiationError:
        await _rollback(
            created_tool_uuids, organization_id=organization_id, tool_client=client
        )
        raise
    except Exception as exc:  # noqa: BLE001 - convert to structured error
        logger.error(
            "Unexpected error instantiating switchboard for org {}: {}",
            organization_id,
            exc,
        )
        await _rollback(
            created_tool_uuids, organization_id=organization_id, tool_client=client
        )
        raise SwitchboardInstantiationError(
            reason="unexpected_instantiation_failure", errors=[str(exc)]
        ) from exc

    return workflow


async def _reconcile_validate_and_persist(
    *,
    template: WorkflowTemplates,
    organization_id: int,
    user_id: int,
    workflow_name: str,
    name_to_uuid: dict[str, str],
    client: DBClient,
) -> WorkflowModel:
    """Run steps 2-6 of instantiation (reconcile, regenerate, validate, persist).

    Raises ``SwitchboardInstantiationError`` for every known failure mode so
    the caller's single rollback net (in :func:`instantiate_switchboard`)
    can react uniformly. Unexpected exceptions are left to propagate and are
    wrapped by the caller.
    """
    # --------------------------------------------------------------------
    # Step 2: load template_json into a ReactFlowDTO and reconcile the
    # template's connector name-string tool_uuids to the org's real
    # provisioned tool_uuids (Req 5.1, 5.2, 5.3).
    # --------------------------------------------------------------------
    try:
        dto = ReactFlowDTO.model_validate(template.template_json)
    except ValidationError as exc:
        raise SwitchboardInstantiationError(
            reason="invalid_template_definition", errors=[str(exc)]
        ) from exc

    try:
        reconciled_dto = reconcile_tool_references(dto, name_to_uuid)
    except UnresolvedToolReference as exc:
        # Req 5.4: reject with an unresolved-reference error.
        raise SwitchboardInstantiationError(
            reason="unresolved_tool_reference", errors=[str(exc)]
        ) from exc

    # --------------------------------------------------------------------
    # Step 3: regenerate trigger node identifiers so this workflow's
    # triggers do not collide with any existing workflow's triggers
    # (Req 3.2). Operates on the dict form, matching the existing
    # regenerate_trigger_uuids contract.
    # --------------------------------------------------------------------
    reconciled_definition = reconciled_dto.model_dump(mode="json")
    regenerated_definition = regenerate_trigger_uuids(reconciled_definition)

    # --------------------------------------------------------------------
    # Step 4: stamp organization_id. There is no in-definition field to
    # stamp -- the workflow row itself carries organization_id, set below by
    # client.create_workflow(...). Every other record created during this
    # run (the provisioned connector tools) was already scoped to
    # organization_id in step 1 (Req 3.1, 3.5, 13.1).
    # --------------------------------------------------------------------

    # --------------------------------------------------------------------
    # Step 5: validate the reconciled, trigger-regenerated definition
    # in memory, before persisting anything (Req 3.3, 3.4, 11.4).
    # --------------------------------------------------------------------
    try:
        final_dto = ReactFlowDTO.model_validate(regenerated_definition)
    except ValidationError as exc:
        raise SwitchboardInstantiationError(
            reason="invalid_reconciled_definition", errors=[str(exc)]
        ) from exc

    try:
        WorkflowGraph(final_dto)
    except ValueError as exc:
        graph_errors = exc.args[0] if exc.args else []
        raise SwitchboardInstantiationError(
            reason="graph_validation_failed",
            errors=[str(error) for error in graph_errors],
        ) from exc

    uuid_to_connector_name = await _resolve_uuid_to_connector_name(
        organization_id=organization_id,
        provisioned_tool_uuids=set(name_to_uuid.values()),
        client=client,
    )
    scoping_violations = validate_uuid_tool_scoping(
        final_dto.nodes, uuid_to_connector_name
    )
    if scoping_violations:
        raise SwitchboardInstantiationError(
            reason="gate_by_scoping_violation", errors=scoping_violations
        )

    # --------------------------------------------------------------------
    # Step 6: persist. Trigger-path availability is checked before creating
    # the workflow row so we never leave a workflow whose trigger sync would
    # subsequently fail (mirrors the existing /templates/duplicate route).
    # --------------------------------------------------------------------
    trigger_paths = extract_trigger_paths(regenerated_definition)
    if trigger_paths:
        try:
            await client.assert_trigger_paths_available(trigger_paths=trigger_paths)
        except TriggerPathConflictError as exc:
            raise SwitchboardInstantiationError(
                reason="trigger_path_conflict", errors=list(exc.trigger_paths)
            ) from exc

    workflow = await client.create_workflow(
        workflow_name,
        regenerated_definition,
        user_id,
        organization_id,
    )

    if trigger_paths:
        await client.sync_triggers_for_workflow(
            workflow_id=workflow.id,
            organization_id=organization_id,
            trigger_paths=trigger_paths,
        )

    return workflow


async def _resolve_uuid_to_connector_name(
    *,
    organization_id: int,
    provisioned_tool_uuids: set[str],
    client: DBClient,
) -> dict[str, str]:
    """Resolve each provisioned ``tool_uuid`` to its connector identity.

    Reads the org's active tools back from the DB and builds the
    ``tool_uuid`` -> connector-name map from each tool's *actual persisted*
    definition (via :func:`build_uuid_to_connector_name`), rather than
    trusting the in-memory ``name_to_uuid`` mapping produced by
    provisioning. This matches the fail-closed intent of gate-by-scoping
    (Req 11.5): a tool_uuid resolves only if its real, persisted definition
    still carries the connector-identity marker.
    """
    active_tools = await client.get_tools_for_organization(
        organization_id, status=ToolStatus.ACTIVE.value
    )
    tool_definitions = {
        tool.tool_uuid: tool.definition or {}
        for tool in active_tools
        if tool.tool_uuid in provisioned_tool_uuids
    }
    return build_uuid_to_connector_name(tool_definitions)


async def _rollback(
    created_tool_uuids: Sequence[str],
    *,
    organization_id: int,
    tool_client: DBClient,
) -> None:
    """Compensating rollback: archive exactly the tool rows newly created
    during this instantiation run (never reused ones) (Req 3.6).

    Best-effort: an individual archive failure is logged (tool_uuid and
    organization_id only -- no sensitive data) and swallowed, so unwinding an
    existing failure never raises a second exception that would mask the
    original error.
    """
    for tool_uuid in created_tool_uuids:
        try:
            archived = await tool_client.archive_tool(tool_uuid, organization_id)
            if archived:
                logger.info(
                    "Rolled back (archived) newly-created tool {} for org {}",
                    tool_uuid,
                    organization_id,
                )
            else:
                logger.warning(
                    "Rollback: tool {} for org {} was not found or already archived",
                    tool_uuid,
                    organization_id,
                )
        except Exception as exc:  # noqa: BLE001 - best-effort, never re-raise
            logger.error(
                "Rollback failed to archive tool {} for org {}: {}",
                tool_uuid,
                organization_id,
                exc,
            )


__all__ = [
    "SwitchboardInstantiationError",
    "instantiate_switchboard",
]
