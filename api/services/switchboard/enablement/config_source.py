"""Switchboard_Config: org-scoped configuration overrides.

Loads the business-hours schedule/timezone and after-hours hotword list from
org-scoped configuration (``switchboard.business_hours`` / ``switchboard.hotwords``
on ``OrganizationConfigurationModel``), layered over the
``api/services/switchboard/config.py`` defaults (America/Chicago business hours,
empty hotword list). This is the enablement layer's I/O boundary feeding the
switchboard's pure decision logic (:func:`~api.services.switchboard.schedule.is_after_hours`,
:func:`~api.services.switchboard.after_hours.detect_hotword`) — those functions
stay pure and side-effect-free; this module is where the DB read happens.

Design references:
- ``design.md`` -> "Switchboard_Config"
- ``requirements.md`` -> Requirements 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4,
  10.5

Requirements: 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

from loguru import logger

from api.db.organization_configuration_client import OrganizationConfigurationClient
from api.services.switchboard.after_hours import detect_hotword
from api.services.worker_sync.manager import get_worker_sync_manager
from api.services.worker_sync.protocol import WorkerSyncEventType
from api.services.switchboard.config import (
    BUSINESS_HOURS_SCHEDULE,
    SCHEDULE_TIMEZONE,
    BusinessHoursWindow,
    load_afterhours_hotwords,
)
from api.services.switchboard.schedule import is_after_hours

#: Org-scoped configuration key holding the business-hours schedule/timezone
#: override (see module docstring for the value shape).
BUSINESS_HOURS_CONFIG_KEY = "switchboard.business_hours"

#: Org-scoped configuration key holding the after-hours hotword keyword list
#: override (see module docstring for the value shape).
HOTWORDS_CONFIG_KEY = "switchboard.hotwords"

#: A single open/close window expressed as ``"HH:MM"`` strings (the JSON-safe
#: shape stored on ``OrganizationConfigurationModel.value``), or ``None`` when
#: the day is closed.
_StrBusinessHoursWindow = Optional[Tuple[str, str]]

#: The full 7-day week, matching ``datetime.date.weekday()`` (Monday=0).
_WEEKDAYS: Tuple[int, ...] = tuple(range(7))


@dataclass(frozen=True)
class BusinessHoursConfig:
    """The resolved business-hours schedule and timezone for an organization.

    ``schedule`` mirrors the ``switchboard.business_hours`` config value shape:
    keyed by ``datetime.date.weekday()`` (Monday=0 .. Sunday=6), each value is
    an ``(open, close)`` pair of ``"HH:MM"`` local-time strings, or ``None``
    when the day is closed. Kept as strings (not ``datetime.time``) so this
    model round-trips the JSON-serializable org-config value directly; use
    :func:`business_hours_schedule_to_windows` to obtain the ``datetime.time``
    windows :func:`~api.services.switchboard.schedule.is_after_hours` expects.
    """

    timezone: str
    schedule: Mapping[int, _StrBusinessHoursWindow]


def _default_schedule_as_strings() -> dict[int, _StrBusinessHoursWindow]:
    """Return :data:`~api.services.switchboard.config.BUSINESS_HOURS_SCHEDULE`
    re-expressed with ``"HH:MM"`` string times instead of ``datetime.time``.
    """
    result: dict[int, _StrBusinessHoursWindow] = {}
    for day, window in BUSINESS_HOURS_SCHEDULE.items():
        if window is None:
            result[day] = None
        else:
            open_time, close_time = window
            result[day] = (open_time.strftime("%H:%M"), close_time.strftime("%H:%M"))
    return result


#: The default business-hours configuration (America/Chicago, Mon-Fri
#: 08:00-17:00, Sat 08:00-12:00, Sunday closed) — applied whenever no org
#: override is configured, or the configured override is malformed
#: (Req 9.2).
DEFAULT_BUSINESS_HOURS_CONFIG: BusinessHoursConfig = BusinessHoursConfig(
    timezone=SCHEDULE_TIMEZONE, schedule=_default_schedule_as_strings()
)


def _parse_window(raw_window: Any) -> _StrBusinessHoursWindow:
    """Parse and validate one schedule day's raw ``[open, close]`` value.

    Raises:
        ValueError: If ``raw_window`` is not ``None`` and not a 2-item pair of
            parseable ``"HH:MM"`` time strings.
    """
    if raw_window is None:
        return None
    if not isinstance(raw_window, (list, tuple)) or len(raw_window) != 2:
        raise ValueError("business_hours schedule window must be [open, close] or null")
    open_str, close_str = raw_window
    if not isinstance(open_str, str) or not isinstance(close_str, str):
        raise ValueError("business_hours schedule window times must be strings")
    # Validate parseability; raises ValueError on a malformed time string.
    time.fromisoformat(open_str)
    time.fromisoformat(close_str)
    return (open_str, close_str)


def _parse_business_hours_value(raw: Any) -> BusinessHoursConfig:
    """Parse and validate a raw ``switchboard.business_hours`` config value.

    Raises:
        ValueError: If ``raw`` does not match the documented
            ``{"timezone": str, "schedule": {"0": [open, close] | null, ...}}``
            shape, including an unresolvable IANA ``timezone`` or a schedule
            missing any of the 7 weekday entries.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("business_hours config value must be a mapping")

    timezone_value = raw.get("timezone")
    if not isinstance(timezone_value, str) or not timezone_value:
        raise ValueError("business_hours.timezone must be a non-empty string")
    ZoneInfo(timezone_value)  # raises on an unresolvable IANA timezone name

    schedule_raw = raw.get("schedule")
    if not isinstance(schedule_raw, Mapping):
        raise ValueError("business_hours.schedule must be a mapping")

    schedule: dict[int, _StrBusinessHoursWindow] = {}
    for day in _WEEKDAYS:
        if day in schedule_raw:
            window_raw = schedule_raw[day]
        elif str(day) in schedule_raw:
            window_raw = schedule_raw[str(day)]
        else:
            raise ValueError(f"business_hours.schedule missing weekday {day}")
        schedule[day] = _parse_window(window_raw)

    return BusinessHoursConfig(timezone=timezone_value, schedule=schedule)


