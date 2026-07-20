"""Tool-reference reconciler: rewrite name-string tool refs to real UUIDs.

Replaces each node's connector-name-string ``tool_uuids`` entries with the
organization's provisioned ``tool_uuid`` values, and binds the greeting
``startCall`` node's ``pre_call_fetch`` patient-lookup reference, preserving
per-node cluster scoping.

The switchboard graph models the patient-lookup capability that
``pre_call_fetch`` depends on as a name-string entry (``"patient_lookup"``) in
the Greeting ``startCall`` node's ``tool_uuids`` (see
``api.services.switchboard.clusters.greeting.build_greeting_cluster``); there
is no separate ``pre_call_fetch``-only tool-reference field. Resolving that
node's ``tool_uuids`` through ``name_to_uuid`` therefore *is* the binding of
the greeting node's pre-call patient-lookup reference to the organization's
provisioned ``patient_lookup`` tool (Req 5.3) — no special-casing beyond the
generic per-node ``tool_uuids`` reconciliation (Req 5.1) is required. The
pre-call fetch request's URL/credential are supplied separately by the
``Tool_Binding_Editor`` (Req 6), not by this reconciler.

Design references:
- ``design.md`` -> "Tool-reference reconciler"
- ``requirements.md`` -> Requirements 5.1, 5.2, 5.3, 5.4

Requirements: 5.1, 5.2, 5.3, 5.4.
"""

from __future__ import annotations

from api.services.workflow.dto import ReactFlowDTO, RFNodeDTO


class UnresolvedToolReference(Exception):
    """Raised when a node references a connector tool with no provisioned UUID.

    Raised by :func:`reconcile_tool_references` when a node's ``tool_uuids``
    names a connector (e.g. ``"patient_lookup"``) that has no entry in the
    organization's ``name_to_uuid`` mapping — i.e. that connector tool was not
    provisioned for the organization. The instantiator surfaces this as a
    rejection of the instantiation (Req 5.4).
    """

    def __init__(self, node_id: str, connector_name: str) -> None:
        self.node_id = node_id
        self.connector_name = connector_name
        super().__init__(
            f"Node {node_id!r} references connector tool {connector_name!r}, "
            "which has no provisioned tool_uuid for this organization."
        )


def _reconcile_node_tool_uuids(
    node: RFNodeDTO, name_to_uuid: dict[str, str]
) -> RFNodeDTO:
    """Return a copy of ``node`` with its ``tool_uuids`` resolved to real UUIDs.

    Nodes with no ``tool_uuids`` field, or an unset/empty ``tool_uuids`` list,
    are returned unchanged (the same object; no copy is made) — this is what
    preserves "nodes/edges otherwise unchanged" for nodes that carry no tool
    references.

    Because the resolved list contains exactly the same connector identities
    the node started with (only the string values change from a name to that
    name's UUID), the set of tools attached to the node is unchanged in
    substance — the node's cluster tool scoping is preserved (Req 5.2).

    Args:
        node: The node to reconcile.
        name_to_uuid: Mapping of connector name (e.g. ``"patient_lookup"``) to
            the organization's provisioned ``tool_uuid`` for that connector.

    Returns:
        A new ``RFNodeDTO`` with resolved ``tool_uuids``, or the original
        ``node`` if it has no tool references to resolve.

    Raises:
        UnresolvedToolReference: If a name-string in the node's ``tool_uuids``
            has no entry in ``name_to_uuid``.
    """
    tool_uuids = getattr(node.data, "tool_uuids", None)
    if not tool_uuids:
        return node

    resolved_tool_uuids: list[str] = []
    for connector_name in tool_uuids:
        tool_uuid = name_to_uuid.get(connector_name)
        if tool_uuid is None:
            raise UnresolvedToolReference(node.id, connector_name)
        resolved_tool_uuids.append(tool_uuid)

    new_data = node.data.model_copy(update={"tool_uuids": resolved_tool_uuids})
    return node.model_copy(update={"data": new_data})


def reconcile_tool_references(
    dto: ReactFlowDTO, name_to_uuid: dict[str, str]
) -> ReactFlowDTO:
    """Replace every node ``tool_uuids`` name-string with the org's real tool_uuid.

    This also binds the greeting ``startCall`` node's ``pre_call_fetch``
    patient-lookup reference to the provisioned ``patient_lookup`` tool,
    because that reference is itself carried in the node's ``tool_uuids`` (see
    module docstring). Preserves per-node cluster scoping exactly: only the
    string values of ``tool_uuids`` change, never the set of connector
    identities a node has access to.

    This is a pure function — it does not mutate ``dto`` in place, and
    returns a new ``ReactFlowDTO`` whose nodes/edges are otherwise unchanged.

    Args:
        dto: The switchboard ``ReactFlowDTO`` (e.g. a template's
            ``template_json`` loaded into a ``ReactFlowDTO``) whose node
            ``tool_uuids`` are connector name-strings.
        name_to_uuid: Mapping of connector name to the organization's
            provisioned ``tool_uuid`` for that connector (produced by
            ``enablement.provisioner.provision_connector_tools``).

    Returns:
        A new ``ReactFlowDTO`` with every node's ``tool_uuids`` resolved to
        real tool UUIDs.

    Raises:
        UnresolvedToolReference: If any node references a connector tool with
            no entry in ``name_to_uuid`` (Req 5.4).
    """
    reconciled_nodes = [
        _reconcile_node_tool_uuids(node, name_to_uuid) for node in dto.nodes
    ]
    return ReactFlowDTO(nodes=reconciled_nodes, edges=dto.edges)


__all__ = [
    "UnresolvedToolReference",
    "reconcile_tool_references",
]
