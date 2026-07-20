"""Property-based test for greeting script selection (task 6.3).

Covers Property 7 — Greeting script selection (Req 6.4).

For any (after_hours, greeting_ani_match_count) pair, select_greeting returns
the Appendix C script mandated for that combination, and treats the greeting
as personalized exactly when greeting_ani_match_count == 1.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard import scripts
from api.services.switchboard.greeting import (
    PERSONALIZED_MATCH_COUNT,
    is_personalized,
    select_greeting,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Match counts covering: 0 (no match), 1 (personalized), >1 (ambiguous)
_match_counts = st.one_of(
    st.just(0),  # No match
    st.just(1),  # Exactly one match (personalized)
    st.integers(min_value=2, max_value=1000),  # Multiple matches (not personalized)
)

_after_hours = st.booleans()


# ===========================================================================
# Property 7: Greeting script selection
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 7: Greeting script selection
@given(after_hours=_after_hours, count=_match_counts)
@example(after_hours=False, count=0)   # In hours, no match → standard
@example(after_hours=False, count=1)   # In hours, personalized → Script 2′
@example(after_hours=False, count=5)   # In hours, ambiguous → standard
@example(after_hours=True, count=0)    # After hours, no match → Script 3′
@example(after_hours=True, count=1)    # After hours, personalized → Path B
@example(after_hours=True, count=3)    # After hours, ambiguous → Script 3′
@settings(max_examples=200)
def test_property_7_select_greeting_returns_correct_script(
    after_hours: bool, count: int
) -> None:
    """select_greeting returns the Appendix C script mandated for the combination.

    **Validates: Requirements 6.4**

    Mapping:
    - after_hours=False, personalized (count==1) → GREETING_SCRIPT_2_PRIME_PERSONALIZED
    - after_hours=False, not personalized         → GREETING_SCRIPT_4_STANDARD_IN_HOURS
    - after_hours=True,  personalized (count==1) → GREETING_PATH_B
    - after_hours=True,  not personalized         → GREETING_SCRIPT_3_PRIME_AFTER_HOURS
    """
    # Feature: spinsci-switchboard-poc, Property 7: Greeting script selection
    result = select_greeting(after_hours, count)

    personalized = count == PERSONALIZED_MATCH_COUNT  # count == 1

    if not after_hours and personalized:
        assert result == scripts.GREETING_SCRIPT_2_PRIME_PERSONALIZED
    elif not after_hours and not personalized:
        assert result == scripts.GREETING_SCRIPT_4_STANDARD_IN_HOURS
    elif after_hours and personalized:
        assert result == scripts.GREETING_PATH_B
    else:  # after_hours and not personalized
        assert result == scripts.GREETING_SCRIPT_3_PRIME_AFTER_HOURS


# Feature: spinsci-switchboard-poc, Property 7: Greeting script selection
@given(count=_match_counts)
@example(count=0)   # Not personalized
@example(count=1)   # Personalized boundary
@example(count=2)   # Just above personalized
@settings(max_examples=200)
def test_property_7_is_personalized_true_only_when_count_is_one(
    count: int,
) -> None:
    """is_personalized returns True exactly when greeting_ani_match_count == 1.

    **Validates: Requirements 6.4**

    A count of 0 (no match / failed / timed-out lookup) and any count > 1
    (ambiguous multi-match) are both non-personalized. Only count == 1 is
    personalized.
    """
    # Feature: spinsci-switchboard-poc, Property 7: Greeting script selection
    result = is_personalized(count)

    if count == 1:
        assert result is True
    else:
        assert result is False


# Feature: spinsci-switchboard-poc, Property 7: Greeting script selection
@given(after_hours=_after_hours, count=_match_counts)
@example(after_hours=False, count=1)
@example(after_hours=True, count=1)
@example(after_hours=False, count=0)
@example(after_hours=True, count=0)
@settings(max_examples=200)
def test_property_7_personalized_iff_count_equals_one(
    after_hours: bool, count: int
) -> None:
    """The greeting is personalized exactly when greeting_ani_match_count == 1.

    **Validates: Requirements 6.4**

    Regardless of after_hours, the personalization decision is driven solely
    by the match count. The returned script is a personalized variant iff
    count == 1.
    """
    # Feature: spinsci-switchboard-poc, Property 7: Greeting script selection
    result = select_greeting(after_hours, count)

    personalized_scripts = {
        scripts.GREETING_SCRIPT_2_PRIME_PERSONALIZED,
        scripts.GREETING_PATH_B,
    }

    if count == 1:
        assert result in personalized_scripts, (
            f"Expected a personalized script for count=1, got: {result!r}"
        )
    else:
        assert result not in personalized_scripts, (
            f"Expected a non-personalized script for count={count}, got: {result!r}"
        )
