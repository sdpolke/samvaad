"""Property-based test for appointment-action classification (task 8.2).

Covers Property 11 — Appointment-action classification never defaults to create
(Requirements 7.6, 7.7, 12.1).

The property verifies that for any caller utterance expressing cancel, reschedule,
list, or confirm, the classified ``appointment_action`` equals that action and is
never ``create``. Generators cover all five AppointmentAction values and edge cases.
"""

# Feature: spinsci-switchboard-poc, Property 11: Appointment-action classification never defaults to create

from __future__ import annotations

from typing import Optional

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.business_hours import (
    AppointmentAction,
    classify_appointment_action,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Representative cue phrases for each manage action (drawn from the regex patterns
# in _ACTION_CUES). These are concrete phrases that each regex will match.
_MANAGE_CUE_PHRASES: dict[AppointmentAction, list[str]] = {
    AppointmentAction.RESCHEDULE: [
        "I need to reschedule",
        "Can I re-schedule my visit",
        "I want to move my appointment",
        "Can you push back my appointment",
        "I need to change my appointment",
        "Can I switch to another day",
        "I need a different time",
        "Can I get another date",
    ],
    AppointmentAction.CANCEL: [
        "I need to cancel my appointment",
        "Please cancel that",
        "I want to call off my visit",
        "Can you drop that appointment",
        "I want to get rid of my appointment",
    ],
    AppointmentAction.CONFIRM: [
        "I want to confirm my appointment",
        "Can you verify my visit",
        "Is my appointment still on",
        "Is it still scheduled",
        "I just want to double check",
        "I want to make sure it's still good",
    ],
    AppointmentAction.LIST: [
        "Can you list my appointments",
        "What appointments do I have",
        "Which appointment is next",
        "Do I have any upcoming visits",
        "Can I see my appointments",
        "Show me my appointments",
        "Any appointments this week",
        "I want to check my appointments",
    ],
}

_CREATE_CUE_PHRASES: list[str] = [
    "I want to create an appointment",
    "I need to make an appointment",
    "Can I book a visit",
    "I want to schedule something",
    "I need to set up an appointment",
    "I'd like a new appointment",
    "I need an appointment",
    "I want an appointment please",
    "Can I get an appointment with the doctor",
    "I'd like to come in for a checkup",
    "I need to see the doctor",
]

# Filler text that contains no action cues — appended to utterances to add noise.
_FILLER_FRAGMENTS: list[str] = [
    "",
    " please",
    " thank you",
    " as soon as possible",
    " for next week",
    " with Dr. Smith",
    " at the downtown office",
    " in the morning",
    " this is urgent",
    " I called earlier today",
]

# Strategy: a manage-action cue phrase paired with the expected action
_manage_action_and_phrase = st.sampled_from(
    [
        (action, phrase)
        for action, phrases in _MANAGE_CUE_PHRASES.items()
        for phrase in phrases
    ]
)

# Strategy: a create cue phrase
_create_phrase = st.sampled_from(_CREATE_CUE_PHRASES)

# Strategy: random filler text to append (noise)
_filler = st.sampled_from(_FILLER_FRAGMENTS)

# Strategy: utterances with NO action cues at all (should classify as None)
_NO_CUE_PHRASES: list[str] = [
    "hello",
    "good morning",
    "yes",
    "no",
    "I'm not sure",
    "uh huh",
    "what are your hours",
    "where are you located",
    "thanks",
    "okay",
    "can you repeat that",
]

_no_cue_phrase = st.sampled_from(_NO_CUE_PHRASES)


# ===========================================================================
# Property 11: Appointment-action classification never defaults to create
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 11: Appointment-action classification never defaults to create
@given(
    action_and_phrase=_manage_action_and_phrase,
    filler=_filler,
)
@example(
    action_and_phrase=(AppointmentAction.CANCEL, "I need to cancel my appointment"),
    filler="",
)
@example(
    action_and_phrase=(AppointmentAction.RESCHEDULE, "I need to reschedule"),
    filler=" please",
)
@example(
    action_and_phrase=(AppointmentAction.CONFIRM, "Is my appointment still on"),
    filler="",
)
@example(
    action_and_phrase=(AppointmentAction.LIST, "Do I have any upcoming visits"),
    filler="",
)
@settings(max_examples=200)
def test_property_11_manage_action_never_classified_as_create(
    action_and_phrase: tuple[AppointmentAction, str],
    filler: str,
) -> None:
    """A manage-action cue is NEVER classified as create (Req 7.7, Property 11).

    **Validates: Requirements 7.6, 7.7, 12.1**

    For any caller utterance that expresses cancel, reschedule, list, or confirm,
    the classified appointment_action is never ``create``. This is the critical
    invariant guaranteed by _CLASSIFICATION_ORDER evaluating manage actions before
    create.
    """
    expected_action, phrase = action_and_phrase
    utterance = phrase + filler

    result = classify_appointment_action(utterance)

    # The result must NOT be create
    assert result is not AppointmentAction.CREATE, (
        f"VIOLATION of Req 7.7 / Property 11: manage utterance classified as create.\n"
        f"Utterance: {utterance!r}\n"
        f"Expected action: {expected_action.value}\n"
        f"Got: {result}"
    )
    # The result should be the expected manage action (or possibly another manage
    # action if the filler triggers a higher-priority manage cue, but never create)
    assert result is not None, (
        f"Expected a manage action but got None.\n"
        f"Utterance: {utterance!r}\n"
        f"Expected: {expected_action.value}"
    )


# Feature: spinsci-switchboard-poc, Property 11: Appointment-action classification never defaults to create
@given(
    action_and_phrase=_manage_action_and_phrase,
    filler=_filler,
)
@example(
    action_and_phrase=(AppointmentAction.CANCEL, "I need to cancel my appointment"),
    filler="",
)
@example(
    action_and_phrase=(AppointmentAction.RESCHEDULE, "Can I re-schedule my visit"),
    filler="",
)
@example(
    action_and_phrase=(AppointmentAction.LIST, "Can you list my appointments"),
    filler="",
)
@example(
    action_and_phrase=(AppointmentAction.CONFIRM, "I want to confirm my appointment"),
    filler="",
)
@settings(max_examples=200)
def test_property_11_manage_action_returns_correct_action(
    action_and_phrase: tuple[AppointmentAction, str],
    filler: str,
) -> None:
    """A manage-action cue classifies to the correct manage action (Req 7.6, 12.1).

    **Validates: Requirements 7.6, 7.7, 12.1**

    For any caller utterance that expresses a single manage action, the classified
    appointment_action equals that specific action — verifying both that it is
    never create (Req 7.7) and that the mapping is correct (Req 7.6).
    """
    expected_action, phrase = action_and_phrase
    utterance = phrase + filler

    result = classify_appointment_action(utterance)

    # Must equal the expected manage action
    assert result == expected_action, (
        f"Manage utterance classified incorrectly.\n"
        f"Utterance: {utterance!r}\n"
        f"Expected: {expected_action.value}\n"
        f"Got: {result.value if result else None}"
    )


# Feature: spinsci-switchboard-poc, Property 11: Appointment-action classification never defaults to create
@given(
    create_phrase=_create_phrase,
    filler=_filler,
)
@example(create_phrase="I want to create an appointment", filler="")
@example(create_phrase="I need to make an appointment", filler=" please")
@example(create_phrase="Can I book a visit", filler="")
@settings(max_examples=200)
def test_property_11_create_cue_classifies_as_create(
    create_phrase: str,
    filler: str,
) -> None:
    """A create-only cue classifies to create (Req 7.6, 12.1).

    **Validates: Requirements 7.6, 7.7, 12.1**

    For caller utterances containing only create cues (no manage cues), the result
    is AppointmentAction.CREATE. This verifies the positive path: create IS returned
    when no manage cue is present.
    """
    utterance = create_phrase + filler

    result = classify_appointment_action(utterance)

    assert result == AppointmentAction.CREATE, (
        f"Create utterance not classified as create.\n"
        f"Utterance: {utterance!r}\n"
        f"Got: {result.value if result else None}"
    )


# Feature: spinsci-switchboard-poc, Property 11: Appointment-action classification never defaults to create
@given(phrase=_no_cue_phrase)
@example(phrase="hello")
@example(phrase="")
@settings(max_examples=200)
def test_property_11_no_cue_returns_none(phrase: str) -> None:
    """No action cue yields None — never defaults to create (Req 7.7).

    **Validates: Requirements 7.6, 7.7, 12.1**

    When the caller utterance has no recognizable action cue, the classifier
    returns None (unclassifiable). It does NOT default to create, satisfying the
    never-create invariant for ambiguous/empty inputs.
    """
    result = classify_appointment_action(phrase)

    assert result is None, (
        f"Expected None for no-cue utterance, got {result}.\n"
        f"Utterance: {phrase!r}"
    )


# Feature: spinsci-switchboard-poc, Property 11: Appointment-action classification never defaults to create
@given(data=st.data())
@settings(max_examples=200)
def test_property_11_none_and_empty_input_returns_none(data: st.DataObject) -> None:
    """None and empty/whitespace inputs yield None (Req 7.7 boundary).

    **Validates: Requirements 7.6, 7.7, 12.1**

    Edge cases: None, empty string, and whitespace-only inputs never default to
    create — they return None.
    """
    speech: Optional[str] = data.draw(
        st.one_of(
            st.none(),
            st.just(""),
            st.just("   "),
            st.just("\t\n"),
        )
    )

    result = classify_appointment_action(speech)

    assert result is None, (
        f"Expected None for empty/None input, got {result}.\n"
        f"Input: {speech!r}"
    )


# Feature: spinsci-switchboard-poc, Property 11: Appointment-action classification never defaults to create
@given(action=st.sampled_from(list(AppointmentAction)))
@settings(max_examples=200)
def test_property_11_all_actions_reachable(action: AppointmentAction) -> None:
    """Every AppointmentAction value is reachable from some utterance (Req 7.6, 12.1).

    **Validates: Requirements 7.6, 7.7, 12.1**

    Confirms the classifier can produce each of the five action values, ensuring
    the generators cover the full AppointmentAction enum space.
    """
    # Pick a representative phrase for the target action
    if action == AppointmentAction.CREATE:
        phrases = _CREATE_CUE_PHRASES
    else:
        phrases = _MANAGE_CUE_PHRASES[action]

    # Any of the cue phrases should produce the expected action
    phrase = phrases[0]
    result = classify_appointment_action(phrase)

    assert result == action, (
        f"Action {action.value} not reachable from representative phrase.\n"
        f"Phrase: {phrase!r}\n"
        f"Got: {result.value if result else None}"
    )
