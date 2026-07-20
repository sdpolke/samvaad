"""Unit tests for the switchboard template registration entry point.

Covers:
- ``main()`` delegates to ``register_switchboard_template()`` using the
  default (real) client, i.e. calling it with no arguments (Req 1.3, 1.4)
- ``main()`` propagates (and logs) ``SwitchboardTemplateInvalid`` raised by
  ``register_switchboard_template()`` rather than swallowing it (Req 1.6)
- End-to-end sanity check against a fake/test ``WorkflowTemplateClient``
  injected at the point ``register_switchboard_template()`` constructs its
  default client, exercising the entry point without mocking
  ``register_switchboard_template`` itself

Design references:
- ``design.md`` -> "Registration (admin/seed, run once per deployment)"
- ``requirements.md`` -> Requirements 1.3, 1.4

File: ``api/tests/switchboard/enablement/test_registration_entrypoint.py``
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest

import api.services.admin_utils.register_switchboard_template as entrypoint
from api.db.models import WorkflowTemplates
from api.services.switchboard.enablement.registrar import (
    SWITCHBOARD_TEMPLATE_NAME,
    SwitchboardTemplateInvalid,
)


class FakeWorkflowTemplateClient:
    """In-memory stand-in for ``WorkflowTemplateClient``.

    Mirrors the subset of the real client's interface that
    ``register_switchboard_template`` depends on, without touching a real
    database or requiring any constructor arguments (mirroring
    ``WorkflowTemplateClient()``'s no-arg construction inside the registrar).
    """

    def __init__(self) -> None:
        self._rows: dict[int, WorkflowTemplates] = {}
        self._id_counter = itertools.count(1)
        self.create_calls: list[dict] = []
        self.update_calls: list[dict] = []

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
        row = self._rows[template_id]
        if template_name is not None:
            row.template_name = template_name
        if template_json is not None:
            row.template_json = template_json
        return row


async def test_main_delegates_to_register_switchboard_template_on_success(
    monkeypatch,
):
    """``main()`` calls ``register_switchboard_template()`` exactly once, with
    no arguments -- confirming it relies on the function's default (real)
    client rather than being passed one -- and logs the returned template's
    id/name without raising."""
    fake_template = SimpleNamespace(id=1, template_name="spinsci-switchboard")
    calls: list[tuple[tuple, dict]] = []

    async def fake_register_switchboard_template(*args, **kwargs):
        calls.append((args, kwargs))
        return fake_template

    monkeypatch.setattr(
        entrypoint,
        "register_switchboard_template",
        fake_register_switchboard_template,
    )

    await entrypoint.main()

    assert len(calls) == 1
    call_args, call_kwargs = calls[0]
    assert call_args == ()
    assert call_kwargs == {}


async def test_main_propagates_switchboard_template_invalid(monkeypatch):
    """``main()`` re-raises ``SwitchboardTemplateInvalid`` from
    ``register_switchboard_template()`` (Req 1.6 abort-on-invalid surfaced as
    a hard failure to the operator) rather than swallowing it."""
    invalid_errors = ["some error"]

    async def fake_register_switchboard_template(*args, **kwargs):
        raise SwitchboardTemplateInvalid(invalid_errors)

    monkeypatch.setattr(
        entrypoint,
        "register_switchboard_template",
        fake_register_switchboard_template,
    )

    with pytest.raises(SwitchboardTemplateInvalid) as exc_info:
        await entrypoint.main()

    assert exc_info.value.errors == invalid_errors


async def test_main_end_to_end_against_fake_workflow_template_client(
    monkeypatch,
):
    """End-to-end check against a fake/test ``WorkflowTemplateClient``: with
    ``register_switchboard_template`` itself left un-mocked, injecting a fake
    client class at the construction point inside the registrar still
    results in the fake client's ``create_workflow_template`` being invoked
    for the ``spinsci-switchboard`` template when ``main()`` runs."""
    fake_client_holder: dict[str, FakeWorkflowTemplateClient] = {}

    def fake_client_factory() -> FakeWorkflowTemplateClient:
        client = FakeWorkflowTemplateClient()
        fake_client_holder["client"] = client
        return client

    monkeypatch.setattr(
        "api.services.switchboard.enablement.registrar.WorkflowTemplateClient",
        fake_client_factory,
    )

    await entrypoint.main()

    fake_client = fake_client_holder["client"]
    assert len(fake_client.create_calls) == 1
    assert fake_client.create_calls[0]["template_name"] == SWITCHBOARD_TEMPLATE_NAME
