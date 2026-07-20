"""Pure after-hours schedule evaluator for the SpinSci switchboard (Requirement 17).

This module holds the single pure decision function that decides whether a call
falls outside SpinSci's business hours. It reads the America/Chicago
business-hours schedule from :mod:`api.services.switchboard.config` and contains
no side effects, so it is directly unit- and property-testable independent of the
LLM/TTS/telephony runtime.

The boolean produced here is used to set ``after_hours`` on the Call State Ledger
at call start (Requirement 17.3), which drives business vs. after-hours behavior.

Design references:
- ``design.md`` → "The evaluation is a pure function ``is_after_hours(dt_local) -> bool``"
- ``design.md`` → Correctness Properties → "Property 1: Business-hours schedule evaluation"
- ``requirements.md`` → Requirement 17 (17.1 timezone, 17.2 schedule, 17.3 set at call start)
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Optional
from zoneinfo import ZoneInfo

from api.services.switchboard.config import (
    BUSINESS_HOURS_SCHEDULE,
    SCHEDULE_TIMEZONE,
    BusinessHoursWindow,
)

#: Cached timezone object for the default schedule zone (Requirement 17.1).
_SCHEDULE_ZONE = ZoneInfo(SCHEDULE_TIMEZONE)


def is_after_hours(
    dt_local: datetime,
    *,
    schedule: Optional[Mapping[int, BusinessHoursWindow]] = None,
    timezone: Optional[str] = None,
) -> bool:
    """Return whether ``dt_local`` falls outside SpinSci business hours.

    Business hours are evaluated in America/Chicago by default (Requirement 17.1)
    against the Monday–Friday 08:00–17:00, Saturday 08:00–12:00, Sunday-closed
    schedule (Requirement 17.2). The function returns ``False`` exactly when the
    local wall-clock time lands inside an open window and ``True`` otherwise —
    including all of Sunday and any time before open or at/after close.

    Open windows are treated as half-open ``[open, close)``: a call at exactly the
    opening time (e.g. 08:00) is within business hours, while a call at exactly the
    closing time (e.g. 17:00 Mon–Fri or 12:00 Sat) is after hours. Because the
    comparison is performed on the resolved local wall-clock time, the result is
    correct across daylight-saving transitions.

    ``schedule`` and ``timezone`` allow an org-scoped override (see
    ``api.services.switchboard.enablement.config_source.evaluate_after_hours``)
    to be evaluated through this same pure function without duplicating the
    comparison logic. When omitted, the module defaults
    (:data:`~api.services.switchboard.config.BUSINESS_HOURS_SCHEDULE` and
    :data:`~api.services.switchboard.config.SCHEDULE_TIMEZONE`) are used, so
    unconfigured behavior is unchanged.

    Args:
        dt_local: The moment the call starts. A timezone-aware datetime is
            converted into the resolved zone before evaluation; a naive datetime
            is assumed to already be local wall-clock time in that zone.
        schedule: An override business-hours schedule keyed by
            ``datetime.date.weekday()``. Defaults to
            :data:`~api.services.switchboard.config.BUSINESS_HOURS_SCHEDULE`.
        timezone: An override IANA timezone name. Defaults to
            :data:`~api.services.switchboard.config.SCHEDULE_TIMEZONE`.

    Returns:
        ``True`` when the call is after hours, ``False`` when it is within business
        hours.
    """
    zone = _SCHEDULE_ZONE if timezone is None else ZoneInfo(timezone)
    if dt_local.tzinfo is not None:
        dt_local = dt_local.astimezone(zone)

    active_schedule = schedule if schedule is not None else BUSINESS_HOURS_SCHEDULE
    window = active_schedule.get(dt_local.weekday())
    if window is None:
        # Closed all day (e.g. Sunday) — always after hours.
        return True

    open_time, close_time = window
    local_time = dt_local.time()
    return not (open_time <= local_time < close_time)


__all__ = ["is_after_hours"]
