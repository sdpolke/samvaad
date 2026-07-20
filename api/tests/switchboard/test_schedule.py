"""Property-based test for the after-hours schedule evaluator (task 2.2).

Covers Property 1 — Business-hours schedule evaluation (Req 17.1, 17.2, 17.3).

The property runs >= 100 iterations (Hypothesis default) and its generators hit
DST boundaries, week edges, all of Sunday, boundary times (open/close), and
both timezone-aware and naive datetimes.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from hypothesis import example, given, settings
from hypothesis import strategies as st
from zoneinfo import ZoneInfo

from api.services.switchboard.config import BUSINESS_HOURS_SCHEDULE, SCHEDULE_TIMEZONE
from api.services.switchboard.schedule import is_after_hours

_CHICAGO = ZoneInfo(SCHEDULE_TIMEZONE)

# ---------------------------------------------------------------------------
# Helpers: oracle that independently computes the expected result
# ---------------------------------------------------------------------------


def _oracle_is_after_hours(dt_local: datetime) -> bool:
    """Independent reference implementation for the schedule evaluator.

    Computes the expected result from the config schedule without relying on
    the implementation under test.
    """
    if dt_local.tzinfo is not None:
        dt_local = dt_local.astimezone(_CHICAGO)

    window = BUSINESS_HOURS_SCHEDULE.get(dt_local.weekday())
    if window is None:
        return True  # Closed day (Sunday)

    open_time, close_time = window
    local_time = dt_local.time()
    # Half-open interval: [open, close)
    return not (open_time <= local_time < close_time)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# All days of the week (0=Mon .. 6=Sun)
_weekdays = st.integers(min_value=0, max_value=6)

# Times covering the full day including boundaries
_times = st.one_of(
    # Exactly at open/close boundaries
    st.sampled_from([
        time(8, 0),      # Open time (in-hours for Mon-Sat)
        time(17, 0),     # Close time (after-hours for Mon-Fri)
        time(12, 0),     # Close time (after-hours for Sat)
        time(7, 59, 59),  # Just before open
        time(0, 0),       # Midnight
        time(23, 59, 59),  # End of day
    ]),
    # Random times throughout the day
    st.times(),
)

# Years that include DST transitions for America/Chicago
# Spring forward: typically 2nd Sunday in March
# Fall back: typically 1st Sunday in November
_years = st.sampled_from([2023, 2024, 2025])


def _build_naive_chicago_datetime(year: int, weekday: int, t: time) -> datetime:
    """Build a naive datetime on the given weekday in the given year."""
    # Start from Jan 1 and find the first occurrence of the desired weekday,
    # then pick a date in the middle of the year for variety.
    base = datetime(year, 6, 1)
    # Advance to the desired weekday
    days_ahead = weekday - base.weekday()
    if days_ahead < 0:
        days_ahead += 7
    target_date = base + timedelta(days=days_ahead)
    return target_date.replace(hour=t.hour, minute=t.minute, second=t.second)


# Strategy: naive datetimes (assumed Chicago local time)
_naive_datetimes = st.builds(
    _build_naive_chicago_datetime,
    year=_years,
    weekday=_weekdays,
    t=_times,
)

# Strategy: timezone-aware datetimes in America/Chicago
_aware_chicago_datetimes = _naive_datetimes.map(
    lambda dt: dt.replace(tzinfo=_CHICAGO)
)

# Strategy: timezone-aware datetimes in UTC (to test conversion)
_aware_utc_datetimes = _naive_datetimes.map(
    lambda dt: dt.replace(tzinfo=ZoneInfo("UTC"))
)

# Strategy: timezone-aware datetimes in other timezones (edge: Asia/Tokyo is +9/+9)
_aware_other_tz_datetimes = _naive_datetimes.map(
    lambda dt: dt.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
)

# Combined strategy covering all input shapes
_all_datetimes = st.one_of(
    _naive_datetimes,
    _aware_chicago_datetimes,
    _aware_utc_datetimes,
    _aware_other_tz_datetimes,
)

# ---------------------------------------------------------------------------
# DST-specific strategies for America/Chicago
# Spring forward 2024: March 10 02:00 → 03:00
# Fall back 2024: November 3 02:00 → 01:00
# ---------------------------------------------------------------------------

_dst_spring_forward_datetimes = st.sampled_from([
    # Just before spring forward (still CST, Sunday)
    datetime(2024, 3, 10, 1, 59, 0, tzinfo=_CHICAGO),
    # After spring forward (CDT, Sunday)
    datetime(2024, 3, 10, 3, 0, 0, tzinfo=_CHICAGO),
    # Monday after spring forward at open
    datetime(2024, 3, 11, 8, 0, 0, tzinfo=_CHICAGO),
    # Monday after spring forward at close
    datetime(2024, 3, 11, 17, 0, 0, tzinfo=_CHICAGO),
])

_dst_fall_back_datetimes = st.sampled_from([
    # Just before fall back (CDT, Sunday)
    datetime(2024, 11, 3, 0, 59, 0, tzinfo=_CHICAGO),
    # After fall back (CST, Sunday)
    datetime(2024, 11, 3, 2, 0, 0, tzinfo=_CHICAGO),
    # Monday after fall back at open
    datetime(2024, 11, 4, 8, 0, 0, tzinfo=_CHICAGO),
    # Monday after fall back at close
    datetime(2024, 11, 4, 17, 0, 0, tzinfo=_CHICAGO),
])

# Week edges: Friday→Saturday, Saturday→Sunday transitions
_week_edge_datetimes = st.sampled_from([
    # Friday at close (after-hours)
    datetime(2024, 7, 5, 17, 0, 0, tzinfo=_CHICAGO),
    # Friday just before close (in-hours)
    datetime(2024, 7, 5, 16, 59, 59, tzinfo=_CHICAGO),
    # Saturday at open (in-hours)
    datetime(2024, 7, 6, 8, 0, 0, tzinfo=_CHICAGO),
    # Saturday at close (after-hours)
    datetime(2024, 7, 6, 12, 0, 0, tzinfo=_CHICAGO),
    # Saturday just before close (in-hours)
    datetime(2024, 7, 6, 11, 59, 59, tzinfo=_CHICAGO),
    # Sunday midnight (after-hours, closed)
    datetime(2024, 7, 7, 0, 0, 0, tzinfo=_CHICAGO),
    # Sunday noon (after-hours, closed)
    datetime(2024, 7, 7, 12, 0, 0, tzinfo=_CHICAGO),
])


# ===========================================================================
# Property 1: Business-hours schedule evaluation
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 1: Business-hours schedule evaluation
@given(dt=_all_datetimes)
@example(dt=datetime(2024, 3, 10, 12, 0, 0, tzinfo=_CHICAGO))  # DST spring forward Sunday
@example(dt=datetime(2024, 11, 3, 12, 0, 0, tzinfo=_CHICAGO))  # DST fall back Sunday
@example(dt=datetime(2024, 7, 7, 0, 0, 0, tzinfo=_CHICAGO))    # Midnight Sunday
@example(dt=datetime(2024, 7, 1, 8, 0, 0, tzinfo=_CHICAGO))    # Monday at open (in-hours)
@example(dt=datetime(2024, 7, 1, 17, 0, 0, tzinfo=_CHICAGO))   # Monday at close (after-hours)
@example(dt=datetime(2024, 7, 6, 8, 0, 0, tzinfo=_CHICAGO))    # Saturday at open (in-hours)
@example(dt=datetime(2024, 7, 6, 12, 0, 0, tzinfo=_CHICAGO))   # Saturday at close (after-hours)
@example(dt=datetime(2024, 7, 6, 11, 59, 59, tzinfo=_CHICAGO))  # Saturday just before close (in-hours)
@settings(max_examples=200)
def test_property_1_business_hours_schedule_evaluation(dt: datetime) -> None:
    """is_after_hours returns False exactly when within business hours, True otherwise.

    **Validates: Requirements 17.1, 17.2, 17.3**

    - Mon-Fri 08:00-17:00 → in-hours (False)
    - Sat 08:00-12:00 → in-hours (False)
    - Sunday → always after-hours (True)
    - Half-open intervals: [open, close) — open is in, close is out
    - Timezone-aware inputs are converted to America/Chicago first
    - Naive inputs are assumed to be America/Chicago local time
    """
    result = is_after_hours(dt)
    expected = _oracle_is_after_hours(dt)
    assert result is expected, (
        f"is_after_hours({dt!r}) returned {result}, expected {expected}. "
        f"weekday={dt.weekday()}, time={dt.time()}"
    )


# Feature: spinsci-switchboard-poc, Property 1: Business-hours schedule evaluation
@given(dt=_dst_spring_forward_datetimes)
def test_property_1_dst_spring_forward(dt: datetime) -> None:
    """DST spring-forward boundary: schedule is correct across the clock change.

    **Validates: Requirements 17.1, 17.2, 17.3**
    """
    result = is_after_hours(dt)
    expected = _oracle_is_after_hours(dt)
    assert result is expected


# Feature: spinsci-switchboard-poc, Property 1: Business-hours schedule evaluation
@given(dt=_dst_fall_back_datetimes)
def test_property_1_dst_fall_back(dt: datetime) -> None:
    """DST fall-back boundary: schedule is correct across the clock change.

    **Validates: Requirements 17.1, 17.2, 17.3**
    """
    result = is_after_hours(dt)
    expected = _oracle_is_after_hours(dt)
    assert result is expected


# Feature: spinsci-switchboard-poc, Property 1: Business-hours schedule evaluation
@given(dt=_week_edge_datetimes)
def test_property_1_week_edges(dt: datetime) -> None:
    """Week edges (Fri→Sat, Sat→Sun): transitions between open and closed.

    **Validates: Requirements 17.1, 17.2, 17.3**
    """
    result = is_after_hours(dt)
    expected = _oracle_is_after_hours(dt)
    assert result is expected


# ===========================================================================
# Targeted unit tests for critical edge cases
# ===========================================================================


class TestScheduleEdgeCases:
    """Explicit unit tests verifying critical boundaries."""

    def test_sunday_always_after_hours(self) -> None:
        """All of Sunday is after-hours (schedule = None)."""
        # Sunday at various times
        for hour in (0, 8, 12, 17, 23):
            dt = datetime(2024, 7, 7, hour, 0, 0, tzinfo=_CHICAGO)
            assert is_after_hours(dt) is True

    def test_monday_at_open_is_in_hours(self) -> None:
        """Exactly 08:00 Mon is in-hours (half-open: includes open)."""
        dt = datetime(2024, 7, 1, 8, 0, 0, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is False

    def test_monday_at_close_is_after_hours(self) -> None:
        """Exactly 17:00 Mon is after-hours (half-open: excludes close)."""
        dt = datetime(2024, 7, 1, 17, 0, 0, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is True

    def test_saturday_at_open_is_in_hours(self) -> None:
        """Exactly 08:00 Sat is in-hours."""
        dt = datetime(2024, 7, 6, 8, 0, 0, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is False

    def test_saturday_at_close_is_after_hours(self) -> None:
        """Exactly 12:00 Sat is after-hours."""
        dt = datetime(2024, 7, 6, 12, 0, 0, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is True

    def test_saturday_just_before_close_is_in_hours(self) -> None:
        """11:59:59 Sat is still in-hours."""
        dt = datetime(2024, 7, 6, 11, 59, 59, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is False

    def test_before_open_is_after_hours(self) -> None:
        """07:59 Mon is before open → after-hours."""
        dt = datetime(2024, 7, 1, 7, 59, 0, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is True

    def test_utc_datetime_converted_correctly(self) -> None:
        """A UTC datetime is converted to Chicago before evaluation."""
        # 2024-07-01 13:00 UTC = 08:00 CDT (Chicago, in-hours)
        dt_utc = datetime(2024, 7, 1, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
        assert is_after_hours(dt_utc) is False

    def test_naive_datetime_treated_as_chicago(self) -> None:
        """A naive datetime is assumed to be Chicago local time."""
        # Monday 10:00 (in-hours)
        dt_naive = datetime(2024, 7, 1, 10, 0, 0)
        assert is_after_hours(dt_naive) is False

    def test_dst_spring_forward_sunday_still_closed(self) -> None:
        """Spring forward happens on a Sunday — still after-hours."""
        dt = datetime(2024, 3, 10, 10, 0, 0, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is True

    def test_dst_fall_back_sunday_still_closed(self) -> None:
        """Fall back happens on a Sunday — still after-hours."""
        dt = datetime(2024, 11, 3, 10, 0, 0, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is True

    def test_monday_after_dst_spring_forward_at_open(self) -> None:
        """Monday after spring forward at 08:00 CDT is in-hours."""
        dt = datetime(2024, 3, 11, 8, 0, 0, tzinfo=_CHICAGO)
        assert is_after_hours(dt) is False
