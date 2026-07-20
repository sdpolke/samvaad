"""Property-based test for ledger intent vs routing-intent separation (task 3.4).

Covers Property 4 — Ledger intent is distinct from routing intent (Req 2.4).

For any ledger and any routing-intent string produced by routing intent resolution,
running route resolution leaves ``ledger.intent`` unchanged and stores the routing
intent separately.
"""

# Feature: spinsci-switchboard-poc, Property 4: Ledger intent is distinct from routing intent

from __future__ import annotations

from typing import Any

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.ledger import (
    LEDGER_FIELD_NAMES,
    CallStateLedger,
    RoutingResolution,
    resolve_routing,
)

# ---------------------------------------------------------------------------
# Strategies: ledger and routing-intent generators
# ---------------------------------------------------------------------------

# Realistic intent values the ledger might hold
_REALISTIC_INTENTS = [
    "Scheduling",
    "Billing",
    "Referrals",
    "Triage",
    "mychart",
    "Paging",
    "Records",
    "General",
    "Directory",
    "Hotword-Urgent",
]

# Ledger intent values: None, empty, whitespace, or realistic classification labels
_ledger_intent_values = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),
    st.sampled_from(_REALISTIC_INTENTS),
    st.text(min_size=1, max_size=40),
)

# Routing intent values: non-empty strings that typically differ from ledger intent
_routing_intent_values = st.one_of(
    st.sampled_from(
        [
            "route_to_scheduling",
            "route_to_billing",
            "route_to_triage",
            "route_to_paging",
            "route_to_referrals",
            "route_to_records",
            "route_to_directory",
            "urgent_transfer",
            "afterhours_answering",
        ]
    ),
    st.text(min_size=1, max_size=60),
)

# String field values for building ledgers
_string_values = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),
    st.text(min_size=1, max_size=50),
)

# Integer field values
_int_values = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=10000),
)

# Boolean field values for Optional[bool]
_optional_bool_values = st.one_of(st.none(), st.booleans())

# Boolean field values for non-optional bool
_bool_values = st.booleans()

