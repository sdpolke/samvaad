"""Property-based test for DOB-determined verification (task 9.7).

Covers Property 18 — DOB-match determines verification
(Requirement 9.11).

For any provided DOB and DOB on file, `patient_verified_from_dob(dob_matches(provided, on_file))`
returns "Success" exactly when the provided DOB equals the DOB on file, and "Fail" otherwise.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.auth import (
    PATIENT_VERIFIED_FAIL,
    PATIENT_VERIFIED_SUCCESS,
    dob_matches,
    patient_verified_from_dob,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: Non-empty text strategy for DOB strings (at least one non-whitespace char).
_nonempty_dob = st.text(min_size=1).filter(lambda s: s.strip() != "")

#: Values that are falsy or None — these trigger the early-return False path.
#: Note: whitespace-only strings are truthy in Python and the implementation
#: strips them before comparing, so they are NOT blank in this context.
_blank_dob = st.one_of(
    st.just(""),
    st.just(None),
)

#: Whitespace padding strategy for wrapping around DOB values.
_whitespace_padding = st.text(alphabet=" \t\n\r", min_size=0, max_size=5)


# ===========================================================================
# Property 18: DOB-match determines verification
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification
@given(dob=_nonempty_dob)
@example(dob="1990-01-01")
@settings(max_examples=200)
def test_dob_matches_returns_true_for_equal_dobs(dob: str) -> None:
    """dob_matches returns True when both DOBs are non-empty and equal.

    **Validates: Requirements 9.11**

    For any non-empty DOB string, dob_matches(dob, dob) must be True — the
    same value always matches itself.
    """
    # Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification

    assert dob_matches(dob, dob) is True, (
        f"Expected dob_matches({dob!r}, {dob!r}) to be True"
    )


# Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification
@given(provided=_nonempty_dob, on_file=_nonempty_dob)
@example(provided="1990-01-01", on_file="2000-12-31")
@settings(max_examples=200)
def test_dob_matches_returns_false_for_different_dobs(
    provided: str, on_file: str
) -> None:
    """dob_matches returns False when the DOBs are different (after strip).

    **Validates: Requirements 9.11**

    For any two non-empty DOB strings whose stripped forms differ,
    dob_matches must return False.
    """
    # Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification

    from hypothesis import assume

    assume(provided.strip() != on_file.strip())

    assert dob_matches(provided, on_file) is False, (
        f"Expected dob_matches({provided!r}, {on_file!r}) to be False"
    )


# Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification
@given(blank=_blank_dob, other=st.one_of(_nonempty_dob, _blank_dob, st.none()))
@example(blank=None, other="1990-01-01")
@example(blank="", other="1990-01-01")
@example(blank=None, other=None)
@settings(max_examples=200)
def test_dob_matches_returns_false_when_either_blank_or_none(
    blank: str | None, other: str | None
) -> None:
    """dob_matches returns False when either DOB is None or blank.

    **Validates: Requirements 9.11**

    A None/blank on either side means there is nothing to verify against,
    so dob_matches must return False regardless of the other value.
    """
    # Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification

    # blank as provided
    assert dob_matches(blank, other) is False, (
        f"Expected dob_matches({blank!r}, {other!r}) to be False (blank provided)"
    )
    # blank as on_file
    assert dob_matches(other, blank) is False, (
        f"Expected dob_matches({other!r}, {blank!r}) to be False (blank on_file)"
    )


# Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification
@given(dob_match=st.just(True))
@example(dob_match=True)
@settings(max_examples=200)
def test_patient_verified_from_dob_returns_success_on_match(
    dob_match: bool,
) -> None:
    """patient_verified_from_dob(True) returns "Success".

    **Validates: Requirements 9.11**

    When the DOB matches, the identity validation sets patient_verified to
    Success.
    """
    # Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification

    result = patient_verified_from_dob(dob_match)
    assert result == PATIENT_VERIFIED_SUCCESS, (
        f"Expected 'Success' for dob_match=True, got {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification
@given(dob_match=st.just(False))
@example(dob_match=False)
@settings(max_examples=200)
def test_patient_verified_from_dob_returns_fail_on_no_match(
    dob_match: bool,
) -> None:
    """patient_verified_from_dob(False) returns "Fail".

    **Validates: Requirements 9.11**

    When the DOB does not match, the identity validation sets patient_verified
    to Fail.
    """
    # Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification

    result = patient_verified_from_dob(dob_match)
    assert result == PATIENT_VERIFIED_FAIL, (
        f"Expected 'Fail' for dob_match=False, got {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification
@given(provided=st.one_of(_nonempty_dob, _blank_dob, st.none()),
       on_file=st.one_of(_nonempty_dob, _blank_dob, st.none()))
@example(provided="1990-01-01", on_file="1990-01-01")
@example(provided="1990-01-01", on_file="2000-12-31")
@example(provided=None, on_file="1990-01-01")
@example(provided="", on_file="1990-01-01")
@settings(max_examples=200)
def test_composed_dob_verification_property(
    provided: str | None, on_file: str | None
) -> None:
    """patient_verified_from_dob(dob_matches(provided, on_file)) returns "Success" iff DOBs match.

    **Validates: Requirements 9.11**

    The composed property: for any provided/on_file pair,
    patient_verified_from_dob(dob_matches(provided, on_file)) returns "Success"
    exactly when the provided DOB equals the DOB on file (both non-empty, equal
    after strip), and "Fail" otherwise.
    """
    # Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification

    match = dob_matches(provided, on_file)
    result = patient_verified_from_dob(match)

    # Determine expected outcome independently — mirror the implementation logic:
    # The implementation checks `if not provided_dob or not dob_on_file` which catches
    # None and empty string (falsy). Whitespace-only strings are truthy and proceed to
    # the strip-and-compare step.
    both_present = bool(provided) and bool(on_file)
    expected_match = both_present and (provided.strip() == on_file.strip())

    if expected_match:
        assert result == PATIENT_VERIFIED_SUCCESS, (
            f"Expected 'Success' for matching DOBs {provided!r}=={on_file!r}, got {result!r}"
        )
    else:
        assert result == PATIENT_VERIFIED_FAIL, (
            f"Expected 'Fail' for non-matching DOBs {provided!r}!={on_file!r}, got {result!r}"
        )


# Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification
@given(dob=_nonempty_dob, left_pad=_whitespace_padding, right_pad=_whitespace_padding)
@example(dob="1990-01-01", left_pad="  ", right_pad="\t")
@settings(max_examples=200)
def test_whitespace_tolerance_does_not_change_match(
    dob: str, left_pad: str, right_pad: str
) -> None:
    """Whitespace padding does not change the match result.

    **Validates: Requirements 9.11**

    Padding a DOB with leading/trailing whitespace should still match the
    unpadded version — dob_matches is whitespace-tolerant.
    """
    # Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification

    padded = left_pad + dob + right_pad

    # Padded vs unpadded should match (since strip makes them equal)
    assert dob_matches(padded, dob) is True, (
        f"Expected dob_matches({padded!r}, {dob!r}) to be True (whitespace tolerance)"
    )
    assert dob_matches(dob, padded) is True, (
        f"Expected dob_matches({dob!r}, {padded!r}) to be True (whitespace tolerance)"
    )
    # Both padded should also match
    assert dob_matches(padded, padded) is True, (
        f"Expected dob_matches({padded!r}, {padded!r}) to be True (both padded)"
    )
