"""After-Hours-phase pure decision logic for the SpinSci switchboard (Req 8).

This module owns the deterministic, side-effect-free decision logic of the After
Hours phase. Like its sibling modules
(:mod:`api.services.switchboard.business_hours`,
:mod:`api.services.switchboard.auth`, :mod:`api.services.switchboard.routing`),
everything here operates purely on its inputs (and the Call State Ledger's field
values) — it never touches the LLM, TTS, lookup/verify tools, or telephony — so
each function is directly unit- and property-testable and is wired into the After
Hours node cluster by a later graph-builder task (task 16.3).

Scope of this module (the three concerns of subtask 12.1):

* **Restricted-service connect decision** (Req 8.2, 8.9, 8.10, 8.11; Property 31).
  The node follows INFORM → ASK → wait ≤10s: it informs the caller of the service
  limitation and asks whether to connect them *before* any Authentication or
  Routing (Req 8.2). Authentication then Routing proceed **iff** the caller agreed
  (Req 8.9); a decline (Req 8.10) or no intelligible decision within 10 seconds
  (Req 8.11) ends the restricted-service flow with no auth/routing.
* **Hotword path** (Req 8.3; Property 32). A detected after-hours hotword
  transitions to Routing as a silent turn, sets ``patient_verified`` to N/A, and
  uses the Hotword-Urgent transfer line. The keyword list is read from
  configuration (Req 21) so it can be supplied later without code changes.
* **Billing / MyChart closed, paging clarifier, and the after-hours
  classification-retry machine** (Req 8.4-8.8; Property 33). Billing/MyChart speak
  their mandated closed lines and perform no in-hours transfer (Req 8.4, 8.5); the
  paging clarifier sets ``caller_is_provider`` / ``ah_intent_selection`` (Req 8.8);
  Retry-1 / Retry-2 then a silent transition to Routing on the third consecutive
  not-understood failure (Req 8.6, 8.7).

All caller-facing wording is reused **verbatim** from
:mod:`api.services.switchboard.scripts` (Appendix C / E). This module never
re-authors any caller-facing text; it only *selects* which mandated line applies.

Design references:
- ``design.md`` → "After Hours cluster (Req 8)" and Correctness Properties 31, 32,
  33
- ``requirements.md`` → Requirement 8 (8.2/8.9/8.10/8.11 restricted connect,
  8.3 hotword, 8.4/8.5 closed, 8.6/8.7 retry, 8.8 paging clarifier) and
  Requirement 21 (config-driven hotword list)

Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Union

from loguru import logger

from api.services.switchboard import scripts
from api.services.switchboard.auth import (
    PATIENT_VERIFIED_NA,
    Intent,
    normalize_intent,
)
from api.services.switchboard.business_hours import (
    SILENT_TO_ROUTING,
    SilentRoutingTransition,
)
from api.services.switchboard.config import load_afterhours_hotwords

# ===========================================================================
# Restricted-service connect decision (Req 8.2, 8.9, 8.10, 8.11, Property 31)
# ===========================================================================
#
# The restricted-service node follows INFORM → ASK → wait ≤10s: it informs the
# caller that the service is limited after hours and asks whether to connect them
# BEFORE any Authentication or Routing (Req 8.2). What happens next is a pure
# decision over the caller's connect response and whether an intelligible decision
# arrived within the 10-second window.

#: The maximum time (seconds) to wait for an intelligible connect decision after
#: asking whether to connect the caller for a restricted service. No intelligible
#: decision within this bound is treated as a decline (Req 8.11, POC-03).
RESTRICTED_CONNECT_TIMEOUT_SECONDS: int = 10


class ConnectResponse(str, Enum):
    """The caller's answer to the restricted-service "connect you?" ASK (Req 8.9-8.11).

    The finite set of connect responses the decision distinguishes:

    * :attr:`AGREED` — the caller agreed to be connected (Req 8.9): proceed to
      Authentication then Routing.
    * :attr:`DECLINED` — the caller declined (Req 8.10): end the restricted-service
      flow with no auth/routing.
    * :attr:`UNINTELLIGIBLE` — no intelligible connect decision was understood;
      treated as a decline (Req 8.11), as is exceeding
      :data:`RESTRICTED_CONNECT_TIMEOUT_SECONDS`.
    """

    AGREED = "agreed"
    DECLINED = "declined"
    UNINTELLIGIBLE = "unintelligible"


def restricted_service_offer_line(*, scheduling: bool = False) -> str:
    """Return the verbatim INFORM→ASK restricted-service offer line (Req 8.2).

    The restricted-service node speaks a single mandated line that both informs the
    caller of the after-hours limitation and asks whether to connect them. For a
    scheduling-specific restricted service this is
    :data:`~api.services.switchboard.scripts.AH_RESTRICTED_SERVICE_SCHEDULING`; for
    any other restricted service it is the generic live-connect offer
    :data:`~api.services.switchboard.scripts.AH_LIVE_CONNECT_OFFER`. Both are
    verbatim Appendix C constants; no wording is authored here.

    Args:
        scheduling: Whether the restricted service is scheduling (uses the
            scheduling-specific INFORM/ASK line). Defaults to the generic
            live-connect offer.

    Returns:
        The verbatim INFORM→ASK offer line for the restricted service.
    """
    if scheduling:
        return scripts.AH_RESTRICTED_SERVICE_SCHEDULING
    return scripts.AH_LIVE_CONNECT_OFFER


@dataclass(frozen=True)
class RestrictedServiceConnectDecision:
    """The outcome of an after-hours restricted-service connect ASK (Req 8.9-8.11).

    Bundles the caller's connect response with the resulting flow decision so a
    graph-builder wires the restricted-service node correctly. Immutable so it can
    be shared/compared freely in property tests.

    Exactly one of the two outcomes is true: either
    :attr:`proceed_to_auth_and_route` (the caller agreed within the window) or
    :attr:`end_restricted_flow` (decline / unintelligible / timeout). They are
    always logical opposites.

    Attributes:
        connect_response: The caller's connect response (see
            :class:`ConnectResponse`).
        timed_out: Whether no intelligible decision arrived within
            :data:`RESTRICTED_CONNECT_TIMEOUT_SECONDS` (Req 8.11).
        proceed_to_auth_and_route: ``True`` iff the caller agreed within the
            window — proceed to Authentication then Routing (Req 8.9).
        end_restricted_flow: ``True`` when the flow ends with no auth/routing
            (decline, unintelligible, or timeout — Req 8.10, 8.11).
    """

    connect_response: ConnectResponse
    timed_out: bool
    proceed_to_auth_and_route: bool
    end_restricted_flow: bool


def is_connect_decision_timed_out(elapsed_seconds: Optional[float]) -> bool:
    """Return whether the connect decision exceeded the 10-second window (Req 8.11).

    An intelligible decision must be received *within*
    :data:`RESTRICTED_CONNECT_TIMEOUT_SECONDS` seconds. This returns ``True`` when
    ``elapsed_seconds`` is greater than that bound (so a decision at exactly the
    bound still counts as in-time). ``None`` means no elapsed time was supplied and
    is treated as *not* timed out (the ``timed_out`` flag, if any, is authoritative
    for that case — see :func:`restricted_service_connect_decision`).

    Args:
        elapsed_seconds: Seconds elapsed before a decision was received, or
            ``None`` when unknown.

    Returns:
        ``True`` when ``elapsed_seconds`` exceeds the timeout bound.
    """
    return elapsed_seconds is not None and elapsed_seconds > RESTRICTED_CONNECT_TIMEOUT_SECONDS


def restricted_service_connect_decision(
    response: ConnectResponse,
    elapsed_seconds: Optional[float] = None,
    *,
    timed_out: bool = False,
) -> RestrictedServiceConnectDecision:
    """Decide whether a restricted-service call proceeds to Auth+Route (Req 8.9-8.11).

    Pure decision implementing the restricted-service connect rule (Property 31).
    Authentication then Routing proceed **if and only if** the caller agreed
    *within* the 10-second window; every other case ends the restricted-service
    flow with no authentication or routing:

    * :attr:`ConnectResponse.AGREED` and not timed out → proceed to Auth+Route
      (Req 8.9).
    * :attr:`ConnectResponse.DECLINED` → end the flow (Req 8.10).
    * :attr:`ConnectResponse.UNINTELLIGIBLE` → treated as declined; end the flow
      (Req 8.11).
    * **Timed out** (no intelligible decision within
      :data:`RESTRICTED_CONNECT_TIMEOUT_SECONDS`) → treated as declined; end the
      flow, even if the (late) response was ``AGREED`` (Req 8.11).

    The effective timeout is the logical OR of the explicit ``timed_out`` flag and
    a derived timeout when ``elapsed_seconds`` exceeds the bound
    (:func:`is_connect_decision_timed_out`), so callers may express the timeout
    either way.

    Args:
        response: The caller's connect response.
        elapsed_seconds: Seconds elapsed before the decision was received, used to
            derive a timeout. Optional.
        timed_out: An explicit timeout flag (e.g. the wait fired with no response).

    Returns:
        The :class:`RestrictedServiceConnectDecision` for the inputs.
    """
    effective_timeout = bool(timed_out) or is_connect_decision_timed_out(elapsed_seconds)

    proceed = response is ConnectResponse.AGREED and not effective_timeout
    if proceed:
        logger.debug("Restricted service: caller agreed — proceed to Auth+Route (Req 8.9)")
    else:
        logger.debug(
            "Restricted service: not connecting (response={}, timed_out={}) — "
            "end flow, no auth/routing (Req 8.10/8.11)",
            response.value,
            effective_timeout,
        )
    return RestrictedServiceConnectDecision(
        connect_response=response,
        timed_out=effective_timeout,
        proceed_to_auth_and_route=proceed,
        end_restricted_flow=not proceed,
    )


# ===========================================================================
# Hotword path (Req 8.3, Property 32)
# ===========================================================================
#
# A detected after-hours hotword short-circuits the normal after-hours handling:
# the traversal transitions to Routing as a silent turn, sets patient_verified to
# N/A, and uses the Hotword-Urgent transfer line (Req 8.3, AC-05, POC-04). The
# keyword list is read from configuration (Req 21) — never hardcoded here.


def detect_hotword(
    speech: Optional[str], keywords: Optional[Sequence[str]] = None
) -> Optional[str]:
    """Return the after-hours hotword found in ``speech``, or ``None`` (Req 8.3, 21).

    Scans caller ``speech`` for any configured hotword keyword and returns the
    first match. The keyword list is read from configuration via
    :func:`~api.services.switchboard.config.load_afterhours_hotwords` when
    ``keywords`` is not supplied (Req 21.1) — keywords are never hardcoded here —
    but a list may be passed in for testability. Matching is case-insensitive: the
    config loader already lower-cases its values, and this function lower-cases
    both the speech and each keyword before comparing, so a caller-supplied
    mixed-case list still matches. A keyword matches when it occurs as a substring
    of the speech (keywords may be multi-word phrases such as ``"chest pain"``).

    Args:
        speech: The caller's utterance. ``None`` or blank yields ``None``.
        keywords: The hotword keyword list to match against. Defaults to the
            configured list from :func:`load_afterhours_hotwords`.

    Returns:
        The matched keyword (as it appears in ``keywords``), or ``None`` when no
        hotword is present.
    """
    if keywords is None:
        keywords = load_afterhours_hotwords()
    if not speech:
        return None
    lowered = speech.lower()
    for keyword in keywords:
        if keyword and keyword.lower() in lowered:
            logger.debug("After-hours hotword detected: {!r}", keyword)
            return keyword
    return None


def is_hotword(
    speech: Optional[str], keywords: Optional[Sequence[str]] = None
) -> bool:
    """Return whether ``speech`` contains an after-hours hotword (Req 8.3, 21).

    Boolean convenience over :func:`detect_hotword`: ``True`` when any configured
    hotword keyword is present in the caller speech.
    """
    return detect_hotword(speech, keywords) is not None


@dataclass(frozen=True)
class HotwordRoutingDecision:
    """The silent-to-Routing transition taken for an after-hours hotword (Req 8.3).

    Describes the hotword short-circuit: a silent turn (no spoken filler) straight
    to Routing, ``patient_verified`` set to N/A, and the Hotword-Urgent transfer
    line to speak on the terminal turn. Immutable so the canonical instance
    (:data:`HOTWORD_ROUTING`) can be shared/compared freely in property tests.

    Attributes:
        to_routing: Always ``True`` — the hotword path enters Routing.
        spoken_filler: Always empty — the transition to Routing is silent
            (Req 8.3, AC-05).
        patient_verified: The ``patient_verified`` ledger value to set — the N/A
            value (:data:`~api.services.switchboard.auth.PATIENT_VERIFIED_NA`),
            since authentication does not apply on the hotword path.
        transfer_line: The verbatim Hotword-Urgent transfer line
            (:data:`~api.services.switchboard.scripts.E_HOTWORD_URGENT`).
    """

    to_routing: bool = True
    spoken_filler: str = ""
    patient_verified: str = PATIENT_VERIFIED_NA
    transfer_line: str = scripts.E_HOTWORD_URGENT

    @property
    def is_silent(self) -> bool:
        """Whether the transition to Routing speaks nothing (always ``True``)."""
        return self.spoken_filler == ""


#: The canonical after-hours hotword silent-to-Routing decision. Immutable, so it
#: is safe to share across every hotword detection (the transition is identical
#: regardless of which keyword matched — Req 8.3).
HOTWORD_ROUTING: HotwordRoutingDecision = HotwordRoutingDecision()


def hotword_routing_decision(
    speech: Optional[str], keywords: Optional[Sequence[str]] = None
) -> Optional[HotwordRoutingDecision]:
    """Return the hotword routing decision for ``speech``, or ``None`` (Req 8.3).

    When an after-hours hotword is detected in the caller speech
    (:func:`detect_hotword`), returns the canonical :data:`HOTWORD_ROUTING`
    decision: a silent transition to Routing with ``patient_verified=N/A`` and the
    Hotword-Urgent transfer line (Req 8.3, Property 32, POC-04). Returns ``None``
    when no hotword is present (the normal after-hours handling continues).

    Args:
        speech: The caller's utterance.
        keywords: The hotword keyword list. Defaults to the configured list from
            :func:`load_afterhours_hotwords`.

    Returns:
        :data:`HOTWORD_ROUTING` when a hotword is detected, otherwise ``None``.
    """
    if is_hotword(speech, keywords):
        return HOTWORD_ROUTING
    return None


# ===========================================================================
# Billing / MyChart closed after hours (Req 8.4, 8.5, Property 33)
# ===========================================================================


@dataclass(frozen=True)
class ClosedServiceDecision:
    """The after-hours "closed" outcome for Billing / MyChart (Req 8.4, 8.5).

    When an after-hours caller requests Billing or MyChart, the phase speaks the
    mandated closed line and performs **no** in-hours department transfer
    (Property 33). Immutable so it can be shared/compared freely in property tests.

    Attributes:
        intent: The closed service's :class:`~api.services.switchboard.auth.Intent`
            (Billing or MyChart).
        closed_line: The verbatim mandated closed line to speak
            (:data:`~api.services.switchboard.scripts.AH_BILLING_CLOSED` /
            :data:`~api.services.switchboard.scripts.AH_MYCHART_CLOSED`).
        perform_in_hours_transfer: Always ``False`` — no in-hours Billing/MyChart
            transfer is performed after hours (Req 8.4, 8.5).
    """

    intent: Intent
    closed_line: str
    perform_in_hours_transfer: bool = False


#: The verbatim after-hours closed line for each closed service intent (Req 8.4,
#: 8.5). Values are verbatim :mod:`~api.services.switchboard.scripts` constants —
#: never re-authored here.
AFTERHOURS_CLOSED_LINES: dict[Intent, str] = {
    Intent.BILLING: scripts.AH_BILLING_CLOSED,
    Intent.MYCHART: scripts.AH_MYCHART_CLOSED,
}


def afterhours_closed_service(
    intent: Union[str, Intent, None]
) -> Optional[ClosedServiceDecision]:
    """Return the closed-service decision for an after-hours Billing/MyChart call.

    Pure decision implementing Req 8.4 / 8.5 (Property 33). When ``intent``
    resolves to :attr:`~api.services.switchboard.auth.Intent.BILLING` or
    :attr:`~api.services.switchboard.auth.Intent.MYCHART`, returns a
    :class:`ClosedServiceDecision` that speaks the mandated closed line and
    performs no in-hours transfer. For any other intent it returns ``None`` (the
    call is not a closed after-hours service and is handled elsewhere).

    Args:
        intent: The ledger ``intent`` value (raw string, :class:`Intent`, or
            ``None``). Normalized via
            :func:`~api.services.switchboard.auth.normalize_intent`.

    Returns:
        The :class:`ClosedServiceDecision` for Billing/MyChart, otherwise ``None``.
    """
    resolved = normalize_intent(intent)
    if resolved in AFTERHOURS_CLOSED_LINES:
        logger.debug(
            "After-hours {} — speak closed line, no in-hours transfer (Req 8.4/8.5)",
            resolved.value,
        )
        return ClosedServiceDecision(
            intent=resolved, closed_line=AFTERHOURS_CLOSED_LINES[resolved]
        )
    return None


# ===========================================================================
# Paging clarifier — caller_is_provider + ah_intent_selection (Req 8.8)
# ===========================================================================
#
# When paging clarification is needed after hours, the phase asks one of the
# mandated paging clarifier lines and sets caller_is_provider and
# ah_intent_selection from the caller's answer (Req 8.8). No ledger enum exists
# for ah_intent_selection (the ledger stores it as a free string, Appendix D), so
# its two allowed values are centralized here as named constants.

#: ``ah_intent_selection`` value for a provider / hospital / medical-facility
#: caller (ledger ``ah_intent_selection``, Appendix D).
AH_INTENT_HOSPITAL_OR_PHYSICIAN: str = "Hospital or Physician"

#: ``ah_intent_selection`` value for a patient calling for themselves after hours
#: (ledger ``ah_intent_selection``, Appendix D).
AH_INTENT_AFTERHOURS_ANSWERING_SERVICE: str = "Afterhours Answering Service"


class PagingClarifierAnswer(str, Enum):
    """Who the after-hours paging caller is, per the clarifier answer (Req 8.8).

    * :attr:`PROVIDER` — the caller is a provider, or is calling from a hospital /
      medical facility / as staff about a patient.
    * :attr:`PATIENT` — the caller is the patient, calling for themselves.
    """

    PROVIDER = "provider"
    PATIENT = "patient"


def paging_clarifier_line(option: int = 1) -> str:
    """Return one of the mandated paging clarifier lines (Req 8.8).

    The paging clarifier asks **one** of the three mandated Appendix C options
    (:data:`~api.services.switchboard.scripts.AH_PAGING_CLARIFIER_OPTIONS`). This
    returns the requested 1-based option verbatim; option ``1`` is the default.

    Args:
        option: The 1-based clarifier option to use (1, 2, or 3).

    Returns:
        The verbatim paging clarifier line for the option.

    Raises:
        ValueError: If ``option`` is not in the range 1..3.
    """
    if not 1 <= option <= len(scripts.AH_PAGING_CLARIFIER_OPTIONS):
        raise ValueError(
            f"paging clarifier option must be 1..{len(scripts.AH_PAGING_CLARIFIER_OPTIONS)}, "
            f"got {option}"
        )
    return scripts.AH_PAGING_CLARIFIER_OPTIONS[option - 1]


@dataclass(frozen=True)
class PagingClarifierDecision:
    """The ledger updates a paging clarifier answer produces (Req 8.8).

    Maps the caller's clarifier answer onto the two ledger fields the paging
    clarifier sets. Immutable so it can be shared/compared freely in property
    tests.

    Attributes:
        answer: The clarifier answer (see :class:`PagingClarifierAnswer`).
        caller_is_provider: The ``caller_is_provider`` ledger value — ``True`` for
            a provider/facility/staff caller, ``False`` for the patient.
        ah_intent_selection: The ``ah_intent_selection`` ledger value —
            :data:`AH_INTENT_HOSPITAL_OR_PHYSICIAN` for a provider, else
            :data:`AH_INTENT_AFTERHOURS_ANSWERING_SERVICE`.
    """

    answer: PagingClarifierAnswer
    caller_is_provider: bool
    ah_intent_selection: str


def paging_clarifier_decision(
    answer: PagingClarifierAnswer,
) -> PagingClarifierDecision:
    """Return the ledger updates for a paging clarifier ``answer`` (Req 8.8).

    Pure decision setting ``caller_is_provider`` and ``ah_intent_selection`` from
    the caller's clarifier answer:

    * :attr:`PagingClarifierAnswer.PROVIDER` → ``caller_is_provider=True`` and
      ``ah_intent_selection`` = :data:`AH_INTENT_HOSPITAL_OR_PHYSICIAN`.
    * :attr:`PagingClarifierAnswer.PATIENT` → ``caller_is_provider=False`` and
      ``ah_intent_selection`` = :data:`AH_INTENT_AFTERHOURS_ANSWERING_SERVICE`.

    Args:
        answer: The caller's paging clarifier answer.

    Returns:
        The :class:`PagingClarifierDecision` with the resulting ledger values.
    """
    is_provider = answer is PagingClarifierAnswer.PROVIDER
    selection = (
        AH_INTENT_HOSPITAL_OR_PHYSICIAN
        if is_provider
        else AH_INTENT_AFTERHOURS_ANSWERING_SERVICE
    )
    logger.debug(
        "Paging clarifier: answer={} → caller_is_provider={}, ah_intent_selection={!r}",
        answer.value,
        is_provider,
        selection,
    )
    return PagingClarifierDecision(
        answer=answer,
        caller_is_provider=is_provider,
        ah_intent_selection=selection,
    )


# ===========================================================================
# After-hours classification-retry machine (Req 8.6, 8.7)
# ===========================================================================
#
# Mirrors the Business-Hours classification-retry machine
# (:func:`~api.services.switchboard.business_hours.bh_classification_retry`): the
# after-hours phase speaks the after-hours Retry-1 line on the first
# not-understood failure and the Retry-2 line on the second, then transitions to
# Routing as a silent turn on the third consecutive failure. It reuses the shared
# :class:`~api.services.switchboard.business_hours.SilentRoutingTransition`
# pattern for the silent fallback.

#: Number of times the After Hours phase speaks a retry line before falling back.
#: The Retry-1 line is spoken on the 1st not-understood turn and the Retry-2 line
#: on the 2nd; on the 3rd consecutive failure the phase stops speaking retries and
#: transitions to Routing as a silent turn (Req 8.6, 8.7).
AH_CLASSIFICATION_MAX_RETRIES: int = 2


@dataclass(frozen=True)
class AHClassificationRetryDecision:
    """What to do after N consecutive after-hours not-understood turns (Req 8.6-7).

    Encodes the after-hours classification-retry outcome for a given
    consecutive-failure count: either a verbatim spoken retry line, or — once the
    two spoken retries are exhausted — a silent transition to Routing. The value
    is immutable so it can be shared/compared freely in property tests. Mirrors
    :class:`~api.services.switchboard.business_hours.BHClassificationRetryDecision`.

    Exactly one of the two outcomes is present:

    * ``spoken_line`` is set (Retry-1 / Retry-2) and ``silent_transition`` is
      ``None`` for the 1st and 2nd failures, or
    * ``spoken_line`` is ``None`` and ``silent_transition`` is
      :data:`~api.services.switchboard.business_hours.SILENT_TO_ROUTING` for the
      3rd and any subsequent failure.
    """

    consecutive_failures: int
    spoken_line: Optional[str]
    silent_transition: Optional[SilentRoutingTransition]

    @property
    def is_silent(self) -> bool:
        """Whether this decision speaks nothing and transitions to Routing."""
        return self.spoken_line is None


def ah_classification_retry(
    consecutive_failures: int,
) -> AHClassificationRetryDecision:
    """Return the retry decision after ``consecutive_failures`` after-hours misses.

    Implements the after-hours classification-retry machine (Requirements 8.6,
    8.7, POC-08). ``consecutive_failures`` is the number of consecutive turns on
    which the caller could not be understood, **including the current one**
    (1-based): the current failure is the ``consecutive_failures``-th in a row.

    * ``1`` → speak the verbatim after-hours Retry-1 line
      (:data:`~api.services.switchboard.scripts.AH_RETRY_1`).
    * ``2`` → speak the verbatim after-hours Retry-2 line
      (:data:`~api.services.switchboard.scripts.AH_RETRY_2`).
    * ``3`` or more → speak nothing and transition to Routing as a silent turn
      (:data:`~api.services.switchboard.business_hours.SILENT_TO_ROUTING`), with no
      spoken filler (Req 8.7).

    Mirrors
    :func:`~api.services.switchboard.business_hours.bh_classification_retry`
    exactly, differing only in the after-hours Retry lines used.

    Args:
        consecutive_failures: Count of consecutive not-understood turns, including
            the current one. Must be at least ``1``.

    Returns:
        The :class:`AHClassificationRetryDecision` for the failure count.

    Raises:
        ValueError: If ``consecutive_failures`` is less than ``1``.
    """
    if consecutive_failures < 1:
        raise ValueError(
            f"consecutive_failures must be >= 1, got {consecutive_failures}"
        )

    if consecutive_failures == 1:
        return AHClassificationRetryDecision(
            consecutive_failures=consecutive_failures,
            spoken_line=scripts.AH_RETRY_1,
            silent_transition=None,
        )
    if consecutive_failures == AH_CLASSIFICATION_MAX_RETRIES:
        return AHClassificationRetryDecision(
            consecutive_failures=consecutive_failures,
            spoken_line=scripts.AH_RETRY_2,
            silent_transition=None,
        )

    logger.debug(
        "Third+ consecutive after-hours failure ({}) — silent transition to Routing",
        consecutive_failures,
    )
    return AHClassificationRetryDecision(
        consecutive_failures=consecutive_failures,
        spoken_line=None,
        silent_transition=SILENT_TO_ROUTING,
    )


@dataclass(frozen=True)
class AHClassificationRetryState:
    """Immutable consecutive-failure counter for after-hours classification.

    Tracks the number of consecutive turns on which the caller could not be
    understood. State transitions return a new instance (the value is never
    mutated in place), keeping the machine pure. A fresh state has zero failures;
    a not-understood turn advances it, and any successful turn resets it. Mirrors
    :class:`~api.services.switchboard.business_hours.BHClassificationRetryState`.
    """

    consecutive_failures: int = 0

    def record_failure(self) -> "AHClassificationRetryState":
        """Return a new state with the consecutive-failure count incremented by one."""
        return AHClassificationRetryState(self.consecutive_failures + 1)

    def reset(self) -> "AHClassificationRetryState":
        """Return a fresh state with the consecutive-failure count cleared to zero."""
        return AHClassificationRetryState(0)

    @property
    def has_fallen_back(self) -> bool:
        """Whether classification has fallen back to a silent Routing transition."""
        return self.consecutive_failures > AH_CLASSIFICATION_MAX_RETRIES

    @property
    def decision(self) -> AHClassificationRetryDecision:
        """Return the retry decision for the current failure count.

        Only meaningful after at least one :meth:`record_failure`; delegates to
        :func:`ah_classification_retry`, which requires a count of at least ``1``.

        Raises:
            ValueError: If no failure has been recorded yet
                (``consecutive_failures`` is ``0``).
        """
        return ah_classification_retry(self.consecutive_failures)


__all__ = [
    # Restricted-service connect decision (Req 8.2, 8.9, 8.10, 8.11, Property 31)
    "RESTRICTED_CONNECT_TIMEOUT_SECONDS",
    "ConnectResponse",
    "restricted_service_offer_line",
    "RestrictedServiceConnectDecision",
    "is_connect_decision_timed_out",
    "restricted_service_connect_decision",
    # Hotword path (Req 8.3, Property 32)
    "detect_hotword",
    "is_hotword",
    "HotwordRoutingDecision",
    "HOTWORD_ROUTING",
    "hotword_routing_decision",
    # Billing / MyChart closed (Req 8.4, 8.5, Property 33)
    "ClosedServiceDecision",
    "AFTERHOURS_CLOSED_LINES",
    "afterhours_closed_service",
    # Paging clarifier (Req 8.8)
    "AH_INTENT_HOSPITAL_OR_PHYSICIAN",
    "AH_INTENT_AFTERHOURS_ANSWERING_SERVICE",
    "PagingClarifierAnswer",
    "paging_clarifier_line",
    "PagingClarifierDecision",
    "paging_clarifier_decision",
    # After-hours classification-retry machine (Req 8.6, 8.7)
    "AH_CLASSIFICATION_MAX_RETRIES",
    "AHClassificationRetryDecision",
    "ah_classification_retry",
    "AHClassificationRetryState",
]