# Field-specific value generators
_FIELD_STRATEGIES: dict[str, st.SearchStrategy[Any]] = {
    "caller_name": _string_values,
    "intent": _ledger_intent_values,
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


@st.composite
def ledger_with_intent_strategy(draw: st.DrawFn) -> CallStateLedger:
    """Generate a ledger that always has the intent field explicitly set."""
    base = draw(ledger_strategy())
    intent_value = draw(_ledger_intent_values)
    return base.model_copy(update={"intent": intent_value})


@st.composite
def differing_routing_intent_strategy(
    draw: st.DrawFn, ledger_intent: str | None
) -> str:
    """Generate a routing intent string that differs from the ledger intent."""
    routing = draw(_routing_intent_values)
    # If they happen to match, append a suffix to guarantee separation test stress
    if routing == ledger_intent:
        routing = routing + "_routed"
    return routing


# ===========================================================================
# Property 4: Ledger intent is distinct from routing intent
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 4: Ledger intent is distinct from routing intent
@given(ledger=ledger_strategy(), routing_intent=_routing_intent_values)
@example(
    ledger=CallStateLedger(),
    routing_intent="route_to_scheduling",
)  # Empty ledger (intent=None), routing intent set
@example(
    ledger=CallStateLedger(intent="Scheduling"),
    routing_intent="route_to_scheduling",
)  # Ledger intent populated, routing intent differs
@example(
    ledger=CallStateLedger(intent="Scheduling"),
    routing_intent="Scheduling",
)  # Same string as ledger intent — must still stay separate
@example(
    ledger=CallStateLedger(intent=None),
    routing_intent="urgent_transfer",
)  # None ledger intent vs non-empty routing intent
@example(
    ledger=CallStateLedger(intent=""),
    routing_intent="route_to_billing",
)  # Empty-string ledger intent vs routing intent
@settings(max_examples=200)
def test_property_4_resolve_routing_does_not_mutate_ledger_intent(
    ledger: CallStateLedger, routing_intent: str
) -> None:
    """resolve_routing never mutates ledger.intent and stores routing intent separately.

    **Validates: Requirements 2.4**

    For any ledger and any routing-intent string, calling resolve_routing:
    1. Does not change ledger.intent
    2. Returns a RoutingResolution with routing_intent == the passed string
    3. Snapshots ledger.intent into RoutingResolution.ledger_intent
    4. The ledger object is identical before and after the call
    """
    # Snapshot the entire ledger state before calling resolve_routing
    original_dump = ledger.model_dump()
    original_intent = ledger.intent

    # Act
    resolution = resolve_routing(ledger, routing_intent)

    # Assert: returns a RoutingResolution
    assert isinstance(resolution, RoutingResolution)

    # Assert: ledger.intent is unchanged after the call
    assert ledger.intent == original_intent, (
        f"ledger.intent was mutated! Before: {original_intent!r}, after: {ledger.intent!r}"
    )

    # Assert: the entire ledger is unchanged (not just intent)
    assert ledger.model_dump() == original_dump, (
        "resolve_routing mutated the ledger object"
    )

    # Assert: RoutingResolution.routing_intent holds the exact routing intent passed in
    assert resolution.routing_intent == routing_intent, (
        f"routing_intent not stored correctly. "
        f"Expected {routing_intent!r}, got {resolution.routing_intent!r}"
    )

    # Assert: RoutingResolution.ledger_intent equals ledger.intent (snapshot)
    assert resolution.ledger_intent == original_intent, (
        f"ledger_intent snapshot mismatch. "
        f"Expected {original_intent!r}, got {resolution.ledger_intent!r}"
    )


# Feature: spinsci-switchboard-poc, Property 4: Ledger intent is distinct from routing intent
@given(ledger=ledger_with_intent_strategy(), routing_intent=_routing_intent_values)
@example(
    ledger=CallStateLedger(intent="Billing"),
    routing_intent="route_to_billing",
)  # Populated ledger intent, different routing intent
@example(
    ledger=CallStateLedger(intent="Triage", caller_name="Ada", after_hours=True),
    routing_intent="urgent_transfer",
)  # Multi-field ledger with populated intent
@settings(max_examples=200)
def test_property_4_routing_intent_never_written_back_to_ledger(
    ledger: CallStateLedger, routing_intent: str
) -> None:
    """The routing intent is never written back onto ledger.intent.

    **Validates: Requirements 2.4**

    Even when the routing intent string differs from the ledger's internal intent
    classification label, calling resolve_routing never writes the routing intent
    back onto ledger.intent. The two are stored in completely separate containers.
    """
    original_intent = ledger.intent
    original_dump = ledger.model_dump()

    resolution = resolve_routing(ledger, routing_intent)

    # The ledger's intent field is still whatever it was before
    assert ledger.intent == original_intent

    # The routing intent lives on the resolution, not on the ledger
    assert resolution.routing_intent == routing_intent

    # If routing_intent != ledger.intent, confirm ledger wasn't contaminated
    if routing_intent != original_intent:
        assert ledger.intent != routing_intent, (
            "Routing intent was written back onto ledger.intent!"
        )

    # Full ledger unchanged
    assert ledger.model_dump() == original_dump


# Feature: spinsci-switchboard-poc, Property 4: Ledger intent is distinct from routing intent
@given(ledger=ledger_strategy(), routing_intent=_routing_intent_values)
@example(
    ledger=CallStateLedger(intent="Scheduling"),
    routing_intent="route_to_scheduling",
)
@settings(max_examples=200)
def test_property_4_routing_resolution_is_frozen(
    ledger: CallStateLedger, routing_intent: str
) -> None:
    """RoutingResolution is immutable (frozen) once created.

    **Validates: Requirements 2.4**

    The routing resolution container is frozen so that neither the ledger_intent
    snapshot nor the routing_intent can be silently altered after creation.
    """
    resolution = resolve_routing(ledger, routing_intent)

    # Verify it's a frozen model — attempting mutation should raise
    import pytest

    with pytest.raises(Exception):
        resolution.routing_intent = "tampered"  # type: ignore[misc]

    with pytest.raises(Exception):
        resolution.ledger_intent = "tampered"  # type: ignore[misc]

    # Values remain as originally set
    assert resolution.routing_intent == routing_intent
    assert resolution.ledger_intent == ledger.intent
