"""Phone read-back formatting for the SpinSci switchboard (Requirements 5.2, 9.9).

This module owns the switchboard's **phone read-back** formatter and its inverse
digit extractor. Both are pure, side-effect-free functions with no I/O or logging,
so they are directly unit- and property-testable independent of the LLM/TTS/
telephony runtime.

The mandated Appendix C read-back format groups a 10-digit number 3, 3, then 4,
separated by periods (e.g. ``"512.555.1234"``). The periods introduce pauses
between digit groups so TTS reads the number back clearly (Requirement 5.2), which
is the format the Authentication cluster uses when confirming a caller's phone
number (Requirement 9.9).

The formatter and extractor are designed to satisfy the read-back round-trip
(``design.md`` → "Property 17: Phone read-back format round-trips"): extracting the
digits from a formatted 10-digit number recovers the original digits exactly.

Design references:
- ``design.md`` → "Phone read-back uses the mandated 3-3-4 period-grouped format
  (Req 5.2, 9.9)."
- ``design.md`` → Correctness Properties → "Property 17: Phone read-back format
  round-trips".
- ``requirements.md`` → Requirement 5.2 (pauses between digit groups) and
  Requirement 9.9 (3-3-4 period-grouped read-back).
"""

from __future__ import annotations

#: Number of digits in a phone number eligible for read-back formatting.
PHONE_NUMBER_LENGTH: int = 10

#: Digit-group sizes for the mandated read-back format, in order (3, then 3,
#: then 4). Their sum equals :data:`PHONE_NUMBER_LENGTH`.
PHONE_READBACK_GROUPS: tuple[int, ...] = (3, 3, 4)

#: Separator placed between digit groups; the period introduces a TTS pause.
PHONE_READBACK_SEPARATOR: str = "."


def extract_digits(value: str) -> str:
    """Return only the digit characters of ``value``, in order.

    This is the inverse of :func:`format_phone_readback`: given a formatted
    read-back string (``"512.555.1234"``), an arbitrary spoken/typed rendering, or
    any other string, it recovers the underlying digit sequence by discarding every
    non-digit character (periods, spaces, dashes, parentheses, letters, etc.).

    Only the ASCII digits ``0``–``9`` are kept; Unicode decimal characters from
    other scripts are treated as non-digits and dropped, so the result is always a
    plain ASCII digit string.

    Args:
        value: Any string that may contain digits interleaved with other
            characters.

    Returns:
        The concatenation of the ASCII digit characters found in ``value``, in the
        order they appear. Empty when ``value`` contains no digits.
    """
    return "".join(char for char in value if char in "0123456789")


def format_phone_readback(number: str) -> str:
    """Format a 10-digit phone number as the mandated 3-3-4 period-grouped string.

    The digits of ``number`` are grouped 3, 3, then 4 and joined with periods
    (Requirements 5.2, 9.9), e.g. ``"5125551234"`` → ``"512.555.1234"``. Input is
    normalized with :func:`extract_digits` first, so a value that already contains
    separators or other formatting characters is accepted as long as it carries
    exactly :data:`PHONE_NUMBER_LENGTH` digits.

    This is the inverse of :func:`extract_digits` for valid input: for any 10-digit
    sequence, ``extract_digits(format_phone_readback(digits))`` returns the original
    digits (the read-back round-trip, Property 17).

    Args:
        number: A phone number whose digits should be read back. May contain
            non-digit characters (they are ignored) but must contain exactly ten
            digits.

    Returns:
        The digits grouped 3-3-4 and separated by periods.

    Raises:
        ValueError: If ``number`` does not contain exactly
            :data:`PHONE_NUMBER_LENGTH` digits.
    """
    digits = extract_digits(number)
    if len(digits) != PHONE_NUMBER_LENGTH:
        raise ValueError(
            f"Phone read-back requires exactly {PHONE_NUMBER_LENGTH} digits, "
            f"got {len(digits)}: {number!r}"
        )

    groups: list[str] = []
    start = 0
    for size in PHONE_READBACK_GROUPS:
        groups.append(digits[start : start + size])
        start += size

    return PHONE_READBACK_SEPARATOR.join(groups)


__all__ = [
    "PHONE_NUMBER_LENGTH",
    "PHONE_READBACK_GROUPS",
    "PHONE_READBACK_SEPARATOR",
    "extract_digits",
    "format_phone_readback",
]
