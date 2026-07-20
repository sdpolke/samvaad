"""Property-based test for template registration idempotence (task 2.3).

Covers Property 2 — Template registration idempotence
(Requirements 1.3, 1.4).

For all integers N >= 1, registering the switchboard template N times against
a catalog leaves exactly one switchboard template entry (keyed by the stable
``SWITCHBOARD_TEMPLATE_NAME``) whose ``template_json`` equals the latest
serialization — never a duplicate.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 2: Template
  registration idempotence"
- ``requirements.md`` -> Requirements 1.3, 1.4
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from api.services.switchboard.enablement.registrar import (
    SWITCHBOARD_TEMPLATE_NAME,
    register_switchboard_template,
)
from api.tests.switchboard.enablement.test_registrar import (
    FakeWorkflowTemplateClient,
)


def _register_n_times(n: int):
    """Register the switchboard template ``n`` times against a fresh
    in-memory fake client, returning the client and every call's result
    (in order) so the test can compare the stored row against the *last*
    performed registration."""

    async def _run():
        client = FakeWorkflowTemplateClient()
        results = []
        for _ in range(n):
            results.append(await register_switchboard_template(template_client=client))
        return client, results

    return asyncio.run(_run())


# Feature: switchboard-frontend-enablement, Property 2: Template registration idempotence
@given(n=st.integers(min_value=1, max_value=10))
@settings(max_examples=100, deadline=None)
def test_registration_is_idempotent_across_n_calls(n: int) -> None:
    """Req 1.3, 1.4: registering N times leaves exactly one row keyed by
    SWITCHBOARD_TEMPLATE_NAME, with template_json equal to the latest
    serialization (the json actually persisted by the Nth call) — never a
    duplicate.

    Note: the assembled switchboard graph mints fresh random suffixes for
    dynamically-named nodes on every build, so ``template_json`` legitimately
    differs from call to call. "Latest serialization" therefore means the
    json produced by the most recent registration call, not an independently
    recomputed serialization.
    """
    client, results = _register_n_times(n)
    last_result = results[-1]

    matching_rows = [
        row
        for row in client._rows.values()
        if row.template_name == SWITCHBOARD_TEMPLATE_NAME
    ]

    # Exactly one row keyed by the stable template name, regardless of N.
    assert len(matching_rows) == 1
    # No duplicate rows of any kind were left behind either.
    assert len(client._rows) == 1

    # The single remaining row's template_json matches what the latest
    # (Nth) registration call actually persisted.
    assert matching_rows[0].template_json == last_result.template_json
    assert matching_rows[0].id == last_result.id

    # The first call creates; every subsequent call updates the same row.
    assert len(client.create_calls) == 1
    assert len(client.update_calls) == n - 1
    # Every create/update call after the first targets the same row id.
    if client.update_calls:
        assert all(
            call["template_id"] == matching_rows[0].id for call in client.update_calls
        )
