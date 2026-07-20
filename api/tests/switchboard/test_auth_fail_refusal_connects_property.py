"""Property-based test for fail/refusal still connects (task 9.5).

Covers Property 15 — Authentication failure or refusal still connects
(Requirements 9.7, 9.12).

For any AuthOutcome (SUCCESS, FAILED, REFUSED, ATTEMPTS_EXHAUSTED), the next
terminal after authentication is always TRANSFER (never HANGUP). Refusal,
failure, or attempt-exhaustion never hangs up for the failure alone — the caller
is always connected.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.auth import (
    AUTH_MAX_PHONE_ATTEMPTS,
    AuthOutcome,
    AuthTerminal,
    NoRecordOutcome,
    auth_fail_route_line,
    auth_outcome_connects,
    next_terminal_after_auth,
    no_record_decision,
    phone_attempts_exhausted,
    should_speak_fail_route_line,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All AuthOutcome enum values.
_all_auth_outcomes = st.sampled_from(list(AuthOutcome))

#: Non-SUCCESS AuthOutcome values (failure/refusal/exhaustion).
_non_success_outcomes = st.sampled_from(
    [o for o in AuthOutcome if o is not AuthOutcome.SUCCESS]
)

#: Attempts range covering values around the threshold (0..10).
_attempts = st.integers(min_value=0, max_value=10)

#: Attempts at or above the exhaustion threshold.
_exhausted_attempts = st.integers(min_value=AUTH_MAX_PHONE_ATTEMPTS, max_value=10)

#: Attempts below the exhaustion threshold.
_remaining_attempts = st.integers(min_value=0, max_value=AUTH_MAX_PHONE_ATTEMPTS - 1)


# ===========================================================================
# Property 15: Authentication failure or refusal still connects
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects
@given(outcome=_all_auth_outcomes)
@example(outcome=AuthOutcome.SUCCESS)
@example(outcome=AuthOutcome.FAILED)
@example(outcome=AuthOutcome.REFUSED)
@example(outcome=AuthOutcome.ATTEMPTS_EXHAUSTED)
@settings(max_examples=200)
def test_auth_outcome_always_connects(outcome: AuthOutcome) -> None:
    """For any AuthOutcome, auth_outcome_connects returns True.

    **Validates: Requirements 9.7, 9.12**

    The caller is always connected regardless of outcome — refusal, failure,
    or attempt-exhaustion never hangs up for the failure alone (Req 9.7, 9.12).
    """
    # Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects

    result = auth_outcome_connects(outcome)
    assert result is True, (
        f"Expected auth_outcome_connects({outcome}) to be True, got {result}"
    )


# Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects
@given(outcome=_all_auth_outcomes)
@example(outcome=AuthOutcome.SUCCESS)
@example(outcome=AuthOutcome.FAILED)
@example(outcome=AuthOutcome.REFUSED)
@example(outcome=AuthOutcome.ATTEMPTS_EXHAUSTED)
@settings(max_examples=200)
def test_next_terminal_always_transfer(outcome: AuthOutcome) -> None:
    """For any AuthOutcome, next_terminal_after_auth returns TRANSFER (never HANGUP).

    **Validates: Requirements 9.7, 9.12**

    The terminal telephony action after any Authentication outcome is always
    TRANSFER — no outcome results in a hangup for the failure alone.
    """
    # Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects

    result = next_terminal_after_auth(outcome)
    assert result is AuthTerminal.TRANSFER, (
        f"Expected TRANSFER for outcome={outcome}, got {result}"
    )
    assert result is not AuthTerminal.HANGUP, (
        f"HANGUP must never occur for any AuthOutcome, but got {result} "
        f"for outcome={outcome}"
    )


# Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects
@given(outcome=_non_success_outcomes)
@example(outcome=AuthOutcome.FAILED)
@example(outcome=AuthOutcome.REFUSED)
@example(outcome=AuthOutcome.ATTEMPTS_EXHAUSTED)
@settings(max_examples=200)
def test_fail_route_line_spoken_on_non_success(outcome: AuthOutcome) -> None:
    """For any non-SUCCESS AuthOutcome, should_speak_fail_route_line returns True.

    **Validates: Requirements 9.7, 9.12**

    The "No problem. I'll connect you now." line is spoken on any non-SUCCESS
    outcome (refusal, failure, exhaustion). For SUCCESS, it returns False.
    """
    # Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects

    result = should_speak_fail_route_line(outcome)
    assert result is True, (
        f"Expected should_speak_fail_route_line({outcome}) to be True "
        f"for non-SUCCESS outcome, got {result}"
    )

    # Also verify SUCCESS returns False (the complementary case)
    success_result = should_speak_fail_route_line(AuthOutcome.SUCCESS)
    assert success_result is False, (
        f"Expected should_speak_fail_route_line(SUCCESS) to be False, "
        f"got {success_result}"
    )


# Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects
def test_fail_route_line_is_verbatim() -> None:
    """The auth_fail_route_line() returns the exact mandated string.

    **Validates: Requirements 9.7, 9.12**

    On auth refusal or failure, the mandated Appendix C line is spoken verbatim:
    "No problem. I\u2019ll connect you now." This is a constant property — no
    Hypothesis generation needed, but included for completeness of the property
    suite.
    """
    # Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects

    expected = "No problem. I\u2019ll connect you now."
    result = auth_fail_route_line()
    assert result == expected, (
        f"Expected verbatim fail/route line {expected!r}, got {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects
@given(attempts_used=_attempts)
@example(attempts_used=0)
@example(attempts_used=2)
@example(attempts_used=3)
@example(attempts_used=10)
@settings(max_examples=200)
def test_phone_attempts_exhausted_threshold(attempts_used: int) -> None:
    """For attempts_used >= AUTH_MAX_PHONE_ATTEMPTS, phone_attempts_exhausted is True.

    **Validates: Requirements 9.7, 9.12**

    The threshold is AUTH_MAX_PHONE_ATTEMPTS (3). At or above that value the
    caller's phone attempts are exhausted; below it they still have remaining
    attempts.
    """
    # Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects

    result = phone_attempts_exhausted(attempts_used)
    if attempts_used >= AUTH_MAX_PHONE_ATTEMPTS:
        assert result is True, (
            f"Expected phone_attempts_exhausted({attempts_used}) to be True "
            f"(>= threshold {AUTH_MAX_PHONE_ATTEMPTS}), got {result}"
        )
    else:
        assert result is False, (
            f"Expected phone_attempts_exhausted({attempts_used}) to be False "
            f"(< threshold {AUTH_MAX_PHONE_ATTEMPTS}), got {result}"
        )


# Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects
@given(attempts_used=_exhausted_attempts)
@example(attempts_used=3)
@example(attempts_used=5)
@example(attempts_used=10)
@settings(max_examples=200)
def test_no_record_routes_without_hangup_when_exhausted(
    attempts_used: int,
) -> None:
    """For attempts_used >= AUTH_MAX_PHONE_ATTEMPTS, no_record_decision returns ROUTE_WITHOUT_HANGUP.

    **Validates: Requirements 9.7, 9.12**

    When phone attempts are exhausted (>= 3), the caller is routed without
    hanging up for the failure alone — never hangs up.
    """
    # Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects

    result = no_record_decision(attempts_used)
    assert result is NoRecordOutcome.ROUTE_WITHOUT_HANGUP, (
        f"Expected ROUTE_WITHOUT_HANGUP for attempts_used={attempts_used} "
        f"(>= threshold {AUTH_MAX_PHONE_ATTEMPTS}), got {result}"
    )


# Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects
@given(attempts_used=_remaining_attempts)
@example(attempts_used=0)
@example(attempts_used=1)
@example(attempts_used=2)
@settings(max_examples=200)
def test_no_record_reprompts_when_attempts_remain(
    attempts_used: int,
) -> None:
    """For attempts_used < AUTH_MAX_PHONE_ATTEMPTS, no_record_decision returns REPROMPT_DIFFERENT_NUMBER.

    **Validates: Requirements 9.7, 9.12**

    While phone attempts remain (below the threshold of 3), the caller is
    re-prompted for a different number rather than being routed or hung up.
    """
    # Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects

    result = no_record_decision(attempts_used)
    assert result is NoRecordOutcome.REPROMPT_DIFFERENT_NUMBER, (
        f"Expected REPROMPT_DIFFERENT_NUMBER for attempts_used={attempts_used} "
        f"(< threshold {AUTH_MAX_PHONE_ATTEMPTS}), got {result}"
    )
