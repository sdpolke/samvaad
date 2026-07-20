"""Business-Hours-phase pure decision logic for the SpinSci switchboard (Req 7, 12).

This module owns the deterministic, side-effect-free decision logic of the
Business Hours phase. Like :mod:`api.services.switchboard.greeting`, everything
here operates purely on its inputs (and, later, the Call State Ledger) — it never
touches the LLM, TTS, directory tools, or telephony — so each function is
directly unit- and property-testable and is wired into the Business Hours node
cluster by a later graph-builder task.

Scope of this module (built up across subtasks 8.1, 8.3, 8.5):

* **8.1 (this file's first section):** the ``appointment_action`` classifier —
  map caller speech to exactly one of create / cancel / reschedule / list /
  confirm, never defaulting to ``create`` when the caller expressed a manage
  action (Requirements 7.6, 7.7, 12.1; Property 11).
* **8.3 (this file's second section):** the GATE-LOOKUP-SPEECH prefix rules —
  a silent (empty) prefix for the first provider/directory lookup on the turn,
  "Let me check that for you." for an FAQ lookup, and "One moment." for any other
  lookup, each invoked on the same turn (Requirements 7.2, 7.3, 7.4; Property 10).
* **8.5 (later):** manage-action consequences and the classification-retry
  machine (Requirements 7.5, 7.8, 7.10-7.13, 12.2, 13.7).

Later sections are added to this same module; the section banners below mark
where they belong so the file stays organized as it grows.

Design references:
- ``design.md`` → "Business Hours cluster (Req 7)" and Correctness Property 11
- ``requirements.md`` → Requirement 7 (7.6 set from speech, 7.7 never-create) and
  Requirement 12 (12.1 classification from caller speech)

Requirements: 7.6, 7.7, 12.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Pattern

from loguru import logger

from api.services.switchboard import scripts

# ===========================================================================
# Appointment-action classification (Requirements 7.6, 7.7, 12.1, Property 11)
# ===========================================================================


class AppointmentAction(str, Enum):
    """The scheduling action a caller wants to take (ledger ``appointment_action``).

    Values are the exact lowercase strings stored on the Call State Ledger's
    ``appointment_action`` field (Appendix D): a ``create`` / ``cancel`` /
    ``reschedule`` / ``list`` / ``confirm`` request. Being a ``str`` subclass, a
    member is directly assignable as the ledger value (``member.value`` or the
    member itself both serialize to the ledger string).
    """

    CREATE = "create"
    CANCEL = "cancel"
    RESCHEDULE = "reschedule"
    LIST = "list"
    CONFIRM = "confirm"


#: Ordered classification precedence. The classifier tries each action's cue
#: patterns in this order and returns the first that matches, so the order is the
#: tie-breaker when a single utterance carries more than one cue. The four
#: **manage** actions are all tried before ``create`` — this is what structurally
#: guarantees Requirement 7.7 / Property 11 (a caller who expressed cancel,
#: reschedule, list, or confirm is never classified as ``create``).
#:
#: Manage-action ordering rationale:
#: * ``reschedule`` first — a reschedule request frequently also mentions the old
#:   visit ("cancel my Tuesday slot and move it to Friday"); the caller's true
#:   goal is the reschedule, so it must win over the co-mentioned ``cancel``.
#: * ``cancel`` next, then ``confirm``, then ``list`` — these rarely co-occur;
#:   the remaining order is stable and deterministic.
_CLASSIFICATION_ORDER: tuple[AppointmentAction, ...] = (
    AppointmentAction.RESCHEDULE,
    AppointmentAction.CANCEL,
    AppointmentAction.CONFIRM,
    AppointmentAction.LIST,
    AppointmentAction.CREATE,
)


def _compile(*fragments: str) -> tuple[Pattern[str], ...]:
    """Compile case-insensitive cue patterns from raw regex ``fragments``."""
    return tuple(re.compile(fragment, re.IGNORECASE) for fragment in fragments)


#: Per-action caller-speech cues. Each entry is a set of regex fragments; an
#: action is signalled when any of its patterns is found in the utterance.
#:
#: The classifier only runs once ``intent`` has been resolved to Scheduling, so
#: the surrounding context is already "an appointment" — that is why broad verbs
#: like "move" / "change" / "switch" are safely read as reschedule cues here.
#:
#: ``\bschedul`` (a ``create`` cue) does not fire on "reschedule": there is no
#: word boundary between "re" and "schedule", so the leading ``\b`` prevents a
#: match — and ``create`` is tried last regardless.
_ACTION_CUES: dict[AppointmentAction, tuple[Pattern[str], ...]] = {
    AppointmentAction.RESCHEDULE: _compile(
        r"\breschedul",
        r"\bre-schedul",
        r"\bmove\b",
        r"\bpush(ed|ing)?\s+(back|out|up)\b",
        r"\bchang(e|ing)\b",
        r"\bswitch\b",
        r"\bdifferent\s+(day|time|date)\b",
        r"\banother\s+(day|time|date)\b",
    ),
    AppointmentAction.CANCEL: _compile(
        r"\bcancel",
        r"\bcall(ed|ing)?\s+off\b",
        r"\bdrop\b",
        r"\bget\s+rid\s+of\b",
    ),
    AppointmentAction.CONFIRM: _compile(
        r"\bconfirm",
        r"\bverif(y|ying|ication)\b",
        r"\bstill\s+(on|have|scheduled|good|set)\b",
        r"\bdouble[-\s]?check\b",
        r"\bmake\s+sure\b",
    ),
    AppointmentAction.LIST: _compile(
        r"\blist\b",
        r"\bwhat\s+appointment",
        r"\bwhich\s+appointment",
        r"\bdo\s+i\s+have\b",
        r"\bany\s+appointment",
        r"\b(see|check|view|show)\s+.*appointment",
        r"\bupcoming\b",
        r"\bmy\s+appointments\b",
    ),
    AppointmentAction.CREATE: _compile(
        r"\bcreate\b",
        r"\bmake\b",
        r"\bbook\b",
        r"\bschedul",
        r"\bset[-\s]?up\b",
        r"\bnew\s+appointment\b",
        r"\bneed\s+an?\b",
        r"\bwant\s+an?\b",
        r"\bget\s+an?\s+appointment\b",
        r"\bcome\s+in\b",
        r"\bsee\s+(the|a|my)\b.*\b(doctor|provider|physician|dr)\b",
    ),
}


def _matches(action: AppointmentAction, speech: str) -> bool:
    """Return whether any cue pattern for ``action`` is present in ``speech``."""
    return any(pattern.search(speech) for pattern in _ACTION_CUES[action])


def classify_appointment_action(speech: Optional[str]) -> Optional[AppointmentAction]:
    """Classify caller speech into a single ``appointment_action`` (Req 7.6, 12.1).

    Maps a caller utterance to exactly one :class:`AppointmentAction`, honoring the
    hard rule that a caller who expressed a manage action (cancel, reschedule,
    list, or confirm) is **never** classified as ``create`` (Requirement 7.7,
    Property 11). This is guaranteed structurally: all four manage actions are
    evaluated before ``create`` (see :data:`_CLASSIFICATION_ORDER`), so a manage
    cue always short-circuits ahead of the ``create`` cues.

    ``create`` is returned only when the caller genuinely expresses intent to
    create/make/book a new appointment (a ``create`` cue matches) **and** no
    manage cue matched. When the utterance carries no recognizable action cue at
    all, the function returns ``None`` rather than defaulting to ``create`` — the
    caller node then re-asks (the classification-retry machine, subtask 8.5).
    This deliberately avoids a "default to create" fallback, which would violate
    the never-create rule for ambiguous manage phrasings.

    Args:
        speech: The caller's utterance. ``None`` or blank yields ``None``.

    Returns:
        The single classified :class:`AppointmentAction`, or ``None`` when no
        action cue is present (unclassifiable — re-ask upstream).
    """
    if speech is None:
        return None
    normalized = speech.strip()
    if not normalized:
        return None

    for action in _CLASSIFICATION_ORDER:
        if _matches(action, normalized):
            logger.debug(
                "Classified appointment_action={} from caller speech", action.value
            )
            return action

    logger.debug("No appointment_action cue found in caller speech; returning None")
    return None


# ===========================================================================
# Lookup-speech prefix rules (Requirements 7.2, 7.3, 7.4) — subtask 8.3
# ===========================================================================


class LookupType(str, Enum):
    """The kind of Business-Hours lookup being performed (Req 7.2, 7.3, 7.4).

    Drives the GATE-LOOKUP-SPEECH prefix decision (:func:`lookup_speech_prefix`).
    The three members are the finite choice set the prefix rules distinguish:

    * :attr:`PROVIDER_DIRECTORY` — a provider/directory search. Its *first*
      occurrence on a turn is silent (Req 7.2); a later provider/directory lookup
      on the same turn is treated as "any other" and gets "One moment." (Req 7.4).
    * :attr:`FAQ` — an FAQ / knowledge-base lookup, always prefixed with
      "Let me check that for you." (Req 7.3).
    * :attr:`OTHER` — any other lookup, prefixed with "One moment." (Req 7.4).
    """

    PROVIDER_DIRECTORY = "provider_directory"
    FAQ = "faq"
    OTHER = "other"


@dataclass(frozen=True)
class LookupSpeechDecision:
    """The spoken prefix for a lookup and the same-turn invocation contract.

    Bundles the two halves of the GATE-LOOKUP-SPEECH rule so a caller/graph-builder
    wires the lookup correctly:

    * :attr:`prefix` — the verbatim spoken prefix (possibly empty for the silent
      first provider/directory lookup, Req 7.2).
    * :attr:`invoke_same_turn` — always ``True``: the lookup MUST be invoked on the
      **same turn** the prefix is spoken (Req 7.3, 7.4). The prefix is filler said
      while the lookup runs, never a turn that only speaks and defers the lookup.

    The value is immutable so it can be shared/compared freely in property tests.
    """

    prefix: str
    invoke_same_turn: bool = True

    @property
    def is_silent(self) -> bool:
        """Whether this decision speaks no prefix (the silent first lookup)."""
        return self.prefix == ""


#: The verbatim prefix for the first provider/directory lookup on a turn: none.
#: Req 7.2 (GATE-LOOKUP-SPEECH exception, AC-13) mandates that lookup be a silent
#: turn with no spoken filler.
FIRST_DIRECTORY_LOOKUP_PREFIX: str = ""


def lookup_speech_prefix(
    lookup_type: LookupType, is_first_directory_lookup_on_turn: bool
) -> LookupSpeechDecision:
    """Return the spoken prefix + same-turn contract for a Business-Hours lookup.

    Implements the GATE-LOOKUP-SPEECH prefix rules (Requirements 7.2, 7.3, 7.4,
    Property 10) as a pure decision over the lookup kind and whether this is the
    first provider/directory lookup on the current turn:

    * **First provider/directory lookup on the turn** →
      :data:`FIRST_DIRECTORY_LOOKUP_PREFIX` (empty, silent — Req 7.2, AC-13). The
      ``is_first_directory_lookup_on_turn`` flag only applies to
      :attr:`LookupType.PROVIDER_DIRECTORY`; it is ignored for other kinds.
    * **FAQ lookup** → :data:`~api.services.switchboard.scripts.BH_FAQ_LOOKUP`
      ("Let me check that for you.", Req 7.3).
    * **Any other lookup** (a non-FAQ lookup, or a non-first provider/directory
      lookup on the turn) → :data:`~api.services.switchboard.scripts.BH_OTHER_LOOKUP`
      ("One moment.", Req 7.4).

    Precedence matters: the silent-first-directory exception is checked before the
    FAQ/other rules, so only a first provider/directory lookup is silent and a
    subsequent provider/directory lookup on the same turn falls through to
    "One moment." The returned :class:`LookupSpeechDecision` always carries
    ``invoke_same_turn=True``, encoding the requirement that the lookup is invoked
    on the same turn the prefix is spoken.

    Args:
        lookup_type: The kind of lookup being performed.
        is_first_directory_lookup_on_turn: Whether this is the first
            provider/directory lookup on the current turn. Only meaningful when
            ``lookup_type`` is :attr:`LookupType.PROVIDER_DIRECTORY`.

    Returns:
        A :class:`LookupSpeechDecision` with the verbatim spoken prefix and the
        same-turn invocation contract.
    """
    if (
        lookup_type is LookupType.PROVIDER_DIRECTORY
        and is_first_directory_lookup_on_turn
    ):
        logger.debug(
            "First provider/directory lookup on turn — silent (no prefix)"
        )
        return LookupSpeechDecision(prefix=FIRST_DIRECTORY_LOOKUP_PREFIX)

    if lookup_type is LookupType.FAQ:
        logger.debug("FAQ lookup — prefix {!r}", scripts.BH_FAQ_LOOKUP)
        return LookupSpeechDecision(prefix=scripts.BH_FAQ_LOOKUP)

    logger.debug("Other lookup — prefix {!r}", scripts.BH_OTHER_LOOKUP)
    return LookupSpeechDecision(prefix=scripts.BH_OTHER_LOOKUP)


# ===========================================================================
# Manage-action consequences + classification-retry machine — subtask 8.5
# (Requirements 7.5, 7.8, 7.10-7.13, 12.2, 13.7)
# ===========================================================================
#
# Everything below is pure, deterministic, and side-effect-free (no LLM/TTS/
# directory/telephony), so it is directly unit- and property-testable and is
# wired into the Business Hours node cluster by a later graph-builder task. All
# caller-facing wording is reused **verbatim** from
# :mod:`api.services.switchboard.scripts` (Appendix C); this module only selects
# which mandated line applies, never re-authoring any text.


# --- Ledger value vocabulary ----------------------------------------------
#
# The ledger stores ``patient_status`` and ``intent`` as free strings (Appendix
# D). There is no shared enum for them yet, so the small set of literal values
# this module compares against is centralized here as named constants rather than
# scattered string literals.

#: ``patient_status`` value for an existing patient (ledger ``patient_status``).
PATIENT_STATUS_EXISTING: str = "existing"

#: ``patient_status`` value for a new patient (ledger ``patient_status``).
PATIENT_STATUS_NEW: str = "new"

#: The ``intent`` value that skips authentication (Req 7.10, Appendix E Records).
#: Matched case-insensitively so a differently-cased ledger value still resolves.
RECORDS_INTENT: str = "Records"


def _patient_status_is_known(patient_status: Optional[str]) -> bool:
    """Return whether ``patient_status`` holds a meaningful new/existing value.

    ``None`` and blank/whitespace-only strings are treated as *unknown* (the
    switchboard has not yet established whether the caller is new or existing),
    which is the condition Req 7.5 / 12.3 use to decide whether to ask the
    new/existing question for a ``create`` action.
    """
    return bool(patient_status and patient_status.strip())


# --- Manage-action consequences (Req 7.5, 7.8, 12.2, 13.7, Property 12) -----

#: The four **manage** appointment actions. A ledger whose ``appointment_action``
#: is one of these describes an existing appointment the caller wants to manage
#: (cancel / reschedule / list / confirm) rather than a brand-new ``create``.
#: Membership — not string literals — is what drives the manage-vs-create split,
#: so this stays in lock-step with :class:`AppointmentAction`.
MANAGE_ACTIONS: frozenset[AppointmentAction] = frozenset(
    {
        AppointmentAction.CANCEL,
        AppointmentAction.RESCHEDULE,
        AppointmentAction.LIST,
        AppointmentAction.CONFIRM,
    }
)


def is_manage_action(action: AppointmentAction) -> bool:
    """Return whether ``action`` is a manage action (not ``create``).

    A manage action is cancel / reschedule / list / confirm (see
    :data:`MANAGE_ACTIONS`); ``create`` is the only non-manage action. Determined
    by enum membership so it can never drift from :class:`AppointmentAction`.
    """
    return action in MANAGE_ACTIONS


@dataclass(frozen=True)
class AppointmentActionConsequences:
    """The switchboard consequences of a Scheduling ``appointment_action``.

    Bundles the deterministic downstream decisions Req 7.5, 7.8, 12.2 and 13.7
    attach to the classified :class:`AppointmentAction`, so a caller/graph-builder
    wires the Scheduling gate correctly. The value is immutable so it can be
    shared and compared freely in property tests.

    Attributes:
        appointment_action: The action these consequences are for.
        ask_new_or_existing: Whether the switchboard must ask "Are you a new or
            existing patient?" before auth/routing. ``True`` only for a
            ``create`` whose ``patient_status`` is still unknown (Req 7.5, 12.3);
            always ``False`` for a manage action (Req 7.8, 12.2).
        new_existing_question: The verbatim new/existing question
            (:data:`~scripts.BH_SCHEDULING_GATE`) when ``ask_new_or_existing`` is
            ``True``, else ``None``.
        patient_status: The resulting ``patient_status`` the switchboard sets.
            :data:`PATIENT_STATUS_EXISTING` for a manage action (Req 7.8, 12.2);
            for ``create`` the prior status is preserved (``None``/unknown until
            the new/existing question is answered).
        require_specialty_before_auth: Whether a populated, confirmed ``specialty``
            is required before Authentication. ``True`` for manage actions —
            authentication is required only **after** ``specialty`` is confirmed
            (Req 7.8, 12.2, REQ-SCHED-01).
        set_visit_type_on_switchboard: Always ``False`` — ``visit_type`` is
            create-only and is set downstream in Scheduling Init, never by the
            switchboard (Req 12.4, 13.2, 13.7).
    """

    appointment_action: AppointmentAction
    ask_new_or_existing: bool
    new_existing_question: Optional[str]
    patient_status: Optional[str]
    require_specialty_before_auth: bool
    set_visit_type_on_switchboard: bool = False


def appointment_action_consequences(
    action: AppointmentAction, patient_status: Optional[str] = None
) -> AppointmentActionConsequences:
    """Return the switchboard consequences of a classified ``appointment_action``.

    Pure decision implementing Requirements 7.5, 7.8, 12.2 and 13.7 (Property 12):

    * **Manage action** (cancel / reschedule / list / confirm — see
      :func:`is_manage_action`): treat the caller as an existing patient — set
      ``patient_status = existing``, ask **no** new/existing question, and require
      authentication only **after** ``specialty`` is confirmed
      (``require_specialty_before_auth=True``). ``patient_status`` provided by the
      caller is ignored here; a manage action is always an existing patient.
    * **Create** with an *unknown* ``patient_status`` (``None``/blank — see
      :func:`_patient_status_is_known`): ask the verbatim new/existing question
      (:data:`~scripts.BH_SCHEDULING_GATE`) before auth/routing (Req 7.5, 12.3);
      the prior ``patient_status`` is preserved (still unknown until answered).
    * **Create** with a *known* ``patient_status`` (already new/existing): do not
      re-ask; carry the known status forward.

    In every case ``set_visit_type_on_switchboard`` is ``False`` — ``visit_type``
    is create-only and set downstream in Scheduling Init, never on the switchboard
    (Req 12.4, 13.7).

    Args:
        action: The classified appointment action (see
            :func:`classify_appointment_action`).
        patient_status: The current ledger ``patient_status`` (``None``/blank when
            not yet established). Consulted only for ``create``.

    Returns:
        The :class:`AppointmentActionConsequences` for the action.
    """
    if is_manage_action(action):
        logger.debug(
            "Manage action {} — patient_status=existing, skip new/existing, "
            "auth after specialty, no visit_type on switchboard",
            action.value,
        )
        return AppointmentActionConsequences(
            appointment_action=action,
            ask_new_or_existing=False,
            new_existing_question=None,
            patient_status=PATIENT_STATUS_EXISTING,
            require_specialty_before_auth=True,
            set_visit_type_on_switchboard=False,
        )

    # create: ask new/existing only while patient_status is unknown (Req 7.5).
    if _patient_status_is_known(patient_status):
        logger.debug(
            "Create action with known patient_status={!r} — no new/existing "
            "question",
            patient_status,
        )
        return AppointmentActionConsequences(
            appointment_action=action,
            ask_new_or_existing=False,
            new_existing_question=None,
            patient_status=patient_status,
            require_specialty_before_auth=False,
            set_visit_type_on_switchboard=False,
        )

    logger.debug(
        "Create action with unknown patient_status — asking new/existing gate"
    )
    return AppointmentActionConsequences(
        appointment_action=action,
        ask_new_or_existing=True,
        new_existing_question=scripts.BH_SCHEDULING_GATE,
        patient_status=patient_status,
        require_specialty_before_auth=False,
        set_visit_type_on_switchboard=False,
    )


# --- Silent, filler-free transition straight to Routing --------------------


@dataclass(frozen=True)
class SilentRoutingTransition:
    """A silent (no spoken filler) transition straight to the Routing phase.

    Shared by the two Business-Hours cases that skip ahead to Routing with no
    speech on the turn: the Records auth-skip (Req 7.10) and the third-failure
    classification fallback (Req 7.12). ``spoken_filler`` is always empty and
    ``to_routing`` always ``True``; the type exists so those decisions are
    explicit and self-documenting rather than a bare ``bool``.
    """

    spoken_filler: str = ""
    to_routing: bool = True

    @property
    def is_silent(self) -> bool:
        """Whether the transition speaks nothing (always ``True`` by construction)."""
        return self.spoken_filler == ""


#: The canonical silent → Routing transition (no spoken filler). Immutable, so it
#: is safe to share across the Records skip-auth and retry-3 fallback decisions.
SILENT_TO_ROUTING: SilentRoutingTransition = SilentRoutingTransition()


# --- Records skips authentication (Req 7.10) -------------------------------


def intent_skips_auth(intent: Optional[str]) -> bool:
    """Return whether ``intent`` is Records, which skips authentication (Req 7.10).

    Records is the intent that skips Authentication and transitions directly to
    Routing as a silent turn (Req 7.10, AC-09, POC-02). The comparison is
    case-insensitive and whitespace-tolerant so a ledger ``intent`` value that is
    cased differently than :data:`RECORDS_INTENT` still resolves.
    """
    return bool(intent and intent.strip().lower() == RECORDS_INTENT.lower())


def records_auth_skip(intent: Optional[str]) -> Optional[SilentRoutingTransition]:
    """Return the silent → Routing transition for Records, else ``None`` (Req 7.10).

    When ``intent`` is Records the switchboard skips Authentication entirely and
    transitions to Routing as a silent turn with no spoken filler; this returns
    the shared :data:`SILENT_TO_ROUTING` decision describing that. For any other
    intent it returns ``None`` (Records is the only auth-skipping intent handled
    here; new-patient ``create`` auth-skip is decided in the Authentication phase,
    task 9).

    Args:
        intent: The ledger ``intent`` classification value.

    Returns:
        :data:`SILENT_TO_ROUTING` when ``intent`` is Records, otherwise ``None``.
    """
    if intent_skips_auth(intent):
        logger.debug("Records intent — skip auth, silent transition to Routing")
        return SILENT_TO_ROUTING
    return None


# --- BH classification-retry machine (Req 7.11, 7.12) ----------------------

#: Number of times the Business Hours phase speaks a retry line before falling
#: back. The Retry-1 line is spoken on the 1st not-understood turn and the
#: Retry-2 line on the 2nd; on the 3rd consecutive failure the phase stops
#: speaking retries and transitions to Routing as a silent turn (Req 7.11, 7.12).
BH_CLASSIFICATION_MAX_RETRIES: int = 2


@dataclass(frozen=True)
class BHClassificationRetryDecision:
    """What to do after N consecutive intent-classification failures (Req 7.11-12).

    Encodes the Business-Hours classification-retry outcome for a given
    consecutive-failure count: either a verbatim spoken retry line, or — once the
    two spoken retries are exhausted — a silent transition to Routing. The value
    is immutable so it can be shared/compared freely in property tests.

    Exactly one of the two outcomes is present:

    * ``spoken_line`` is set (Retry-1 / Retry-2) and ``silent_transition`` is
      ``None`` for the 1st and 2nd failures, or
    * ``spoken_line`` is ``None`` and ``silent_transition`` is
      :data:`SILENT_TO_ROUTING` for the 3rd and any subsequent failure.
    """

    consecutive_failures: int
    spoken_line: Optional[str]
    silent_transition: Optional[SilentRoutingTransition]

    @property
    def is_silent(self) -> bool:
        """Whether this decision speaks nothing and transitions to Routing."""
        return self.spoken_line is None


def bh_classification_retry(
    consecutive_failures: int,
) -> BHClassificationRetryDecision:
    """Return the retry decision after ``consecutive_failures`` classification misses.

    Implements the Business-Hours classification-retry machine (Requirements 7.11,
    7.12, POC-08). ``consecutive_failures`` is the number of consecutive turns on
    which ``intent`` could not be classified, **including the current one**
    (1-based): the current failure is the ``consecutive_failures``-th in a row.

    * ``1`` → speak the verbatim Retry-1 line (:data:`~scripts.BH_RETRY_1`).
    * ``2`` → speak the verbatim Retry-2 line (:data:`~scripts.BH_RETRY_2`).
    * ``3`` or more → speak nothing and transition to Routing as a silent turn
      (:data:`SILENT_TO_ROUTING`), with no spoken filler (Req 7.12).

    Mirrors the Greeting Path E repeat-then-fall-back machine
    (:func:`~api.services.switchboard.greeting.path_e_response`); the difference
    is that Business Hours falls back to a *silent* Routing transition rather than
    a spoken line.

    Args:
        consecutive_failures: Count of consecutive classification failures,
            including the current one. Must be at least ``1``.

    Returns:
        The :class:`BHClassificationRetryDecision` for the failure count.

    Raises:
        ValueError: If ``consecutive_failures`` is less than ``1``.
    """
    if consecutive_failures < 1:
        raise ValueError(
            f"consecutive_failures must be >= 1, got {consecutive_failures}"
        )

    if consecutive_failures == 1:
        return BHClassificationRetryDecision(
            consecutive_failures=consecutive_failures,
            spoken_line=scripts.BH_RETRY_1,
            silent_transition=None,
        )
    if consecutive_failures == BH_CLASSIFICATION_MAX_RETRIES:
        return BHClassificationRetryDecision(
            consecutive_failures=consecutive_failures,
            spoken_line=scripts.BH_RETRY_2,
            silent_transition=None,
        )

    logger.debug(
        "Third+ consecutive classification failure ({}) — silent transition to "
        "Routing",
        consecutive_failures,
    )
    return BHClassificationRetryDecision(
        consecutive_failures=consecutive_failures,
        spoken_line=None,
        silent_transition=SILENT_TO_ROUTING,
    )


@dataclass(frozen=True)
class BHClassificationRetryState:
    """Immutable consecutive-failure counter for BH intent classification.

    Tracks the number of consecutive turns on which ``intent`` could not be
    classified. State transitions return a new instance (the value is never
    mutated in place), keeping the machine pure. A fresh state has zero failures;
    a not-understood turn advances it, and any successful classification resets
    it. Mirrors :class:`~api.services.switchboard.greeting.PathERetryState`.
    """

    consecutive_failures: int = 0

    def record_failure(self) -> "BHClassificationRetryState":
        """Return a new state with the consecutive-failure count incremented by one."""
        return BHClassificationRetryState(self.consecutive_failures + 1)

    def reset(self) -> "BHClassificationRetryState":
        """Return a fresh state with the consecutive-failure count cleared to zero."""
        return BHClassificationRetryState(0)

    @property
    def has_fallen_back(self) -> bool:
        """Whether classification has fallen back to a silent Routing transition."""
        return self.consecutive_failures > BH_CLASSIFICATION_MAX_RETRIES

    @property
    def decision(self) -> BHClassificationRetryDecision:
        """Return the retry decision for the current failure count.

        Only meaningful after at least one :meth:`record_failure`; delegates to
        :func:`bh_classification_retry`, which requires a count of at least ``1``.

        Raises:
            ValueError: If no failure has been recorded yet
                (``consecutive_failures`` is ``0``).
        """
        return bh_classification_retry(self.consecutive_failures)


# --- Search-trouble line for a no-match search (Req 7.13) ------------------


def search_trouble_response() -> str:
    """Return the verbatim "Search trouble" line for a no-match search (Req 7.13).

    When a directory or provider search returns no matching record, the Business
    Hours phase speaks the mandated :data:`~scripts.BH_SEARCH_TROUBLE` line, which
    offers to connect the caller with someone who can help. This is the verbatim
    Appendix C constant; no wording is authored here.

    Returns:
        The verbatim :data:`~scripts.BH_SEARCH_TROUBLE` line.
    """
    return scripts.BH_SEARCH_TROUBLE


__all__ = [
    # Appointment-action classification (subtask 8.1, Property 11)
    "AppointmentAction",
    "classify_appointment_action",
    # Lookup-speech prefix rules (subtask 8.3, Property 10)
    "LookupType",
    "LookupSpeechDecision",
    "FIRST_DIRECTORY_LOOKUP_PREFIX",
    "lookup_speech_prefix",
    # Manage-action consequences + retry machine (subtask 8.5, Property 12)
    "PATIENT_STATUS_EXISTING",
    "PATIENT_STATUS_NEW",
    "RECORDS_INTENT",
    "MANAGE_ACTIONS",
    "is_manage_action",
    "AppointmentActionConsequences",
    "appointment_action_consequences",
    "SilentRoutingTransition",
    "SILENT_TO_ROUTING",
    "intent_skips_auth",
    "records_auth_skip",
    "BH_CLASSIFICATION_MAX_RETRIES",
    "BHClassificationRetryDecision",
    "bh_classification_retry",
    "BHClassificationRetryState",
    "search_trouble_response",
]
