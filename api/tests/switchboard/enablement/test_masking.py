"""Unit tests: enablement logging references sensitive fields by name only.

Covers Req 7.2 — log calls in ``provisioner.py``/``reconcile.py`` must never
include a sensitive field's *value*, only safe identifiers (connector name,
organization id, tool_uuid, node id). Also adds a focused example-based unit
test for ``mask_connector_tool_definition`` (task 6.1), complementing the
property test in task 6.2.

``provisioner.py`` only ever logs ``tool.name``, ``created_tool.tool_uuid``,
and ``organization_id`` (confirmed by reading the module) — it never logs the
tool definition/parameters that could carry sensitive data. ``reconcile.py``
has no logging call sites at all (confirmed by reading the module). To make
these guarantees concrete rather than vacuous, the tests below construct
scenarios where a realistic-looking sensitive value (a fake phone number) is
present in the data each function actually processes, and assert that value
never appears in the captured log output.

Design references:
- ``design.md`` -> "Connector-tool masking"
- ``requirements.md`` -> Requirement 7.2

Task: 6.3.
"""

from __future__ import annotations

import io
import itertools
import uuid

from loguru import logger

from api.db.models import ToolModel
from api.enums import ToolCategory, ToolStatus
from api.services.switchboard.enablement import provisioner as provisioner_module
from api.services.switchboard.enablement.masking import mask_connector_tool_definition
from api.services.switchboard.enablement.provisioner import provision_connector_tools
from api.services.switchboard.enablement.reconcile import reconcile_tool_references
from api.services.switchboard.graph import build_switchboard_reactflow_dto

#: A realistic-looking sensitive value that must never be echoed by any log
#: call, no matter where it appears in the data a function processes.
_FAKE_SENSITIVE_PHONE = "+15555550101"


def _capture_logs() -> tuple[io.StringIO, int]:
    """Attach a fresh loguru sink capturing all log output.

    Matches this repo's existing convention for capturing loguru output in
    tests (see ``pipecat/tests/test_openai_realtime_reasoning.py``). Caller is
    responsible for ``logger.remove(handler_id)``.
    """
    sink = io.StringIO()
    handler_id = logger.add(sink, level="TRACE", format="{message}")
    return sink, handler_id


class _FakeToolClient:
    """Minimal in-memory ``ToolClient`` stand-in.

    Mirrors the fake used by ``test_provisioner_property.py`` — only the
    subset of the real client's interface ``provision_connector_tools``
    depends on.
    """

    def __init__(self) -> None:
        self._tools: list[ToolModel] = []
        self._id_counter = itertools.count(1)

    async def get_tools_for_organization(
        self,
        organization_id: int,
        status: str | None = None,
        category: str | None = None,
    ) -> list[ToolModel]:
        results = [t for t in self._tools if t.organization_id == organization_id]
        if status:
            status_list = [s.strip() for s in status.split(",")]
            results = [t for t in results if t.status in status_list]
        if category:
            results = [t for t in results if t.category == category]
        return list(results)

    async def create_tool(
        self,
        organization_id: int,
        user_id: int,
        name: str,
        definition: dict,
        category: str = ToolCategory.HTTP_API.value,
        description: str | None = None,
        icon: str | None = None,
        icon_color: str | None = None,
    ) -> ToolModel:
        tool = ToolModel(
            id=next(self._id_counter),
            tool_uuid=str(uuid.uuid4()),
            organization_id=organization_id,
            created_by=user_id,
            name=name,
            description=description,
            category=category,
            icon=icon,
            icon_color=icon_color,
            definition=definition,
            status=ToolStatus.ACTIVE.value,
        )
        self._tools.append(tool)
        return tool


class _FakeSensitiveConnectorTool:
    """A fake connector tool whose definition embeds an actual sensitive value.

    The real ``ConnectorTool.to_tool_definition()`` only ever emits parameter
    *schema* entries (name/type/description) — never an actual value — so
    ``provisioner.py`` never sees a real phone number in practice (there is no
    raw connector-tool parameter *value* flowing through it at all). This fake
    stands in for a worst-case scenario where a sensitive-looking value ends
    up in the definition data the provisioner handles end-to-end, to prove its
    log calls still never echo it.
    """

    name = "patient_lookup"

    @staticmethod
    def to_tool_definition() -> dict:
        return {
            "schema_version": 1,
            "type": "http_api",
            "config": {
                "url": "",
                "credential_uuid": None,
                "field_mapping": {},
                "parameters": [
                    {
                        "name": "phone",
                        "type": "string",
                        "description": "Caller phone",
                        "required": True,
                        # A realistic-looking sensitive value embedded
                        # directly in the data provisioner processes.
                        "value": _FAKE_SENSITIVE_PHONE,
                    },
                ],
                "timeout_ms": 5000,
            },
            "switchboard": {
                "clusters": ["greeting"],
                "sensitive_fields": ["phone"],
            },
        }


