"""Property-based test for the full-carry ledger reducer (task 3.2).

Covers Property 2 — Ledger carried in full across transitions (Req 2.1, 2.2).

For any initial ledger and any sequence of phase transitions, exactly one ledger
exists for the call and the ledger entering each phase contains every field the
previous phase held (no field is dropped or reset by a transition).
"""

from __future__ import annotations

from typing import Any

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.ledger import (
    LEDGER_FIELD_NAMES,
    CallStateLedger,
    reduce_ledger,
)

# ---------------------------------------------------------------------------
# Strategies: ledger field value generators
# ---------------------------------------------------------------------------

# String field values: None, empty, whitespace, or realistic content
_string_values = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),
    st.text(min_size=1, max_size=50),
)

# Integer field values for selected_id and greeting_ani_match_count
_int_values = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=10000),
)

# Boolean field values for caller_is_provider (Optional[bool])
_optional_bool_values = st.one_of(st.none(), st.booleans())

# Boolean field values for after_hours and greeting_ani_lookup_done (non-optional bool)
_bool_values = st.booleans()

# Field-specific value generators
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
    # Pick a random subset of fields to populate
    fields_to_set = draw(
        st.lists(st.sampled_from(sorted(LEDGER_FIELD_NAMES)), unique=True)
    )
    kwargs: dict[str, Any] = {}
    for field in fields_to_set:
        kwargs[field] = draw(_FIELD_STRATEGIES[field])
    return CallStateLedger(**kwargs)


@st.composite
def full_ledger_strategy(draw: st.DrawFn) -> CallStateLedger:
    """Generate a fully-populated ledger (all 23 fields explicitly set)."""
    kwargs: dict[str, Any] = {}
    for field in sorted(LEDGER_FIELD_NAMES):
        kwargs[field] = draw(_FIELD_STRATEGIES[field])
    return CallStateLedger(**kwargs)


