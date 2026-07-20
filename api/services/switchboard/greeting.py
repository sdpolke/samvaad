"""Greeting-phase pure decision logic for the SpinSci switchboard (Requirement 6).

This module owns the deterministic, side-effect-free decision logic of the
Greeting phase: which mandated Appendix C greeting script to speak, whether the
caller has said enough to hand off, the turn-1 ANI-lookup post-state, and the
Path E "not understood" retry state machine. None of these touch the LLM, TTS, or
telephony — they operate purely on their inputs and the Call State Ledger — so
they are directly unit- and property-testable and are wired into the Greeting
node cluster by a later graph-builder task.

All caller-facing wording is reused **verbatim** from
:mod:`api.services.switchboard.scripts` (Appendix C). This module never
re-authors any caller-facing text; it only *selects* which mandated line applies.

Design references:
- ``design.md`` → "Greeting cluster (Req 6)" and Correctness Properties 6, 7, 8, 9
- ``requirements.md`` → Requirement 6 (6.1-6.4 turn-1 post-state, 6.4/6.5 script
  selection, 6.7/6.8 ready-to-hand-off, 6.9-6.11 Path E retry)

Requirements: 6.1, 6.2, 6.3, 6.4, 6.7, 6.9, 6.10, 6.11.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from loguru import logger

from api.services.switchboard import scripts
from api.services.switchboard.ledger import (
    CallStateLedger,
    reduce_ledger,
    should_ask,
)

# ===========================================================================
# Greeting script selection (Requirement 6.4 / 6.5, Property 7)
# ===========================================================================

#: A caller record is treated as personalized exactly when the turn-1 ANI lookup
#: returned exactly one match. Zero matches (no record) and more than one match
#: (ambiguous) are both **not** personalized (Requirement 6.5, Property 7).
PERSONALIZED_MATCH_COUNT: int = 1


def is_personalized(greeting_ani_match_count: int) -> bool:
    """Return whether the greeting should be personalized (Requirement 6.5).

    Personalization is driven solely by the turn-1 ANI match count: the caller
    record is personalized **iff** exactly one record matched. A count of ``0``
    (no record found, or a failed/timed-out lookup) and any count greater than
    ``1`` (ambiguous multi-match) are both treated as non-personalized.

    Args:
        greeting_ani_match_count: Number of records the turn-1 ANI lookup matched.

    Returns:
        ``True`` when the count equals exactly one, ``False`` otherwise.
    """
    return greeting_ani_match_count == PERSONALIZED_MATCH_COUNT


def select_greeting(after_hours: bool, greeting_ani_match_count: int) -> str:
    """Return the mandated Appendix C greeting script for the call's state.

    Selects the caller-facing greeting line from ``after_hours`` and whether the
    caller record was personalized (Requirement 6.5, Property 7), where
    "personalized" means the turn-1 ANI lookup matched exactly one record
    (:func:`is_personalized`). The returned value is a **verbatim** Appendix C
    constant from :mod:`api.services.switchboard.scripts`.

    Mapping (Appendix C):

    ======================  ==============  ============================================
    ``after_hours``         personalized    Returned script
    ======================  ==============  ============================================
    ``False`` (in hours)    yes             ``GREETING_SCRIPT_2_PRIME_PERSONALIZED``
                                            ("Am I speaking with {FirstName}?")
    ``False`` (in hours)    no              ``GREETING_SCRIPT_4_STANDARD_IN_HOURS``
    ``True`` (after hours)  yes             ``GREETING_PATH_B``
    ``True`` (after hours)  no              ``GREETING_SCRIPT_3_PRIME_AFTER_HOURS``
    ======================  ==============  ============================================

    After-hours personalized mapping decision (Req 6.5). Requirement 6.5 mandates
    that the greeting script be chosen from ``after_hours`` **and** personalization.
    Appendix C provides only one after-hours base script (Script 3′), so if
    after-hours personalized reused Script 3′ it would be identical to the
    after-hours non-personalized case and personalization would have no effect
    after hours — contradicting Req 6.5. Appendix C's only personalized greeting
    that addresses the known caller by name while still soliciting routing
    information is **Path B** ("Hi {{caller_name}}, nice to meet you. …"), and
    Req 6.5 explicitly lists Path B among the selectable greeting scripts.
    After-hours personalized therefore maps to :data:`~scripts.GREETING_PATH_B`.
    (Trade-off: Path B omits Script 3′'s "our offices are currently closed"
    notice; this is the defensible reading because Req 6.5 requires personalization
    to change the selection, and the closed-offices context is still conveyed
    elsewhere in the after-hours cluster.)

    Args:
        after_hours: Whether the call is outside business hours (ledger
            ``after_hours``).
        greeting_ani_match_count: Number of records the turn-1 ANI lookup matched
            (ledger ``greeting_ani_match_count``).

    Returns:
        The verbatim Appendix C greeting script string for the combination.
    """
    personalized = is_personalized(greeting_ani_match_count)

    if after_hours:
        if personalized:
            return scripts.GREETING_PATH_B
        return scripts.GREETING_SCRIPT_3_PRIME_AFTER_HOURS

    if personalized:
        return scripts.GREETING_SCRIPT_2_PRIME_PERSONALIZED
    return scripts.GREETING_SCRIPT_4_STANDARD_IN_HOURS


# ===========================================================================
# Ready-to-hand-off predicate (Requirements 6.7, 6.8, Property 8)
# ===========================================================================

#: Ledger fields whose presence signals the caller has given enough to hand off
#: (Requirement 6.7/6.8): an intent, a specialty, a provider, or a specific
#: request. ``caller_name`` is deliberately excluded — a name alone is never
#: enough to hand off. "Specific request" is represented by a concrete service
#: ask on the ledger: ``scan_type`` (a specific imaging request) or
#: ``appointment_action`` (a specific scheduling action such as cancel/confirm).
HANDOFF_SIGNAL_FIELDS: tuple[str, ...] = (
    "intent",
    "specialty",
    "provider_name",
    "scan_type",
    "appointment_action",
)


def ready_to_handoff(ledger: CallStateLedger) -> bool:
    """Return whether the caller has said enough for the Greeting phase to hand off.

    Implements the Greeting "Ready to hand off" rule (Requirements 6.7, 6.8,
    Property 8): a hand-off is permitted only once at least one hand-off signal is
    present — an intent, a specialty, a provider, or a specific request
    (:data:`HANDOFF_SIGNAL_FIELDS`). The caller name alone is **never** sufficient,
    so a ledger with only ``caller_name`` populated returns ``False``.

    Populated-field semantics mirror the ledger's own never-re-ask predicate:
    a field counts as present exactly when
    :func:`~api.services.switchboard.ledger.should_ask` reports it no longer needs
    asking (``None``/blank strings are unpopulated; ``0``/``False`` are populated).

    Args:
        ledger: The current call-state ledger.

    Returns:
        ``True`` when at least one hand-off signal field is populated, ``False``
        otherwise (including a ledger with only ``caller_name`` set).
    """
    return any(
        not should_ask(field, ledger) for field in HANDOFF_SIGNAL_FIELDS
    )


# ===========================================================================
# Turn-1 ANI-lookup post-state builder (Requirements 6.1, 6.2, 6.3, Property 6)
# ===========================================================================


class AniLookupOutcome(str, Enum):
    """Outcome of the silent turn-1 ANI patient lookup (Requirement 6.2, 6.3).

    The lookup runs as a pre-call fetch bounded to 2 seconds. It can either
    complete (returning zero or more matches) or fail to produce a usable result
    (an error, or exceeding the 2-second bound).
    """

    #: Lookup completed within the 2s bound; ``match_count`` holds the matches.
    SUCCESS = "success"
    #: Lookup errored before returning a result — treated as zero matches.
    FAILURE = "failure"
    #: Lookup exceeded its 2-second bound — treated as zero matches.
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class AniLookupResult:
    """Typed result of the turn-1 ANI lookup, suitable for property testing.

    Encapsulates the lookup ``outcome`` and, for a successful lookup, the number
    of matched records. For :attr:`AniLookupOutcome.FAILURE` and
    :attr:`AniLookupOutcome.TIMEOUT` the match count is defined to be ``0``
    (Requirement 6.3), so those constructors reject a non-zero count.

    Use the :meth:`success`, :meth:`failure`, and :meth:`timeout` factory methods
    rather than constructing directly.
    """

    outcome: AniLookupOutcome
    match_count: int = 0

    def __post_init__(self) -> None:
        if self.match_count < 0:
            raise ValueError(
                f"ANI match_count cannot be negative: {self.match_count}"
            )
        if self.outcome is not AniLookupOutcome.SUCCESS and self.match_count != 0:
            raise ValueError(
                f"{self.outcome.value} outcome must have match_count 0, "
                f"got {self.match_count}"
            )

    @classmethod
    def success(cls, match_count: int) -> "AniLookupResult":
        """Build a successful result with ``match_count`` matched records (>= 0)."""
        return cls(outcome=AniLookupOutcome.SUCCESS, match_count=match_count)

    @classmethod
    def failure(cls) -> "AniLookupResult":
        """Build a failed-lookup result (zero matches, Requirement 6.3)."""
        return cls(outcome=AniLookupOutcome.FAILURE)

    @classmethod
    def timeout(cls) -> "AniLookupResult":
        """Build a timed-out-lookup result (zero matches, Requirement 6.3)."""
        return cls(outcome=AniLookupOutcome.TIMEOUT)


def build_turn1_post_state(result: AniLookupResult) -> dict[str, Any]:
    """Return the ledger updates for the turn-1 ANI lookup (Req 6.2, 6.3, Property 6).

    Turn 1 is silent (no Switchboard-generated speech); this builder produces only
    the ledger state that follows it. Regardless of outcome, the lookup is marked
    done. On :attr:`AniLookupOutcome.SUCCESS` the match count is carried through;
    on failure or timeout the count is ``0`` and no caller-facing error is produced
    (the returned mapping contains only ledger fields, never an error).

    Args:
        result: The typed turn-1 ANI lookup result.

    Returns:
        A mapping suitable for
        :func:`~api.services.switchboard.ledger.reduce_ledger` setting
        ``greeting_ani_lookup_done=True`` and ``greeting_ani_match_count`` to the
        match count (``0`` on failure/timeout).
    """
    if result.outcome is AniLookupOutcome.SUCCESS:
        match_count = result.match_count
    else:
        logger.debug(
            "Turn-1 ANI lookup {} — recording 0 matches, no caller-facing error",
            result.outcome.value,
        )
        match_count = 0

    return {
        "greeting_ani_lookup_done": True,
        "greeting_ani_match_count": match_count,
    }


def apply_turn1_ani_lookup(
    ledger: CallStateLedger, result: AniLookupResult
) -> CallStateLedger:
    """Return a new ledger with the turn-1 ANI post-state merged in (Property 6).

    Pure convenience wrapper that applies :func:`build_turn1_post_state` through
    :func:`~api.services.switchboard.ledger.reduce_ledger`, carrying the full prior
    ledger forward and setting only the two greeting ANI fields. ``ledger`` is not
    mutated.

    Args:
        ledger: The ledger held at the start of turn 1. Not mutated.
        result: The typed turn-1 ANI lookup result.

    Returns:
        A new :class:`CallStateLedger` with ``greeting_ani_lookup_done`` and
        ``greeting_ani_match_count`` set per the lookup outcome.
    """
    return reduce_ledger(ledger, build_turn1_post_state(result))


# ===========================================================================
# Path E "not understood" retry machine (Requirements 6.9, 6.10, 6.11, Property 9)
# ===========================================================================

#: Number of times the Path E line is repeated before falling back. The Path E
#: line is spoken on the 1st and 2nd consecutive not-understood turns; on the 3rd
#: the phase stops repeating Path E and speaks the ROUTING REQUEST wording
#: instead (Requirement 6.10, Property 9).
PATH_E_MAX_REPEATS: int = 2


def path_e_response(consecutive_failures: int) -> str:
    """Return the line to speak after ``consecutive_failures`` not-understood turns.

    Implements the Path E repeat-then-fall-back rule (Requirements 6.9, 6.10,
    6.11, Property 9). ``consecutive_failures`` is the number of consecutive
    not-understood turns **including the current one** (1-based): the current
    failure is the ``consecutive_failures``-th in a row.

    * ``1`` and ``2`` → the verbatim Path E line
      (:data:`~scripts.GREETING_PATH_E`, "I didn't quite catch that. …").
    * ``3`` or more → stop repeating Path E and fall back to the verbatim ROUTING
      REQUEST wording (:data:`~scripts.GREETING_ROUTING_REQUEST`).

    Args:
        consecutive_failures: Count of consecutive not-understood turns, including
            the current one. Must be at least ``1``.

    Returns:
        The verbatim Path E line for the 1st/2nd failure, or the verbatim ROUTING
        REQUEST wording on the 3rd and any subsequent failure.

    Raises:
        ValueError: If ``consecutive_failures`` is less than ``1``.
    """
    if consecutive_failures < 1:
        raise ValueError(
            f"consecutive_failures must be >= 1, got {consecutive_failures}"
        )
    if consecutive_failures <= PATH_E_MAX_REPEATS:
        return scripts.GREETING_PATH_E
    return scripts.GREETING_ROUTING_REQUEST


@dataclass(frozen=True)
class PathERetryState:
    """Immutable Path E retry counter for the Greeting phase (Property 9).

    Tracks the number of consecutive not-understood turns. State transitions
    return a new instance (the value is never mutated in place), keeping the
    machine pure. A fresh state has zero failures; a not-understood turn advances
    it, and any understood turn resets it.
    """

    consecutive_failures: int = 0

    def record_not_understood(self) -> "PathERetryState":
        """Return a new state with the consecutive-failure count incremented by one."""
        return PathERetryState(self.consecutive_failures + 1)

    def reset(self) -> "PathERetryState":
        """Return a fresh state with the consecutive-failure count cleared to zero."""
        return PathERetryState(0)

    @property
    def has_fallen_back(self) -> bool:
        """Whether Path E has stopped repeating and fallen back (>= 3 failures)."""
        return self.consecutive_failures > PATH_E_MAX_REPEATS

    @property
    def response(self) -> str:
        """Return the line to speak for the current failure count.

        Only meaningful after at least one :meth:`record_not_understood`; delegates
        to :func:`path_e_response`, which requires a count of at least ``1``.

        Raises:
            ValueError: If no not-understood turn has been recorded yet
                (``consecutive_failures`` is ``0``).
        """
        return path_e_response(self.consecutive_failures)


__all__ = [
    # Script selection (Property 7)
    "PERSONALIZED_MATCH_COUNT",
    "is_personalized",
    "select_greeting",
    # Ready to hand off (Property 8)
    "HANDOFF_SIGNAL_FIELDS",
    "ready_to_handoff",
    # Turn-1 ANI post-state (Property 6)
    "AniLookupOutcome",
    "AniLookupResult",
    "build_turn1_post_state",
    "apply_turn1_ani_lookup",
    # Path E retry machine (Property 9)
    "PATH_E_MAX_REPEATS",
    "path_e_response",
    "PathERetryState",
]
