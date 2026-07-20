"""Property-based test for the never-re-ask predicate (task 3.3).

Covers Property 3 — Never re-ask a populated field (Req 2.3, 15.4).

For any ledger and any collection node, if the field that node would collect is
already populated, the node emits no question for that field (``should_ask(field,
ledger)`` is False whenever the field is non-empty).
"""

from __future__ import annotations

from typing import Any

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.ledger import (
    LEDGER_FIELD_NAMES,
    CallStateLedger,
    should_ask,
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

# Strategies for *populated* values only (never None/empty/whitespace-only)
_POPULATED_STRING = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")
_POPULATED_INT = st.integers(min_value=0, max_value=10000)
_POPULATED_BOOL = st.booleans()

_POPULATED_FIELD_STRATEGIES: dict[str, st.SearchStrategy[Any]] = {
    "caller_name": _POPULATED_STRING,
    "intent": _POPULATED_STRING,
    "patient_status": _POPULATED_STRING,
    "provider_name": _POPULATED_STRING,
    "specialty": _POPULATED_STRING,
    "scan_type": _POPULATED_STRING,
    "location": _POPULATED_STRING,
    "department_name": _POPULATED_STRING,
    "department_id": _POPULATED_STRING,
    "patient_verified": _POPULATED_STRING,
    "appointment_action": _POPULATED_STRING,
    "existing_appointment_date": _POPULATED_STRING,
    "visit_type": _POPULATED_STRING,
    "visit_reason": _POPULATED_STRING,
    "preferred_provider_id": _POPULATED_STRING,
    "preferred_date": _POPULATED_STRING,
    "patient_id": _POPULATED_STRING,
    "ah_intent_selection": _POPULATED_STRING,
    "selected_id": _POPULATED_INT,
    "greeting_ani_match_count": _POPULATED_INT,
    "caller_is_provider": _POPULATED_BOOL,
    "after_hours": _POPULATED_BOOL,
    "greeting_ani_lookup_done": _POPULATED_BOOL,
}

# Strategies for *not-populated* values only (None, empty string, whitespace)
_NOT_POPULATED_STRING = st.one_of(st.none(), st.just(""), st.just("   "), st.just("  \t "))
_NOT_POPULATED_INT = st.none()
_NOT_POPULATED_OPTIONAL_BOOL = st.none()

_NOT_POPULATED_FIELD_STRATEGIES: dict[str, st.SearchStrategy[Any]] = {
    "caller_name": _NOT_POPULATED_STRING,
    "intent": _NOT_POPULATED_STRING,
    "patient_status": _NOT_POPULATED_STRING,
    "provider_name": _NOT_POPULATED_STRING,
    "specialty": _NOT_POPULATED_STRING,
    "scan_type": _NOT_POPULATED_STRING,
    "location": _NOT_POPULATED_STRING,
    "department_name": _NOT_POPULATED_STRING,
    "department_id": _NOT_POPULATED_STRING,
    "patient_verified": _NOT_POPULATED_STRING,
    "appointment_action": _NOT_POPULATED_STRING,
    "existing_appointment_date": _NOT_POPULATED_STRING,
    "visit_type": _NOT_POPULATED_STRING,
    "visit_reason": _NOT_POPULATED_STRING,
    "preferred_provider_id": _NOT_POPULATED_STRING,
    "preferred_date": _NOT_POPULATED_STRING,
    "patient_id": _NOT_POPULATED_STRING,
    "ah_intent_selection": _NOT_POPULATED_STRING,
    "selected_id": _NOT_POPULATED_INT,
    "greeting_ani_match_count": _NOT_POPULATED_INT,
    # caller_is_provider is Optional[bool], None = not populated
    "caller_is_provider": _NOT_POPULATED_OPTIONAL_BOOL,
    # after_hours and greeting_ani_lookup_done are non-optional bool with defaults;
    # they are ALWAYS populated (even False counts as populated), so we cannot
    # generate a "not populated" value for them in normal circumstances.
    # However, their default is False, which IS populated, so they are excluded
    # from "not populated" tests.
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


@st.composite
def full_ledger_strategy(draw: st.DrawFn) -> CallStateLedger:
    """Generate a fully-populated ledger (all 23 fields explicitly set with populated values)."""
    kwargs: dict[str, Any] = {}
    for field in sorted(LEDGER_FIELD_NAMES):
        kwargs[field] = draw(_POPULATED_FIELD_STRATEGIES[field])
    return CallStateLedger(**kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fields that are non-optional bool (always populated since even False counts)
_ALWAYS_POPULATED_FIELDS = frozenset({"after_hours", "greeting_ani_lookup_done"})

# Fields that can be "not populated" (Optional or nullable)
_NULLABLE_FIELDS = LEDGER_FIELD_NAMES - _ALWAYS_POPULATED_FIELDS


def _is_populated(value: Any) -> bool:
    """Mirror the ledger module's population check for test assertions."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


# ===========================================================================
# Property 3: Never re-ask a populated field
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 3: Never re-ask a populated field
@given(ledger=ledger_strategy(), field=st.sampled_from(sorted(LEDGER_FIELD_NAMES)))
@example(
    ledger=CallStateLedger(),
    field="caller_name",
)  # Empty ledger — should_ask returns True for an unpopulated field
@example(
    ledger=CallStateLedger(caller_name="Ada"),
    field="caller_name",
)  # Populated string field — should_ask returns False
@example(
    ledger=CallStateLedger(selected_id=0),
    field="selected_id",
)  # 0 is populated for a number field — should_ask returns False
@example(
    ledger=CallStateLedger(after_hours=False),
    field="after_hours",
)  # False is populated for a bool field — should_ask returns False
@example(
    ledger=CallStateLedger(caller_is_provider=False),
    field="caller_is_provider",
)  # False is populated for Optional[bool] — should_ask returns False
@example(
    ledger=CallStateLedger(specialty="   "),
    field="specialty",
)  # Whitespace-only specialty normalizes to None — should_ask returns True
@settings(max_examples=200)
def test_property_3_never_reask_populated_field(
    ledger: CallStateLedger, field: str
) -> None:
    """should_ask returns False for any field that is already populated.

    **Validates: Requirements 2.3, 15.4**

    For any field on the ledger, if the current value is populated (non-None,
    non-empty/whitespace for strings, any int/bool value including 0/False),
    then should_ask(field, ledger) returns False — the collection node must
    NOT re-ask for that field.

    Conversely, if the field is not populated (None or empty/whitespace string),
    should_ask returns True — the node should still ask.
    """
    value = getattr(ledger, field)
    populated = _is_populated(value)

    result = should_ask(field, ledger)

    if populated:
        assert result is False, (
            f"should_ask('{field}', ledger) returned True but the field is populated "
            f"with {value!r}. The node must NOT re-ask."
        )
    else:
        assert result is True, (
            f"should_ask('{field}', ledger) returned False but the field is NOT "
            f"populated (value={value!r}). The node should still ask."
        )


# Feature: spinsci-switchboard-poc, Property 3: Never re-ask a populated field
@given(ledger=full_ledger_strategy(), field=st.sampled_from(sorted(LEDGER_FIELD_NAMES)))
@settings(max_examples=200)
def test_property_3_fully_populated_ledger_never_asks(
    ledger: CallStateLedger, field: str
) -> None:
    """For a fully-populated ledger, should_ask returns False for every field.

    **Validates: Requirements 2.3, 15.4**

    When all 23 fields hold meaningful values, no collection node should emit a
    question for any field.
    """
    result = should_ask(field, ledger)

    assert result is False, (
        f"should_ask('{field}', ledger) returned True on a fully-populated ledger. "
        f"Value was {getattr(ledger, field)!r}. Must never re-ask."
    )


# Feature: spinsci-switchboard-poc, Property 3: Never re-ask a populated field
@given(
    field=st.sampled_from(sorted(_NULLABLE_FIELDS)),
    data=st.data(),
)
@settings(max_examples=200)
def test_property_3_not_populated_field_should_ask(
    field: str, data: st.DataObject
) -> None:
    """For any field that is NOT populated, should_ask returns True.

    **Validates: Requirements 2.3, 15.4**

    When a nullable field holds None or an empty/whitespace-only string, the
    collection node should still ask for that field.
    """
    # Build a ledger with this specific field set to a not-populated value
    if field in _NOT_POPULATED_FIELD_STRATEGIES:
        value = data.draw(_NOT_POPULATED_FIELD_STRATEGIES[field], label=f"{field}_value")
    else:
        value = None

    kwargs: dict[str, Any] = {field: value}
    ledger = CallStateLedger(**kwargs)

    # After model construction, get the actual stored value (specialty normalizes)
    actual_value = getattr(ledger, field)

    # Confirm the value is indeed not populated
    assert not _is_populated(actual_value), (
        f"Expected field '{field}' to be NOT populated with value {value!r} "
        f"(actual stored: {actual_value!r})"
    )

    result = should_ask(field, ledger)

    assert result is True, (
        f"should_ask('{field}', ledger) returned False but the field is not populated "
        f"(value={actual_value!r}). The node should ask."
    )


# Feature: spinsci-switchboard-poc, Property 3: Never re-ask a populated field
@given(
    field=st.sampled_from(sorted(LEDGER_FIELD_NAMES)),
    data=st.data(),
)
@settings(max_examples=200)
def test_property_3_populated_field_never_asks(
    field: str, data: st.DataObject
) -> None:
    """For any field explicitly set to a populated value, should_ask returns False.

    **Validates: Requirements 2.3, 15.4**

    Tests the populated direction explicitly: generate a ledger where the target
    field is guaranteed to hold a meaningful value, and assert should_ask is False.
    """
    value = data.draw(_POPULATED_FIELD_STRATEGIES[field], label=f"{field}_value")
    kwargs: dict[str, Any] = {field: value}
    ledger = CallStateLedger(**kwargs)

    result = should_ask(field, ledger)

    assert result is False, (
        f"should_ask('{field}', ledger) returned True but the field is populated "
        f"with {value!r}. Must never re-ask a populated field."
    )
