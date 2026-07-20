"""Property-based test for the greeting turn-1 ANI-lookup post-state (task 6.2).

Covers Property 6 — Greeting turn 1 is silent with a well-defined post-state
(Req 6.1, 6.2, 6.3).

For any ANI-lookup outcome (match(s), no match, failure, or 2-second timeout),
turn 1 emits no Switchboard-generated speech, and after turn 1
`greeting_ani_lookup_done` is true with `greeting_ani_match_count` equal to
the number of matches (0 on failure/timeout) and no caller-facing error is
produced.
"""

from __future__ import annotations

from typing import Any

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.greeting import (
    AniLookupOutcome,
    AniLookupResult,
    apply_turn1_ani_lookup,
    build_turn1_post_state,
)
from api.services.switchboard.ledger import (
    LEDGER_FIELD_NAMES,
    CallStateLedger,
)

# ---------------------------------------------------------------------------
# Strategies: ANI lookup result generators
# ---------------------------------------------------------------------------

# Match counts for successful lookups: 0 (no match), 1 (single match), many
_success_match_counts = st.one_of(
    st.just(0),  # No match found
    st.just(1),  # Exactly one match (personalized)
    st.integers(min_value=2, max_value=100),  # Multiple matches (ambiguous)
)


@st.composite
def ani_lookup_result_strategy(draw: st.DrawFn) -> AniLookupResult:
    """Generate a random AniLookupResult covering all outcome types.

    Generators cover: SUCCESS with match_count 0/1/many, FAILURE, and TIMEOUT.
    """
    outcome = draw(st.sampled_from(list(AniLookupOutcome)))
    if outcome is AniLookupOutcome.SUCCESS:
        match_count = draw(_success_match_counts)
        return AniLookupResult.success(match_count)
    elif outcome is AniLookupOutcome.FAILURE:
        return AniLookupResult.failure()
    else:
        return AniLookupResult.timeout()


# String field values for ledger generation
_string_values = st.one_of(
    st.none(),
    st.just(""),
    st.text(min_size=1, max_size=30),
)

_int_values = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=10000),
)

_optional_bool_values = st.one_of(st.none(), st.booleans())
_bool_values = st.booleans()

_FIELD_STRATEGIES: dict[str, st.SearchStrategy[Any]] = {
    "caller_name": _string_values,
    "intent": _string_values,
    "patient_status": _string_values,
    "provider_name": _string_values,
    "specialty": _string_values,
    "scan_type": _string_values,
    "location": _string_values,
    "department_name": _string_values,
    "department_id": _string_values,
    "patient_verified": _string_values,
    "appointment_action": _string_values,
    "existing_appointment_date": _string_values,
    "visit_type": _string_values,
    "visit_reason": _string_values,
    "preferred_provider_id": _string_values,
    "preferred_date": _string_values,
    "patient_id": _string_values,
    "ah_intent_selection": _string_values,
    "selected_id": _int_values,
    "greeting_ani_match_count": _int_values,
    "caller_is_provider": _optional_bool_values,
    "after_hours": _bool_values,
    "greeting_ani_lookup_done": _bool_values,
}


@st.composite
def ledger_strategy(draw: st.DrawFn) -> CallStateLedger:
    """Generate a random CallStateLedger with a random subset of fields populated."""
    fields_to_set = draw(
        st.lists(st.sampled_from(sorted(LEDGER_FIELD_NAMES)), unique=True)
    )
    kwargs: dict[str, Any] = {}
    for field in fields_to_set:
        kwargs[field] = draw(_FIELD_STRATEGIES[field])
    return CallStateLedger(**kwargs)


# ===========================================================================
# Property 6: Greeting turn 1 is silent with a well-defined post-state
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state
@given(result=ani_lookup_result_strategy())
@example(result=AniLookupResult.success(0))   # No match
@example(result=AniLookupResult.success(1))   # Single match (personalized)
@example(result=AniLookupResult.success(5))   # Multiple matches
@example(result=AniLookupResult.failure())    # Lookup failure
@example(result=AniLookupResult.timeout())    # 2-second timeout
@settings(max_examples=200)
def test_property_6_build_turn1_post_state_always_sets_done(
    result: AniLookupResult,
) -> None:
    """build_turn1_post_state always sets greeting_ani_lookup_done to True.

    **Validates: Requirements 6.1, 6.2, 6.3**

    Regardless of the ANI-lookup outcome (success/failure/timeout), turn 1
    completes with greeting_ani_lookup_done=True.
    """
    # Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state
    post_state = build_turn1_post_state(result)

    # greeting_ani_lookup_done is always True after turn 1
    assert post_state["greeting_ani_lookup_done"] is True


# Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state
@given(result=ani_lookup_result_strategy())
@example(result=AniLookupResult.success(0))   # No match → count 0
@example(result=AniLookupResult.success(1))   # Single match → count 1
@example(result=AniLookupResult.success(42))  # Many matches → count 42
@example(result=AniLookupResult.failure())    # Failure → count 0
@example(result=AniLookupResult.timeout())    # Timeout → count 0
@settings(max_examples=200)
def test_property_6_match_count_correct_per_outcome(
    result: AniLookupResult,
) -> None:
    """greeting_ani_match_count equals match_count for SUCCESS, 0 for FAILURE/TIMEOUT.

    **Validates: Requirements 6.1, 6.2, 6.3**

    On SUCCESS the count is carried through; on FAILURE or TIMEOUT the count
    is forced to 0 (Requirement 6.3).
    """
    # Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state
    post_state = build_turn1_post_state(result)

    if result.outcome is AniLookupOutcome.SUCCESS:
        assert post_state["greeting_ani_match_count"] == result.match_count
    else:
        # FAILURE and TIMEOUT produce 0 matches (Req 6.3)
        assert post_state["greeting_ani_match_count"] == 0


# Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state
@given(result=ani_lookup_result_strategy())
@example(result=AniLookupResult.success(0))
@example(result=AniLookupResult.failure())
@example(result=AniLookupResult.timeout())
@settings(max_examples=200)
def test_property_6_no_speech_or_error_in_post_state(
    result: AniLookupResult,
) -> None:
    """The post-state dict contains ONLY ledger fields — no error or speech keys.

    **Validates: Requirements 6.1, 6.2, 6.3**

    Turn 1 emits no Switchboard-generated speech and no caller-facing error.
    The returned dict must contain only recognized ledger field names.
    """
    # Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state
    post_state = build_turn1_post_state(result)

    # No "error" or "speech" field present (no caller-facing error, no speech)
    assert "error" not in post_state
    assert "speech" not in post_state
    assert "error_message" not in post_state
    assert "tts_text" not in post_state

    # All keys are valid ledger field names
    for key in post_state:
        assert key in LEDGER_FIELD_NAMES, (
            f"Post-state key '{key}' is not a recognized ledger field"
        )


# Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state
@given(ledger=ledger_strategy(), result=ani_lookup_result_strategy())
@example(
    ledger=CallStateLedger(),
    result=AniLookupResult.success(1),
)  # Empty ledger + single match
@example(
    ledger=CallStateLedger(
        caller_name="Ada",
        intent="Scheduling",
        after_hours=True,
    ),
    result=AniLookupResult.failure(),
)  # Populated ledger + failure
@example(
    ledger=CallStateLedger(
        caller_name="Bob",
        specialty="cardiology",
        selected_id=7,
        after_hours=False,
        greeting_ani_lookup_done=False,
    ),
    result=AniLookupResult.timeout(),
)  # Populated ledger + timeout
@settings(max_examples=200)
def test_property_6_apply_carries_full_ledger_forward(
    ledger: CallStateLedger, result: AniLookupResult
) -> None:
    """apply_turn1_ani_lookup carries the full prior ledger forward.

    **Validates: Requirements 6.1, 6.2, 6.3**

    All prior fields are preserved when applying the turn-1 post-state.
    Only greeting_ani_lookup_done and greeting_ani_match_count change.
    """
    # Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state
    original_dump = ledger.model_dump()

    reduced = apply_turn1_ani_lookup(ledger, result)

    assert isinstance(reduced, CallStateLedger)

    # The two ANI fields are set correctly
    assert reduced.greeting_ani_lookup_done is True
    if result.outcome is AniLookupOutcome.SUCCESS:
        assert reduced.greeting_ani_match_count == result.match_count
    else:
        assert reduced.greeting_ani_match_count == 0

    # All OTHER fields are carried forward unchanged
    reduced_dump = reduced.model_dump()
    for field in LEDGER_FIELD_NAMES:
        if field in ("greeting_ani_lookup_done", "greeting_ani_match_count"):
            continue
        # Account for specialty normalization
        expected = original_dump[field]
        if field == "specialty" and isinstance(expected, str):
            expected = expected.strip() or None
        assert reduced_dump[field] == expected, (
            f"Field '{field}' was not carried forward. "
            f"Expected {expected!r}, got {reduced_dump[field]!r}"
        )

    # Non-mutation: original ledger unchanged
    assert ledger.model_dump() == original_dump
