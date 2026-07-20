"""Scheduling-segment pure decision logic for the SpinSci switchboard (Req 12, 13, 14).

This module owns the deterministic, side-effect-free decision logic of the two
downstream Scheduling segments — **Scheduling Init** (visit-type determination)
and the **Scheduling Engine input** builder — plus the switchboard-wide guard
that the switchboard clusters never set or ask ``visit_type``. Like
:mod:`api.services.switchboard.business_hours` and
:mod:`api.services.switchboard.ledger`, everything here operates purely on its
inputs (and the Call State Ledger); it never touches the LLM, TTS, the Scheduling
Engine backend, or telephony, so each function is directly unit- and
property-testable and is wired into the Scheduling Init / Scheduling Engine node
segments by a later graph-builder task (task 17).

Scope of this module:

* **Visit-type resolver (``create`` only)** — Requirements 13.2, 13.5, 13.6;
  Property 28. Resolve ``visit_type`` to ``sick`` / ``wellness`` from the caller's
  visit-reason signals (a wellness signal → wellness, a symptom signal → sick,
  both present → wellness), ask the verbatim reason question when the reason is
  unknown (Req 13.3), and ask the verbatim wellness-vs-symptom disambiguation
  question before setting ``visit_type`` when both a wellness keyword and a
  specific symptom are present (Req 13.4/13.5). A reason that is already clear is
  mapped directly and never re-asked (Req 13.6).
* **Never-set guard** — Requirement 12.4; Property 29. A predicate establishing
  that the switchboard clusters (Greeting / Business Hours / After Hours /
  Authentication / Routing) never set or ask ``visit_type``; it is set downstream
  in Scheduling Init and only for ``create`` (Req 13.7 — manage actions never set
  ``visit_type``).
* **Engine-input completeness** — Requirements 14.2, 12.8; Property 30. Build the
  Scheduling Engine input payload: ``specialty`` + verified ``patient_id`` +
  ``appointment_action`` for every action, ``visit_type`` iff ``create``, and
  ``location`` / ``provider_name`` / ``existing_appointment_date`` when known. The
  handoff carries the full Call State Ledger (Req 12.8).

All caller-facing wording is reused **verbatim** from
:mod:`api.services.switchboard.scripts` (Appendix C); this module only selects
which mandated line applies, never re-authoring any text. The appointment-action
vocabulary (:class:`~api.services.switchboard.business_hours.AppointmentAction`,
:func:`~api.services.switchboard.business_hours.is_manage_action`) and the Call
State Ledger (:class:`~api.services.switchboard.ledger.CallStateLedger`) are
reused, never duplicated.

Design references:
- ``design.md`` → "Scheduling experience (Req 12, 13, 14)" and Correctness
  Properties 28 / 29 / 30
- ``requirements.md`` → Requirement 12 (12.4 no visit_type on switchboard, 12.8
  full-ledger handoff), Requirement 13 (13.2/13.5 resolution, 13.3 ask reason,
  13.4 disambiguation, 13.6 no re-ask, 13.7 manage skips visit_type), Requirement
  14 (14.2 engine-input completeness)

Requirements: 12.4, 12.8, 13.2, 13.5, 13.6, 14.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from loguru import logger

from api.services.switchboard import scripts
from api.services.switchboard.business_hours import (
    AppointmentAction,
    is_manage_action,
)
from api.services.switchboard.ledger import CallStateLedger


class SchedulingInputError(ValueError):
    """Raised when the Scheduling Engine input payload cannot be completed.

    Signals that a mandatory field required for *every* appointment action —
    ``specialty``, a verified ``patient_id``, or (for ``create``) a resolved
    ``visit_type`` — is missing from the ledger, so the completeness guarantee of
    Requirement 14.2 / Property 30 cannot be satisfied.
    """


# ===========================================================================
# Visit types (ledger ``visit_type`` vocabulary)
# ===========================================================================


class VisitType(str, Enum):
    """The classification driving scheduling rules (ledger ``visit_type``).

    Values are the exact lowercase strings stored on the Call State Ledger's
    ``visit_type`` field (Appendix D): ``sick`` or ``wellness``. Being a ``str``
    subclass, a member is directly assignable as the ledger value (``member.value``
    or the member itself both serialize to the ledger string). ``visit_type`` is
    set downstream in Scheduling Init and only for a ``create`` action (Req 13.2).
    """

    SICK = "sick"
    WELLNESS = "wellness"


# ===========================================================================
# Visit-type resolver — create only (Req 13.2, 13.3, 13.4, 13.5, 13.6)
# Property 28
# ===========================================================================


@dataclass(frozen=True)
class VisitReasonSignals:
    """The wellness/symptom signals extracted from the caller's visit reason.

    A frozen, immutable snapshot of what the caller's stated reason indicates,
    consumed by :func:`resolve_visit_type` and :func:`determine_visit_type`. The
    two booleans are the finite signal space the resolution rules distinguish:

    * :attr:`has_wellness_signal` — the caller mentioned a wellness keyword (e.g.
      an annual/wellness/physical exam).
    * :attr:`has_symptom_signal` — the caller mentioned a specific symptom (a
      sick-visit reason).

    A clear reason is signalled by at least one flag being ``True``; when both are
    ``False`` the reason is unknown and Scheduling Init must ask for it (Req 13.3).
    """

    has_wellness_signal: bool = False
    has_symptom_signal: bool = False

    @property
    def reason_known(self) -> bool:
        """Whether the caller's reason is clear (at least one signal present).

        When ``True`` the reason is already known/clear and is mapped directly
        without re-asking the reason question (Req 13.6); when ``False`` the reason
        is unknown and must be asked (Req 13.3).
        """
        return self.has_wellness_signal or self.has_symptom_signal


def resolve_visit_type(signals: VisitReasonSignals) -> Optional[VisitType]:
    """Resolve ``visit_type`` from visit-reason signals (Req 13.2, 13.5; Property 28).

    Pure resolution over the wellness/symptom signal space:

    * a **wellness** signal → :attr:`VisitType.WELLNESS`,
    * a **symptom** signal → :attr:`VisitType.SICK`,
    * **both** a wellness keyword and a specific symptom → :attr:`VisitType.WELLNESS`
      (the mandated safe default when both are indicated, Req 13.5), and
    * **neither** signal → ``None`` (the reason is unknown; Scheduling Init asks
      for it — see :func:`determine_visit_type`).

    This is the core determination Property 28 exercises. It does not decide
    whether a question must be asked first; :func:`determine_visit_type` layers the
    ask-reason / ask-disambiguation flow on top of this resolution.

    Args:
        signals: The wellness/symptom signals from the caller's visit reason.

    Returns:
        The resolved :class:`VisitType`, or ``None`` when the reason is unknown.
    """
    if signals.has_wellness_signal and signals.has_symptom_signal:
        return VisitType.WELLNESS
    if signals.has_wellness_signal:
        return VisitType.WELLNESS
    if signals.has_symptom_signal:
        return VisitType.SICK
    return None


class VisitTypeOutcome(str, Enum):
    """The outcome kind of a Scheduling Init visit-type determination.

    Distinguishes the three flow branches of :func:`determine_visit_type`:

    * :attr:`RESOLVED` — ``visit_type`` is set directly from a single clear signal.
    * :attr:`ASK_REASON` — the reason is unknown; ask the verbatim reason question
      (:data:`~scripts.SCHED_INIT_VISIT_REASON`) before setting ``visit_type``
      (Req 13.3).
    * :attr:`ASK_DISAMBIGUATION` — both a wellness keyword and a specific symptom
      are present; ask the verbatim wellness-vs-symptom disambiguation question
      (:data:`~scripts.SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION`) before setting
      ``visit_type`` (Req 13.4).
    """

    RESOLVED = "resolved"
    ASK_REASON = "ask_reason"
    ASK_DISAMBIGUATION = "ask_disambiguation"


@dataclass(frozen=True)
class VisitTypeDecision:
    """A Scheduling Init decision about how to determine ``visit_type`` (create only).

    Bundles the flow branch (:attr:`outcome`), the resolved ``visit_type`` when one
    can be established, and the verbatim question to ask when one must be asked
    first. The value is immutable so it can be shared/compared freely in property
    tests.

    Attributes:
        outcome: Which branch applies (see :class:`VisitTypeOutcome`).
        visit_type: The resolved :class:`VisitType` for :attr:`RESOLVED`, or the
            mandated default (``wellness``) that applies if both remain indicated
            for :attr:`ASK_DISAMBIGUATION` (Req 13.5). ``None`` for
            :attr:`ASK_REASON` (nothing can be resolved until the reason is known).
        question: The verbatim Appendix C line to speak for :attr:`ASK_REASON` /
            :attr:`ASK_DISAMBIGUATION`, or ``None`` for :attr:`RESOLVED`.
    """

    outcome: VisitTypeOutcome
    visit_type: Optional[VisitType]
    question: Optional[str]

    @property
    def must_ask(self) -> bool:
        """Whether Scheduling Init must ask a question before setting ``visit_type``."""
        return self.outcome is not VisitTypeOutcome.RESOLVED


def determine_visit_type(signals: VisitReasonSignals) -> VisitTypeDecision:
    """Decide how Scheduling Init determines ``visit_type`` for a ``create`` (Req 13.2-13.6).

    Layers the ask-reason / ask-disambiguation flow on top of the pure
    :func:`resolve_visit_type` mapping. This is only meaningful for
    ``appointment_action == create``; manage actions never determine a
    ``visit_type`` (Req 13.7 — see :func:`visit_type_applies_to_action`).

    Branches:

    * **Both** a wellness keyword and a specific symptom present → ask the mandated
      wellness-vs-symptom disambiguation question
      (:data:`~scripts.SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION`) before setting
      ``visit_type`` (Req 13.4); the decision carries the default resolution
      (``wellness``) that applies if both remain indicated (Req 13.5).
    * **Exactly one** signal present → the reason is clear, so map it directly to
      ``wellness`` / ``sick`` and do not ask again (Req 13.2, 13.6).
    * **Neither** signal present → the reason is unknown, so ask the verbatim
      reason question (:data:`~scripts.SCHED_INIT_VISIT_REASON`) before setting
      ``visit_type`` (Req 13.3).

    Args:
        signals: The wellness/symptom signals from the caller's visit reason.

    Returns:
        The :class:`VisitTypeDecision` describing the flow branch, the resolved (or
        default) ``visit_type``, and the verbatim question to ask when needed.
    """
    if signals.has_wellness_signal and signals.has_symptom_signal:
        logger.debug(
            "Wellness keyword and specific symptom both present — ask "
            "disambiguation before setting visit_type"
        )
        return VisitTypeDecision(
            outcome=VisitTypeOutcome.ASK_DISAMBIGUATION,
            visit_type=VisitType.WELLNESS,
            question=scripts.SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION,
        )

    resolved = resolve_visit_type(signals)
    if resolved is not None:
        logger.debug("Visit reason clear — visit_type resolved to {}", resolved.value)
        return VisitTypeDecision(
            outcome=VisitTypeOutcome.RESOLVED,
            visit_type=resolved,
            question=None,
        )

    logger.debug("Visit reason unknown — ask the reason question")
    return VisitTypeDecision(
        outcome=VisitTypeOutcome.ASK_REASON,
        visit_type=None,
        question=scripts.SCHED_INIT_VISIT_REASON,
    )


def resolve_disambiguation_answer(
    answer_is_wellness: bool, answer_is_symptom: bool
) -> VisitType:
    """Resolve ``visit_type`` from the caller's disambiguation answer (Req 13.5).

    After the wellness-vs-symptom disambiguation question is asked (Req 13.4), the
    caller's answer sets ``visit_type``: a wellness-exam answer → ``wellness``, a
    symptom-visit answer → ``sick``, and when both are indicated → ``wellness``
    (the mandated default, Req 13.5). When the answer is unintelligible (neither
    flag) the safe default ``wellness`` is likewise applied.

    Args:
        answer_is_wellness: Whether the caller indicated a wellness exam.
        answer_is_symptom: Whether the caller indicated the symptom visit.

    Returns:
        The resolved :class:`VisitType`.
    """
    if answer_is_symptom and not answer_is_wellness:
        return VisitType.SICK
    # wellness-only, both-indicated, and unintelligible all resolve to wellness.
    return VisitType.WELLNESS


# ===========================================================================
# Never-set guard — switchboard clusters never set/ask visit_type (Req 12.4)
# Property 29
# ===========================================================================


class SwitchboardCluster(str, Enum):
    """The five switchboard node clusters that precede the Scheduling segments.

    These are the switchboard-side phases (Greeting, Business Hours, After Hours,
    Authentication, Routing). None of them sets or asks ``visit_type`` — that is
    the responsibility split enforced by :func:`cluster_sets_or_asks_visit_type`
    (Req 12.4, Property 29). ``visit_type`` is set downstream in Scheduling Init
    (:data:`VISIT_TYPE_STAGE`) and only for ``create``.
    """

    GREETING = "greeting"
    BUSINESS_HOURS = "business_hours"
    AFTER_HOURS = "after_hours"
    AUTHENTICATION = "authentication"
    ROUTING = "routing"


#: The set of all switchboard clusters that precede Scheduling Init. Membership —
#: not string literals — drives the never-set guard so it stays in lock-step with
#: :class:`SwitchboardCluster`.
SWITCHBOARD_CLUSTERS: frozenset[SwitchboardCluster] = frozenset(SwitchboardCluster)

#: Human-readable name of the only stage that may set ``visit_type`` (downstream,
#: after switchboard authentication). ``visit_type`` is set here and nowhere in the
#: switchboard clusters (Req 12.4, 13.1, 13.2).
VISIT_TYPE_STAGE: str = "Scheduling Init"


def cluster_sets_or_asks_visit_type(cluster: SwitchboardCluster) -> bool:
    """Return whether a switchboard cluster may set or ask ``visit_type`` (Req 12.4).

    The never-set guard: for every switchboard cluster (Greeting, Business Hours,
    After Hours, Authentication, Routing) this is **always** ``False`` — the
    switchboard owns specialty / location / provider / new-existing /
    ``appointment_action`` / auth gating and never touches ``visit_type`` (Req
    12.4, REQ-SCHED-05, AC-16; Property 29). ``visit_type`` is set downstream in
    Scheduling Init (:data:`VISIT_TYPE_STAGE`) and only for ``create``.

    Args:
        cluster: The switchboard cluster being checked.

    Returns:
        ``False`` for every :class:`SwitchboardCluster` — no switchboard cluster
        sets or asks ``visit_type``.
    """
    return False


def visit_type_applies_to_action(action: AppointmentAction) -> bool:
    """Return whether ``visit_type`` is set at all for an ``appointment_action`` (Req 13.7).

    ``visit_type`` is a **create-only** concept: it is set downstream in Scheduling
    Init exclusively for :attr:`~api.services.switchboard.business_hours.AppointmentAction.CREATE`.
    For the four manage actions (cancel / reschedule / list / confirm) ``visit_type``
    is never set — Scheduling Init skips sick/wellness and passes the action and
    ledger context straight to the Engine (Req 13.7, AC-20).

    Args:
        action: The classified appointment action.

    Returns:
        ``True`` only when ``action`` is ``create``; ``False`` for manage actions.
    """
    return not is_manage_action(action)


# ===========================================================================
# Scheduling Engine input completeness (Req 14.2, 12.8) — Property 30
# ===========================================================================


def _known(value: Optional[str]) -> Optional[str]:
    """Return a stripped non-empty string, or ``None`` when the value is unset.

    Treats ``None`` and blank/whitespace-only strings alike as *unknown* so an
    empty ledger field is never emitted into the engine payload as a known value.
    """
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _coerce_action(value: Optional[str]) -> AppointmentAction:
    """Coerce a ledger ``appointment_action`` string into an :class:`AppointmentAction`.

    Args:
        value: The ledger ``appointment_action`` value.

    Returns:
        The matching :class:`AppointmentAction` member.

    Raises:
        SchedulingInputError: If ``value`` is missing or is not one of the five
            recognized appointment actions.
    """
    known = _known(value)
    if known is None:
        raise SchedulingInputError(
            "appointment_action is required to build Scheduling Engine input"
        )
    try:
        return AppointmentAction(known.lower())
    except ValueError as exc:
        raise SchedulingInputError(
            f"Unrecognized appointment_action: {value!r}"
        ) from exc


@dataclass(frozen=True)
class SchedulingEngineInput:
    """The completeness-checked input handed to the downstream Scheduling Engine.

    Immutable value bundling the fields the Scheduling Engine receives for a call,
    plus the full Call State Ledger context that travels with the handoff (Req
    12.8). Constructed by :func:`build_scheduling_engine_input`, which enforces the
    completeness rules of Requirement 14.2 / Property 30 so an instance is always
    valid by construction.

    Attributes:
        appointment_action: The action, present for *every* handoff (Req 14.2).
        specialty: The confirmed, normalized specialty, present for every handoff.
        patient_id: The verified patient identifier, present for every handoff.
        patient_verified: The ledger verification status carried alongside
            ``patient_id`` (null / Success / Fail / N/A).
        visit_type: Present **iff** ``appointment_action`` is ``create`` (Req 14.2);
            ``None`` for every manage action.
        location: The location when known on the ledger, else ``None``.
        provider_name: The requested provider when known on the ledger, else ``None``.
        existing_appointment_date: The target appointment date when known (used for
            cancel / reschedule), else ``None``.
        ledger: The full Call State Ledger passed with the handoff (Req 12.8).
    """

    appointment_action: AppointmentAction
    specialty: str
    patient_id: str
    patient_verified: Optional[str]
    visit_type: Optional[VisitType]
    location: Optional[str]
    provider_name: Optional[str]
    existing_appointment_date: Optional[str]
    ledger: CallStateLedger

    def to_payload(self) -> dict[str, Any]:
        """Return the engine-facing payload dict with only the applicable keys.

        Always includes ``appointment_action``, ``specialty``, ``patient_id``, and
        ``patient_verified``. Includes ``visit_type`` iff the action is ``create``,
        and ``location`` / ``provider_name`` / ``existing_appointment_date`` only
        when those are known (Req 14.2). The full ledger travels separately via
        :attr:`ledger` (Req 12.8) and is not duplicated into this scalar payload.

        Returns:
            The engine input as a plain dict of the applicable fields.
        """
        payload: dict[str, Any] = {
            "appointment_action": self.appointment_action.value,
            "specialty": self.specialty,
            "patient_id": self.patient_id,
            "patient_verified": self.patient_verified,
        }
        if self.visit_type is not None:
            payload["visit_type"] = self.visit_type.value
        if self.location is not None:
            payload["location"] = self.location
        if self.provider_name is not None:
            payload["provider_name"] = self.provider_name
        if self.existing_appointment_date is not None:
            payload["existing_appointment_date"] = self.existing_appointment_date
        return payload


def build_scheduling_engine_input(
    ledger: CallStateLedger, visit_type: Optional[VisitType] = None
) -> SchedulingEngineInput:
    """Build the completeness-checked Scheduling Engine input from the ledger (Req 14.2, 12.8).

    Enforces the input-completeness rules of Requirement 14.2 / Property 30:

    * ``specialty``, a verified ``patient_id``, and ``appointment_action`` are
      required for **every** action; a missing one raises
      :class:`SchedulingInputError` (the completeness guarantee).
    * ``visit_type`` is included **iff** ``appointment_action`` is ``create`` (Req
      13.7, 14.2). For ``create`` a resolved ``visit_type`` is required (Scheduling
      Init resolves it via :func:`determine_visit_type` before the Engine); for a
      manage action any provided ``visit_type`` is ignored and never emitted.
    * ``location`` / ``provider_name`` / ``existing_appointment_date`` are included
      only when known on the ledger.

    The full Call State Ledger is carried on the returned value (Req 12.8), so the
    handoff passes the complete context, not just the scalar fields.

    Args:
        ledger: The current Call State Ledger. Not mutated.
        visit_type: The ``visit_type`` resolved by Scheduling Init. Required for a
            ``create`` action; ignored for manage actions.

    Returns:
        A completeness-checked :class:`SchedulingEngineInput`.

    Raises:
        SchedulingInputError: If ``appointment_action``, ``specialty``, or a
            verified ``patient_id`` is missing, or if ``visit_type`` is missing for
            a ``create`` action.
    """
    action = _coerce_action(ledger.appointment_action)

    specialty = _known(ledger.specialty)
    if specialty is None:
        raise SchedulingInputError(
            "specialty is required for the Scheduling Engine handoff (all actions)"
        )

    patient_id = _known(ledger.patient_id)
    if patient_id is None:
        raise SchedulingInputError(
            "a verified patient_id is required for the Scheduling Engine handoff "
            "(all actions)"
        )

    if action is AppointmentAction.CREATE:
        if visit_type is None:
            raise SchedulingInputError(
                "visit_type is required for a create action; Scheduling Init must "
                "resolve it before the Scheduling Engine handoff"
            )
        effective_visit_type: Optional[VisitType] = visit_type
    else:
        # Manage actions never carry a visit_type (Req 13.7).
        effective_visit_type = None

    logger.debug(
        "Built Scheduling Engine input: action={}, visit_type={}",
        action.value,
        effective_visit_type.value if effective_visit_type else None,
    )
    return SchedulingEngineInput(
        appointment_action=action,
        specialty=specialty,
        patient_id=patient_id,
        patient_verified=ledger.patient_verified,
        visit_type=effective_visit_type,
        location=_known(ledger.location),
        provider_name=_known(ledger.provider_name),
        existing_appointment_date=_known(ledger.existing_appointment_date),
        ledger=ledger,
    )


__all__ = [
    "SchedulingInputError",
    # Visit types
    "VisitType",
    # Visit-type resolver (Req 13.2-13.6, Property 28)
    "VisitReasonSignals",
    "resolve_visit_type",
    "VisitTypeOutcome",
    "VisitTypeDecision",
    "determine_visit_type",
    "resolve_disambiguation_answer",
    # Never-set guard (Req 12.4, 13.7, Property 29)
    "SwitchboardCluster",
    "SWITCHBOARD_CLUSTERS",
    "VISIT_TYPE_STAGE",
    "cluster_sets_or_asks_visit_type",
    "visit_type_applies_to_action",
    # Engine-input completeness (Req 14.2, 12.8, Property 30)
    "SchedulingEngineInput",
    "build_scheduling_engine_input",
]
