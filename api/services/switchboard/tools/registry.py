"""The 11 switchboard connector tools and their registry (Req 16.1, 16.2, 1.7).

This module assembles the concrete :class:`~api.services.switchboard.tools.base.ConnectorTool`
instances — one per capability in the design's connector-tool table — wiring each
switchboard-side contract (:mod:`.contracts`) to its PoC mock backend
(:mod:`.backends`), its :class:`~api.services.switchboard.tools.base.ToolCluster`
scoping, and its sensitive fields for masking. Every tool defaults to the empty
:data:`~api.services.switchboard.tools.base.UNBOUND` binding, so no SpinSci wire
format is hardcoded and the PoC runs entirely on mocks (Req 16.2).

The registry accessors let the graph builder (task 16.8) enumerate tools and scope
them per cluster via ``tool_uuids`` — e.g. ``transfer`` and
``route_metadata_resolution`` are Routing-only, so they cannot fire before Routing
(Req 1.7, 9.2).

Requirements: 16.1, 16.2, 1.7.
"""

from __future__ import annotations

from api.services.switchboard.tools import backends, contracts
from api.services.switchboard.tools.base import ConnectorTool, ToolCluster

# ---------------------------------------------------------------------------
# The 11 connector tools (design "Backend connector tools" table)
# ---------------------------------------------------------------------------

PATIENT_LOOKUP: ConnectorTool = ConnectorTool(
    name="patient_lookup",
    description=(
        "Look up a patient by ANI (turn 1) or a confirmed phone number; returns "
        "patient id, match count, name, and an opaque DOB-on-file token."
    ),
    input_model=contracts.PatientLookupInput,
    output_model=contracts.PatientLookupOutput,
    clusters=frozenset({ToolCluster.GREETING, ToolCluster.AUTHENTICATION}),
    backend=backends.patient_lookup_backend,
    sensitive_fields=frozenset({"phone", "patient_id", "dob_on_file", "name"}),
)

DIRECTORY_LOOKUP: ConnectorTool = ConnectorTool(
    name="directory_lookup",
    description=(
        "Search the directory by specialty, provider, or location; returns the "
        "resolved department name/id, numeric selected_id, and candidate matches."
    ),
    input_model=contracts.DirectoryLookupInput,
    output_model=contracts.DirectoryLookupOutput,
    clusters=frozenset({ToolCluster.BUSINESS_HOURS, ToolCluster.AFTER_HOURS}),
    backend=backends.directory_lookup_backend,
)

FAQ_KB: ConnectorTool = ConnectorTool(
    name="faq_kb",
    description="Answer a free-text FAQ / knowledge-base question with answer text.",
    input_model=contracts.FaqKbInput,
    output_model=contracts.FaqKbOutput,
    clusters=frozenset({ToolCluster.BUSINESS_HOURS, ToolCluster.AFTER_HOURS}),
    backend=backends.faq_kb_backend,
)

DOB_VALIDATION: ConnectorTool = ConnectorTool(
    name="dob_validation",
    description="Validate a caller-provided DOB against the patient's DOB on file.",
    input_model=contracts.DobValidationInput,
    output_model=contracts.DobValidationOutput,
    clusters=frozenset({ToolCluster.AUTHENTICATION}),
    backend=backends.dob_validation_backend,
    sensitive_fields=frozenset({"provided_dob", "patient_id"}),
)

IDENTITY_VERIFY: ConnectorTool = ConnectorTool(
    name="identity_verify",
    description=(
        "Resolve identity verification from a patient id and verification signals; "
        "returns patient_verified = Success or Fail."
    ),
    input_model=contracts.IdentityVerifyInput,
    output_model=contracts.IdentityVerifyOutput,
    clusters=frozenset({ToolCluster.AUTHENTICATION}),
    backend=backends.identity_verify_backend,
    sensitive_fields=frozenset({"patient_id"}),
)

ROUTING_INTENT_RESOLUTION: ConnectorTool = ConnectorTool(
    name="routing_intent_resolution",
    description=(
        "Step 1 of the routing chain: resolve the route listing (exact "
        "routing-intent strings) from department/intent context."
    ),
    input_model=contracts.RoutingIntentResolutionInput,
    output_model=contracts.RoutingIntentResolutionOutput,
    clusters=frozenset({ToolCluster.ROUTING}),
    backend=backends.routing_intent_resolution_backend,
)

