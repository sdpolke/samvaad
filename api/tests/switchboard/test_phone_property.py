"""Property-based test for phone read-back round-trip (task 5.2).

Covers Property 17 — Phone read-back format round-trips (Req 5.2, 9.9).

The property verifies that for any 10-digit phone number,
``extract_digits(format_phone_readback(digits))`` recovers the original digits
exactly. Generators produce pure 10-digit strings, numbers with existing formatting
(dashes, spaces, parens, dots), and edge cases like all-zeros/all-nines.
"""

# Feature: spinsci-switchboard-poc, Property 17: Phone read-back format round-trips

from __future__ import annotations

import re

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.phone import (
    PHONE_NUMBER_LENGTH,
    PHONE_READBACK_GROUPS,
    PHONE_READBACK_SEPARATOR,
    extract_digits,
    format_phone_readback,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Pure 10-digit strings (e.g. "5125551234")
_pure_digits = st.text(
    alphabet="0123456789",
    min_size=PHONE_NUMBER_LENGTH,
    max_size=PHONE_NUMBER_LENGTH,
)

# Phone numbers with common US formatting characters injected
_formatted_phone = _pure_digits.map(
    lambda d: d  # base digits; the flatmap below adds formatting
).flatmap(
    lambda digits: st.sampled_from([
        # Plain
        digits,
        # Dashes: 512-555-1234
        f"{digits[:3]}-{digits[3:6]}-{digits[6:]}",
        # Dots: 512.555.1234
        f"{digits[:3]}.{digits[3:6]}.{digits[6:]}",
        # Parens + space: (512) 555-1234
        f"({digits[:3]}) {digits[3:6]}-{digits[6:]}",
        # Spaces: 512 555 1234
        f"{digits[:3]} {digits[3:6]} {digits[6:]}",
        # Mixed: (512) 555.1234
        f"({digits[:3]}) {digits[3:6]}.{digits[6:]}",
        # With country prefix text: +1 512-555-1234 → more than 10 digits,
        # so skip this variant (format_phone_readback would reject it)
    ])
)

# Strategy combining pure and formatted inputs
_phone_input = st.one_of(_pure_digits, _formatted_phone)

# The expected output pattern: exactly 3 digits, dot, 3 digits, dot, 4 digits
_READBACK_PATTERN = re.compile(r"^\d{3}\.\d{3}\.\d{4}$")


# ===========================================================================
# Property 17: Phone read-back format round-trips
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 17: Phone read-back format round-trips
@given(phone=_phone_input)
@example(phone="0000000000")  # All zeros
@example(phone="9999999999")  # All nines
@example(phone="(000) 000-0000")  # Formatted all-zeros
@example(phone="123.456.7890")  # Already dot-formatted
@settings(max_examples=200)
def test_property_17_round_trip(phone: str) -> None:
    """extract_digits(format_phone_readback(phone)) == extract_digits(phone).

    **Validates: Requirements 5.2, 9.9**

    For any 10-digit phone number (possibly with formatting characters), formatting
    it as the mandated 3-3-4 period-grouped read-back string and then extracting the
    digits recovers the original digit sequence exactly.
    """
    original_digits = extract_digits(phone)
    formatted = format_phone_readback(phone)
    recovered = extract_digits(formatted)

    assert recovered == original_digits, (
        f"Round-trip failed.\n"
        f"Input:     {phone!r}\n"
        f"Digits:    {original_digits!r}\n"
        f"Formatted: {formatted!r}\n"
        f"Recovered: {recovered!r}"
    )


# Feature: spinsci-switchboard-poc, Property 17: Phone read-back format round-trips
@given(phone=_phone_input)
@example(phone="5125551234")
@example(phone="0000000000")
@example(phone="9999999999")
@settings(max_examples=200)
def test_property_17_format_matches_334_pattern(phone: str) -> None:
    """format_phone_readback output matches the 3.3.4 period-separated pattern.

    **Validates: Requirements 5.2, 9.9**

    The formatted output must always be exactly 12 characters: 3 digits, a period,
    3 digits, a period, and 4 digits — matching the mandated read-back format.
    """
    formatted = format_phone_readback(phone)

    assert _READBACK_PATTERN.match(formatted), (
        f"Formatted output does not match 3.3.4 pattern.\n"
        f"Input:     {phone!r}\n"
        f"Formatted: {formatted!r}\n"
        f"Expected pattern: ddd.ddd.dddd"
    )

    # Verify group sizes match PHONE_READBACK_GROUPS constant
    groups = formatted.split(PHONE_READBACK_SEPARATOR)
    assert len(groups) == len(PHONE_READBACK_GROUPS), (
        f"Expected {len(PHONE_READBACK_GROUPS)} groups, got {len(groups)}"
    )
    for group, expected_size in zip(groups, PHONE_READBACK_GROUPS):
        assert len(group) == expected_size, (
            f"Group {group!r} has length {len(group)}, expected {expected_size}"
        )


# Feature: spinsci-switchboard-poc, Property 17: Phone read-back format round-trips
@given(
    digits=st.text(
        alphabet="0123456789",
        min_size=PHONE_NUMBER_LENGTH,
        max_size=PHONE_NUMBER_LENGTH,
    )
)
@example(digits="5125551234")
@settings(max_examples=200)
def test_property_17_format_separator_is_period(digits: str) -> None:
    """The separator between digit groups is always a period (Req 5.2 pause).

    **Validates: Requirements 5.2, 9.9**

    Requirement 5.2 mandates periods to introduce pauses between digit groups.
    The output must use periods (and only periods) as separators.
    """
    formatted = format_phone_readback(digits)

    # Only digits and periods in the output
    allowed_chars = set("0123456789" + PHONE_READBACK_SEPARATOR)
    assert set(formatted) <= allowed_chars, (
        f"Unexpected characters in formatted output.\n"
        f"Formatted: {formatted!r}\n"
        f"Unexpected: {set(formatted) - allowed_chars}"
    )

    # Exactly (len(PHONE_READBACK_GROUPS) - 1) separators
    expected_separator_count = len(PHONE_READBACK_GROUPS) - 1
    actual_separator_count = formatted.count(PHONE_READBACK_SEPARATOR)
    assert actual_separator_count == expected_separator_count, (
        f"Expected {expected_separator_count} separators, "
        f"got {actual_separator_count} in {formatted!r}"
    )


# Feature: spinsci-switchboard-poc, Property 17: Phone read-back format round-trips
@given(
    bad_input=st.one_of(
        # Too few digits (0-9 digits)
        st.text(alphabet="0123456789", min_size=0, max_size=9),
        # Too many digits (11-20 digits)
        st.text(alphabet="0123456789", min_size=11, max_size=20),
    )
)
@example(bad_input="")  # Empty
@example(bad_input="123456789")  # 9 digits
@example(bad_input="12345678901")  # 11 digits
@settings(max_examples=200)
def test_property_17_rejects_non_10_digit_inputs(bad_input: str) -> None:
    """format_phone_readback raises ValueError for non-10-digit inputs.

    **Validates: Requirements 5.2, 9.9**

    The formatter must reject inputs that do not contain exactly 10 digits,
    ensuring only valid phone numbers produce a read-back string.
    """
    with pytest.raises(ValueError):
        format_phone_readback(bad_input)