@st.composite
def update_dict_strategy(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a valid update dictionary for reduce_ledger.

    Picks a random subset of ledger fields with random valid values.
    """
    fields_to_update = draw(
        st.lists(st.sampled_from(sorted(LEDGER_FIELD_NAMES)), unique=True)
    )
    updates: dict[str, Any] = {}
    for field in fields_to_update:
        updates[field] = draw(_FIELD_STRATEGIES[field])
    return updates


@st.composite
def transition_sequence_strategy(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a sequence of 1–5 update dicts simulating phase transitions."""
    num_transitions = draw(st.integers(min_value=1, max_value=5))
    return [draw(update_dict_strategy()) for _ in range(num_transitions)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_field_value(ledger: CallStateLedger, field: str) -> Any:
    """Retrieve a field value from a ledger, accounting for specialty normalization."""
    return getattr(ledger, field)


def _normalize_for_comparison(field: str, value: Any) -> Any:
    """Normalize a value for comparison, handling specialty normalization.

    The specialty field is normalized (stripped, blank→None) on assignment. When
    comparing carried-forward values, apply the same normalization so comparisons
    are correct.
    """
    if field == "specialty" and isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return value


# ===========================================================================
# Property 2: Ledger carried in full across transitions
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 2: Ledger carried in full across transitions
@given(ledger=ledger_strategy(), updates=update_dict_strategy())
@example(ledger=CallStateLedger(), updates={})  # Empty ledger, no-op transition
@example(
    ledger=CallStateLedger(
        caller_name="Ada",
        intent="Scheduling",
        specialty="cardiology",
        after_hours=True,
        selected_id=42,
    ),
    updates={},
)  # Populated ledger, no-op transition
@example(
    ledger=CallStateLedger(caller_name="Ada"),
    updates={"intent": "Scheduling"},
)  # Single field update
@example(
    ledger=CallStateLedger(
        caller_name="Ada",
        intent="Scheduling",
        patient_status="existing",
        provider_name="Dr. Smith",
        specialty="cardiology",
        scan_type="MRI",
        location="Chicago",
        department_name="Radiology",
        department_id="RAD-001",
        selected_id=7,
        patient_verified="Success",
        appointment_action="create",
        existing_appointment_date="2024-07-15",
        visit_type="sick",
        visit_reason="follow-up",
        preferred_provider_id="P100",
        preferred_date="2024-08-01",
        patient_id="PAT-999",
        ah_intent_selection="Hospital or Physician",
        greeting_ani_match_count=1,
        caller_is_provider=False,
        after_hours=False,
        greeting_ani_lookup_done=True,
    ),
    updates={"provider_name": None},
)  # Fully populated, one field cleared
@settings(max_examples=200)
def test_property_2_full_carry_single_transition(
    ledger: CallStateLedger, updates: dict[str, Any]
) -> None:
    """reduce_ledger carries every non-updated field forward unchanged.

    **Validates: Requirements 2.1, 2.2**

    For any field NOT in the updates dict, the reduced ledger has the same value
    as the current ledger. No field is dropped or reset by a transition.
    """
    # Snapshot input to verify non-mutation
    original_dump = ledger.model_dump()

    reduced = reduce_ledger(ledger, updates)

    # 1. Single ledger: returns exactly one new ledger
    assert reduced is not None
    assert isinstance(reduced, CallStateLedger)

    # 2. Full carry: every field NOT in updates retains its prior value
    for field in LEDGER_FIELD_NAMES:
        if field not in updates:
            expected = _normalize_for_comparison(field, _get_field_value(ledger, field))
            actual = _get_field_value(reduced, field)
            assert actual == expected, (
                f"Field '{field}' was not carried forward. "
                f"Expected {expected!r}, got {actual!r}"
            )

    # 3. No field dropped: all 23 fields exist on the reduced ledger
    reduced_dump = reduced.model_dump()
    assert set(reduced_dump.keys()) >= LEDGER_FIELD_NAMES

    # 4. Non-mutation: the input ledger is unchanged
    assert ledger.model_dump() == original_dump


# Feature: spinsci-switchboard-poc, Property 2: Ledger carried in full across transitions
@given(ledger=ledger_strategy(), transitions=transition_sequence_strategy())
@example(
    ledger=CallStateLedger(),
    transitions=[{}, {}, {}],
)  # Empty ledger through multiple no-op transitions
@example(
    ledger=CallStateLedger(caller_name="Ada", intent="Scheduling"),
    transitions=[
        {"patient_status": "existing"},
        {"provider_name": "Dr. Smith"},
        {"specialty": "cardiology"},
    ],
)  # Sequential field additions
@example(
    ledger=CallStateLedger(
        caller_name="Ada",
        intent="Scheduling",
        specialty="cardiology",
    ),
    transitions=[
        {"caller_name": None},
        {"caller_name": "Grace"},
    ],
)  # Clear then re-set
@settings(max_examples=200)
def test_property_2_sequential_transitions_full_carry(
    ledger: CallStateLedger, transitions: list[dict[str, Any]]
) -> None:
    """Applying N transitions in sequence carries ALL fields forward that weren't
    explicitly updated in any given step.

    **Validates: Requirements 2.1, 2.2**

    After applying the entire transition sequence, for any field that was NOT
    updated in the LAST transition that touched it, the field value equals what
    the previous step set it to (full carry through multi-step chains).
    """
    current = ledger

    for step_updates in transitions:
        # Snapshot the state before this transition
        before_dump = current.model_dump()

        reduced = reduce_ledger(current, step_updates)

        # Each step returns exactly one new ledger
        assert reduced is not None
        assert isinstance(reduced, CallStateLedger)

        # Full carry at each step: non-updated fields carried forward
        for field in LEDGER_FIELD_NAMES:
            if field not in step_updates:
                expected = _normalize_for_comparison(field, before_dump[field])
                actual = _get_field_value(reduced, field)
                assert actual == expected, (
                    f"Field '{field}' not carried in step with updates "
                    f"{list(step_updates.keys())}. Expected {expected!r}, got {actual!r}"
                )

        # No field dropped at each step
        reduced_dump = reduced.model_dump()
        assert set(reduced_dump.keys()) >= LEDGER_FIELD_NAMES

        # Non-mutation: the previous ledger is not altered
        assert current.model_dump() == before_dump

        current = reduced

    # Final ledger still has all 23 fields
    final_dump = current.model_dump()
    assert set(final_dump.keys()) >= LEDGER_FIELD_NAMES


# Feature: spinsci-switchboard-poc, Property 2: Ledger carried in full across transitions
@given(ledger=full_ledger_strategy(), updates=update_dict_strategy())
@settings(max_examples=200)
def test_property_2_fully_populated_ledger_carry(
    ledger: CallStateLedger, updates: dict[str, Any]
) -> None:
    """A fully-populated ledger (all 23 fields set) carries all non-updated fields.

    **Validates: Requirements 2.1, 2.2**

    This variant ensures the property holds when starting from a completely full
    ledger, confirming no field is accidentally zeroed or defaulted during merge.
    """
    original_dump = ledger.model_dump()

    reduced = reduce_ledger(ledger, updates)

    assert reduced is not None
    assert isinstance(reduced, CallStateLedger)

    for field in LEDGER_FIELD_NAMES:
        if field not in updates:
            expected = _normalize_for_comparison(field, _get_field_value(ledger, field))
            actual = _get_field_value(reduced, field)
            assert actual == expected, (
                f"Fully-populated field '{field}' was not carried forward. "
                f"Expected {expected!r}, got {actual!r}"
            )

    # Non-mutation
    assert ledger.model_dump() == original_dump


# Feature: spinsci-switchboard-poc, Property 2: Ledger carried in full across transitions
@given(ledger=ledger_strategy())
@settings(max_examples=200)
def test_property_2_empty_update_is_identity(ledger: CallStateLedger) -> None:
    """An empty updates dict produces a ledger equal to the input (identity transition).

    **Validates: Requirements 2.1, 2.2**

    A no-op phase transition (no fields changed) must yield a ledger with every
    field identical to the prior state.
    """
    original_dump = ledger.model_dump()

    reduced = reduce_ledger(ledger, {})

    # The reduced ledger equals the original in content
    assert reduced.model_dump() == original_dump

    # But it's a distinct object (non-mutation guarantee)
    assert reduced is not ledger
