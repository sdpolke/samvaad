"""Property-based test for lookup-speech prefix rules (task 8.4).

Covers Property 10 — Lookup speech prefix rules
(Requirements 7.2, 7.3, 7.4).

The property verifies that for any lookup, the spoken prefix is empty when it is
the first provider/directory lookup on the turn, "Let me check that for you." for
an FAQ lookup, and "One moment." for any other lookup, and the lookup is invoked
on the same turn.
"""

# Feature: spinsci-switchboard-poc, Property 10: Lookup speech prefix rules

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard import scripts
from api.services.switchboard.business_hours import (
    FIRST_DIRECTORY_LOOKUP_PREFIX,
    LookupSpeechDecision,
    LookupType,
    lookup_speech_prefix,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: any LookupType enum value
_lookup_type = st.sampled_from(list(LookupType))

# Strategy: the boolean flag for first-directory-lookup-on-turn
_is_first_directory = st.booleans()


# ===========================================================================
# Property 10: Lookup speech prefix rules
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 10: Lookup speech prefix rules
@given(is_first=_is_first_directory)
@example(is_first=True)
@example(is_first=False)
@settings(max_examples=200)
def test_property_10_first_directory_lookup_is_silent(is_first: bool) -> None:
    """First provider/directory lookup on a turn is silent (Req 7.2, AC-13).

    **Validates: Requirements 7.2, 7.3, 7.4**

    When lookup_type is PROVIDER_DIRECTORY and is_first_directory_lookup_on_turn
    is True, the prefix must be empty (silent) and invoke_same_turn must be True.
    When is_first is False, the lookup falls through to "One moment." (Req 7.4).
    """
    result = lookup_speech_prefix(LookupType.PROVIDER_DIRECTORY, is_first)

    assert isinstance(result, LookupSpeechDecision)
    assert result.invoke_same_turn is True

    if is_first:
        # Req 7.2: first provider/directory lookup is silent
        assert result.prefix == FIRST_DIRECTORY_LOOKUP_PREFIX
        assert result.prefix == ""
        assert result.is_silent is True
    else:
        # Req 7.4: non-first provider/directory falls through to "One moment."
        assert result.prefix == scripts.BH_OTHER_LOOKUP
        assert result.prefix == "One moment."
        assert result.is_silent is False


# Feature: spinsci-switchboard-poc, Property 10: Lookup speech prefix rules
@given(is_first=_is_first_directory)
@example(is_first=True)
@example(is_first=False)
@settings(max_examples=200)
def test_property_10_faq_lookup_prefix(is_first: bool) -> None:
    """FAQ lookup always gets "Let me check that for you." prefix (Req 7.3).

    **Validates: Requirements 7.2, 7.3, 7.4**

    Regardless of the is_first_directory_lookup_on_turn flag, an FAQ lookup
    always speaks "Let me check that for you." and invokes on the same turn.
    """
    result = lookup_speech_prefix(LookupType.FAQ, is_first)

    assert isinstance(result, LookupSpeechDecision)
    assert result.prefix == scripts.BH_FAQ_LOOKUP
    assert result.prefix == "Let me check that for you."
    assert result.invoke_same_turn is True
    assert result.is_silent is False


# Feature: spinsci-switchboard-poc, Property 10: Lookup speech prefix rules
@given(is_first=_is_first_directory)
@example(is_first=True)
@example(is_first=False)
@settings(max_examples=200)
def test_property_10_other_lookup_prefix(is_first: bool) -> None:
    """OTHER lookup always gets "One moment." prefix (Req 7.4).

    **Validates: Requirements 7.2, 7.3, 7.4**

    Regardless of the is_first_directory_lookup_on_turn flag, an OTHER lookup
    always speaks "One moment." and invokes on the same turn.
    """
    result = lookup_speech_prefix(LookupType.OTHER, is_first)

    assert isinstance(result, LookupSpeechDecision)
    assert result.prefix == scripts.BH_OTHER_LOOKUP
    assert result.prefix == "One moment."
    assert result.invoke_same_turn is True
    assert result.is_silent is False


# Feature: spinsci-switchboard-poc, Property 10: Lookup speech prefix rules
@given(lookup_type=_lookup_type, is_first=_is_first_directory)
@example(lookup_type=LookupType.PROVIDER_DIRECTORY, is_first=True)
@example(lookup_type=LookupType.PROVIDER_DIRECTORY, is_first=False)
@example(lookup_type=LookupType.FAQ, is_first=True)
@example(lookup_type=LookupType.FAQ, is_first=False)
@example(lookup_type=LookupType.OTHER, is_first=True)
@example(lookup_type=LookupType.OTHER, is_first=False)
@settings(max_examples=200)
def test_property_10_all_lookups_invoke_same_turn(
    lookup_type: LookupType, is_first: bool
) -> None:
    """All lookups have invoke_same_turn=True (same-turn contract).

    **Validates: Requirements 7.2, 7.3, 7.4**

    For any combination of lookup_type and is_first_directory_lookup_on_turn,
    the returned decision always carries invoke_same_turn=True, encoding the
    requirement that the lookup is invoked on the same turn the prefix is spoken.
    """
    result = lookup_speech_prefix(lookup_type, is_first)

    assert isinstance(result, LookupSpeechDecision)
    assert result.invoke_same_turn is True, (
        f"VIOLATION: invoke_same_turn must always be True.\n"
        f"lookup_type={lookup_type.value}, is_first={is_first}\n"
        f"Got invoke_same_turn={result.invoke_same_turn}"
    )


# Feature: spinsci-switchboard-poc, Property 10: Lookup speech prefix rules
@given(lookup_type=_lookup_type, is_first=_is_first_directory)
@example(lookup_type=LookupType.PROVIDER_DIRECTORY, is_first=True)
@example(lookup_type=LookupType.FAQ, is_first=False)
@example(lookup_type=LookupType.OTHER, is_first=False)
@settings(max_examples=200)
def test_property_10_prefix_matches_expected_for_all_inputs(
    lookup_type: LookupType, is_first: bool
) -> None:
    """Comprehensive prefix rule: correct prefix for every input combination.

    **Validates: Requirements 7.2, 7.3, 7.4**

    For any lookup_type and is_first_directory_lookup_on_turn combination, the
    prefix is exactly one of:
    - "" (empty) for first provider/directory lookup (Req 7.2)
    - "Let me check that for you." for FAQ (Req 7.3)
    - "One moment." for everything else (Req 7.4)
    """
    result = lookup_speech_prefix(lookup_type, is_first)

    if lookup_type is LookupType.PROVIDER_DIRECTORY and is_first:
        expected_prefix = ""
    elif lookup_type is LookupType.FAQ:
        expected_prefix = "Let me check that for you."
    else:
        expected_prefix = "One moment."

    assert result.prefix == expected_prefix, (
        f"Prefix mismatch.\n"
        f"lookup_type={lookup_type.value}, is_first={is_first}\n"
        f"Expected: {expected_prefix!r}\n"
        f"Got: {result.prefix!r}"
    )
    assert result.invoke_same_turn is True
