"""Property-based test for ANI non-repeat in Authentication (task 9.4).

Covers Property 14 — ANI lookup is not repeated in Authentication
(Requirement 9.6).

For any ledger with ``greeting_ani_lookup_done`` set to true, the Authentication
phase reuses the Greeting ANI result and does NOT repeat the ANI lookup. When
``greeting_ani_lookup_done`` is false, the Authentication phase MUST perform the
lookup.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.auth import (
    AniLookupDecision,
    AuthStep,
    ani_lookup_decision,
    next_auth_step,
    should_perform_ani_lookup,
    should_reuse_ani_lookup,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: Boolean strategy for the greeting_ani_lookup_done flag.
_greeting_ani_lookup_done = st.booleans()

#: All AuthStep values for flow traversal tests.
_all_auth_steps = st.sampled_from(list(AuthStep))


# ===========================================================================
# Property 14: ANI lookup is not repeated in Authentication
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication
@given(greeting_ani_lookup_done=st.just(True))
@example(greeting_ani_lookup_done=True)
@settings(max_examples=200)
def test_ani_lookup_decision_reuses_when_done(
    greeting_ani_lookup_done: bool,
) -> None:
    """ani_lookup_decision returns REUSE when greeting_ani_lookup_done is True.

    **Validates: Requirements 9.6**

    When the Greeting phase already completed the ANI patient lookup
    (greeting_ani_lookup_done=True), Authentication reuses that result and
    does NOT repeat the lookup.
    """
    # Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication

    decision = ani_lookup_decision(greeting_ani_lookup_done)
    assert decision is AniLookupDecision.REUSE, (
        f"Expected REUSE when greeting_ani_lookup_done=True, got {decision}"
    )


# Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication
@given(greeting_ani_lookup_done=st.just(False))
@example(greeting_ani_lookup_done=False)
@settings(max_examples=200)
def test_ani_lookup_decision_performs_when_not_done(
    greeting_ani_lookup_done: bool,
) -> None:
    """ani_lookup_decision returns PERFORM when greeting_ani_lookup_done is False.

    **Validates: Requirements 9.6**

    When no prior ANI lookup was completed in Greeting
    (greeting_ani_lookup_done=False), Authentication MUST perform the lookup.
    """
    # Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication

    decision = ani_lookup_decision(greeting_ani_lookup_done)
    assert decision is AniLookupDecision.PERFORM, (
        f"Expected PERFORM when greeting_ani_lookup_done=False, got {decision}"
    )


# Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication
@given(greeting_ani_lookup_done=_greeting_ani_lookup_done)
@example(greeting_ani_lookup_done=True)
@example(greeting_ani_lookup_done=False)
@settings(max_examples=200)
def test_should_reuse_and_perform_are_mutually_exclusive(
    greeting_ani_lookup_done: bool,
) -> None:
    """should_reuse_ani_lookup and should_perform_ani_lookup are mutually exclusive.

    **Validates: Requirements 9.6**

    For any boolean value of greeting_ani_lookup_done, exactly one of
    should_reuse_ani_lookup and should_perform_ani_lookup is True — they are
    complementary predicates. When done=True → reuse=True, perform=False.
    When done=False → reuse=False, perform=True.
    """
    # Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication

    reuse = should_reuse_ani_lookup(greeting_ani_lookup_done)
    perform = should_perform_ani_lookup(greeting_ani_lookup_done)

    # Exactly one must be True
    assert reuse != perform, (
        f"Expected mutual exclusivity: reuse={reuse}, perform={perform} "
        f"for greeting_ani_lookup_done={greeting_ani_lookup_done}"
    )

    # Direction check
    if greeting_ani_lookup_done:
        assert reuse is True and perform is False, (
            f"When done=True, expected reuse=True/perform=False, "
            f"got reuse={reuse}/perform={perform}"
        )
    else:
        assert reuse is False and perform is True, (
            f"When done=False, expected reuse=False/perform=True, "
            f"got reuse={reuse}/perform={perform}"
        )


# Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication
@given(greeting_ani_lookup_done=st.just(True))
@example(greeting_ani_lookup_done=True)
@settings(max_examples=200)
def test_next_auth_step_skips_patient_lookup_when_ani_done(
    greeting_ani_lookup_done: bool,
) -> None:
    """next_auth_step skips PATIENT_LOOKUP when greeting_ani_lookup_done=True.

    **Validates: Requirements 9.6**

    The flow-level invariant: when greeting_ani_lookup_done is True,
    next_auth_step(READ_BACK, ...) advances straight to DOB, skipping
    PATIENT_LOOKUP entirely. This ensures the ANI lookup is not repeated at
    the flow level.
    """
    # Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication

    result = next_auth_step(AuthStep.READ_BACK, greeting_ani_lookup_done)
    assert result is AuthStep.DOB, (
        f"Expected READ_BACK → DOB (skip PATIENT_LOOKUP) when "
        f"greeting_ani_lookup_done=True, got {result}"
    )


# Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication
@given(greeting_ani_lookup_done=st.just(False))
@example(greeting_ani_lookup_done=False)
@settings(max_examples=200)
def test_next_auth_step_includes_patient_lookup_when_not_done(
    greeting_ani_lookup_done: bool,
) -> None:
    """next_auth_step includes PATIENT_LOOKUP when greeting_ani_lookup_done=False.

    **Validates: Requirements 9.6**

    When greeting_ani_lookup_done is False, next_auth_step(READ_BACK, ...)
    advances to PATIENT_LOOKUP (the lookup IS performed).
    """
    # Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication

    result = next_auth_step(AuthStep.READ_BACK, greeting_ani_lookup_done)
    assert result is AuthStep.PATIENT_LOOKUP, (
        f"Expected READ_BACK → PATIENT_LOOKUP when "
        f"greeting_ani_lookup_done=False, got {result}"
    )


# Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication
@given(greeting_ani_lookup_done=_greeting_ani_lookup_done)
@example(greeting_ani_lookup_done=True)
@example(greeting_ani_lookup_done=False)
@settings(max_examples=200)
def test_ani_decision_consistent_with_flow_step(
    greeting_ani_lookup_done: bool,
) -> None:
    """ani_lookup_decision is consistent with the flow step advancement.

    **Validates: Requirements 9.6**

    When ani_lookup_decision returns REUSE, the flow skips PATIENT_LOOKUP
    (next_auth_step from READ_BACK goes to DOB). When it returns PERFORM,
    the flow includes PATIENT_LOOKUP (next_auth_step from READ_BACK goes to
    PATIENT_LOOKUP). The decision function and the flow function agree.
    """
    # Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication

    decision = ani_lookup_decision(greeting_ani_lookup_done)
    next_step = next_auth_step(AuthStep.READ_BACK, greeting_ani_lookup_done)

    if decision is AniLookupDecision.REUSE:
        assert next_step is AuthStep.DOB, (
            f"Decision=REUSE but flow did not skip PATIENT_LOOKUP: "
            f"next_step={next_step}"
        )
    else:
        assert next_step is AuthStep.PATIENT_LOOKUP, (
            f"Decision=PERFORM but flow skipped PATIENT_LOOKUP: "
            f"next_step={next_step}"
        )