ROUTE_METADATA_RESOLUTION: ConnectorTool = ConnectorTool(
    name="route_metadata_resolution",
    description=(
        "Step 2 of the routing chain: resolve queue/destination metadata for one "
        "exact routing-intent string returned by the listing step."
    ),
    input_model=contracts.RouteMetadataResolutionInput,
    output_model=contracts.RouteMetadataResolutionOutput,
    clusters=frozenset({ToolCluster.ROUTING}),
    backend=backends.route_metadata_resolution_backend,
)

TRANSFER: ConnectorTool = ConnectorTool(
    name="transfer",
    description=(
        "Transfer the call to a destination, carrying the call summary, "
        "verification status, and the spoken transfer message."
    ),
    input_model=contracts.TransferInput,
    output_model=contracts.TransferOutput,
    clusters=frozenset({ToolCluster.ROUTING}),
    backend=backends.transfer_backend,
)

HANGUP: ConnectorTool = ConnectorTool(
    name="hangup",
    description="End the call after speaking the verbatim goodbye line.",
    input_model=contracts.HangupInput,
    output_model=contracts.HangupOutput,
    clusters=frozenset({ToolCluster.ROUTING}),
    backend=backends.hangup_backend,
)

SCHEDULING_HANDOFF: ConnectorTool = ConnectorTool(
    name="scheduling_handoff",
    description="Hand the full Call State Ledger to Scheduling Init for a specialty.",
    input_model=contracts.SchedulingHandoffInput,
    output_model=contracts.SchedulingHandoffOutput,
    clusters=frozenset({ToolCluster.SCHEDULING}),
    backend=backends.scheduling_handoff_backend,
    sensitive_fields=frozenset({"ledger"}),
)

SCHEDULING_ENGINE: ConnectorTool = ConnectorTool(
    name="scheduling_engine",
    description=(
        "Run the Scheduling Engine for an appointment action; returns available "
        "slots for create/reschedule or the action result for cancel/list/confirm."
    ),
    input_model=contracts.SchedulingEngineToolInput,
    output_model=contracts.SchedulingEngineToolOutput,
    clusters=frozenset({ToolCluster.SCHEDULING}),
    backend=backends.scheduling_engine_backend,
    sensitive_fields=frozenset({"patient_id"}),
)


#: All connector tools keyed by their stable name. Insertion order follows the
#: design's connector-tool table.
CONNECTOR_TOOLS: dict[str, ConnectorTool] = {
    tool.name: tool
    for tool in (
        PATIENT_LOOKUP,
        DIRECTORY_LOOKUP,
        FAQ_KB,
        DOB_VALIDATION,
        IDENTITY_VERIFY,
        ROUTING_INTENT_RESOLUTION,
        ROUTE_METADATA_RESOLUTION,
        TRANSFER,
        HANGUP,
        SCHEDULING_HANDOFF,
        SCHEDULING_ENGINE,
    )
}


def get_connector_tools() -> list[ConnectorTool]:
    """Return all 11 connector tools in the design's table order."""
    return list(CONNECTOR_TOOLS.values())


def get_connector_tool(name: str) -> ConnectorTool:
    """Return the connector tool registered under ``name``.

    Raises:
        KeyError: If no connector tool is registered under ``name``.
    """
    try:
        return CONNECTOR_TOOLS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown switchboard connector tool: {name!r}") from exc


def tools_for_cluster(cluster: ToolCluster) -> list[ConnectorTool]:
    """Return the connector tools scoped to ``cluster`` (drives per-node scoping)."""
    return [tool for tool in CONNECTOR_TOOLS.values() if tool.is_scoped_to(cluster)]


__all__ = [
    "PATIENT_LOOKUP",
    "DIRECTORY_LOOKUP",
    "FAQ_KB",
    "DOB_VALIDATION",
    "IDENTITY_VERIFY",
    "ROUTING_INTENT_RESOLUTION",
    "ROUTE_METADATA_RESOLUTION",
    "TRANSFER",
    "HANGUP",
    "SCHEDULING_HANDOFF",
    "SCHEDULING_ENGINE",
    "CONNECTOR_TOOLS",
    "get_connector_tools",
    "get_connector_tool",
    "tools_for_cluster",
]
