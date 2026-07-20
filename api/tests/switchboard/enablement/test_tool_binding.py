"""Edge-case test for binding persistence failure (Req 6.6).

``PUT /tools/{tool_uuid}/binding`` (``api/routes/tool.py::update_tool_binding``)
has no explicit ``try``/``except`` around the ``db_client.update_tool(...)``
call. If that call raises instead of returning ``None``, the exception
propagates uncaught and FastAPI's default unhandled-exception handling turns
it into an HTTP 500 response — satisfying Req 6.6 ("display an error and NOT
present the save as successful") through default framework behavior rather
than explicit error-handling code in the route.

This test simulates that DB failure (by monkeypatching
``api.routes.tool.db_client.update_tool`` to raise) and asserts:

1. The route does not return a 200/success ``ToolResponse`` — it surfaces as
   a 5xx error.
2. No partial binding is persisted: a direct (unpatched) DB read of the tool
   shows the pre-request ``config.url``/``config.credential_uuid``/
   ``config.field_mapping`` values, not the values from the failed request.

Design references:
- ``design.md`` -> "Tool_Binding_Editor + binding persistence", "Error Handling"
  -> "Binding persistence failure (Req 6.6)"
- ``requirements.md`` -> Requirement 6.6

Task: 12.6.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from api.db.models import OrganizationModel, UserModel
from api.services.switchboard.enablement.provisioner import (
    CONNECTOR_NAME_KEY,
    provision_connector_tools,
)


@asynccontextmanager
async def _client_surfacing_server_errors(user):
    """Like the ``test_client_factory`` fixture, but with
    ``raise_app_exceptions=False`` so an unhandled exception in the route is
    observed as the HTTP 500 response FastAPI's default handling produces,
    instead of propagating out of the ASGI transport and failing the test."""
    from api.app import app
    from api.services.auth.depends import get_user

    async def mock_get_user():
        return user

    original_override = app.dependency_overrides.get(get_user)
    app.dependency_overrides[get_user] = mock_get_user

    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        if original_override:
            app.dependency_overrides[get_user] = original_override
        else:
            app.dependency_overrides.pop(get_user, None)


async def test_binding_persistence_failure_returns_error_and_persists_nothing(
    db_session, async_session
):
    """Req 6.6: a simulated DB failure during ``update_tool`` for a binding
    save must surface as an error (not a 200 success), and the tool's
    pre-request binding fields must remain unchanged (no partial write)."""
    org = OrganizationModel(provider_id="test-org-binding-failure")
    async_session.add(org)
    await async_session.flush()

    user = UserModel(
        provider_id="test-user-binding-failure",
        selected_organization_id=org.id,
    )
    async_session.add(user)
    await async_session.flush()

    # Provision one real connector tool for the org so we have a valid
    # tool_uuid to send a binding request against.
    name_to_uuid = await provision_connector_tools(
        organization_id=org.id,
        user_id=user.id,
        tool_client=db_session,
    )
    tool_uuid = name_to_uuid["patient_lookup"]

    # Capture the pre-request binding fields via a direct, unpatched DB read.
    pre_request_tool = await db_session.get_tool_by_uuid(
        tool_uuid, org.id, include_archived=True
    )
    pre_request_config = dict(pre_request_tool.definition.get("config", {}))
    assert pre_request_config.get("url") == ""
    assert pre_request_config.get("credential_uuid") is None
    assert pre_request_config.get("field_mapping") == {}

    # Reload the user so selected_organization_id is populated on the object
    # the auth dependency override will return.
    user = await db_session.get_user_by_id(user.id)

    failing_binding_body = {
        "url": "https://spinsci.example.com/patient-lookup",
        "credential_uuid": None,
        "field_mapping": {"mrn": "patient_id"},
    }

    with patch(
        "api.routes.tool.db_client.update_tool",
        new_callable=AsyncMock,
        side_effect=RuntimeError("simulated DB failure"),
    ):
        async with _client_surfacing_server_errors(user) as client:
            response = await client.put(
                f"/api/v1/tools/{tool_uuid}/binding",
                json=failing_binding_body,
            )

    # The route has no explicit try/except around db_client.update_tool, so
    # the unhandled RuntimeError propagates and FastAPI's default handling
    # turns it into a 500 — not a 200 success (Req 6.6).
    assert response.status_code >= 500, (
        f"Expected a server error, got {response.status_code}: {response.text}"
    )
    assert response.status_code != 200

    # Independently verify (direct, unpatched DB read) that no partial
    # binding was persisted: the tool's config fields remain at their
    # pre-request (provisioned) values.
    post_request_tool = await db_session.get_tool_by_uuid(
        tool_uuid, org.id, include_archived=True
    )
    post_request_config = dict(post_request_tool.definition.get("config", {}))
    assert post_request_config.get("url") == pre_request_config.get("url")
    assert post_request_config.get("credential_uuid") == pre_request_config.get(
        "credential_uuid"
    )
    assert post_request_config.get("field_mapping") == pre_request_config.get(
        "field_mapping"
    )
    # Explicitly confirm the failed request's values were NOT persisted.
    assert post_request_config.get("url") != failing_binding_body["url"]
    assert (
        post_request_config.get("field_mapping") != failing_binding_body["field_mapping"]
    )

    # The switchboard identity marker (untouched metadata) should also be
    # unaffected.
    assert (
        post_request_tool.definition.get("switchboard", {}).get(CONNECTOR_NAME_KEY)
        == "patient_lookup"
    )
