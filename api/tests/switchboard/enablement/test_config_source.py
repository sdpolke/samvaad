"""Unit tests for config defaults and representative evaluations.

Covers:
- Default America/Chicago business-hours schedule when unconfigured (Req 9.2)
- Default empty hotword list when unconfigured (Req 10.2)
- Malformed org override falls back to defaults (Req 9.2/10.2 error-handling)
- Representative in/after-hours and hotword-match evaluations using an org
  override (Req 9.4, 10.4)

Design references:
- ``design.md`` -> "Switchboard_Config"
- ``requirements.md`` -> Requirements 9.2, 9.4, 10.2, 10.4

Task: 8.3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.services.switchboard.enablement.config_source import (
    BUSINESS_HOURS_CONFIG_KEY,
    DEFAULT_BUSINESS_HOURS_CONFIG,
    HOTWORDS_CONFIG_KEY,
    evaluate_after_hours,
    evaluate_hotword,
    load_business_hours,
    load_hotwords,
)


class FakeOrganizationConfigurationClient:
    """In-memory stand-in for ``OrganizationConfigurationClient``.

    Mirrors the subset of the real client's interface that
    ``load_business_hours``/``load_hotwords`` depend on
    (``get_configuration_value``), without touching a real database. Values
    are keyed by ``(organization_id, key)``.
    """

    def __init__(self, values: dict[str, Any] | None = None) -> None:
        # For these tests every value is keyed by config key only, since each
        # test uses a single organization id.
        self._values: dict[str, Any] = dict(values or {})

    async def get_configuration_value(
        self, organization_id: int, key: str, default: Any = None
    ) -> Any:
        return self._values.get(key, default)


ORG_ID = 1


# ---------------------------------------------------------------------------
# Default business hours when unconfigured (Req 9.2)
# ---------------------------------------------------------------------------


async def test_load_business_hours_defaults_when_unconfigured():
    """Req 9.2: with no org override configured, load_business_hours returns
    the America/Chicago default schedule."""
    client = FakeOrganizationConfigurationClient()

    config = await load_business_hours(ORG_ID, config_client=client)

    assert config == DEFAULT_BUSINESS_HOURS_CONFIG
    assert config.timezone == "America/Chicago"
    assert config.schedule[0] == ("08:00", "17:00")  # Monday
    assert config.schedule[5] == ("08:00", "12:00")  # Saturday
    assert config.schedule[6] is None  # Sunday closed


# ---------------------------------------------------------------------------
# Default empty hotword list when unconfigured (Req 10.2)
# ---------------------------------------------------------------------------


async def test_load_hotwords_defaults_to_empty_when_unconfigured(monkeypatch):
    """Req 10.2: with no org override and no env var configured,
    load_hotwords returns an empty list."""
    monkeypatch.delenv("SWITCHBOARD_AFTERHOURS_HOTWORDS", raising=False)
    client = FakeOrganizationConfigurationClient()

    hotwords = await load_hotwords(ORG_ID, config_client=client)

    assert hotwords == []


# ---------------------------------------------------------------------------
# Malformed org override falls back to defaults (Req 9.2/10.2 error handling)
# ---------------------------------------------------------------------------


async def test_load_business_hours_falls_back_on_malformed_override_missing_schedule():
    """Req 9.2: a malformed business-hours override (missing "schedule") falls
    back to the module defaults rather than raising."""
    client = FakeOrganizationConfigurationClient(
        {BUSINESS_HOURS_CONFIG_KEY: {"timezone": "America/Chicago"}}
    )

    config = await load_business_hours(ORG_ID, config_client=client)

    assert config == DEFAULT_BUSINESS_HOURS_CONFIG


async def test_load_business_hours_falls_back_on_unresolvable_timezone():
    """Req 9.2: a malformed business-hours override with an unresolvable IANA
    timezone name falls back to the module defaults rather than raising."""
    client = FakeOrganizationConfigurationClient(
        {
            BUSINESS_HOURS_CONFIG_KEY: {
                "timezone": "Not/A_Real_Timezone",
                "schedule": {str(day): None for day in range(7)},
            }
        }
    )

    config = await load_business_hours(ORG_ID, config_client=client)

    assert config == DEFAULT_BUSINESS_HOURS_CONFIG


async def test_load_hotwords_falls_back_to_env_loader_on_malformed_override(
    monkeypatch,
):
    """Req 10.2: a malformed hotwords override (keywords not a list) falls back
    to the env-configured hotword list."""
    monkeypatch.setenv("SWITCHBOARD_AFTERHOURS_HOTWORDS", "chest pain,stroke")
    client = FakeOrganizationConfigurationClient(
        {HOTWORDS_CONFIG_KEY: {"keywords": "not-a-list"}}
    )

    hotwords = await load_hotwords(ORG_ID, config_client=client)

    assert hotwords == ["chest pain", "stroke"]


# ---------------------------------------------------------------------------
# Representative in/after-hours evaluation with an org override (Req 9.4)
# ---------------------------------------------------------------------------


async def test_evaluate_after_hours_with_org_override():
    """Req 9.4: evaluate_after_hours reads the org's overridden schedule and
    timezone (not the module defaults) when deciding in/after hours."""
    # Override: America/New_York, open only Monday 09:00-10:00, closed every
    # other day - a schedule clearly different from the default.
    override_schedule = {str(day): None for day in range(7)}
    override_schedule["0"] = ["09:00", "10:00"]
    client = FakeOrganizationConfigurationClient(
        {
            BUSINESS_HOURS_CONFIG_KEY: {
                "timezone": "America/New_York",
                "schedule": override_schedule,
            }
        }
    )

    # Monday 09:30 local - within the overridden open window.
    within_hours = datetime(2024, 1, 1, 9, 30)  # 2024-01-01 is a Monday
    assert await evaluate_after_hours(ORG_ID, within_hours, config_client=client) is False

    # Monday 11:00 local - outside the overridden open window.
    after_hours = datetime(2024, 1, 1, 11, 0)
    assert await evaluate_after_hours(ORG_ID, after_hours, config_client=client) is True

    # Tuesday - closed all day per the override.
    closed_day = datetime(2024, 1, 2, 9, 30)
    assert await evaluate_after_hours(ORG_ID, closed_day, config_client=client) is True


# ---------------------------------------------------------------------------
# Representative hotword-match evaluation with an org override (Req 10.4)
# ---------------------------------------------------------------------------


async def test_evaluate_hotword_with_org_override():
    """Req 10.4: evaluate_hotword matches against the org's overridden hotword
    list, returning the matched keyword or None for unrelated speech."""
    client = FakeOrganizationConfigurationClient(
        {HOTWORDS_CONFIG_KEY: {"keywords": ["chest pain"]}}
    )

    matched = await evaluate_hotword(
        ORG_ID, "I am having chest pain", config_client=client
    )
    assert matched == "chest pain"

    unmatched = await evaluate_hotword(
        ORG_ID, "I would like to schedule an appointment", config_client=client
    )
    assert unmatched is None
