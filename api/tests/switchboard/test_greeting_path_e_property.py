"""Property-based test for Path E repeat-then-fallback (task 6.5).

Covers Property 9 — Path E repeats then falls back on the third failure
(Requirements 6.9, 6.10).

For any run of consecutive not-understood turns, the Greeting phase emits the
Path E line on turns 1 and 2 and, on the third consecutive failure, stops
repeating Path E and emits the ROUTING REQUEST wording instead.
"""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.greeting import (
    PATH_E_MAX_REPEATS,
    PathERetryState,
    path_e_response,
)
from api.services.switchboard.scripts import GREETING_PATH_E, GREETING_ROUTING_REQUEST

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Consecutive failures in the "Path E" zone (turns 1 and 2).
_path_e_failures = st.integers(min_value=1, max_value=PATH_E_MAX_REPEATS)

# Consecutive failures in the "fallback" zone (turn 3+).
_fallback_failures = st.integers(min_value=PATH_E_MAX_REPEATS + 1, max_value=100)

# Invalid (zero or negative) failure counts.
_invalid_failures = st.integers(min_value=-100, max_value=0)

# Arbitrary valid failure counts (>= 1).
_any_valid_failures = st.integers(min_value=1, max_value=200)

# Number of not-understood turns to simulate in state machine tests.
_turn_counts = st.integers(min_value=1, max_value=20)


# ===========================================================================
# Property 9: Path E repeats then falls back on the third failure
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
@given(failures=_path_e_failures)
@example(failures=1)
@example(failures=2)
@settings(max_examples=200)
def test_property_9_path_e_on_turns_1_and_2(failures: int) -> None:
    """path_e_response returns the Path E line for consecutive_failures 1 and 2.

    **Validates: Requirements 6.9, 6.10**

    On the first and second consecutive not-understood turns, the Greeting phase
    speaks the Path E line ("I didn't quite catch that. Could you repeat that
    for me?").
    """
    # Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
    result = path_e_response(failures)

    assert result == GREETING_PATH_E, (
        f"Expected Path E line for consecutive_failures={failures}, "
        f"got {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
@given(failures=_fallback_failures)
@example(failures=3)
@example(failures=4)
@example(failures=10)
@settings(max_examples=200)
def test_property_9_fallback_on_turn_3_plus(failures: int) -> None:
    """path_e_response returns ROUTING REQUEST for consecutive_failures >= 3.

    **Validates: Requirements 6.9, 6.10**

    On the third and any subsequent consecutive not-understood turn, the Greeting
    phase stops repeating Path E and speaks the ROUTING REQUEST wording instead.
    """
    # Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
    result = path_e_response(failures)

    assert result == GREETING_ROUTING_REQUEST, (
        f"Expected ROUTING REQUEST for consecutive_failures={failures}, "
        f"got {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
@given(num_turns=_turn_counts)
@example(num_turns=1)
@example(num_turns=2)
@example(num_turns=3)
@example(num_turns=5)
@settings(max_examples=200)
def test_property_9_state_machine_advances(num_turns: int) -> None:
    """PathERetryState machine produces Path E on turns 1-2, fallback on turn 3+.

    **Validates: Requirements 6.9, 6.10**

    Starting from a fresh state, recording consecutive not-understood turns
    advances the counter. The response property produces Path E for the first two
    turns and ROUTING REQUEST from the third onward.
    """
    # Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
    state = PathERetryState()

    for turn in range(1, num_turns + 1):
        state = state.record_not_understood()
        response = state.response

        if turn <= PATH_E_MAX_REPEATS:
            assert response == GREETING_PATH_E, (
                f"Turn {turn}: expected Path E, got {response!r}"
            )
        else:
            assert response == GREETING_ROUTING_REQUEST, (
                f"Turn {turn}: expected ROUTING REQUEST, got {response!r}"
            )


# Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
@given(failures_before_reset=_any_valid_failures, failures_after_reset=_turn_counts)
@example(failures_before_reset=3, failures_after_reset=1)
@example(failures_before_reset=5, failures_after_reset=2)
@example(failures_before_reset=1, failures_after_reset=3)
@settings(max_examples=200)
def test_property_9_reset_restarts_from_scratch(
    failures_before_reset: int, failures_after_reset: int
) -> None:
    """After a reset, PathERetryState starts fresh (Path E again on next failure).

    **Validates: Requirements 6.9, 6.10**

    Regardless of how many consecutive failures occurred before, a reset clears
    the counter and the machine behaves as if starting over.
    """
    # Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
    state = PathERetryState()

    # Accumulate failures before reset
    for _ in range(failures_before_reset):
        state = state.record_not_understood()

    # Reset
    state = state.reset()
    assert state.consecutive_failures == 0, (
        "After reset, consecutive_failures should be 0"
    )

    # Accumulate failures after reset — should behave like a fresh start
    for turn in range(1, failures_after_reset + 1):
        state = state.record_not_understood()
        response = state.response

        if turn <= PATH_E_MAX_REPEATS:
            assert response == GREETING_PATH_E, (
                f"Post-reset turn {turn}: expected Path E, got {response!r}"
            )
        else:
            assert response == GREETING_ROUTING_REQUEST, (
                f"Post-reset turn {turn}: expected ROUTING REQUEST, got {response!r}"
            )


# Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
@given(failures=_fallback_failures)
@example(failures=3)
@example(failures=50)
@settings(max_examples=200)
def test_property_9_never_path_e_after_fallback(failures: int) -> None:
    """For any consecutive_failures > PATH_E_MAX_REPEATS, response is always ROUTING REQUEST.

    **Validates: Requirements 6.9, 6.10**

    Once the threshold is exceeded, Path E is never returned — the response is
    always the ROUTING REQUEST wording regardless of how high the counter goes.
    """
    # Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
    result = path_e_response(failures)

    assert result != GREETING_PATH_E, (
        f"Path E should never be returned for consecutive_failures={failures}"
    )
    assert result == GREETING_ROUTING_REQUEST, (
        f"Expected ROUTING REQUEST for consecutive_failures={failures}, "
        f"got {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
@given(failures=_invalid_failures)
@example(failures=0)
@example(failures=-1)
@example(failures=-100)
@settings(max_examples=200)
def test_property_9_value_error_for_invalid_input(failures: int) -> None:
    """path_e_response raises ValueError for consecutive_failures < 1.

    **Validates: Requirements 6.9, 6.10**

    The function requires at least 1 failure (the current turn is a failure).
    Zero or negative values are invalid and must raise ValueError.
    """
    # Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure
    with pytest.raises(ValueError):
        path_e_response(failures)