def business_hours_schedule_to_windows(
    config: BusinessHoursConfig,
) -> Mapping[int, BusinessHoursWindow]:
    """Convert a :class:`BusinessHoursConfig` schedule to ``datetime.time`` windows.

    Bridges the JSON-safe string schedule stored/loaded here to the
    ``Mapping[int, Optional[Tuple[time, time]]]`` shape
    :func:`~api.services.switchboard.schedule.is_after_hours` accepts as its
    ``schedule`` override. ``config.schedule`` is always already validated
    (either the module defaults or a parsed, validated override), so this never
    raises.
    """
    return {
        day: None if window is None else (time.fromisoformat(window[0]), time.fromisoformat(window[1]))
        for day, window in config.schedule.items()
    }


async def load_business_hours(
    organization_id: int,
    *,
    config_client: OrganizationConfigurationClient | None = None,
) -> BusinessHoursConfig:
    """Load the effective business-hours schedule/timezone for an organization.

    Reads the ``switchboard.business_hours`` org-config override via
    :meth:`~api.db.organization_configuration_client.OrganizationConfigurationClient.get_configuration_value`
    (Req 9.1, 9.3). When the value is absent, or present but malformed, falls
    back to the :mod:`api.services.switchboard.config` defaults — America/Chicago,
    Monday-Friday 08:00-17:00, Saturday 08:00-12:00, Sunday closed (Req 9.2). A
    malformed override is logged by config key name only; the raw value is
    never logged.

    Args:
        organization_id: The organization whose business-hours override (if
            any) should be read.
        config_client: The org-configuration DB client to use. Defaults to a
            new :class:`OrganizationConfigurationClient`, but tests may inject
            an in-memory fake.

    Returns:
        The effective :class:`BusinessHoursConfig` — the org override when
        present and well-formed, otherwise :data:`DEFAULT_BUSINESS_HOURS_CONFIG`.
    """
    client = config_client or OrganizationConfigurationClient()
    raw_value = await client.get_configuration_value(
        organization_id, BUSINESS_HOURS_CONFIG_KEY, default=None
    )
    if raw_value is None:
        return DEFAULT_BUSINESS_HOURS_CONFIG

    try:
        return _parse_business_hours_value(raw_value)
    except Exception:
        logger.warning(
            "Malformed organization override for config key {!r} (org {}); "
            "falling back to switchboard defaults",
            BUSINESS_HOURS_CONFIG_KEY,
            organization_id,
        )
        return DEFAULT_BUSINESS_HOURS_CONFIG


