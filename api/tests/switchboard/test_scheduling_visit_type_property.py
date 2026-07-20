"""Property-based test for visit-type resolution and disambiguation (task 13.2).

Covers Property 28 — Visit-type resolution and disambiguation
(Requirements 13.2, 13.5).

WHEN `appointment_action` is `create`, THE Scheduling_Init SHALL set `visit_type`
to `sick` or `wellness` before invoking the Scheduling_Engine (Req 13.2).

WHEN the disambiguation answer is a wellness exam, THE Scheduling_Init SHALL set
`visit_type` to `wellness`; WHEN the answer is the symptom visit, THE Scheduling_Init
SHALL set `visit_type` to `sick`; WHEN both are indicated, THE Scheduling_Init SHALL
set `visit_type` to `wellness` (Req 13.5).
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard import scripts
from api.services.switchboard.scheduling import (
    VisitReasonSignals,
    VisitType,
    VisitTypeDecision,
    VisitTypeOutcome,
    determine_visit_type,
    resolve_disambiguation_answer,
    resolve_visit_type,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All four signal combinations for VisitReasonSignals.
_visit_reason_signals = st.builds(
    VisitReasonSignals,
    has_wellness_signal=st.booleans(),
    has_symptom_signal=st.booleans(),
)

#: Boolean pairs for disambiguation answers.
_disambiguation_answers = st.tuples(st.booleans(), st.booleans())


# ===========================================================================
# Property 28: Visit-type resolution and disambiguation
# ===========================================================================


# ---------------------------------------------------------------------------
# resolve_visit_type
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 28: Visit-type resolution and disambiguation
@given(signals=_visit_reason_signals)
@example(signals=VisitReasonSignals(has_wellness_signal=True, has_symptom_signal=False))
@example(signals=VisitReasonSignals(has_wellness_signal=False, has_symptom_signal=True))
@example(signals=VisitReasonSignals(has_wellness_signal=True, has_symptom_signal=True))
@example(signals=VisitReasonSignals(has_wellness_signal=False, has_symptom_signal=False))
@settings(max_examples=200)
def test_resolve_visit_type_wellness_signal_only(signals: VisitReasonSignals) -> None:
    """resolve_visit_type maps signals correctly per Req 13.2, 13.5.

    **Validates: Requirements 13.2, 13.5**

    - wellness only → WELLNESS
    - symptom only → SICK
    - both → WELLNESS (mandated safe default, Req 13.5)
    - neither → None (unknown)
    """
    # Feature: spinsci-switchboard-poc, Property 28: Visit-type resolution and disambiguation

    result = resolve_visit_type(signals)

    if signals.has_wellness_signal and signals.has_symptom_signal:
        assert result is VisitType.WELLNESS, (
            f"Both signals present — expected WELLNESS (safe default), got {result}"
        )
    elif signals.has_wellness_signal:
        assert result is VisitType.WELLNESS, (
            f"Wellness signal only — expected WELLNESS, got {result}"
        )
    elif signals.has_symptom_signal:
        assert result is VisitType.SICK, (
            f"Symptom signal only — expected SICK, got {result}"
        )
    else:
        assert result is None, (
            f"Neither signal — expected None, got {result}"
        )


# ---------------------------------------------------------------------------
# determine_visit_type
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 28: Visit-type resolution and disambiguation
@given(signals=_visit_reason_signals)
@example(signals=VisitReasonSignals(has_wellness_signal=True, has_symptom_signal=True))
@example(signals=VisitReasonSignals(has_wellness_signal=True, has_symptom_signal=False))
@example(signals=VisitReasonSignals(has_wellness_signal=False, has_symptom_signal=True))
@example(signals=VisitReasonSignals(has_wellness_signal=False, has_symptom_signal=False))
@settings(max_examples=200)
def test_determine_visit_type_flow_branches(signals: VisitReasonSignals) -> None:
    """determine_visit_type selects the correct flow branch per Req 13.2-13.6.

    **Validates: Requirements 13.2, 13.5**

    - Both signals → ASK_DISAMBIGUATION, visit_type=WELLNESS (default), question=disambiguation
    - One signal only → RESOLVED, visit_type set directly, no question
    - Neither → ASK_REASON, visit_type=None, question=visit reason
    """
    # Feature: spinsci-switchboard-poc, Property 28: Visit-type resolution and disambiguation

    decision: VisitTypeDecision = determine_visit_type(signals)

    if signals.has_wellness_signal and signals.has_symptom_signal:
        # Both signals: ask disambiguation
        assert decision.outcome is VisitTypeOutcome.ASK_DISAMBIGUATION, (
            f"Both signals — expected ASK_DISAMBIGUATION, got {decision.outcome}"
        )
        assert decision.visit_type is VisitType.WELLNESS, (
            f"Both signals — default visit_type should be WELLNESS, got {decision.visit_type}"
        )
        assert decision.question == scripts.SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION, (
            f"Both signals — expected disambiguation question, got {decision.question!r}"
        )
        assert decision.must_ask is True

    elif signals.has_wellness_signal:
        # Wellness only: resolved directly
        assert decision.outcome is VisitTypeOutcome.RESOLVED, (
            f"Wellness only — expected RESOLVED, got {decision.outcome}"
        )
        assert decision.visit_type is VisitType.WELLNESS, (
            f"Wellness only — expected WELLNESS, got {decision.visit_type}"
        )
        assert decision.question is None, (
            f"Wellness only — expected no question, got {decision.question!r}"
        )
        assert decision.must_ask is False

    elif signals.has_symptom_signal:
        # Symptom only: resolved directly
        assert decision.outcome is VisitTypeOutcome.RESOLVED, (
            f"Symptom only — expected RESOLVED, got {decision.outcome}"
        )
        assert decision.visit_type is VisitType.SICK, (
            f"Symptom only — expected SICK, got {decision.visit_type}"
        )
        assert decision.question is None, (
            f"Symptom only — expected no question, got {decision.question!r}"
        )
        assert decision.must_ask is False

    else:
        # Neither signal: ask reason
        assert decision.outcome is VisitTypeOutcome.ASK_REASON, (
            f"Neither signal — expected ASK_REASON, got {decision.outcome}"
        )
        assert decision.visit_type is None, (
            f"Neither signal — expected visit_type=None, got {decision.visit_type}"
        )
        assert decision.question == scripts.SCHED_INIT_VISIT_REASON, (
            f"Neither signal — expected visit reason question, got {decision.question!r}"
        )
        assert decision.must_ask is True


# ---------------------------------------------------------------------------
# resolve_disambiguation_answer
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 28: Visit-type resolution and disambiguation
@given(answer=_disambiguation_answers)
@example(answer=(True, False))
@example(answer=(False, True))
@example(answer=(True, True))
@example(answer=(False, False))
@settings(max_examples=200)
def test_resolve_disambiguation_answer(answer: tuple[bool, bool]) -> None:
    """resolve_disambiguation_answer maps answer booleans per Req 13.5.

    **Validates: Requirements 13.5**

    - answer_is_symptom only → SICK
    - answer_is_wellness (with or without symptom) → WELLNESS
    - neither (unintelligible) → WELLNESS (safe default)
    """
    # Feature: spinsci-switchboard-poc, Property 28: Visit-type resolution and disambiguation

    answer_is_wellness, answer_is_symptom = answer
    result = resolve_disambiguation_answer(answer_is_wellness, answer_is_symptom)

    if answer_is_symptom and not answer_is_wellness:
        assert result is VisitType.SICK, (
            f"Symptom only answer — expected SICK, got {result}"
        )
    else:
        # wellness-only, both, or unintelligible all resolve to WELLNESS
        assert result is VisitType.WELLNESS, (
            f"answer_is_wellness={answer_is_wellness}, answer_is_symptom={answer_is_symptom} "
            f"— expected WELLNESS, got {result}"
        )
