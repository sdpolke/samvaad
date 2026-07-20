"""Property-based test for zero-speech resolution (task 11.2).

Covers Property 19 — Routing resolution emits zero speech (Requirement 10.1).

While resolving a destination in the Routing phase, zero speech tokens are emitted —
no filler, acknowledgment, or stall phrases — on every turn up to (but not including)
the terminal transfer/hangup turn.
"""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.routing import (
    FORBIDDEN_RESOLUTION_PHRASES,
    RESOLUTION_SPEECH,
    ResolutionSpeechError,
    assert_zero_speech,
    emits_zero_speech,
    find_resolution_speech_violation,
    is_zero_speech,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Whitespace-only strings (zero-speech values that are not None)
_whitespace_only = st.text(
    alphabet=st.sampled_from(" \t\n\r\v\f"),
    min_size=0,
    max_size=20,
)

# Non-whitespace strings (always violate zero-speech)
_non_whitespace = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

# Optional[str] that is always zero-speech (None or whitespace-only)
_zero_speech_value = st.one_of(st.none(), _whitespace_only)

# A list of zero-speech values
_zero_speech_list = st.lists(_zero_speech_value, min_size=0, max_size=15)

# A list that contains at least one non-zero-speech value
_list_with_violation = st.tuples(
    st.lists(_zero_speech_value, min_size=0, max_size=7),
    _non_whitespace,
    st.lists(_zero_speech_value, min_size=0, max_size=7),
).map(lambda t: t[0] + [t[1]] + t[2])


# ===========================================================================
# Property 19: Routing resolution emits zero speech
# ===========================================================================


# ---------------------------------------------------------------------------
# Sub-property 1: None and whitespace-only strings are always zero speech
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(speech=_zero_speech_value)
@example(speech=None)
@example(speech="")
@example(speech="   ")
@example(speech="\t\n")
@settings(max_examples=200)
def test_none_and_whitespace_are_zero_speech(speech: str | None) -> None:
    """None and whitespace-only strings are always zero speech.

    **Validates: Requirements 10.1**

    The invariant treats None and any whitespace-only string as emitting zero
    speech tokens — these never violate the zero-speech contract.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    assert is_zero_speech(speech) is True


# ---------------------------------------------------------------------------
# Sub-property 2: Any non-whitespace string is NOT zero speech
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(speech=_non_whitespace)
@example(speech="hello")
@example(speech="one moment")
@example(speech="let me check")
@example(speech="X")
@settings(max_examples=200)
def test_non_whitespace_is_not_zero_speech(speech: str) -> None:
    """Any non-whitespace string violates the zero-speech invariant.

    **Validates: Requirements 10.1**

    Any string containing a non-whitespace character represents speech emitted
    during resolution — this always violates the Routing phase zero-speech
    contract (Req 10.1).
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    assert is_zero_speech(speech) is False


# ---------------------------------------------------------------------------
# Sub-property 3: emits_zero_speech returns True iff ALL items are zero speech
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(tokens=_zero_speech_list)
@example(tokens=[])
@example(tokens=[None])
@example(tokens=["", None, "   ", "\t"])
@settings(max_examples=200)
def test_emits_zero_speech_all_silent(tokens: list[str | None]) -> None:
    """emits_zero_speech returns True when ALL items in a sequence are zero speech.

    **Validates: Requirements 10.1**

    Every resolution turn in the sequence is silent, so the overall invariant holds.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    assert emits_zero_speech(tokens) is True


# ---------------------------------------------------------------------------
# Sub-property 4: emits_zero_speech returns False if ANY item is non-zero speech
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(tokens=_list_with_violation)
@example(tokens=["hang tight"])
@example(tokens=[None, "", "one moment", None])
@example(tokens=["X"])
@settings(max_examples=200)
def test_emits_zero_speech_any_violation(tokens: list[str | None]) -> None:
    """emits_zero_speech returns False if ANY item in a sequence is non-zero speech.

    **Validates: Requirements 10.1**

    A single resolution turn that emits speech breaks the overall invariant.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    assert emits_zero_speech(tokens) is False


# ---------------------------------------------------------------------------
# Sub-property 5: find_resolution_speech_violation returns None for zero-speech
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(speech=_zero_speech_value)
@example(speech=None)
@example(speech="")
@example(speech="   ")
@settings(max_examples=200)
def test_find_violation_returns_none_for_zero_speech(speech: str | None) -> None:
    """find_resolution_speech_violation returns None for zero-speech inputs.

    **Validates: Requirements 10.1**

    When a resolution turn emits zero speech, there is no violation to report.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    assert find_resolution_speech_violation(speech) is None


# ---------------------------------------------------------------------------
# Sub-property 6: find_resolution_speech_violation returns non-None description
# for non-zero-speech inputs and names FORBIDDEN_RESOLUTION_PHRASES
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(speech=_non_whitespace)
@example(speech="hello world")
@example(speech="random text")
@settings(max_examples=200)
def test_find_violation_returns_description_for_non_zero_speech(
    speech: str,
) -> None:
    """find_resolution_speech_violation returns a non-None description for non-zero-speech.

    **Validates: Requirements 10.1**

    When speech would be emitted, the function always returns a descriptive string
    explaining the violation.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    result = find_resolution_speech_violation(speech)
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(phrase=st.sampled_from(FORBIDDEN_RESOLUTION_PHRASES))
@settings(max_examples=200)
def test_find_violation_names_forbidden_phrase(phrase: str) -> None:
    """find_resolution_speech_violation specifically names FORBIDDEN_RESOLUTION_PHRASES.

    **Validates: Requirements 10.1**

    When a recognizable stall/filler phrase is present, the violation description
    explicitly names the offending phrase.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    result = find_resolution_speech_violation(phrase)
    assert result is not None
    assert phrase in result


# ---------------------------------------------------------------------------
# Sub-property 7: assert_zero_speech returns input for zero-speech,
# raises ResolutionSpeechError for non-zero
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(speech=_zero_speech_value)
@example(speech=None)
@example(speech="")
@example(speech="   ")
@settings(max_examples=200)
def test_assert_zero_speech_returns_input_for_silent(speech: str | None) -> None:
    """assert_zero_speech returns the input unchanged for zero-speech.

    **Validates: Requirements 10.1**

    When the resolution turn is silent, the guard returns the speech value as-is
    so it can be used inline.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    assert assert_zero_speech(speech) is speech


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
@given(speech=_non_whitespace)
@example(speech="hang tight")
@example(speech="one moment please")
@example(speech="X")
@settings(max_examples=200)
def test_assert_zero_speech_raises_for_non_silent(speech: str) -> None:
    """assert_zero_speech raises ResolutionSpeechError for non-zero-speech.

    **Validates: Requirements 10.1**

    When the resolution turn would emit speech, the guard raises
    ResolutionSpeechError to prevent the violation.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    with pytest.raises(ResolutionSpeechError):
        assert_zero_speech(speech)


# ---------------------------------------------------------------------------
# Sub-property 8: RESOLUTION_SPEECH constant itself passes is_zero_speech
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech
def test_resolution_speech_constant_is_zero_speech() -> None:
    """RESOLUTION_SPEECH constant itself passes is_zero_speech.

    **Validates: Requirements 10.1**

    The module's mandated constant for resolution turns must itself be zero-speech,
    confirming that wiring code that uses RESOLUTION_SPEECH is silent by construction.
    """
    # Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech

    assert is_zero_speech(RESOLUTION_SPEECH) is True
    assert find_resolution_speech_violation(RESOLUTION_SPEECH) is None
    assert assert_zero_speech(RESOLUTION_SPEECH) is RESOLUTION_SPEECH
