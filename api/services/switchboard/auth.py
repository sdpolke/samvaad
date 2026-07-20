"""Authentication-phase pure decision logic for the SpinSci switchboard (Req 9, 11).

This module owns the deterministic, side-effect-free decision logic of the
Authentication phase. Like :mod:`api.services.switchboard.greeting` and
:mod:`api.services.switchboard.business_hours`, everything here operates purely on
its inputs (and the Call State Ledger's field values) — it never touches the LLM,
TTS, lookup/verify tools, or telephony — so each function is directly unit- and
property-testable and is wired into the Authentication node cluster by a later
graph-builder task.

Scope of this module (built up across subtasks 9.1 and 9.3):

* **9.1 (this file's first sections):** the auth-gate / auth-matrix decision —
  whether authentication is *required* for a given ``intent``/``patient_status``
  (REQ-AUTH-01, Req 9.3-9.5), the ``patient_status=existing`` default for the
  intents that never ask new/existing (Req 9.5), and the GATE-AUTH predicate that
  blocks ``transfer`` and ``route_metadata_resolution`` until ``patient_verified``
  becomes Success / Fail / N/A (Req 9.2, 11.2, Property 13).
* **9.3 (added to this same module afterward):** ANI-reuse guard, fail/refusal
  still-connects, changed-request routing, and DOB-determined verification
  (Req 9.1, 9.6, 9.7, 9.8, 9.10, 9.11, 9.12).

Later sections are appended to this same module; the section banners below mark
where they belong so the file stays organized as it grows. The ``Intent`` enum,
the ``PATIENT_VERIFIED_*`` vocabulary, and the auth-required matrix defined here
are the seams subtask 9.3 (and the Routing phase, task 11) build on.

Design references:
- ``design.md`` → "Authentication cluster (Req 9)" and Correctness Property 13
  (GATE-AUTH)
- ``requirements.md`` → Requirement 9 (9.2 gate, 9.3 required set, 9.4 skip set,
  9.5 default-existing) and Requirement 11 (11.2 require-auth-then-route)

Requirements: 9.2, 9.3, 9.4, 9.5, 11.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union

from loguru import logger

from api.services.switchboard import scripts
from api.services.switchboard.business_hours import (
    PATIENT_STATUS_EXISTING,
    PATIENT_STATUS_NEW,
)

# ===========================================================================
# Switchboard intent vocabulary (Appendix B route matrix)
# ===========================================================================


class Intent(str, Enum):
    """The switchboard ``intent`` classification values (ledger ``intent``).

    These are the intent labels the switchboard's route matrix (Appendix B)
    distinguishes and that the auth matrix (Req 9.3-9.5) keys off. The ledger
    stores ``intent`` as a free string (Appendix D); use :func:`normalize_intent`
    to map a raw ledger value onto one of these members case-insensitively before
    comparing, since caller/upstream casing varies (e.g. ``"mychart"`` in Req 9.3
    vs. ``"MyChart"`` in Req 9.5).

    Being a ``str`` subclass, a member compares/serializes as its canonical value.
    """

    SCHEDULING = "Scheduling"
    REFERRALS = "Referrals"
    TRIAGE = "Triage"
    BILLING = "Billing"
    MYCHART = "MyChart"
    PAGING = "Paging"
    DIRECTORY = "Directory"
    PHARMACY = "Pharmacy"
    GENERAL = "General"
    RECORDS = "Records"


#: Case-insensitive lookup from a normalized (lower-cased) intent string to its
#: :class:`Intent` member. Built from the enum so the two can never drift apart.
_INTENT_BY_LOWER: dict[str, Intent] = {
    member.value.lower(): member for member in Intent
}


def normalize_intent(intent: Union[str, Intent, None]) -> Optional[Intent]:
    """Map a raw ledger ``intent`` value onto an :class:`Intent`, else ``None``.

    The ledger stores ``intent`` as a free string, so upstream casing/whitespace
    varies. This resolves a raw value to its canonical :class:`Intent` member
    case-insensitively and whitespace-tolerantly (so ``"mychart"``, ``"MyChart"``
    and ``"  mychart "`` all resolve to :attr:`Intent.MYCHART`). An
    :class:`Intent` passed through is returned unchanged.

    Args:
        intent: A raw ledger intent string, an :class:`Intent`, or ``None``.

    Returns:
        The matching :class:`Intent`, or ``None`` when the value is empty or not
        a recognized switchboard intent (e.g. an unresolved/Fallback intent).
    """
    if intent is None:
        return None
    if isinstance(intent, Intent):
        return intent
    return _INTENT_BY_LOWER.get(intent.strip().lower())


# ===========================================================================
# Auth requirement matrix (REQ-AUTH-01, Req 9.3, 9.4, 9.5) — subtask 9.1
# ===========================================================================

#: Intents that require authentication (before routing) when the patient is not
#: new (Req 9.3, REQ-AUTH-01). ``Records`` is deliberately absent — it always
#: skips auth (Req 9.4). Membership — not string literals — drives the matrix so
#: it stays in lock-step with :class:`Intent`.
AUTH_REQUIRED_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.SCHEDULING,
        Intent.REFERRALS,
        Intent.TRIAGE,
        Intent.BILLING,
        Intent.MYCHART,
        Intent.PAGING,
        Intent.DIRECTORY,
        Intent.PHARMACY,
        Intent.GENERAL,
    }
)

#: Intents for which the switchboard defaults ``patient_status`` to ``existing``
#: and never asks the new/existing question (Req 9.5, REQ-AUTH-01
#: "Default to existing"). For these intents ``patient_status`` is therefore
#: always ``existing`` at the auth gate, so authentication is always required.
DEFAULT_EXISTING_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.BILLING,
        Intent.MYCHART,
        Intent.PAGING,
        Intent.DIRECTORY,
        Intent.PHARMACY,
        Intent.GENERAL,
    }
)


def _is_new_patient(patient_status: Optional[str]) -> bool:
    """Return whether ``patient_status`` explicitly says the caller is a new patient.

    Matched case-insensitively and whitespace-tolerantly against
    :data:`~api.services.switchboard.business_hours.PATIENT_STATUS_NEW`. A ``None``
    /blank/unknown status is **not** treated as new — it is not-yet-established —
    so the auth gate defaults to *requiring* auth rather than skipping it.
    """
    return bool(
        patient_status and patient_status.strip().lower() == PATIENT_STATUS_NEW
    )


def auth_required(
    intent: Union[str, Intent, None], patient_status: Optional[str] = None
) -> bool:
    """Return whether authentication is required for ``intent``/``patient_status``.

    Implements the auth requirement matrix (REQ-AUTH-01, Requirements 9.3, 9.4,
    Property 13). Authentication is *skipped* in exactly two cases, and *required*
    for every auth-matrix intent otherwise:

    * **Records** → skipped (Req 9.4). Records transitions straight to Routing as
      a silent turn (still routes; the skip is of the auth step only).
    * **New-patient Scheduling** (``intent`` Scheduling and ``patient_status`` is
      ``new``) → skipped (Req 9.4, POC-01c). This is the new-patient ``create``
      path, which still routes to the general intake path before any transfer.
    * **Any other intent in** :data:`AUTH_REQUIRED_INTENTS` → required (Req 9.3,
      11.2). This holds regardless of ``patient_status`` for the non-Scheduling
      intents; the default-existing intents (:data:`DEFAULT_EXISTING_INTENTS`)
      never reach the gate as ``new`` anyway (Req 9.5).
    * **Unrecognized / unresolved intent** (``None`` after normalization, e.g. a
      Fallback) → not required here (no protected data to gate).

    The skip set is intentionally closed to *only* Records and new-patient
    Scheduling — matching Property 13 ("authentication is skipped only for Records
    and new-patient create") — so the gate errs toward requiring authentication.
    In particular, an unknown/None ``patient_status`` for an auth-matrix intent is
    treated as *not* new, so auth is still required (the secure default).

    Args:
        intent: The ledger ``intent`` value (raw string, :class:`Intent`, or
            ``None``). Normalized via :func:`normalize_intent`.
        patient_status: The ledger ``patient_status`` (``new`` / ``existing`` /
            ``None``). Only consulted for :attr:`Intent.SCHEDULING`.

    Returns:
        ``True`` when authentication must complete before routing/transfer,
        ``False`` when it is skipped for this intent/status.
    """
    resolved = normalize_intent(intent)

    if resolved is None:
        logger.debug("Unrecognized intent {!r} — auth not required", intent)
        return False

    if resolved is Intent.RECORDS:
        logger.debug("Records intent — auth skipped (still routes)")
        return False

    if resolved is Intent.SCHEDULING and _is_new_patient(patient_status):
        logger.debug("New-patient Scheduling — auth skipped (still routes)")
        return False

    required = resolved in AUTH_REQUIRED_INTENTS
    logger.debug(
        "Auth {} for intent={} patient_status={!r}",
        "required" if required else "not required",
        resolved.value,
        patient_status,
    )
    return required


# ===========================================================================
# patient_status=existing default (Req 9.5) — subtask 9.1
# ===========================================================================


def defaults_to_existing(intent: Union[str, Intent, None]) -> bool:
    """Return whether ``intent`` defaults ``patient_status`` to existing (Req 9.5).

    For Billing, MyChart, Paging, Directory, Pharmacy, and General
    (:data:`DEFAULT_EXISTING_INTENTS`) the switchboard treats the caller as an
    existing patient and never asks the new/existing question (Req 9.5,
    REQ-AUTH-01 "Default to existing"). Every other intent — including Scheduling,
    which asks new/existing for ``create`` — returns ``False``.

    Args:
        intent: The ledger ``intent`` value (raw string, :class:`Intent`, or
            ``None``). Normalized via :func:`normalize_intent`.

    Returns:
        ``True`` when the intent defaults ``patient_status`` to existing and skips
        the new/existing question, ``False`` otherwise.
    """
    return normalize_intent(intent) in DEFAULT_EXISTING_INTENTS


def should_ask_new_or_existing(intent: Union[str, Intent, None]) -> bool:
    """Return whether the switchboard should ask the new/existing question (Req 9.5).

    The inverse of :func:`defaults_to_existing`: the default-existing intents never
    ask new/existing, so this returns ``False`` for them and ``True`` for every
    other intent. (Whether a *Scheduling* ``create`` actually asks is further
    gated by the appointment-action consequences in
    :mod:`api.services.switchboard.business_hours`; this reflects only the
    intent-level default of Req 9.5.)

    Args:
        intent: The ledger ``intent`` value. Normalized via
            :func:`normalize_intent`.

    Returns:
        ``False`` for a default-existing intent, ``True`` otherwise.
    """
    return not defaults_to_existing(intent)


def default_patient_status(
    intent: Union[str, Intent, None], patient_status: Optional[str] = None
) -> Optional[str]:
    """Return the ``patient_status`` the switchboard should hold for ``intent``.

    Applies the Req 9.5 default: for a default-existing intent
    (:func:`defaults_to_existing`) the resulting ``patient_status`` is
    :data:`~api.services.switchboard.business_hours.PATIENT_STATUS_EXISTING`,
    overriding whatever (if anything) was previously set — those intents never ask
    new/existing, so the caller is always treated as existing. For every other
    intent the prior ``patient_status`` is carried through unchanged.

    Args:
        intent: The ledger ``intent`` value. Normalized via
            :func:`normalize_intent`.
        patient_status: The current ledger ``patient_status`` (``None`` when not
            yet established). Preserved for non-default-existing intents.

    Returns:
        ``"existing"`` for a default-existing intent, otherwise ``patient_status``
        unchanged.
    """
    if defaults_to_existing(intent):
        logger.debug(
            "Intent {!r} defaults patient_status to existing (Req 9.5)", intent
        )
        return PATIENT_STATUS_EXISTING
    return patient_status


# ===========================================================================
# GATE-AUTH: block transfer + route_metadata_resolution (Req 9.2, 11.2) — 9.1
# ===========================================================================

#: ``patient_verified`` ledger value set when the caller's identity was verified.
PATIENT_VERIFIED_SUCCESS: str = "Success"

#: ``patient_verified`` ledger value set when identity verification failed.
PATIENT_VERIFIED_FAIL: str = "Fail"

#: ``patient_verified`` ledger value set when authentication does not apply
#: (e.g. the after-hours hotword immediate path, Req 8.3).
PATIENT_VERIFIED_NA: str = "N/A"

#: The set of ``patient_verified`` values that mean the authentication step has
#: reached a terminal outcome and the GATE-AUTH gate may open (Req 9.2,
#: Property 13). ``None`` (not yet run) is deliberately absent.
AUTH_RESOLVED_STATES: frozenset[str] = frozenset(
    {
        PATIENT_VERIFIED_SUCCESS,
        PATIENT_VERIFIED_FAIL,
        PATIENT_VERIFIED_NA,
    }
)

#: Case-insensitive lookup of the resolved ``patient_verified`` states, so a
#: differently-cased ledger value (e.g. ``"success"`` / ``"n/a"``) still resolves.
_RESOLVED_STATE_BY_LOWER: dict[str, str] = {
    state.lower(): state for state in AUTH_RESOLVED_STATES
}


def is_patient_verified_resolved(patient_verified: Optional[str]) -> bool:
    """Return whether ``patient_verified`` holds a terminal Success/Fail/N/A value.

    The GATE-AUTH gate opens once ``patient_verified`` becomes one of Success,
    Fail, or N/A (Req 9.2, Property 13). A ``None``/blank value means
    authentication has not yet produced a result and the gate stays closed. The
    comparison is case-insensitive and whitespace-tolerant.

    Args:
        patient_verified: The ledger ``patient_verified`` value.

    Returns:
        ``True`` when the value is one of Success / Fail / N/A, ``False`` for
        ``None``/blank or any other value.
    """
    if not patient_verified:
        return False
    return patient_verified.strip().lower() in _RESOLVED_STATE_BY_LOWER


def may_proceed_to_routing(
    intent: Union[str, Intent, None],
    patient_status: Optional[str],
    patient_verified: Optional[str],
) -> bool:
    """Return whether routing/transfer may proceed for the current auth state.

    This is the GATE-AUTH predicate (Requirements 9.2, 11.2, Property 13). It
    answers "may routing/transfer proceed?" and is what structurally blocks the
    ``transfer`` and ``route_metadata_resolution`` tools until authentication is
    resolved. The gate is **open** (returns ``True``) exactly when either:

    * authentication is not required for this ``intent``/``patient_status``
      (:func:`auth_required` is ``False`` — e.g. Records or new-patient
      Scheduling, which still route), **or**
    * ``patient_verified`` has reached a terminal Success / Fail / N/A value
      (:func:`is_patient_verified_resolved`).

    While authentication is required and ``patient_verified`` is still null, the
    gate is **closed** (returns ``False``): no ``transfer`` and no
    ``route_metadata_resolution`` may occur (Req 9.2, POC-10). Note that a failed
    verification (``Fail``) still *opens* the gate — a fail/refusal still connects
    (Req 9.7); it is the *null* (not-yet-run) state that keeps it closed.

    Args:
        intent: The ledger ``intent`` value. Normalized via
            :func:`normalize_intent`.
        patient_status: The ledger ``patient_status`` (``new`` / ``existing`` /
            ``None``).
        patient_verified: The ledger ``patient_verified`` value (``Success`` /
            ``Fail`` / ``N/A`` / ``None``).

    Returns:
        ``True`` when routing intent metadata resolution and transfer may proceed,
        ``False`` while the auth gate must keep them blocked.
    """
    if not auth_required(intent, patient_status):
        return True

    resolved = is_patient_verified_resolved(patient_verified)
    if not resolved:
        logger.debug(
            "GATE-AUTH closed: auth required for intent={!r} but patient_verified"
            "={!r}",
            intent,
            patient_verified,
        )
    return resolved


# ===========================================================================
# Authentication flow, ANI reuse, fail/refusal-connects, changed-request, and
# DOB-determined verification — subtask 9.3
# (Requirements 9.1, 9.6, 9.7, 9.8, 9.10, 9.11, 9.12)
# ===========================================================================
#
# Everything below is pure, deterministic, and side-effect-free (no LLM/TTS/
# lookup-verify tools/telephony), so it is directly unit- and property-testable
# and is wired into the Authentication node cluster by a later graph-builder
# task. Any caller-facing wording is reused **verbatim** from
# :mod:`api.services.switchboard.scripts` (Appendix C); this module only selects
# which mandated line applies and which phase/terminal to move to, never
# re-authoring any text.


# --- Authentication flow order (Req 9.1) -----------------------------------


class AuthStep(str, Enum):
    """The ordered steps of the Authentication flow (Req 9.1).

    The Authentication phase follows a fixed sequence — phone number → read-back →
    patient lookup → date of birth → identity validation → Routing (Req 9.1). The
    members are the ordered stages of that flow (see :data:`AUTH_FLOW_SEQUENCE`);
    :func:`next_auth_step` walks it, honoring the ANI-reuse guard (Req 9.6) that
    skips the ``PATIENT_LOOKUP`` step when Greeting already looked the caller up.
    """

    PHONE = "phone"
    READ_BACK = "read_back"
    PATIENT_LOOKUP = "patient_lookup"
    DOB = "dob"
    IDENTITY = "identity"
    ROUTING = "routing"


#: The canonical Authentication flow order (Req 9.1). The tuple order *is* the
#: contract: phone → read-back → patient lookup → DOB → identity → Routing.
#: :func:`next_auth_step` advances through it; Routing is the terminal step.
AUTH_FLOW_SEQUENCE: tuple[AuthStep, ...] = (
    AuthStep.PHONE,
    AuthStep.READ_BACK,
    AuthStep.PATIENT_LOOKUP,
    AuthStep.DOB,
    AuthStep.IDENTITY,
    AuthStep.ROUTING,
)


def next_auth_step(
    current: AuthStep, greeting_ani_lookup_done: bool = False
) -> Optional[AuthStep]:
    """Return the next Authentication step after ``current`` (Req 9.1, 9.6).

    Walks :data:`AUTH_FLOW_SEQUENCE` in order (Req 9.1). When advancing *into* the
    :attr:`AuthStep.PATIENT_LOOKUP` step while ``greeting_ani_lookup_done`` is
    true, the lookup is skipped — the Greeting ANI result is reused and the flow
    advances straight to :attr:`AuthStep.DOB` instead (Req 9.6; see also
    :func:`ani_lookup_decision`). Returns ``None`` when ``current`` is the terminal
    :attr:`AuthStep.ROUTING` step (the flow has completed).

    Args:
        current: The current Authentication step.
        greeting_ani_lookup_done: The ledger ``greeting_ani_lookup_done`` flag.
            When true, the redundant patient-lookup step is skipped (Req 9.6).

    Returns:
        The next :class:`AuthStep`, or ``None`` after the terminal Routing step.
    """
    index = AUTH_FLOW_SEQUENCE.index(current)
    if index + 1 >= len(AUTH_FLOW_SEQUENCE):
        return None

    nxt = AUTH_FLOW_SEQUENCE[index + 1]
    if nxt is AuthStep.PATIENT_LOOKUP and greeting_ani_lookup_done:
        logger.debug(
            "ANI lookup already done in Greeting — skipping Authentication "
            "patient-lookup step (Req 9.6)"
        )
        return AuthStep.DOB
    return nxt


# --- ANI-reuse guard (Req 9.6) ---------------------------------------------


class AniLookupDecision(str, Enum):
    """Whether Authentication should reuse or perform the ANI patient lookup.

    Drives the ANI-reuse guard (:func:`ani_lookup_decision`, Req 9.6):

    * :attr:`REUSE` — a turn-1 ANI patient lookup already completed in Greeting
      (``greeting_ani_lookup_done`` is true); reuse that result and do **not**
      repeat the lookup in Authentication.
    * :attr:`PERFORM` — no prior ANI lookup was done; Authentication performs the
      patient lookup.
    """

    REUSE = "reuse"
    PERFORM = "perform"


def ani_lookup_decision(greeting_ani_lookup_done: bool) -> AniLookupDecision:
    """Return whether Authentication reuses or performs the ANI lookup (Req 9.6).

    The ANI-reuse guard. When the ledger ``greeting_ani_lookup_done`` flag is true,
    the turn-1 ANI patient lookup already ran in Greeting, so Authentication
    **reuses** that result and does not repeat the lookup (Req 9.6, Property 14) —
    :attr:`AniLookupDecision.REUSE`. Otherwise it performs the lookup —
    :attr:`AniLookupDecision.PERFORM`.

    Args:
        greeting_ani_lookup_done: The ledger ``greeting_ani_lookup_done`` flag.

    Returns:
        :attr:`AniLookupDecision.REUSE` when a Greeting ANI lookup already
        completed, else :attr:`AniLookupDecision.PERFORM`.
    """
    if greeting_ani_lookup_done:
        logger.debug("Reusing Greeting ANI lookup — no repeat in Authentication")
        return AniLookupDecision.REUSE
    return AniLookupDecision.PERFORM


def should_reuse_ani_lookup(greeting_ani_lookup_done: bool) -> bool:
    """Return whether Authentication should reuse the Greeting ANI lookup (Req 9.6).

    Boolean convenience over :func:`ani_lookup_decision`: ``True`` (reuse / do not
    repeat the lookup) exactly when ``greeting_ani_lookup_done`` is true.
    """
    return ani_lookup_decision(greeting_ani_lookup_done) is AniLookupDecision.REUSE


def should_perform_ani_lookup(greeting_ani_lookup_done: bool) -> bool:
    """Return whether Authentication should perform the ANI lookup (Req 9.6).

    The inverse of :func:`should_reuse_ani_lookup`: ``True`` only when no prior
    Greeting ANI lookup completed, so Authentication must perform the lookup.
    """
    return ani_lookup_decision(greeting_ani_lookup_done) is AniLookupDecision.PERFORM


# --- Fail / refusal / attempt-exhaustion still connects (Req 9.7, 9.12) -----

#: Maximum number of phone-number attempts before the caller is routed without
#: hanging up for the failure alone (Req 9.12, AC-11). After this many failed
#: attempts the outcome is :attr:`AuthOutcome.ATTEMPTS_EXHAUSTED`.
AUTH_MAX_PHONE_ATTEMPTS: int = 3


class AuthOutcome(str, Enum):
    """The terminal outcome of the Authentication phase (Req 9.7, 9.11, 9.12).

    * :attr:`SUCCESS` — identity was verified (DOB matched — see
      :func:`patient_verified_from_dob`).
    * :attr:`FAILED` — identity verification failed (DOB mismatch).
    * :attr:`REFUSED` — the caller refused to authenticate.
    * :attr:`ATTEMPTS_EXHAUSTED` — the caller could not provide a matching phone
      number after :data:`AUTH_MAX_PHONE_ATTEMPTS` attempts (Req 9.12).

    Every one of these outcomes still connects the caller (transfer) — a
    fail/refusal/exhaustion never hangs up for the failure alone (Req 9.7, 9.12);
    see :func:`auth_outcome_connects` and :func:`next_terminal_after_auth`.
    """

    SUCCESS = "success"
    FAILED = "failed"
    REFUSED = "refused"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


class AuthTerminal(str, Enum):
    """The terminal telephony action taken after Authentication (Req 9.7).

    :attr:`TRANSFER` connects the caller; :attr:`HANGUP` ends the call. The member
    exists so :func:`next_terminal_after_auth` can make explicit that **no**
    Authentication outcome maps to :attr:`HANGUP` for a refusal/failure alone
    (Req 9.7, 9.12) — the next terminal is always :attr:`TRANSFER`.
    """

    TRANSFER = "transfer"
    HANGUP = "hangup"


def phone_attempts_exhausted(attempts_used: int) -> bool:
    """Return whether the caller has used all phone-number attempts (Req 9.12).

    ``True`` once ``attempts_used`` reaches :data:`AUTH_MAX_PHONE_ATTEMPTS` (3),
    the point at which the caller is routed without hanging up for the failure
    alone (Req 9.12, AC-11).

    Args:
        attempts_used: The number of failed phone-number attempts so far.

    Returns:
        ``True`` when ``attempts_used`` is at least
        :data:`AUTH_MAX_PHONE_ATTEMPTS`, else ``False``.
    """
    return attempts_used >= AUTH_MAX_PHONE_ATTEMPTS


def auth_outcome_connects(outcome: AuthOutcome) -> bool:
    """Return whether an Authentication ``outcome`` still connects the caller.

    Always ``True``. Refusal, verification failure, and attempt-exhaustion each
    still connect the caller (transfer), exactly like success — the switchboard
    never hangs up for a refusal or failure alone (Req 9.7, 9.12, AC-11, POC-06).
    Modeled over the full :class:`AuthOutcome` enum so a property test can assert
    that *no* outcome maps to a non-connecting result.

    Args:
        outcome: The Authentication outcome.

    Returns:
        ``True`` for every :class:`AuthOutcome` — the caller is always connected.
    """
    logger.debug("Auth outcome {} connects (transfer, never hangup)", outcome.value)
    return True


def next_terminal_after_auth(outcome: AuthOutcome) -> AuthTerminal:
    """Return the terminal telephony action after an Authentication ``outcome``.

    Always :attr:`AuthTerminal.TRANSFER`. Whether the caller succeeded, failed,
    refused, or exhausted their phone attempts, the next terminal is a transfer
    (connect) — never a hangup for the failure alone (Req 9.7, 9.12, AC-11,
    POC-06). This is the terminal-selection counterpart of
    :func:`auth_outcome_connects`.

    Args:
        outcome: The Authentication outcome.

    Returns:
        :attr:`AuthTerminal.TRANSFER` for every outcome.
    """
    return AuthTerminal.TRANSFER


def should_speak_fail_route_line(outcome: AuthOutcome) -> bool:
    """Return whether the fail/refusal route line should be spoken (Req 9.7).

    The "No problem. I'll connect you now." line (:func:`auth_fail_route_line`) is
    spoken when the caller refused, failed verification, or exhausted their phone
    attempts — i.e. for every non-:attr:`AuthOutcome.SUCCESS` outcome. On a
    successful verification the caller is routed without that line.

    Args:
        outcome: The Authentication outcome.

    Returns:
        ``True`` for any outcome other than :attr:`AuthOutcome.SUCCESS`.
    """
    return outcome is not AuthOutcome.SUCCESS


def auth_fail_route_line() -> str:
    """Return the verbatim fail/refusal → route line (Req 9.7, Appendix C).

    On auth refusal or failure the Authentication phase speaks the mandated
    :data:`~api.services.switchboard.scripts.AUTH_FAIL_ROUTE` line
    ("No problem. I'll connect you now.") and routes on the same turn, never
    hanging up for refusal alone (Req 9.7, AC-11, POC-06). This returns the
    verbatim Appendix C constant; no wording is authored here.
    """
    return scripts.AUTH_FAIL_ROUTE


# --- Changed-request routing (Req 9.8) -------------------------------------


class ReturnPhase(str, Enum):
    """The phase Authentication returns to on a changed request (Req 9.8).

    A caller who changes their request mid-Authentication is sent back to the
    hours-appropriate phase — **never** straight to Routing (Req 9.8, AC-06,
    POC-09):

    * :attr:`BUSINESS_HOURS` — returned to when the call is in business hours
      (``after_hours`` is false); modeled as an edge back to ``BH0``.
    * :attr:`AFTER_HOURS` — returned to when the call is after hours
      (``after_hours`` is true); modeled as an edge back to ``AH0``.

    Routing is deliberately **not** a member: it is never the changed-request
    target.
    """

    BUSINESS_HOURS = "business_hours"
    AFTER_HOURS = "after_hours"


@dataclass(frozen=True)
class ChangedRequestTransition:
    """The transition taken when the caller changes their request in Auth (Req 9.8).

    Bundles the three parts of the changed-request decision so a graph-builder
    wires it correctly. Immutable so it can be shared/compared freely in property
    tests.

    Attributes:
        line: The verbatim changed-request line
            (:data:`~api.services.switchboard.scripts.AUTH_CHANGED_REQUEST`) spoken
            on the transition.
        return_phase: The hours-appropriate phase to return to
            (:class:`ReturnPhase`) — Business Hours or After Hours.
        to_routing: Always ``False`` — a changed request never goes straight to
            Routing (Req 9.8, AC-06, POC-09).
    """

    line: str
    return_phase: ReturnPhase
    to_routing: bool = False


def changed_request_return_phase(after_hours: bool) -> ReturnPhase:
    """Return the phase Authentication returns to on a changed request (Req 9.8).

    Maps the ledger ``after_hours`` flag onto the hours-appropriate return phase:
    :attr:`ReturnPhase.AFTER_HOURS` when ``after_hours`` is true, else
    :attr:`ReturnPhase.BUSINESS_HOURS`. Routing is never returned (Req 9.8, AC-06,
    POC-09).

    Args:
        after_hours: The ledger ``after_hours`` flag.

    Returns:
        :attr:`ReturnPhase.AFTER_HOURS` when after hours, else
        :attr:`ReturnPhase.BUSINESS_HOURS`.
    """
    return ReturnPhase.AFTER_HOURS if after_hours else ReturnPhase.BUSINESS_HOURS


def changed_request_transition(after_hours: bool) -> ChangedRequestTransition:
    """Return the full changed-request transition for Authentication (Req 9.8).

    On a changed request the Authentication phase speaks the verbatim
    :data:`~api.services.switchboard.scripts.AUTH_CHANGED_REQUEST` line
    ("Sure, let me get you to the right place for that.") and returns to Business
    Hours or After Hours per :func:`changed_request_return_phase` — never straight
    to Routing (Req 9.8, AC-06, POC-09). The returned
    :class:`ChangedRequestTransition` always carries ``to_routing=False``,
    encoding that invariant explicitly.

    Args:
        after_hours: The ledger ``after_hours`` flag.

    Returns:
        The :class:`ChangedRequestTransition` describing the spoken line and the
        (non-Routing) phase to return to.
    """
    phase = changed_request_return_phase(after_hours)
    logger.debug("Changed request during Auth — returning to {} (never Routing)", phase.value)
    return ChangedRequestTransition(
        line=scripts.AUTH_CHANGED_REQUEST,
        return_phase=phase,
        to_routing=False,
    )


# --- DOB-determined identity verification (Req 9.11) -----------------------


def dob_matches(provided_dob: Optional[str], dob_on_file: Optional[str]) -> bool:
    """Return whether a provided DOB matches the one on file (Req 9.11).

    Compares the caller-provided date of birth against the record's DOB
    whitespace-tolerantly. A ``None``/blank on either side is treated as a
    non-match (there is nothing to verify against), yielding ``False``.

    Args:
        provided_dob: The date of birth the caller provided.
        dob_on_file: The date of birth on the patient record.

    Returns:
        ``True`` when both values are present and equal after stripping
        surrounding whitespace, else ``False``.
    """
    if not provided_dob or not dob_on_file:
        return False
    return provided_dob.strip() == dob_on_file.strip()


def patient_verified_from_dob(dob_match: bool) -> str:
    """Return the ``patient_verified`` value determined by a DOB match (Req 9.11).

    Identity validation sets ``patient_verified`` to
    :data:`PATIENT_VERIFIED_SUCCESS` **only** when the provided date of birth
    matches the record, and to :data:`PATIENT_VERIFIED_FAIL` otherwise (Req 9.11,
    Property 18). Callers that hold the raw provided/on-file values can obtain the
    match boolean via :func:`dob_matches` first.

    Args:
        dob_match: Whether the provided DOB matched the record.

    Returns:
        :data:`PATIENT_VERIFIED_SUCCESS` on a match, else
        :data:`PATIENT_VERIFIED_FAIL`.
    """
    result = PATIENT_VERIFIED_SUCCESS if dob_match else PATIENT_VERIFIED_FAIL
    logger.debug("DOB match={} → patient_verified={}", dob_match, result)
    return result


# --- No record found (Req 9.10, 9.12) --------------------------------------


class NoRecordOutcome(str, Enum):
    """What to do when no patient record is found for a phone number (Req 9.10, 9.12).

    * :attr:`REPROMPT_DIFFERENT_NUMBER` — speak the "No record" line
      (:func:`no_record_line`) and ask for a different number, while phone attempts
      remain (Req 9.10).
    * :attr:`ROUTE_WITHOUT_HANGUP` — once phone attempts are exhausted
      (:func:`phone_attempts_exhausted`), route the caller without hanging up for
      the failure alone (Req 9.12).
    """

    REPROMPT_DIFFERENT_NUMBER = "reprompt_different_number"
    ROUTE_WITHOUT_HANGUP = "route_without_hangup"


def no_record_decision(attempts_used: int) -> NoRecordOutcome:
    """Return what to do after a no-record phone lookup (Req 9.10, 9.12).

    Called when a phone-number lookup found no patient record. While phone
    attempts remain, the caller is re-prompted for a different number
    (:attr:`NoRecordOutcome.REPROMPT_DIFFERENT_NUMBER`, Req 9.10). Once
    ``attempts_used`` reaches :data:`AUTH_MAX_PHONE_ATTEMPTS`
    (:func:`phone_attempts_exhausted`), the caller is routed without hanging up
    for the failure alone (:attr:`NoRecordOutcome.ROUTE_WITHOUT_HANGUP`, Req 9.12).

    Args:
        attempts_used: The number of failed phone-number attempts so far
            (including the one that just returned no record).

    Returns:
        :attr:`NoRecordOutcome.ROUTE_WITHOUT_HANGUP` when attempts are exhausted,
        else :attr:`NoRecordOutcome.REPROMPT_DIFFERENT_NUMBER`.
    """
    if phone_attempts_exhausted(attempts_used):
        logger.debug(
            "No record and {} attempts exhausted — route without hanging up "
            "(Req 9.12)",
            attempts_used,
        )
        return NoRecordOutcome.ROUTE_WITHOUT_HANGUP
    return NoRecordOutcome.REPROMPT_DIFFERENT_NUMBER


def no_record_line() -> str:
    """Return the verbatim "No record" line (Req 9.10, Appendix C).

    When no patient record is found for a provided phone number, the Authentication
    phase speaks the mandated
    :data:`~api.services.switchboard.scripts.AUTH_NO_RECORD` line, which asks the
    caller to try a different number (Req 9.10). This returns the verbatim
    Appendix C constant; no wording is authored here.
    """
    return scripts.AUTH_NO_RECORD


__all__ = [
    # Intent vocabulary
    "Intent",
    "normalize_intent",
    # Auth requirement matrix (Req 9.3, 9.4, 11.2)
    "AUTH_REQUIRED_INTENTS",
    "DEFAULT_EXISTING_INTENTS",
    "auth_required",
    # patient_status=existing default (Req 9.5)
    "defaults_to_existing",
    "should_ask_new_or_existing",
    "default_patient_status",
    # GATE-AUTH predicate (Req 9.2, 11.2, Property 13)
    "PATIENT_VERIFIED_SUCCESS",
    "PATIENT_VERIFIED_FAIL",
    "PATIENT_VERIFIED_NA",
    "AUTH_RESOLVED_STATES",
    "is_patient_verified_resolved",
    "may_proceed_to_routing",
    # Authentication flow order (subtask 9.3, Req 9.1)
    "AuthStep",
    "AUTH_FLOW_SEQUENCE",
    "next_auth_step",
    # ANI-reuse guard (subtask 9.3, Req 9.6, Property 14)
    "AniLookupDecision",
    "ani_lookup_decision",
    "should_reuse_ani_lookup",
    "should_perform_ani_lookup",
    # Fail/refusal-connects (subtask 9.3, Req 9.7, 9.12, Property 15)
    "AUTH_MAX_PHONE_ATTEMPTS",
    "AuthOutcome",
    "AuthTerminal",
    "phone_attempts_exhausted",
    "auth_outcome_connects",
    "next_terminal_after_auth",
    "should_speak_fail_route_line",
    "auth_fail_route_line",
    # Changed-request routing (subtask 9.3, Req 9.8, Property 16)
    "ReturnPhase",
    "ChangedRequestTransition",
    "changed_request_return_phase",
    "changed_request_transition",
    # DOB-determined verification (subtask 9.3, Req 9.11, Property 18)
    "dob_matches",
    "patient_verified_from_dob",
    # No record found (subtask 9.3, Req 9.10, 9.12)
    "NoRecordOutcome",
    "no_record_decision",
    "no_record_line",
]
