"""Unit tests for switchboard config loading and config-driven hotword behavior.

Validates:
- Schedule constants (Requirements 17.1, 17.2)
- Default session lines (Requirements 17.4, 17.5)
- Hotword list loaded from config, not hardcoded (Requirements 21.1, 21.2)
"""

from __future__ import annotations

import os
from datetime import time
from unittest.mock import patch

import pytest

from api.services.switchboard.config import (
    AFTERHOURS_HOTWORDS_ENV_VAR,
    BUSINESS_HOURS_SCHEDULE,
    DEFAULT_GOODBYE_LINE,
    DEFAULT_TRANSFER_FALLBACK_LINE,
    SCHEDULE_TIMEZONE,
    load_afterhours_hotwords,
)


# ---------------------------------------------------------------------------
# Schedule constants (Requirement 17.1, 17.2)
# ---------------------------------------------------------------------------


class TestScheduleConstants:
    """Assert the business-hours schedule is configured correctly."""

    def test_timezone_is_america_chicago(self) -> None:
        """SCHEDULE_TIMEZONE must be America/Chicago (Req 17.1)."""
        assert SCHEDULE_TIMEZONE == "America/Chicago"

    def test_all_seven_days_covered(self) -> None:
        """The schedule must define entries for all 7 weekdays (0-6)."""
        assert set(BUSINESS_HOURS_SCHEDULE.keys()) == {0, 1, 2, 3, 4, 5, 6}

    @pytest.mark.parametrize("weekday", [0, 1, 2, 3, 4])
    def test_mon_fri_hours(self, weekday: int) -> None:
        """Mon-Fri (0-4) must have open=08:00, close=17:00 (Req 17.2)."""
        window = BUSINESS_HOURS_SCHEDULE[weekday]
        assert window is not None
        open_time, close_time = window
        assert open_time == time(8, 0)
        assert close_time == time(17, 0)

    def test_saturday_hours(self) -> None:
        """Saturday (5) must have open=08:00, close=12:00 (Req 17.2)."""
        window = BUSINESS_HOURS_SCHEDULE[5]
        assert window is not None
        open_time, close_time = window
        assert open_time == time(8, 0)
        assert close_time == time(12, 0)

    def test_sunday_closed(self) -> None:
        """Sunday (6) must be None — closed (Req 17.2)."""
        assert BUSINESS_HOURS_SCHEDULE[6] is None


# ---------------------------------------------------------------------------
# Default session lines (Requirement 17.4, 17.5)
# ---------------------------------------------------------------------------


class TestDefaultSessionLines:
    """Assert the mandatory default session lines are exact."""

    def test_default_goodbye_line(self) -> None:
        """DEFAULT_GOODBYE_LINE must be the exact mandated text (Req 17.4)."""
        assert DEFAULT_GOODBYE_LINE == "Thank you for calling SpinSci. Goodbye."

    def test_default_transfer_fallback_line(self) -> None:
        """DEFAULT_TRANSFER_FALLBACK_LINE must be the exact mandated text (Req 17.5)."""
        assert DEFAULT_TRANSFER_FALLBACK_LINE == "One moment while I connect you."


# ---------------------------------------------------------------------------
# Hotword list loaded from config, not hardcoded (Requirement 21.1, 21.2)
# ---------------------------------------------------------------------------


class TestLoadAfterhoursHotwords:
    """Assert that the hotword list comes from configuration (env var), not hardcoded."""

    def test_env_var_name(self) -> None:
        """The env var name constant must be SWITCHBOARD_AFTERHOURS_HOTWORDS."""
        assert AFTERHOURS_HOTWORDS_ENV_VAR == "SWITCHBOARD_AFTERHOURS_HOTWORDS"

    def test_returns_empty_list_when_unset(self) -> None:
        """When env var is unset, load_afterhours_hotwords returns [] (Req 21.2)."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the env var is definitely absent
            os.environ.pop(AFTERHOURS_HOTWORDS_ENV_VAR, None)
            result = load_afterhours_hotwords()
        assert result == []

    def test_parses_comma_separated_keywords(self) -> None:
        """Comma-separated keywords are parsed into a list (Req 21.1)."""
        with patch.dict(
            os.environ, {AFTERHOURS_HOTWORDS_ENV_VAR: "chest pain,stroke,bleeding"}
        ):
            result = load_afterhours_hotwords()
        assert result == ["chest pain", "stroke", "bleeding"]

    def test_whitespace_trimmed(self) -> None:
        """Whitespace around each keyword is trimmed."""
        with patch.dict(
            os.environ,
            {AFTERHOURS_HOTWORDS_ENV_VAR: "  chest pain , stroke ,  bleeding  "},
        ):
            result = load_afterhours_hotwords()
        assert result == ["chest pain", "stroke", "bleeding"]

    def test_empty_entries_dropped(self) -> None:
        """Empty entries from consecutive commas are dropped."""
        with patch.dict(
            os.environ,
            {AFTERHOURS_HOTWORDS_ENV_VAR: "chest pain,,stroke,,,bleeding,"},
        ):
            result = load_afterhours_hotwords()
        assert result == ["chest pain", "stroke", "bleeding"]

    def test_keywords_lowercased(self) -> None:
        """Keywords are normalized to lowercase."""
        with patch.dict(
            os.environ,
            {AFTERHOURS_HOTWORDS_ENV_VAR: "Chest Pain,STROKE,Bleeding"},
        ):
            result = load_afterhours_hotwords()
        assert result == ["chest pain", "stroke", "bleeding"]

    def test_hotwords_come_from_env_not_hardcoded(self) -> None:
        """Different env values produce different results — proving config-driven (Req 21.2)."""
        with patch.dict(
            os.environ, {AFTERHOURS_HOTWORDS_ENV_VAR: "fever,cough"}
        ):
            result_a = load_afterhours_hotwords()

        with patch.dict(
            os.environ, {AFTERHOURS_HOTWORDS_ENV_VAR: "headache,nausea,dizziness"}
        ):
            result_b = load_afterhours_hotwords()

        assert result_a == ["fever", "cough"]
        assert result_b == ["headache", "nausea", "dizziness"]
        # Different inputs produce different outputs — not hardcoded
        assert result_a != result_b