def _parse_hotwords_value(raw: Any) -> list[str]:
    """Parse and validate a raw ``switchboard.hotwords`` config value.

    Raises:
        ValueError: If ``raw`` does not match the documented
            ``{"keywords": [str, ...]}`` shape.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("hotwords config value must be a mapping")
    keywords_raw = raw.get("keywords")
    if not isinstance(keywords_raw, list):
        raise ValueError("hotwords.keywords must be a list")

    keywords: list[str] = []
    for item in keywords_raw:
        if not isinstance(item, str):
            raise ValueError("hotwords.keywords entries must be strings")
        trimmed = item.strip().lower()
        if trimmed:
            keywords.append(trimmed)
    return keywords


async def load_hotwords(
    organization_id: int,
    *,
    config_client: OrganizationConfigurationClient | None = None,
) -> list[str]:
    """Load the effective after-hours hotword keyword list for an organization.

    Reads the ``switchboard.hotwords`` org-config override via
    :meth:`~api.db.organization_configuration_client.OrganizationConfigurationClient.get_configuration_value`
    (Req 10.1, 10.3). When the value is absent, falls back to
    :func:`~api.services.switchboard.config.load_afterhours_hotwords` (the
    ``SWITCHBOARD_AFTERHOURS_HOTWORDS`` env var) (Req 10.2). When the value is
    present but malformed, also falls back to the env loader, logging the
    config key name only (never the raw value). A present-and-well-formed
    override — including an explicit empty ``keywords`` list — is honored as
    given: an empty list matches nothing (Req 10.5).

    Args:
        organization_id: The organization whose hotword override (if any)
            should be read.
        config_client: The org-configuration DB client to use. Defaults to a
            new :class:`OrganizationConfigurationClient`, but tests may inject
            an in-memory fake.

    Returns:
        The effective hotword keyword list, lower-cased and trimmed.
    """
    client = config_client or OrganizationConfigurationClient()
    raw_value = await client.get_configuration_value(
        organization_id, HOTWORDS_CONFIG_KEY, default=None
    )
    if raw_value is None:
        return load_afterhours_hotwords()

    try:
        return _parse_hotwords_value(raw_value)
    except Exception:
        logger.warning(
            "Malformed organization override for config key {!r} (org {}); "
            "falling back to the environment-configured hotword list",
            HOTWORDS_CONFIG_KEY,
            organization_id,
        )
        return load_afterhours_hotwords()


# ---------------------------------------------------------------------------
# After-hours evaluation call sites (Req 9.4, 10.4, 10.5)
# ---------------------------------------------------------------------------
#
# These wrap the switchboard's pure decision functions
# (schedule.is_after_hours, after_hours.detect_hotword) with the org-scoped
# config source above, so a graph-builder/pipeline call site reads business
# hours and hotwords through configuration rather than the module-level
# config.py constants directly. The decision functions themselves stay pure;
# the DB read happens only here, at the I/O boundary.


async def evaluate_after_hours(
    organization_id: int,
    dt_local: datetime,
    *,
    config_client: OrganizationConfigurationClient | None = None,
) -> bool:
    """Config-aware ``after_hours`` evaluation for a call (Req 9.1, 9.4).

    Loads the organization's effective :class:`BusinessHoursConfig` via
    :func:`load_business_hours` and evaluates ``dt_local`` against it through
    the pure :func:`~api.services.switchboard.schedule.is_after_hours`
    evaluator. When no org override is configured this reduces to the same
    result :func:`~api.services.switchboard.schedule.is_after_hours` would
    give against the module defaults (Req 9.2), preserving current behavior.

    Args:
        organization_id: The organization whose business-hours configuration
            governs this call.
        dt_local: The moment the call starts.
        config_client: The org-configuration DB client to use. Defaults to a
            new :class:`OrganizationConfigurationClient`.

    Returns:
        ``True`` when the call is after hours, ``False`` when within business
        hours, per the organization's effective schedule and timezone.
    """
    config = await load_business_hours(organization_id, config_client=config_client)
    schedule = business_hours_schedule_to_windows(config)
    return is_after_hours(dt_local, schedule=schedule, timezone=config.timezone)


async def evaluate_hotword(
    organization_id: int,
    speech: Optional[str],
    *,
    config_client: OrganizationConfigurationClient | None = None,
) -> Optional[str]:
    """Config-aware after-hours hotword detection for a call (Req 10.1, 10.4, 10.5).

    Loads the organization's effective hotword list via :func:`load_hotwords`
    and scans ``speech`` for a match through the pure
    :func:`~api.services.switchboard.after_hours.detect_hotword` evaluator.
    An empty or unconfigured list never matches (Req 10.5); a configured match
    is returned so the caller can trigger the urgent silent-routing path
    (Req 10.4).

    Args:
        organization_id: The organization whose hotword configuration governs
            this call.
        speech: The caller's utterance.
        config_client: The org-configuration DB client to use. Defaults to a
            new :class:`OrganizationConfigurationClient`.

    Returns:
        The matched keyword, or ``None`` when no hotword is present.
    """
    keywords = await load_hotwords(organization_id, config_client=config_client)
    return detect_hotword(speech, keywords)


# ---------------------------------------------------------------------------
# Upsert + cross-worker propagation (repo multi-worker rule)
# ---------------------------------------------------------------------------
#
# `load_business_hours`/`load_hotwords` above read straight from the DB on
# every call (no local caching), so today there is no in-worker cache for a
# write to go stale. Still, per the repo's multi-worker rule, any write path
# for these two config keys must broadcast through `WorkerSyncManager` rather
# than assume in-process state is global — these helpers are that write path
# so a future admin/config route (or ARQ task) has a single, correct place to
# call rather than reimplementing the upsert + broadcast pattern. Mirrors
# `save_langfuse_credentials` in `api/routes/organization.py`.


async def upsert_business_hours_config(
    organization_id: int,
    value: dict,
    *,
    config_client: OrganizationConfigurationClient | None = None,
) -> None:
    """Upsert the org's ``switchboard.business_hours`` override and broadcast it.

    Writes ``value`` (the ``{"timezone": ..., "schedule": {...}}`` shape
    documented on :class:`BusinessHoursConfig`) via
    :meth:`OrganizationConfigurationClient.upsert_configuration`, then
    broadcasts a :attr:`WorkerSyncEventType.SWITCHBOARD_BUSINESS_HOURS` event
    via :class:`~api.services.worker_sync.manager.WorkerSyncManager` so every
    worker is notified of the change (repo multi-worker rule).

    Args:
        organization_id: The organization the override applies to.
        value: The raw config value to store (validated by
            :func:`load_business_hours` on next read; malformed values fall
            back to defaults rather than raising here).
        config_client: The org-configuration DB client to use. Defaults to a
            new :class:`OrganizationConfigurationClient`.
    """
    client = config_client or OrganizationConfigurationClient()
    await client.upsert_configuration(organization_id, BUSINESS_HOURS_CONFIG_KEY, value)
    await get_worker_sync_manager().broadcast(
        WorkerSyncEventType.SWITCHBOARD_BUSINESS_HOURS,
        action="update",
        org_id=str(organization_id),
    )


async def upsert_hotwords_config(
    organization_id: int,
    value: dict,
    *,
    config_client: OrganizationConfigurationClient | None = None,
) -> None:
    """Upsert the org's ``switchboard.hotwords`` override and broadcast it.

    Writes ``value`` (the ``{"keywords": [...]}`` shape) via
    :meth:`OrganizationConfigurationClient.upsert_configuration`, then
    broadcasts a :attr:`WorkerSyncEventType.SWITCHBOARD_HOTWORDS` event via
    :class:`~api.services.worker_sync.manager.WorkerSyncManager` so every
    worker is notified of the change (repo multi-worker rule).

    Args:
        organization_id: The organization the override applies to.
        value: The raw config value to store (validated by
            :func:`load_hotwords` on next read; malformed values fall back to
            the env-configured list rather than raising here).
        config_client: The org-configuration DB client to use. Defaults to a
            new :class:`OrganizationConfigurationClient`.
    """
    client = config_client or OrganizationConfigurationClient()
    await client.upsert_configuration(organization_id, HOTWORDS_CONFIG_KEY, value)
    await get_worker_sync_manager().broadcast(
        WorkerSyncEventType.SWITCHBOARD_HOTWORDS,
        action="update",
        org_id=str(organization_id),
    )


__all__ = [
    "BUSINESS_HOURS_CONFIG_KEY",
    "HOTWORDS_CONFIG_KEY",
    "BusinessHoursConfig",
    "DEFAULT_BUSINESS_HOURS_CONFIG",
    "business_hours_schedule_to_windows",
    "load_business_hours",
    "load_hotwords",
    "evaluate_after_hours",
    "evaluate_hotword",
    "upsert_business_hours_config",
    "upsert_hotwords_config",
]