async def test_provisioner_logging_never_includes_sensitive_field_values(monkeypatch):
    """Req 7.2: ``provisioner.py`` log calls reference the connector name and
    organization id only — never a sensitive field's value — even when a
    sensitive-looking value is present in the definition data the provisioner
    handles, on both the create path (``logger.info``) and the reuse path
    (``logger.debug``)."""
    monkeypatch.setattr(
        provisioner_module,
        "get_connector_tools",
        lambda: [_FakeSensitiveConnectorTool()],
    )

    tool_client = _FakeToolClient()
    sink, handler_id = _capture_logs()
    try:
        # First call: create path (logger.info).
        await provision_connector_tools(
            organization_id=4242, user_id=7, tool_client=tool_client
        )
        # Second call: reuse path (logger.debug) — provisioning is idempotent.
        await provision_connector_tools(
            organization_id=4242, user_id=7, tool_client=tool_client
        )
    finally:
        logger.remove(handler_id)

    log_output = sink.getvalue()
    assert log_output, "expected provisioner to emit log lines for this scenario"
    assert _FAKE_SENSITIVE_PHONE not in log_output

    # Sanity: the logging that *did* happen references only safe identifiers
    # (connector name, org id) — confirming the assertion above isn't
    # vacuously true because nothing was logged at all.
    assert "patient_lookup" in log_output
    assert "4242" in log_output


async def test_reconcile_emits_no_log_output_at_all():
    """Req 7.2: ``reconcile.py`` has no logging call sites at all (confirmed
    by reading the module), so reconciling the real switchboard tool
    references — including a synthetic sensitive-looking value threaded
    through the ``name_to_uuid`` mapping — never logs anything, let alone a
    sensitive value."""
    dto = build_switchboard_reactflow_dto()

    connector_names: set[str] = set()
    for node in dto.nodes:
        tool_uuids = getattr(node.data, "tool_uuids", None)
        if tool_uuids:
            connector_names.update(tool_uuids)
    assert connector_names, "expected the real switchboard graph to reference tools"

    name_to_uuid = {name: str(uuid.uuid4()) for name in connector_names}
    # Replace one entry's value with a synthetic, sensitive-looking string
    # (rather than a real UUID) — standing in for the kind of value that must
    # never surface in a log line if reconcile.py ever gained logging.
    name_to_uuid[next(iter(connector_names))] = _FAKE_SENSITIVE_PHONE

    sink, handler_id = _capture_logs()
    try:
        reconcile_tool_references(dto, name_to_uuid)
    finally:
        logger.remove(handler_id)

    log_output = sink.getvalue()
    assert log_output == ""
    assert _FAKE_SENSITIVE_PHONE not in log_output


def test_mask_connector_tool_definition_masks_single_sensitive_field():
    """Focused example test for ``masking.py`` (task 6.1), complementing the
    property test in task 6.2: a single declared sensitive field's value is
    masked, while the ``credential_uuid`` identifier stays visible (Req 6.2)."""
    definition = {
        "schema_version": 1,
        "type": "http_api",
        "config": {
            "url": "https://example.test/patient-lookup",
            "credential_uuid": "cred-1234",
            "field_mapping": {},
            "parameters": [
                {
                    "name": "phone",
                    "type": "string",
                    "description": "Caller phone",
                    "required": True,
                    "value": _FAKE_SENSITIVE_PHONE,
                },
            ],
            "timeout_ms": 5000,
        },
        "switchboard": {
            "clusters": ["greeting"],
            "sensitive_fields": ["phone"],
        },
    }

    masked = mask_connector_tool_definition(definition)

    masked_param = masked["config"]["parameters"][0]
    # The field identifier ("name": "phone") stays visible; only its value is masked.
    assert masked_param["name"] == "phone"
    assert masked_param["value"] != _FAKE_SENSITIVE_PHONE
    assert _FAKE_SENSITIVE_PHONE not in str(masked)

    # Credential identifier is a reference, never a secret — never masked (Req 6.2).
    assert masked["config"]["credential_uuid"] == "cred-1234"

    # Pure function: the original definition is untouched.
    assert definition["config"]["parameters"][0]["value"] == _FAKE_SENSITIVE_PHONE
