"""Property-based test for changed-request return (task 9.6).

Covers Property 16 — Changed request returns to Business/After Hours
(Requirements 9.8).

IF the caller changes their request during Authentication, THEN the Authentication
phase speaks "Sure, let me get you to the right place for that." and returns to
Business Hours or After Hours — NEVER straight to Routing.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.auth import (
    ChangedRequestTransition,
    ReturnPhase,
    changed_request_return_phase,
    changed_request_transition,
)
from api.services.switchboard.scripts import AUTH_CHANGED_REQUEST

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All possible after_hours boolean values.
_after_hours_flag = st.booleans()


# ===========================================================================
# Property 16: Changed request returns to Business/After Hours
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours
@given(after_hours=_after_hours_flag)
@example(after_hours=True)
@example(after_hours=False)
@settings(max_examples=200)
def test_changed_request_return_phase_maps_correctly(after_hours: bool) -> None:
    """changed_request_return_phase maps after_hours to the correct ReturnPhase.

    **Validates: Requirements 9.8**

    For any after_hours boolean, the function returns AFTER_HOURS when True and
    BUSINESS_HOURS when False — never Routing (Routing is not a ReturnPhase member).
    """
    # Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours

    result = changed_request_return_phase(after_hours)

    if after_hours:
        assert result is ReturnPhase.AFTER_HOURS, (
            f"Expected ReturnPhase.AFTER_HOURS for after_hours=True, got {result}"
        )
    else:
        assert result is ReturnPhase.BUSINESS_HOURS, (
            f"Expected ReturnPhase.BUSINESS_HOURS for after_hours=False, got {result}"
        )

    # ReturnPhase has no Routing member — structural guarantee
    assert result in (ReturnPhase.BUSINESS_HOURS, ReturnPhase.AFTER_HOURS), (
        f"Return phase must be BUSINESS_HOURS or AFTER_HOURS, got {result}"
    )


# Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours
@given(after_hours=_after_hours_flag)
@example(after_hours=True)
@example(after_hours=False)
@settings(max_examples=200)
def test_return_phase_never_routing(after_hours: bool) -> None:
    """ReturnPhase has no Routing member; to_routing is always False.

    **Validates: Requirements 9.8**

    The return phase is NEVER Routing — ReturnPhase only has BUSINESS_HOURS and
    AFTER_HOURS members, and ChangedRequestTransition.to_routing is always False.
    """
    # Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours

    # Structural: ReturnPhase has exactly two members, neither named ROUTING
    all_members = list(ReturnPhase)
    assert len(all_members) == 2, (
        f"Expected exactly 2 ReturnPhase members, got {len(all_members)}: {all_members}"
    )
    assert all(
        m in (ReturnPhase.BUSINESS_HOURS, ReturnPhase.AFTER_HOURS) for m in all_members
    ), f"Unexpected ReturnPhase members: {all_members}"

    # Behavioural: the transition always has to_routing=False
    transition = changed_request_transition(after_hours)
    assert transition.to_routing is False, (
        f"Expected to_routing=False for after_hours={after_hours}, "
        f"got {transition.to_routing}"
    )


# Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours
@given(after_hours=_after_hours_flag)
@example(after_hours=True)
@example(after_hours=False)
@settings(max_examples=200)
def test_changed_request_transition_bundle(after_hours: bool) -> None:
    """changed_request_transition returns a correct ChangedRequestTransition.

    **Validates: Requirements 9.8**

    For any after_hours boolean, the returned transition has:
    - line equal to the verbatim AUTH_CHANGED_REQUEST constant
    - return_phase matching changed_request_return_phase(after_hours)
    - to_routing always False
    """
    # Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours

    transition = changed_request_transition(after_hours)

    # Correct type
    assert isinstance(transition, ChangedRequestTransition), (
        f"Expected ChangedRequestTransition, got {type(transition)}"
    )

    # line matches the AUTH_CHANGED_REQUEST constant
    assert transition.line == AUTH_CHANGED_REQUEST, (
        f"Expected line={AUTH_CHANGED_REQUEST!r}, got {transition.line!r}"
    )

    # return_phase matches the standalone function
    expected_phase = changed_request_return_phase(after_hours)
    assert transition.return_phase is expected_phase, (
        f"Expected return_phase={expected_phase} for after_hours={after_hours}, "
        f"got {transition.return_phase}"
    )

    # to_routing is always False
    assert transition.to_routing is False, (
        f"Expected to_routing=False, got {transition.to_routing}"
    )


# Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours
def test_verbatim_line_matches_appendix_c() -> None:
    """AUTH_CHANGED_REQUEST matches the mandated Appendix C text exactly.

    **Validates: Requirements 9.8**

    The verbatim line spoken on a changed request is exactly:
    "Sure, let me get you to the right place for that."
    """
    # Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours

    expected = "Sure, let me get you to the right place for that."
    assert AUTH_CHANGED_REQUEST == expected, (
        f"Expected AUTH_CHANGED_REQUEST={expected!r}, got {AUTH_CHANGED_REQUEST!r}"
    )
