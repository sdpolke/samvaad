"""Property test for binding persistence round-trip (task 12.4).

Covers Property 10 — Binding persistence round-trip (Requirement 6.5).

For arbitrary valid bindings (endpoint URL, credential reference, field
mapping) saved onto a real, provisioned connector ``ToolModel`` via
``PUT /tools/{tool_uuid}/binding``, reading the tool back must yield a
definition whose ``config.url`` / ``config.credential_uuid`` /
``config.field_mapping`` equal exactly what was saved.

This exercises the full route (``api/routes/tool.py::update_tool_binding``)
through HTTP via the repo's ``test_client_factory`` fixture, against the real
test database (transaction-rolled-back-per-test isolation), per
``.kiro/steering/testing.md`` ("For routes, test through
``test_client_factory``").

Masking note: ``build_tool_response`` (called by the route) applies
``mask_connector_tool_definition`` whenever ``definition.get("switchboard")``
is present -- true for every provisioned connector tool. To make this a
genuine, unconfounded round-trip check (masking is a separate, already-tested
concern -- Property 11), this test verifies persistence by reading the tool
back directly from the DB via ``db_session.get_tool_by_uuid(...)``,
bypassing the route's response-level masking, rather than comparing against
the route's own (possibly masked) JSON response.

In fact, per ``masking.py``, ``url``/``field_mapping`` *keys* are never
masked by name (only *values* stored under a name in the tool's declared
``sensitive_fields`` -- e.g. ``phone``, ``patient_id`` -- are masked), and
``config.credential_uuid`` is explicitly always left visible (Req 6.2). So a
same-route-response comparison would likely also pass for these particular
fields; the direct-DB read is used anyway as the safer, masking-independent
verification path the task calls for.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 10: Binding
  persistence round-trip"
- ``design.md`` -> "Tool_Binding_Editor + binding persistence"
- ``requirements.md`` -> Requirement 6.5

Task: 12.4.
"""

from __future__ import annotations

import itertools
import string

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from api.db.models import OrganizationModel, UserModel
from api.enums import WebhookCredentialType
from api.services.switchboard.enablement.provisioner import provision_connector_tools

_suffix_counter = itertools.count(1)


def _next_suffix() -> int:
    return next(_suffix_counter)

# Candidate endpoint URLs, including the empty string (an "unbound" tool is a
# valid state -- Req 6.3) and representative shapes with paths/query strings.
_st_url = st.sampled_from(
    [
        "",
        "https://example.test/a",
        "https://example.test/b/c?x=1",
        "https://spinsci.example.com/patient-lookup?mrn=123&dob=2000-01-01",
    ]
)

_st_field_mapping = st.dictionaries(
    keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=10),
    values=st.text(min_size=1, max_size=10),
    max_size=5,
)


async def _setup_org_user_tool_and_credential(
    db_session, async_session, *, suffix: str
) -> tuple[int, int, str, str]:
    """Create an org/user, provision one real connector tool, and create one
    real credential for that org. Returns
    ``(organization_id, user_id, tool_uuid, credential_uuid)``.

    Runs against the real test DB (transaction-rolled-back-per-test
    isolation, via the ``db_session``/``async_session`` fixtures).
    """
    org = OrganizationModel(provider_id=f"test-org-binding-property-{suffix}")
    async_session.add(org)
    await async_session.flush()

    user = UserModel(
        provider_id=f"test-user-binding-property-{suffix}",
        selected_organization_id=org.id,
    )
    async_session.add(user)
    await async_session.flush()

    name_to_uuid = await provision_connector_tools(
        organization_id=org.id,
        user_id=user.id,
        tool_client=db_session,
    )
    tool_uuid = name_to_uuid["patient_lookup"]

    credential = await db_session.create_credential(
        organization_id=org.id,
        user_id=user.id,
        name="binding-property-credential",
        credential_type=WebhookCredentialType.BEARER_TOKEN.value,
        credential_data={"token": "test-token"},
    )

    return org.id, user.id, tool_uuid, credential.credential_uuid


async def _put_binding_and_read_back(
    test_client_factory,
    db_client,
    *,
    organization_id: int,
    user_id: int,
    tool_uuid: str,
    url: str,
    credential_uuid: str | None,
    field_mapping: dict[str, str],
):
    user = await db_client.get_user_by_id(user_id)

    async with test_client_factory(user) as client:
        response = await client.put(
            f"/api/v1/tools/{tool_uuid}/binding",
            json={
                "url": url,
                "credential_uuid": credential_uuid,
                "field_mapping": field_mapping,
            },
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )

    # Independently verify persistence via a direct DB read, bypassing the
    # route's response-level masking entirely.
    persisted_tool = await db_client.get_tool_by_uuid(
        tool_uuid, organization_id, include_archived=True
    )
    return persisted_tool


# Feature: switchboard-frontend-enablement, Property 10: Binding persistence
# round-trip
# Validates: Requirements 6.5
#
# max_examples is lower than the usual 100 because each example performs a
# real HTTP round-trip through the route plus multiple real DB round-trips
# (tool lookup, credential lookup, tool update, and the direct verification
# read) against the test Postgres instance -- keeping this at 100 would make
# the test suite noticeably slower for comparatively little extra coverage
# of a straightforward merge-and-persist code path.
@given(
    url=_st_url,
    use_real_credential=st.booleans(),
    field_mapping=_st_field_mapping,
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_binding_persistence_round_trip(
    test_client_factory,
    db_session,
    async_session,
    url: str,
    use_real_credential: bool,
    field_mapping: dict[str, str],
) -> None:
    """Req 6.5: saving a binding via ``PUT /tools/{tool_uuid}/binding`` and
    then reading the tool back yields a definition whose ``config.url`` /
    ``config.credential_uuid`` / ``config.field_mapping`` equal exactly what
    was saved.

    Runs as an ``async def`` test (rather than driving its own event loop
    with ``asyncio.run(...)``) so it shares the single session-scoped event
    loop pytest-asyncio and the ``db_session``/``async_session`` fixtures
    are already bound to (``asyncio_default_fixture_loop_scope = session`` in
    ``api/pytest.ini``); spinning up a second event loop per generated
    example caused the underlying asyncpg connection to be driven from
    multiple loops and produced flaky ``InvalidRequestError``s.
    """
    # Each generated example needs its own org/user/tool/credential so
    # repeated examples within the same test invocation (sharing the same
    # rolled-back transaction) don't collide on unique provider_id constraints.
    suffix = str(_next_suffix())

    (
        organization_id,
        user_id,
        tool_uuid,
        real_credential_uuid,
    ) = await _setup_org_user_tool_and_credential(
        db_session, async_session, suffix=suffix
    )

    credential_uuid = real_credential_uuid if use_real_credential else None

    persisted_tool = await _put_binding_and_read_back(
        test_client_factory,
        db_session,
        organization_id=organization_id,
        user_id=user_id,
        tool_uuid=tool_uuid,
        url=url,
        credential_uuid=credential_uuid,
        field_mapping=field_mapping,
    )

    assert persisted_tool is not None
    config = persisted_tool.definition.get("config", {})
    assert config.get("url") == url
    assert config.get("credential_uuid") == credential_uuid
    assert config.get("field_mapping") == field_mapping
