"""Unit/edge tests for Template_Registrar create/update/abort paths.

Covers:
- Create branch when no existing template row (Req 1.3)
- Update branch when a template row already exists (Req 1.4)
- Stable ``template_name``/``template_description`` used for both branches (Req 1.2)
- Abort-and-write-nothing on an invalid serialized DTO (Req 1.6)

Design references:
- ``design.md`` -> "Template_Registrar"
- ``requirements.md`` -> Requirements 1.2, 1.3, 1.4, 1.6
"""

from __future__ import annotations

import itertools

import pytest

from api.db.models import WorkflowTemplates
from api.services.switchboard.enablement.registrar import (
    SWITCHBOARD_TEMPLATE_DESCRIPTION,
    SWITCHBOARD_TEMPLATE_NAME,
    SwitchboardTemplateInvalid,
    register_switchboard_template,
)


class FakeWorkflowTemplateClient:
    """In-memory stand-in for ``WorkflowTemplateClient``.

    Mirrors the subset of the real client's interface that
    ``register_switchboard_template`` depends on
    (``get_workflow_template_by_name``, ``create_workflow_template``,
    ``update_workflow_template``), without touching a real database.
    """

    def __init__(self, seed_rows: list[WorkflowTemplates] | None = None) -> None:
        self._rows: dict[int, WorkflowTemplates] = {}
        self._id_counter = itertools.count(1)
        self.create_calls: list[dict] = []
        self.update_calls: list[dict] = []
        for row in seed_rows or []:
            self._rows[row.id] = row

    async def get_workflow_template_by_name(
        self, template_name: str
    ) -> WorkflowTemplates | None:
        for row in self._rows.values():
            if row.template_name == template_name:
                return row
        return None

    async def create_workflow_template(
        self, template_name: str, template_description: str, template_json: dict
    ) -> WorkflowTemplates:
        self.create_calls.append(
            {
                "template_name": template_name,
                "template_description": template_description,
                "template_json": template_json,
            }
        )
        new_id = next(self._id_counter)
        row = WorkflowTemplates(
            id=new_id,
            template_name=template_name,
            template_description=template_description,
            template_json=template_json,
        )
        self._rows[new_id] = row
        return row

    async def update_workflow_template(
        self,
        template_id: int,
        template_name: str | None = None,
        template_json: dict | None = None,
    ) -> WorkflowTemplates:
        self.update_calls.append(
            {
                "template_id": template_id,
                "template_name": template_name,
                "template_json": template_json,
            }
        )
        row = self._rows.get(template_id)
        if row is None:
            raise ValueError(f"Workflow template with ID {template_id} not found")
        if template_name is not None:
            row.template_name = template_name
        if template_json is not None:
            row.template_json = template_json
        return row


async def test_register_creates_when_absent():
    """Req 1.3: with no existing template row, registration creates a new one."""
    client = FakeWorkflowTemplateClient()

    result = await register_switchboard_template(template_client=client)

    assert len(client.create_calls) == 1
    assert len(client.update_calls) == 0
    assert result.template_name == SWITCHBOARD_TEMPLATE_NAME


async def test_register_updates_when_present():
    """Req 1.4: with a pre-seeded row keyed by the stable template name,
    registration updates the existing row rather than creating a duplicate,
    preserving the same row id."""
    existing = WorkflowTemplates(
        id=42,
        template_name=SWITCHBOARD_TEMPLATE_NAME,
        template_description=SWITCHBOARD_TEMPLATE_DESCRIPTION,
        template_json={"nodes": [], "edges": []},
    )
    client = FakeWorkflowTemplateClient(seed_rows=[existing])

    result = await register_switchboard_template(template_client=client)

    assert len(client.create_calls) == 0
    assert len(client.update_calls) == 1
    assert result.id == 42
    # No duplicate row was created alongside the existing one.
    assert len(client._rows) == 1


async def test_register_uses_stable_name_and_description_on_create():
    """Req 1.2: SWITCHBOARD_TEMPLATE_NAME/DESCRIPTION are used for the create call."""
    client = FakeWorkflowTemplateClient()

    await register_switchboard_template(template_client=client)

    assert client.create_calls[0]["template_name"] == SWITCHBOARD_TEMPLATE_NAME
    assert (
        client.create_calls[0]["template_description"]
        == SWITCHBOARD_TEMPLATE_DESCRIPTION
    )


async def test_register_uses_stable_name_for_lookup_on_update():
    """Req 1.2: the same stable template_name is used to look up (and thus key)
    the row that gets updated."""
    existing = WorkflowTemplates(
        id=7,
        template_name=SWITCHBOARD_TEMPLATE_NAME,
        template_description=SWITCHBOARD_TEMPLATE_DESCRIPTION,
        template_json={"nodes": [], "edges": []},
    )
    client = FakeWorkflowTemplateClient(seed_rows=[existing])

    result = await register_switchboard_template(template_client=client)

    assert result.template_name == SWITCHBOARD_TEMPLATE_NAME
    assert result.template_description == SWITCHBOARD_TEMPLATE_DESCRIPTION


async def test_register_aborts_and_writes_nothing_on_invalid_dto(monkeypatch):
    """Req 1.6: when serialization produces an invalid DTO, registration raises
    SwitchboardTemplateInvalid and never calls create/update on the client."""

    def _raise_invalid() -> dict:
        raise SwitchboardTemplateInvalid(["fake validation error"])

    monkeypatch.setattr(
        "api.services.switchboard.enablement.registrar.serialize_switchboard_template_json",
        _raise_invalid,
    )

    client = FakeWorkflowTemplateClient()

    with pytest.raises(SwitchboardTemplateInvalid):
        await register_switchboard_template(template_client=client)

    assert len(client.create_calls) == 0
    assert len(client.update_calls) == 0
    assert len(client._rows) == 0


async def test_register_aborts_on_invalid_dto_with_existing_row(monkeypatch):
    """Req 1.6: abort-and-write-nothing also holds on the update branch — an
    existing row is left untouched when serialization is invalid."""
    existing = WorkflowTemplates(
        id=99,
        template_name=SWITCHBOARD_TEMPLATE_NAME,
        template_description=SWITCHBOARD_TEMPLATE_DESCRIPTION,
        template_json={"nodes": [], "edges": []},
    )
    client = FakeWorkflowTemplateClient(seed_rows=[existing])

    def _raise_invalid() -> dict:
        raise SwitchboardTemplateInvalid(["fake validation error"])

    monkeypatch.setattr(
        "api.services.switchboard.enablement.registrar.serialize_switchboard_template_json",
        _raise_invalid,
    )

    with pytest.raises(SwitchboardTemplateInvalid):
        await register_switchboard_template(template_client=client)

    assert len(client.create_calls) == 0
    assert len(client.update_calls) == 0
    # The pre-existing row is unchanged.
    assert client._rows[99].template_json == {"nodes": [], "edges": []}
