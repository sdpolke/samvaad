"""Routing-phase pure decision logic for the SpinSci switchboard (Req 10, 11).

This module owns the deterministic, side-effect-free decision logic of the
Routing phase. Like :mod:`api.services.switchboard.auth` and
:mod:`api.services.switchboard.business_hours`, everything here operates purely on
its inputs (and the Call State Ledger's field values) — it never touches the LLM,
TTS, the ``routing_intent_resolution`` / ``route_metadata_resolution`` tools, or
telephony — so each function is directly unit- and property-testable and is wired
into the Routing node cluster by a later graph-builder task.

Scope of this module (built up across subtasks 11.1 and 11.4):

* **11.1 (this file's first sections):** the **sequential routing-chain
  sequencer** and the **zero-speech invariant checker**.

  * *Sequential routing chain* (Req 10.2, 10.3, Property 20): route listing
    (``routing_intent_resolution``) must COMPLETE before route metadata
    resolution (``route_metadata_resolution``) is invoked, metadata resolution is
    never issued concurrently with listing, and it is invoked with the **exact**
    string returned by listing — never fabricated, never a value absent from the
    returned listing. The chain is modeled here as a pure, immutable state machine
    plus standalone validators so the ordering/exact-string contract is enforced
    structurally and is directly testable.
  * *Zero-speech invariant* (Req 10.1, Property 19): during route resolution the
    phase emits zero speech tokens — no filler, acknowledgment, or stall phrase —
    on every turn up to (but not including) the terminal transfer/hangup turn.
    A pure predicate/guard validates that invariant.

* **11.4 (added to this same module afterward):** terminal-line selection,
  after-hours routing-mode gating, lab→General, new-patient intake, and the
  Fallback route (Req 10.4-10.10, 11.5, 11.6, 12.7).

Later sections are appended to this same module; the section banners below mark
where they belong so the file stays organized as it grows.

Design references:
- ``design.md`` → "Routing cluster (Req 10, Req 11)", "Backend connector tools"
  (the ``routing_intent_resolution`` → ``route_metadata_resolution`` sequential
  chain contract), and Correctness Properties 19 and 20
- ``requirements.md`` → Requirement 10 (10.1 zero speech, 10.2 sequential chain,
  10.3 exact string / never fabricated, 10.4-10.10 terminal line + AH gating),
  Requirement 11 (11.5 lab→General, 11.6 Fallback), Requirement 12 (12.7
  new-patient create → general intake)

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 11.5,
11.6, 12.7.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Union

from loguru import logger

from api.services.switchboard import scripts
from api.services.switchboard.auth import Intent, normalize_intent
from api.services.switchboard.business_hours import (
    AppointmentAction,
    PATIENT_STATUS_NEW,
)

# ===========================================================================
# Zero-speech invariant checker (Req 10.1, Property 19) — subtask 11.1
# ===========================================================================
#
# While the Routing phase resolves a destination it MUST emit zero speech tokens:
# no filler, no acknowledgment, and no stall phrase, on every turn up to (but not
# including) the terminal transfer/hangup turn (Req 10.1, GATE-LOOKUP-SPEECH
# exception, AC-07, POC-05). The invariant is therefore the strongest possible
# form — *any* non-whitespace speech on a resolution turn is a violation — so the
# checker below treats emptiness as the only valid resolution "speech".

#: The mandated speech emitted on a route-resolution turn: none. Resolution turns
#: are silent (Req 10.1); this constant makes the "zero speech" contract explicit
#: for graph-builders wiring the resolution node's ``transition_speech``.
RESOLUTION_SPEECH: str = ""

#: Representative filler / acknowledgment / stall phrases that are forbidden on a
#: resolution turn. This list is **not** the definition of a violation — the
#: invariant forbids *any* speech, so :func:`is_zero_speech` rejects far more than
#: these — it exists only to give :func:`find_resolution_speech_violation` a more
#: descriptive reason when a recognizable stall phrase is what leaked.
FORBIDDEN_RESOLUTION_PHRASES: tuple[str, ...] = (
    "hang tight",
    "one moment",
    "let me check",
    "please hold",
    "bear with me",
    "just a moment",
    "give me a second",
)


class ResolutionSpeechError(Exception):
    """Raised when a route-resolution turn would emit speech (Req 10.1).

    Signals a violation of the zero-speech invariant (Property 19): the Routing
    phase produced filler / acknowledgment / stall speech (or any speech at all)
    while resolving a destination, rather than staying silent until the terminal
    transfer/hangup turn.
    """


def is_zero_speech(speech: Optional[str]) -> bool:
    """Return whether ``speech`` emits zero speech tokens (Req 10.1, Property 19).

    A route-resolution turn is silent iff it produces no speech. ``None`` and any
    whitespace-only string (``""`` / ``"   "`` / newlines) count as zero speech;
    any string containing a non-whitespace character is speech and therefore
    violates the invariant. The check is deliberately the strongest form — it
    does not merely look for the known :data:`FORBIDDEN_RESOLUTION_PHRASES`, since
    the invariant forbids *all* speech on a resolution turn, not just recognizable
    stall phrases.

    Args:
        speech: The candidate speech a resolution turn would emit.

    Returns:
        ``True`` when nothing would be spoken, ``False`` when any non-whitespace
        speech is present.
    """
    return speech is None or speech.strip() == ""


def emits_zero_speech(speech_tokens: Iterable[Optional[str]]) -> bool:
    """Return whether every resolution turn in ``speech_tokens`` is silent.

    Convenience over :func:`is_zero_speech` for validating a whole sequence of
    resolution turns at once (e.g. every turn from entering the Routing cluster up
    to but not including the terminal transfer/hangup turn). The invariant holds
    only when *all* turns are silent.

    Args:
        speech_tokens: The speech emitted on each resolution turn (each item may
            be ``None`` or a string).

    Returns:
        ``True`` when every item emits zero speech, ``False`` if any turn speaks.
    """
    return all(is_zero_speech(token) for token in speech_tokens)


def find_resolution_speech_violation(speech: Optional[str]) -> Optional[str]:
    """Return a description of a zero-speech violation in ``speech``, or ``None``.

    Companion to :func:`is_zero_speech` that explains *why* a resolution turn is
    not silent, for logging/diagnosis. When a recognizable
    :data:`FORBIDDEN_RESOLUTION_PHRASES` stall phrase is present it is named;
    otherwise any other non-whitespace content is reported generically. Returns
    ``None`` when the turn is silent (the invariant holds).

    Args:
        speech: The candidate speech a resolution turn would emit.

    Returns:
        A short human-readable reason for the violation, or ``None`` when
        ``speech`` emits zero speech.
    """
    if is_zero_speech(speech):
        return None

    assert speech is not None  # guaranteed non-silent by is_zero_speech above
    lowered = speech.lower()
    for phrase in FORBIDDEN_RESOLUTION_PHRASES:
        if phrase in lowered:
            return f"contains a forbidden stall/filler phrase: {phrase!r}"
    return f"emits non-empty speech during resolution: {speech!r}"


def assert_zero_speech(speech: Optional[str]) -> Optional[str]:
    """Return ``speech`` unchanged, or raise if a resolution turn would speak.

    Guard wrapper around :func:`find_resolution_speech_violation` enforcing the
    zero-speech invariant (Req 10.1, Property 19) on a route-resolution turn.
    Returns the input so it can be used inline.

    Args:
        speech: The candidate speech a resolution turn would emit.

    Returns:
        ``speech`` unchanged when the resolution turn emits zero speech.

    Raises:
        ResolutionSpeechError: If ``speech`` contains any filler, acknowledgment,
            stall phrase, or other non-whitespace speech.
    """
    reason = find_resolution_speech_violation(speech)
    if reason is not None:
        raise ResolutionSpeechError(f"Route-resolution turn {reason}")
    return speech


# ===========================================================================
# Sequential routing-chain sequencer (Req 10.2, 10.3, Property 20) — 11.1
# ===========================================================================
#
# The routing chain is strictly sequential: routing_intent_resolution (route
# listing) COMPLETES first and returns the exact set of routing-intent strings;
# only then may route_metadata_resolution run, and only with a string that is
# exactly one of the strings the listing returned — never fabricated, never a
# value absent from the listing, and never issued concurrently with listing
# (Req 10.2, 10.3, REQ-LEDGER-03). The pure state machine and validators below
# make that contract explicit and testable independently of the tools' I/O.


class RoutingChainError(Exception):
    """Base class for sequential routing-chain contract violations (Req 10.2, 10.3)."""


class ListingIncompleteError(RoutingChainError):
    """Raised when metadata resolution is attempted before listing completes.

    Signals a violation of the sequential-chain ordering (Req 10.2): route
    metadata resolution was requested while route listing had not yet completed
    (i.e. concurrently with, or ahead of, ``routing_intent_resolution``).
    """


class FabricatedRoutingIntentError(RoutingChainError):
    """Raised when metadata resolution uses a string not present in the listing.

    Signals a violation of the exact-string contract (Req 10.3, REQ-LEDGER-03):
    ``route_metadata_resolution`` was asked to resolve a routing-intent string
    that route listing never returned — a fabricated or altered value.
    """


@dataclass(frozen=True)
class RouteListing:
    """The completed result of ``routing_intent_resolution`` (Req 10.2).

    Holds the exact, ordered routing-intent strings route listing returned for the
    department/intent context. Constructing a :class:`RouteListing` represents a
    *completed* listing (the sequential predecessor of metadata resolution); the
    Routing chain has nothing to resolve metadata for until one exists.

    Duplicate strings are collapsed while preserving first-seen order, so
    membership checks are exact-string and unambiguous. The value is immutable so
    it can be shared/compared freely in property tests.

    Attributes:
        routing_intents: The exact routing-intent strings returned by listing, in
            listing order with duplicates removed.
    """

    routing_intents: tuple[str, ...]

    def __init__(self, routing_intents: Iterable[str]) -> None:
        deduped: list[str] = []
        for value in routing_intents:
            if value not in deduped:
                deduped.append(value)
        # frozen dataclass: assign through object.__setattr__.
        object.__setattr__(self, "routing_intents", tuple(deduped))

    @property
    def is_empty(self) -> bool:
        """Whether route listing returned no routing-intent strings."""
        return len(self.routing_intents) == 0

    def contains(self, routing_intent: str) -> bool:
        """Return whether ``routing_intent`` is exactly one of the listed strings.

        Membership is an **exact** string match against the returned listing (no
        normalization, casing tolerance, or substring matching), so only a value
        route listing actually returned resolves (Req 10.3).
        """
        return routing_intent in self.routing_intents


@dataclass(frozen=True)
class RouteMetadataRequest:
    """A validated request to run ``route_metadata_resolution`` (Req 10.2, 10.3).

    Produced only after route listing has completed and the chosen routing-intent
    string has been verified to be exactly one of the strings the listing returned
    (:func:`select_route_metadata_intent`). Its existence is the evidence that the
    sequential-chain and exact-string contracts held. Immutable so it can be
    shared/compared freely in property tests.

    Attributes:
        routing_intent: The exact routing-intent string (drawn from the listing)
            to resolve metadata for.
    """

    routing_intent: str


def is_valid_routing_intent(listing: RouteListing, routing_intent: str) -> bool:
    """Return whether ``routing_intent`` is an exact member of ``listing`` (Req 10.3).

    Pure predicate over the exact-string contract: metadata resolution may use a
    routing-intent string only when route listing actually returned it. A value
    absent from the listing is a fabricated/altered intent and returns ``False``.

    Args:
        listing: The completed route listing.
        routing_intent: The candidate routing-intent string.

    Returns:
        ``True`` when ``routing_intent`` is exactly one of the listed strings.
    """
    return listing.contains(routing_intent)


def select_route_metadata_intent(
    listing: Optional[RouteListing], routing_intent: str
) -> RouteMetadataRequest:
    """Validate the sequential chain and return the exact-string metadata request.

    Enforces both halves of the routing-chain contract (Req 10.2, 10.3,
    Property 20) as a single pure gate before ``route_metadata_resolution`` runs:

    * **Sequential ordering** (Req 10.2): ``listing`` must be a *completed*
      :class:`RouteListing` (not ``None``). A ``None`` listing means route listing
      has not completed, so requesting metadata now would be out-of-order or
      concurrent — rejected with :class:`ListingIncompleteError`.
    * **Exact string** (Req 10.3): ``routing_intent`` must be exactly one of the
      strings the listing returned (:func:`is_valid_routing_intent`). Any other
      value is fabricated/altered — rejected with
      :class:`FabricatedRoutingIntentError`.

    Only when both hold does it return a :class:`RouteMetadataRequest` carrying the
    exact string, which is the evidence metadata resolution may proceed.

    Args:
        listing: The route listing returned by ``routing_intent_resolution``, or
            ``None`` when listing has not completed.
        routing_intent: The routing-intent string chosen for metadata resolution.

    Returns:
        A :class:`RouteMetadataRequest` holding the validated exact string.

    Raises:
        ListingIncompleteError: If ``listing`` is ``None`` (listing not complete).
        FabricatedRoutingIntentError: If ``routing_intent`` is not exactly one of
            the strings the listing returned.
    """
    if listing is None:
        raise ListingIncompleteError(
            "route_metadata_resolution requested before route listing completed "
            "(Req 10.2)"
        )
    if not is_valid_routing_intent(listing, routing_intent):
        raise FabricatedRoutingIntentError(
            f"routing intent {routing_intent!r} is not in the route listing "
            f"{listing.routing_intents!r} — never fabricate a routing intent "
            f"(Req 10.3)"
        )
    logger.debug(
        "Routing chain: resolving metadata for exact listed intent {!r}",
        routing_intent,
    )
    return RouteMetadataRequest(routing_intent=routing_intent)


class RoutingChainPhase(str, Enum):
    """The ordered phases of the sequential routing chain (Req 10.2).

    The chain advances strictly forward: listing → metadata → resolved. The
    phases make the sequential contract explicit for :class:`RoutingChainState`:

    * :attr:`LISTING` — ``routing_intent_resolution`` has not yet completed; no
      metadata resolution may occur (would be concurrent/out-of-order).
    * :attr:`LISTING_COMPLETE` — route listing completed and its strings are
      known; ``route_metadata_resolution`` may now run with an exact listed string.
    * :attr:`METADATA_RESOLVED` — metadata resolution completed for the chosen
      exact string; the chain is done and a terminal turn may follow.
    """

    LISTING = "listing"
    LISTING_COMPLETE = "listing_complete"
    METADATA_RESOLVED = "metadata_resolved"


@dataclass(frozen=True)
class RoutingChainState:
    """Immutable state machine enforcing the sequential routing chain (Req 10.2, 10.3).

    Threads the routing chain through its phases while structurally forbidding
    out-of-order or fabricated metadata resolution. State transitions return a new
    instance (the value is never mutated in place), keeping the machine pure and
    freely shareable in property tests. A fresh state is in
    :attr:`RoutingChainPhase.LISTING`; :meth:`complete_listing` records the listing
    result, and :meth:`resolve_metadata` validates and advances to the resolved
    phase.

    Attributes:
        listing: The completed route listing, or ``None`` until listing completes.
        resolved_intent: The exact routing-intent string metadata was resolved
            for, or ``None`` until :meth:`resolve_metadata` succeeds.
    """

    listing: Optional[RouteListing] = None
    resolved_intent: Optional[str] = None

    @property
    def phase(self) -> RoutingChainPhase:
        """Return the current chain phase derived from the recorded progress."""
        if self.resolved_intent is not None:
            return RoutingChainPhase.METADATA_RESOLVED
        if self.listing is not None:
            return RoutingChainPhase.LISTING_COMPLETE
        return RoutingChainPhase.LISTING

    @property
    def listing_complete(self) -> bool:
        """Whether route listing has completed (metadata resolution may proceed)."""
        return self.listing is not None

    def complete_listing(self, listing: RouteListing) -> "RoutingChainState":
        """Return a new state recording the completed route listing (Req 10.2).

        Marks ``routing_intent_resolution`` as complete, advancing the chain to
        :attr:`RoutingChainPhase.LISTING_COMPLETE`. Any previously resolved
        metadata is cleared, since a fresh listing restarts the resolution step.

        Args:
            listing: The route listing returned by ``routing_intent_resolution``.

        Returns:
            A new :class:`RoutingChainState` with ``listing`` recorded and
            ``resolved_intent`` cleared.
        """
        return RoutingChainState(listing=listing, resolved_intent=None)

    def resolve_metadata(self, routing_intent: str) -> "RoutingChainState":
        """Validate the chain and return a new state with metadata resolved.

        Delegates the sequential-ordering and exact-string checks to
        :func:`select_route_metadata_intent` (Req 10.2, 10.3, Property 20), then
        advances to :attr:`RoutingChainPhase.METADATA_RESOLVED` recording the exact
        string resolved.

        Args:
            routing_intent: The routing-intent string chosen for metadata
                resolution; must be exactly one of the listed strings.

        Returns:
            A new :class:`RoutingChainState` in the resolved phase.

        Raises:
            ListingIncompleteError: If listing has not completed yet.
            FabricatedRoutingIntentError: If ``routing_intent`` is not exactly one
                of the strings the listing returned.
        """
        request = select_route_metadata_intent(self.listing, routing_intent)
        return RoutingChainState(
            listing=self.listing, resolved_intent=request.routing_intent
        )


# ===========================================================================
# Route destination resolution — lab→General, new-patient intake, Fallback
# (Req 11.5, 11.6, 12.7) — subtask 11.4
# ===========================================================================
#
# Everything below is pure, deterministic, and side-effect-free (no LLM/TTS/
# routing tools/telephony), so it is directly unit- and property-testable and is
# wired into the Routing node cluster by a later graph-builder task. Any
# caller-facing wording is reused **verbatim** from
# :mod:`api.services.switchboard.scripts` (Appendix E); this module only selects
# which mandated line applies and which destination a call resolves to, never
# re-authoring any text.


class RouteDestination(str, Enum):
    """The resolved Routing-phase destination for a call (Req 11, Appendix B/E).

    A destination is the department/path the Routing phase resolves a call to,
    derived from the ledger ``intent`` (and, for Scheduling, ``patient_status`` /
    ``appointment_action``) by :func:`resolve_route`. It is one step removed from
    the raw :class:`~api.services.switchboard.auth.Intent`: it splits Scheduling
    into the new-patient intake vs. existing-patient paths (Req 12.7), folds the
    Directory-connect case into General, and adds an explicit
    :attr:`FALLBACK` for calls with no matched destination (Req 11.6). Each
    destination maps to exactly one Appendix E transfer line
    (:data:`DESTINATION_TERMINAL_LINES`).

    Members:
        SCHEDULING_NEW_INTAKE: General new-patient intake path — a new-patient
            ``create`` Scheduling call, routed here rather than the specialty
            scheduling agent (Req 12.7).
        SCHEDULING_EXISTING: Existing-patient Scheduling, handed off to Scheduling
            Init for the ledger ``specialty``.
        REFERRALS / TRIAGE / BILLING / MYCHART / PAGING / PHARMACY / RECORDS /
            GENERAL: The corresponding department destinations from the route
            matrix (Appendix B).
        FALLBACK: The Switchboard/fallback route used when no destination is
            matched (Req 11.6, Appendix E "Switchboard / fallback").
    """

    SCHEDULING_NEW_INTAKE = "scheduling_new_intake"
    SCHEDULING_EXISTING = "scheduling_existing"
    REFERRALS = "referrals"
    TRIAGE = "triage"
    BILLING = "billing"
    MYCHART = "mychart"
    PAGING = "paging"
    PHARMACY = "pharmacy"
    RECORDS = "records"
    GENERAL = "general"
    FALLBACK = "fallback"


#: Non-Scheduling, non-Directory intents that map one-to-one onto a
#: :class:`RouteDestination`. Scheduling (new/existing split, Req 12.7) and
#: Directory (folded into General for the connect case) are handled explicitly in
#: :func:`resolve_route`; membership — not string literals — keeps this in
#: lock-step with :class:`~api.services.switchboard.auth.Intent`.
_INTENT_TO_DESTINATION: dict[Intent, RouteDestination] = {
    Intent.REFERRALS: RouteDestination.REFERRALS,
    Intent.TRIAGE: RouteDestination.TRIAGE,
    Intent.BILLING: RouteDestination.BILLING,
    Intent.MYCHART: RouteDestination.MYCHART,
    Intent.PAGING: RouteDestination.PAGING,
    Intent.PHARMACY: RouteDestination.PHARMACY,
    Intent.GENERAL: RouteDestination.GENERAL,
    Intent.RECORDS: RouteDestination.RECORDS,
}


def _is_create_action(
    appointment_action: Union[str, AppointmentAction, None]
) -> bool:
    """Return whether ``appointment_action`` is the ``create`` action.

    Accepts an :class:`~api.services.switchboard.business_hours.AppointmentAction`
    or the raw ledger string (compared case-insensitively / whitespace-tolerantly)
    so a ledger value cased differently than ``"create"`` still resolves. ``None``
    / blank is not ``create``.
    """
    if appointment_action is None:
        return False
    if isinstance(appointment_action, AppointmentAction):
        return appointment_action is AppointmentAction.CREATE
    return appointment_action.strip().lower() == AppointmentAction.CREATE.value


def is_new_patient_create(
    patient_status: Optional[str],
    appointment_action: Union[str, AppointmentAction, None],
) -> bool:
    """Return whether the ledger describes a new-patient ``create`` (Req 12.7).

    ``True`` exactly when ``patient_status`` is ``new`` (matched case-insensitively
    against
    :data:`~api.services.switchboard.business_hours.PATIENT_STATUS_NEW`) **and**
    ``appointment_action`` is ``create`` (:func:`_is_create_action`). This is the
    condition that routes a Scheduling call to the general new-patient intake path
    rather than the specialty scheduling agent (Req 12.7, AC-15, POC-01c).

    Args:
        patient_status: The ledger ``patient_status`` (``new`` / ``existing`` /
            ``None``).
        appointment_action: The ledger ``appointment_action`` (enum or raw
            string).

    Returns:
        ``True`` for a new-patient ``create``, ``False`` otherwise.
    """
    status_is_new = bool(
        patient_status and patient_status.strip().lower() == PATIENT_STATUS_NEW
    )
    return status_is_new and _is_create_action(appointment_action)


def resolve_route(
    intent: Union[str, Intent, None],
    patient_status: Optional[str] = None,
    appointment_action: Union[str, AppointmentAction, None] = None,
    *,
    requests_lab_results: bool = False,
) -> RouteDestination:
    """Resolve the Routing-phase destination for a call (Req 11.5, 11.6, 12.7).

    Pure decision mapping the ledger ``intent`` (plus, for Scheduling,
    ``patient_status`` / ``appointment_action`` and the lab-results signal) onto a
    single :class:`RouteDestination`. The special cases are applied in a fixed
    precedence so the resolution is deterministic:

    1. **Lab results → General** (Req 11.5, Property 26): when the caller requests
       lab results, the destination is :attr:`RouteDestination.GENERAL` — never
       :attr:`RouteDestination.RECORDS` — regardless of the classified intent.
    2. **New-patient ``create`` → general intake** (Req 12.7, Property 27): a
       ledger with ``patient_status = new`` and ``appointment_action = create``
       resolves to :attr:`RouteDestination.SCHEDULING_NEW_INTAKE` (the general
       new-patient intake path), not the specialty scheduling agent. This is
       keyed on the status/action pair (which only occurs for Scheduling) so it
       holds for any such ledger.
    3. **Scheduling (existing)** → :attr:`RouteDestination.SCHEDULING_EXISTING`.
    4. **Directory** → :attr:`RouteDestination.GENERAL`: a Directory call that
       needs connecting is handed to the General/Switchboard queue (Directory has
       no Appendix E line of its own). An *info-only* Directory call does not
       route at all — it ends in a goodbye, decided at terminal-line selection
       (:func:`select_terminal_line`, Req 10.9).
    5. **Any other recognized intent** → its department destination
       (:data:`_INTENT_TO_DESTINATION`).
    6. **Unrecognized / unresolved intent** (``None`` after normalization) →
       :attr:`RouteDestination.FALLBACK` (Req 11.6): no destination was matched,
       so the Switchboard/fallback route is used.

    Args:
        intent: The ledger ``intent`` value (raw string, :class:`Intent`, or
            ``None``). Normalized via
            :func:`~api.services.switchboard.auth.normalize_intent`.
        patient_status: The ledger ``patient_status`` (consulted only for
            Scheduling / the new-patient-create check).
        appointment_action: The ledger ``appointment_action`` (consulted only for
            the new-patient-create check).
        requests_lab_results: Whether the caller requested lab results (Req 11.5).

    Returns:
        The resolved :class:`RouteDestination`.
    """
    if requests_lab_results:
        logger.debug("Lab-results request — routing to General, not Records (Req 11.5)")
        return RouteDestination.GENERAL

    if is_new_patient_create(patient_status, appointment_action):
        logger.debug(
            "New-patient create — routing to general new-patient intake (Req 12.7)"
        )
        return RouteDestination.SCHEDULING_NEW_INTAKE

    resolved = normalize_intent(intent)

    if resolved is None:
        logger.debug("No matched destination for intent {!r} — Fallback (Req 11.6)", intent)
        return RouteDestination.FALLBACK

    if resolved is Intent.SCHEDULING:
        return RouteDestination.SCHEDULING_EXISTING

    if resolved is Intent.DIRECTORY:
        return RouteDestination.GENERAL

    return _INTENT_TO_DESTINATION[resolved]


# ===========================================================================
# Terminal-line selection (Req 10.4, 10.5, 10.6, 10.9, 10.10, Property 21) — 11.4
# ===========================================================================
#
# On the terminal transfer/hangup turn the Routing phase speaks ONLY the
# prescribed Appendix E line and emits no other Switchboard speech
# (GATE-TRANSFER-SPEECH, Req 10.4). The line is selected by the resolved
# destination — i.e. by the ledger ``intent`` (Req 10.5) — or is the goodbye line
# for an info-only Directory call (Req 10.9) or the transfer-error line when a
# transfer fails (Req 10.10). Stall phrases such as "Hang tight." are forbidden on
# terminal turns (Req 10.6).

#: Stall / filler phrases forbidden on a **terminal** transfer/hangup turn
#: (Req 10.6, Appendix E "Forbidden in Routing phase"). This is intentionally
#: **narrower** than :data:`FORBIDDEN_RESOLUTION_PHRASES`: the prescribed
#: Appendix E transfer lines legitimately end with "One moment.", so "one moment"
#: (and the like) must NOT be treated as forbidden here — only genuine stall
#: phrases that never appear in a mandated line are listed. None of these is a
#: substring of any Appendix E transfer/goodbye/error line, so a correctly
#: selected line never trips the guard.
FORBIDDEN_TERMINAL_STALL_PHRASES: tuple[str, ...] = (
    "hang tight",
    "hold on",
    "bear with me",
    "just a sec",
    "give me a second",
    "let me check",
)


class TerminalStallPhraseError(Exception):
    """Raised when a terminal transfer/hangup line contains a stall phrase (Req 10.6).

    Signals a violation of the "Forbidden in Routing phase" rule (Req 10.6): the
    terminal turn's line contains a stall/filler phrase such as "Hang tight."
    """


class TerminalKind(str, Enum):
    """The kind of terminal turn the Routing phase performs (Req 10.4, 10.9, 10.10).

    * :attr:`TRANSFER` — a transfer to a resolved destination; speaks the
      destination's Appendix E transfer line (Req 10.4, 10.5).
    * :attr:`GOODBYE` — an info-only Directory call ends the call with the goodbye
      line instead of a transfer (Req 10.9).
    * :attr:`TRANSFER_ERROR` — a transfer failed; speaks the mandated
      transfer-error line (Req 10.10).
    """

    TRANSFER = "transfer"
    GOODBYE = "goodbye"
    TRANSFER_ERROR = "transfer_error"


#: The verbatim Appendix E transfer line for each :class:`RouteDestination`
#: (Req 10.5). Values are the verbatim :mod:`~api.services.switchboard.scripts`
#: constants — never re-authored here. The mapping is total over
#: :class:`RouteDestination`.
DESTINATION_TERMINAL_LINES: dict[RouteDestination, str] = {
    RouteDestination.SCHEDULING_NEW_INTAKE: scripts.E_SCHEDULING_NEW,
    RouteDestination.SCHEDULING_EXISTING: scripts.E_SCHEDULING_EXISTING,
    RouteDestination.REFERRALS: scripts.E_REFERRALS,
    RouteDestination.TRIAGE: scripts.E_TRIAGE,
    RouteDestination.BILLING: scripts.E_BILLING,
    RouteDestination.MYCHART: scripts.E_MYCHART,
    RouteDestination.PAGING: scripts.E_PAGING,
    RouteDestination.PHARMACY: scripts.E_PHARMACY,
    RouteDestination.RECORDS: scripts.E_RECORDS,
    RouteDestination.GENERAL: scripts.E_GENERAL,
    RouteDestination.FALLBACK: scripts.E_SWITCHBOARD_FALLBACK,
}


@dataclass(frozen=True)
class TerminalTurn:
    """The single spoken line for a terminal transfer/hangup turn (Req 10.4).

    Bundles the terminal turn's :class:`TerminalKind` with the one verbatim line
    that is the *only* Switchboard speech emitted on that turn (GATE-TRANSFER-
    SPEECH, Req 10.4, Property 21). Immutable so it can be shared/compared freely
    in property tests.

    Attributes:
        kind: Whether the turn transfers, ends with a goodbye, or reports a
            transfer error.
        line: The verbatim Appendix E line spoken on the turn — guaranteed free of
            forbidden stall phrases by :func:`select_terminal_line`.
    """

    kind: TerminalKind
    line: str


def find_terminal_stall_violation(line: str) -> Optional[str]:
    """Return a description of a forbidden stall phrase in ``line``, or ``None``.

    Scans ``line`` for any :data:`FORBIDDEN_TERMINAL_STALL_PHRASES` entry
    (case-insensitively) and names the first one found, for logging/diagnosis
    (Req 10.6). Returns ``None`` when the line carries no forbidden stall phrase.

    Args:
        line: The candidate terminal line.

    Returns:
        A short human-readable reason naming the forbidden phrase, or ``None``.
    """
    lowered = line.lower()
    for phrase in FORBIDDEN_TERMINAL_STALL_PHRASES:
        if phrase in lowered:
            return f"contains a forbidden stall phrase: {phrase!r}"
    return None


def assert_no_terminal_stall_phrase(line: str) -> str:
    """Return ``line`` unchanged, or raise if it contains a forbidden stall phrase.

    Guard wrapper around :func:`find_terminal_stall_violation` enforcing Req 10.6
    on a terminal transfer/hangup line before it is spoken. Returns the input so
    it can be used inline.

    Args:
        line: The candidate terminal line.

    Returns:
        ``line`` unchanged when it carries no forbidden stall phrase.

    Raises:
        TerminalStallPhraseError: If ``line`` contains a forbidden stall phrase.
    """
    reason = find_terminal_stall_violation(line)
    if reason is not None:
        raise TerminalStallPhraseError(f"Terminal turn {reason}: {line!r}")
    return line


def select_terminal_line(
    destination: RouteDestination,
    *,
    directory_info_only: bool = False,
    transfer_failed: bool = False,
) -> TerminalTurn:
    """Select the single line spoken on a terminal transfer/hangup turn (Req 10.4-10.10).

    Chooses the *only* Switchboard speech emitted on the terminal turn
    (GATE-TRANSFER-SPEECH, Req 10.4, Property 21). The cases are applied in a fixed
    precedence:

    1. **Transfer failed** (Req 10.10): speak the mandated transfer-error line
       (:data:`~api.services.switchboard.scripts.E_TRANSFER_ERROR`) — this takes
       precedence, since a failed transfer is the exceptional terminal outcome.
    2. **Directory info-only** (Req 10.9): end the call with the goodbye line
       (:data:`~api.services.switchboard.scripts.E_HANGUP`) instead of a transfer.
    3. **Transfer** (Req 10.4, 10.5): speak the destination's Appendix E transfer
       line (:data:`DESTINATION_TERMINAL_LINES`), selected by the resolved
       destination — i.e. by the ledger ``intent``.

    The selected line is validated free of forbidden stall phrases
    (:func:`assert_no_terminal_stall_phrase`, Req 10.6) before it is returned, so
    the guarantee holds even if the verbatim constants are ever edited.

    Args:
        destination: The resolved :class:`RouteDestination` (from
            :func:`resolve_route`). Used only for the transfer case.
        directory_info_only: Whether this is an info-only Directory call that
            should end with a goodbye rather than a transfer (Req 10.9).
        transfer_failed: Whether an attempted transfer failed (Req 10.10).

    Returns:
        The :class:`TerminalTurn` with the terminal turn's kind and its single
        verbatim line.

    Raises:
        TerminalStallPhraseError: If the selected line contains a forbidden stall
            phrase (only possible if the verbatim constants are changed).
    """
    if transfer_failed:
        logger.debug("Transfer failed — speaking transfer-error line (Req 10.10)")
        line = assert_no_terminal_stall_phrase(scripts.E_TRANSFER_ERROR)
        return TerminalTurn(kind=TerminalKind.TRANSFER_ERROR, line=line)

    if directory_info_only:
        logger.debug("Directory info-only — ending with goodbye, not transfer (Req 10.9)")
        line = assert_no_terminal_stall_phrase(scripts.E_HANGUP)
        return TerminalTurn(kind=TerminalKind.GOODBYE, line=line)

    line = assert_no_terminal_stall_phrase(DESTINATION_TERMINAL_LINES[destination])
    logger.debug("Terminal transfer to {} — line {!r}", destination.value, line)
    return TerminalTurn(kind=TerminalKind.TRANSFER, line=line)


# ===========================================================================
# After-hours routing-mode gating (GATE-AH-SPEC, Req 10.7, 10.8) — subtask 11.4
# ===========================================================================


def uses_after_hours_routing_mode(
    after_hours: bool,
    is_post_authentication_routing: bool,
    is_hotword_immediate_path: bool = False,
) -> bool:
    """Return whether after-hours switchboard routing mode is used (GATE-AH-SPEC).

    The GATE-AH-SPEC predicate (Req 10.7, 10.8, Property 22). After-hours routing
    mode — resolving the route via the after-hours switchboard path rather than
    the caller's real specialty — is used **if and only if** all three hold:

    * ``after_hours`` is true, **and**
    * the traversal is resolving post-authentication routing
      (``is_post_authentication_routing``), **and**
    * it is **not** the hotword immediate path (``is_hotword_immediate_path`` is
      false).

    Consequently, while ``after_hours`` is false the mode is never used (Req 10.7,
    AC-12), and even after hours the hotword immediate path is excluded (Req 10.8).

    Args:
        after_hours: The ledger ``after_hours`` flag.
        is_post_authentication_routing: Whether the current traversal is resolving
            routing after authentication (the post-auth routing path).
        is_hotword_immediate_path: Whether this is the after-hours hotword
            immediate path, which is excluded from after-hours routing mode.

    Returns:
        ``True`` iff after-hours routing mode applies, else ``False``.
    """
    result = bool(
        after_hours
        and is_post_authentication_routing
        and not is_hotword_immediate_path
    )
    logger.debug(
        "GATE-AH-SPEC: after_hours={} post_auth={} hotword={} → AH routing mode={}",
        after_hours,
        is_post_authentication_routing,
        is_hotword_immediate_path,
        result,
    )
    return result


__all__ = [
    # Zero-speech invariant checker (subtask 11.1, Req 10.1, Property 19)
    "RESOLUTION_SPEECH",
    "FORBIDDEN_RESOLUTION_PHRASES",
    "ResolutionSpeechError",
    "is_zero_speech",
    "emits_zero_speech",
    "find_resolution_speech_violation",
    "assert_zero_speech",
    # Sequential routing-chain sequencer (subtask 11.1, Req 10.2, 10.3, Property 20)
    "RoutingChainError",
    "ListingIncompleteError",
    "FabricatedRoutingIntentError",
    "RouteListing",
    "RouteMetadataRequest",
    "is_valid_routing_intent",
    "select_route_metadata_intent",
    "RoutingChainPhase",
    "RoutingChainState",
    # Route destination resolution (subtask 11.4, Req 11.5, 11.6, 12.7)
    "RouteDestination",
    "is_new_patient_create",
    "resolve_route",
    # Terminal-line selection (subtask 11.4, Req 10.4-10.6, 10.9, 10.10, Property 21)
    "FORBIDDEN_TERMINAL_STALL_PHRASES",
    "TerminalStallPhraseError",
    "TerminalKind",
    "DESTINATION_TERMINAL_LINES",
    "TerminalTurn",
    "find_terminal_stall_violation",
    "assert_no_terminal_stall_phrase",
    "select_terminal_line",
    # After-hours routing-mode gating (subtask 11.4, Req 10.7, 10.8, Property 22)
    "uses_after_hours_routing_mode",
]
