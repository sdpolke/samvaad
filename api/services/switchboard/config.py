"""Schedule and session configuration for the SpinSci Switchboard PoC.

This module holds the *static* configuration consumed by the switchboard's
pure decision logic:

* the America/Chicago business-hours schedule (Requirement 17.1, 17.2),
* the mandatory default session lines (Requirement 17.4, 17.5), and
* a config-driven loader for the after-hours hotword keyword list
  (Requirement 21.1, 21.2).

It deliberately contains **no** evaluation logic. The pure
``is_after_hours(dt_local) -> bool`` evaluator (task 2) reads
:data:`BUSINESS_HOURS_SCHEDULE` and :data:`SCHEDULE_TIMEZONE` from here, and the
hotword-detection path reads the list returned by
:func:`load_afterhours_hotwords`.
"""

from __future__ import annotations

import os
from datetime import time
from typing import Mapping, Optional, Tuple

from loguru import logger

# ---------------------------------------------------------------------------
# Schedule configuration (Requirement 17.1, 17.2)
# ---------------------------------------------------------------------------

#: IANA timezone in which business hours are evaluated. All schedule
#: comparisons happen in this zone (Requirement 17.1).
SCHEDULE_TIMEZONE: str = "America/Chicago"

# A single open/close window for a weekday, expressed as local wall-clock
# times in :data:`SCHEDULE_TIMEZONE`. ``None`` means the day is closed.
BusinessHoursWindow = Optional[Tuple[time, time]]

#: Business-hours schedule keyed by ``datetime.date.weekday()`` value where
#: Monday is ``0`` and Sunday is ``6``. Each value is an ``(open, close)``
#: tuple of local times, or ``None`` when the day is closed.
#:
#: Monday–Friday 08:00–17:00, Saturday 08:00–12:00, Sunday closed
#: (Requirement 17.2). Consumed read-only by the pure ``is_after_hours``
#: evaluator (task 2).
BUSINESS_HOURS_SCHEDULE: Mapping[int, BusinessHoursWindow] = {
    0: (time(8, 0), time(17, 0)),  # Monday
    1: (time(8, 0), time(17, 0)),  # Tuesday
    2: (time(8, 0), time(17, 0)),  # Wednesday
    3: (time(8, 0), time(17, 0)),  # Thursday
    4: (time(8, 0), time(17, 0)),  # Friday
    5: (time(8, 0), time(12, 0)),  # Saturday
    6: None,  # Sunday — closed
}

# ---------------------------------------------------------------------------
# Default session lines (Requirement 17.4, 17.5)
# ---------------------------------------------------------------------------

#: Default hangup/goodbye line spoken before ending a call (Requirement 17.4).
#: Reproduced verbatim — do not alter wording or punctuation.
DEFAULT_GOODBYE_LINE: str = "Thank you for calling SpinSci. Goodbye."

#: Default transfer fallback line spoken while connecting a call
#: (Requirement 17.5). Reproduced verbatim — do not alter wording or
#: punctuation.
DEFAULT_TRANSFER_FALLBACK_LINE: str = "One moment while I connect you."

# ---------------------------------------------------------------------------
# After-hours hotword keyword list (Requirement 21.1, 21.2)
# ---------------------------------------------------------------------------

#: Environment variable that supplies the after-hours hotword keyword list.
#: Values are comma-separated (e.g. ``"chest pain,stroke,bleeding"``). The
#: actual keywords are supplied by SpinSci later purely via configuration with
#: no code change (Requirement 21.2).
AFTERHOURS_HOTWORDS_ENV_VAR: str = "SWITCHBOARD_AFTERHOURS_HOTWORDS"


def load_afterhours_hotwords() -> list[str]:
    """Load the after-hours hotword keyword list from configuration.

    The list is read from the :data:`AFTERHOURS_HOTWORDS_ENV_VAR` environment
    variable rather than hardcoded (Requirement 21.1). Values are
    comma-separated; surrounding whitespace is trimmed and empty entries are
    dropped. Matching is normalised to lower case so downstream detection can
    compare case-insensitively.

    When nothing is configured the loader returns an empty list, allowing the
    keyword list to be supplied later by SpinSci without any code change
    (Requirement 21.2).

    Returns:
        The configured hotword keywords, or an empty list when unset.
    """
    raw = os.getenv(AFTERHOURS_HOTWORDS_ENV_VAR, "")
    keywords = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not keywords:
        logger.debug(
            "No after-hours hotwords configured via {}; defaulting to empty list.",
            AFTERHOURS_HOTWORDS_ENV_VAR,
        )
    return keywords
