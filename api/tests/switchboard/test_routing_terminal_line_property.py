"""Property-based test for terminal-turn line-only (task 11.5).

Covers Property 21 — Terminal turn speaks only the prescribed line
(Requirements 10.4, 10.5, 10.6, 18.2).

On any terminal transfer/hangup turn, the Routing phase speaks ONLY the
prescribed Appendix E line (selected by the ledger `intent` / resolved
destination) and emits no other Switchboard speech. No stall phrases are
permitted on terminal turns (Req 10.6). The line is selected from Appendix E
by the ledger intent (Req 10.5).
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.routing import (
    DESTINATION_TERMINAL_LINES,
    FORBIDDEN_TERMINAL_STALL_PHRASES,
    RouteDestination,
    TerminalKind,
    TerminalTurn,
    find_terminal_stall_violation,
    select_terminal_line,
)
from api.services.switchboard.scripts import (
    E_HANGUP,
    E_TRANSFER_ERROR,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All RouteDestination enum values.
_all_destinations = st.sampled_from(list(RouteDestination))


# ===========================================================================
# Property 21: Terminal turn speaks only the prescribed line
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line
@given(destination=_all_destinations)
@example(destination=RouteDestination.SCHEDULING_NEW_INTAKE)
@example(destination=RouteDestination.SCHEDULING_EXISTING)
@example(destination=RouteDestination.FALLBACK)
@example(destination=RouteDestination.GENERAL)
@settings(max_examples=200)
def test_terminal_line_matches_destination(destination: RouteDestination) -> None:
    """For any RouteDestination, select_terminal_line returns the exact DESTINATION_TERMINAL_LINES entry.

    **Validates: Requirements 10.4, 10.5**

    The terminal transfer line is selected by the resolved destination (i.e. by
    the ledger intent, Req 10.5) and equals exactly the corresponding Appendix E
    constant in DESTINATION_TERMINAL_LINES (Req 10.4).
    """
    # Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line

    result = select_terminal_line(destination)
    expected_line = DESTINATION_TERMINAL_LINES[destination]
    assert result.line == expected_line, (
        f"Expected line for {destination} to be {expected_line!r}, got {result.line!r}"
    )


# Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line
@given(destination=_all_destinations)
@example(destination=RouteDestination.SCHEDULING_NEW_INTAKE)
@example(destination=RouteDestination.FALLBACK)
@example(destination=RouteDestination.PHARMACY)
@settings(max_examples=200)
def test_terminal_line_no_stall_phrases(destination: RouteDestination) -> None:
    """For any RouteDestination, the returned line contains no FORBIDDEN_TERMINAL_STALL_PHRASES.

    **Validates: Requirements 10.6**

    No stall phrases (like "Hang tight.") are permitted on terminal turns
    (Req 10.6). The line must be free of all entries in
    FORBIDDEN_TERMINAL_STALL_PHRASES.
    """
    # Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line

    result = select_terminal_line(destination)
    violation = find_terminal_stall_violation(result.line)
    assert violation is None, (
        f"Terminal line for {destination} has a stall violation: {violation}. "
        f"Line: {result.line!r}"
    )
    # Also verify directly against the tuple for exhaustive coverage
    lowered = result.line.lower()
    for phrase in FORBIDDEN_TERMINAL_STALL_PHRASES:
        assert phrase not in lowered, (
            f"Terminal line for {destination} contains forbidden stall phrase "
            f"{phrase!r}. Line: {result.line!r}"
        )


# Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line
@given(destination=_all_destinations)
@example(destination=RouteDestination.SCHEDULING_NEW_INTAKE)
@example(destination=RouteDestination.BILLING)
@example(destination=RouteDestination.TRIAGE)
@settings(max_examples=200)
def test_terminal_kind_is_transfer(destination: RouteDestination) -> None:
    """For any RouteDestination, the returned kind is TRANSFER.

    **Validates: Requirements 10.4**

    On a normal terminal transfer turn (no transfer_failed, no directory_info_only),
    the TerminalKind is always TRANSFER — the Routing phase transfers the call
    (Req 10.4, GATE-TRANSFER-SPEECH).
    """
    # Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line

    result = select_terminal_line(destination)
    assert result.kind is TerminalKind.TRANSFER, (
        f"Expected kind=TRANSFER for {destination}, got {result.kind}"
    )


# Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line
@given(destination=_all_destinations)
@example(destination=RouteDestination.SCHEDULING_NEW_INTAKE)
@example(destination=RouteDestination.FALLBACK)
@example(destination=RouteDestination.GENERAL)
@settings(max_examples=200)
def test_transfer_failed_returns_error_line(destination: RouteDestination) -> None:
    """When transfer_failed=True, the line is exactly E_TRANSFER_ERROR regardless of destination.

    **Validates: Requirements 10.4, 10.5**

    A failed transfer speaks the mandated transfer-error line (Req 10.10) —
    this takes precedence over the destination's normal line (Property 21).
    """
    # Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line

    result = select_terminal_line(destination, transfer_failed=True)
    assert result.line == E_TRANSFER_ERROR, (
        f"Expected E_TRANSFER_ERROR for transfer_failed=True with {destination}, "
        f"got {result.line!r}"
    )
    assert result.kind is TerminalKind.TRANSFER_ERROR, (
        f"Expected kind=TRANSFER_ERROR for transfer_failed=True, got {result.kind}"
    )


# Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line
@given(destination=_all_destinations)
@example(destination=RouteDestination.SCHEDULING_NEW_INTAKE)
@example(destination=RouteDestination.GENERAL)
@example(destination=RouteDestination.FALLBACK)
@settings(max_examples=200)
def test_directory_info_only_returns_hangup(destination: RouteDestination) -> None:
    """When directory_info_only=True, the line is exactly E_HANGUP and kind is GOODBYE.

    **Validates: Requirements 10.4, 10.5**

    An info-only Directory call ends the call with the goodbye line (Req 10.9)
    instead of a transfer — the destination's normal line is not spoken.
    """
    # Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line

    result = select_terminal_line(destination, directory_info_only=True)
    assert result.line == E_HANGUP, (
        f"Expected E_HANGUP for directory_info_only=True with {destination}, "
        f"got {result.line!r}"
    )
    assert result.kind is TerminalKind.GOODBYE, (
        f"Expected kind=GOODBYE for directory_info_only=True, got {result.kind}"
    )


# Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line
@given(destination=_all_destinations)
@example(destination=RouteDestination.SCHEDULING_NEW_INTAKE)
@example(destination=RouteDestination.BILLING)
@settings(max_examples=200)
def test_terminal_turn_produces_single_line(destination: RouteDestination) -> None:
    """The terminal turn produces exactly ONE line (a single string, not multiple).

    **Validates: Requirements 10.4, 18.2**

    Property 21 states the terminal turn "speaks only the prescribed line" — the
    TerminalTurn.line is a single non-empty string (no embedded newlines forming
    multiple speech segments) and the result is exactly one TerminalTurn instance.
    """
    # Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line

    result = select_terminal_line(destination)

    # The result is a single TerminalTurn
    assert isinstance(result, TerminalTurn), (
        f"Expected a TerminalTurn instance, got {type(result)}"
    )

    # The line is a non-empty string
    assert isinstance(result.line, str), (
        f"Expected line to be a string, got {type(result.line)}"
    )
    assert len(result.line) > 0, "Terminal line must not be empty"

    # No embedded newlines — it's a single line of speech
    assert "\n" not in result.line, (
        f"Terminal line must be a single line (no embedded newlines), "
        f"got: {result.line!r}"
    )
