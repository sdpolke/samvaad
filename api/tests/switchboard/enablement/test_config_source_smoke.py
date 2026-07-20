"""Smoke test for config plumbing — no switchboard code changes required.

Proves, end-to-end against the **real test database**, that the business-hours
schedule/timezone and the after-hours hotword list are read live from
``OrganizationConfigurationClient`` at runtime and change the moment the org
config value is upserted — with zero changes to any switchboard business-logic
module (``after_hours.py``, ``schedule.py``, ``config.py``). Everything here
exercises ``config_source.py`` (task 8.1) exactly as written; this file adds
no new production code.

Unlike ``test_config_source.py`` (task 8.3), which uses an in-memory fake
``OrganizationConfigurationClient`` to test parsing/defaulting logic in
isolation, this test uses the real ``db_session``/``async_session`` fixtures
(the transaction-rolled-back test DB — see ``api/conftest.py``) so the
DB round trip itself — write via ``upsert_configuration``, read back via
``get_configuration_value`` — is what's under test, not a stand-in.

``db_session`` (the patched ``DBClient`` from ``api/conftest.py``) is passed
as the ``config_client`` because ``DBClient`` inherits directly from
``OrganizationConfigurationClient`` (see ``api/db/db_client.py``) and exposes
the exact same ``get_configuration_value``/``upsert_configuration`` methods a
plain ``OrganizationConfigurationClient()`` would — the only difference is
that ``db_session`` is bound to the test's isolated, rolled-back transaction
instead of opening a brand-new engine connection straight at
``DATABASE_URL`` (which would write real, uncommitted-per-test-rollback rows
into the shared test database). This keeps the test hermetic while still
exercising the real client class and the real upsert helpers
(``upsert_business_hours_config``/``upsert_hotwords_config``) end-to-end.

Design references:
- ``design.md`` -> "Switchboard_Config"
- ``requirements.md`` -> Requirements 9.1, 9.3, 10.1, 10.3

Task: 8.4.
"""

from __future__ import annotations

import pytest

import api.services.worker_sync.manager as worker_sync_manager_module
from api.db.models import OrganizationModel
from api.services.switchboard.enablement.config_source import (
    DEFAULT_BUSINESS_HOURS_CONFIG,
    load_business_hours,
    load_hotwords,
    upsert_business_hours_config,
    upsert_hotwords_config,
)
from api.services.worker_sync.manager import WorkerSyncManager


@pytest.fixture(autouse=True)
def _stub_worker_sync_manager(monkeypatch):
    """Stand in for the app-lifespan-started ``WorkerSyncManager`` singleton.

    ``upsert_business_hours_config``/``upsert_hotwords_config`` call
    ``get_worker_sync_manager().broadcast(...)`` after writing the org config
    (repo multi-worker rule). Outside the FastAPI lifespan the module-level
    singleton is uninitialized, so ``get_worker_sync_manager()`` raises
    ``RuntimeError``. Rather than requiring a live Redis connection for this
    test, install a real ``WorkerSyncManager`` instance that was never
    ``.start()``-ed: ``WorkerSyncManager.broadcast`` checks ``self._redis`` and
    gracefully no-ops with a warning log when it is ``None`` (see
    ``api/services/worker_sync/manager.py``), so no Redis instance is needed
    here. ``monkeypatch`` restores the original (uninitialized) module state
    after the test.
    """
    manager = WorkerSyncManager(redis_url="redis://unused-in-this-test")
    monkeypatch.setattr(worker_sync_manager_module, "_manager", manager)
    return manager


async def test_business_hours_and_hotwords_are_live_from_org_config(
    db_session, async_session, monkeypatch
):
    """Req 9.1, 9.3, 10.1, 10.3: schedule/timezone and hotwords are read from
    ``OrganizationConfigurationClient`` at runtime and change when the org
    config value is upserted — no switchboard code changes required.

    No production module in ``api/services/switchboard/`` (in particular
    ``after_hours.py``, ``schedule.py``, ``config.py``) is modified to make
    this pass; the plumbing added in task 8.1 (``config_source.py``) is
    already entirely data-driven off ``OrganizationConfigurationClient``.
    """
    # Ensure a predictable env-fallback default for hotwords regardless of the
    # ambient environment (Req 10.2 default, exercised here only as a
    # baseline before the override).
    monkeypatch.delenv("SWITCHBOARD_AFTERHOURS_HOTWORDS", raising=False)

    org = OrganizationModel(provider_id="test-org-config-source-smoke")
    async_session.add(org)
    await async_session.flush()

    # --- Business hours: default -> live override, read through the DB ----

    before = await load_business_hours(org.id, config_client=db_session)
    assert before == DEFAULT_BUSINESS_HOURS_CONFIG
    assert before.timezone == "America/Chicago"

    override_business_hours = {
        "timezone": "America/New_York",
        "schedule": {
            "0": ["09:00", "18:00"],
            "1": ["09:00", "18:00"],
            "2": ["09:00", "18:00"],
            "3": ["09:00", "18:00"],
            "4": ["09:00", "18:00"],
            "5": None,
            "6": None,
        },
    }
    await upsert_business_hours_config(
        org.id, override_business_hours, config_client=db_session
    )

    after = await load_business_hours(org.id, config_client=db_session)
    assert after != before
    assert after.timezone == "America/New_York"
    assert after.schedule[0] == ("09:00", "18:00")  # Monday, overridden
    assert after.schedule[5] is None  # Saturday, now closed (was open by default)

    # --- Hotwords: default empty -> live override, read through the DB ----

    hotwords_before = await load_hotwords(org.id, config_client=db_session)
    assert hotwords_before == []

    await upsert_hotwords_config(
        org.id, {"keywords": ["stroke"]}, config_client=db_session
    )

    hotwords_after = await load_hotwords(org.id, config_client=db_session)
    assert hotwords_after == ["stroke"]
