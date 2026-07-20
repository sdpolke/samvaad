"""Property-based test for name-alone insufficiency (task 6.4).

Covers Property 8 — Name alone is insufficient to hand off (Req 6.7).

For any ledger, `ready_to_handoff(ledger)` is true only when at least one of
intent, specialty, provider, or specific request is present; a ledger with only
`caller_name` set is never ready.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.greeting import (
    HANDOFF_SIGNAL_FIELDS,
    ready_to_handoff,
)
from api.services.switchboard.ledger import CallStateLedger

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-blank strings for populating fields (a populated field is any non-None,
# non-blank value per should_ask semantics).
_nonempty_strings = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

# Caller names: always non-blank when we want the "name-only" scenario.
_caller_names = _nonempty_strings

# One of the hand-off signal fields, with a non-blank value.
_signal_field_with_value = st.sampled_from(list(HANDOFF_SIGNAL_FIELDS)).flatmap(
    lambda field: _nonempty_strings.map(lambda val: (field, val))
)

# Multiple signal fields populated simultaneously (1–5 fields).
_multiple_signal_fields = st.lists(
    st.sampled_from(list(HANDOFF_SIGNAL_FIELDS)),
    min_size=1,
    max_size=len(HANDOFF_SIGNAL_FIELDS),
    unique=True,
).flatmap(
    lambda fields: st.fixed_dictionaries(
        {field: _nonempty_strings for field in fields}
    )
)


# ===========================================================================
# Property 8: Name alone is insufficient to hand off
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
@given(caller_name=_caller_names)
@example(caller_name="John Smith")
@example(caller_name="A")
@example(caller_name="Jane Doe-Williams")
@settings(max_examples=200)
def test_property_8_name_alone_never_ready(caller_name: str) -> None:
    """A ledger with only caller_name set is never ready to hand off.

    **Validates: Requirements 6.7**

    The Greeting phase treats the caller name alone as insufficient to hand off.
    No matter what name the caller provides, unless at least one of intent,
    specialty, provider_name, scan_type, or appointment_action is also populated,
    the predicate returns False.
    """
    # Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
    ledger = CallStateLedger(caller_name=caller_name)

    assert ready_to_handoff(ledger) is False, (
        f"ready_to_handoff should be False with only caller_name={caller_name!r}"
    )


# Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
@given(signal=_signal_field_with_value)
@example(signal=("intent", "scheduling"))
@example(signal=("specialty", "cardiology"))
@example(signal=("provider_name", "Dr. Smith"))
@example(signal=("scan_type", "MRI"))
@example(signal=("appointment_action", "create"))
@settings(max_examples=200)
def test_property_8_single_signal_field_is_ready(
    signal: tuple[str, str],
) -> None:
    """A ledger with any single signal field populated is ready to hand off.

    **Validates: Requirements 6.7**

    When at least one of the HANDOFF_SIGNAL_FIELDS is populated (even without
    caller_name), ready_to_handoff returns True.
    """
    # Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
    field, value = signal
    ledger = CallStateLedger(**{field: value})

    assert ready_to_handoff(ledger) is True, (
        f"ready_to_handoff should be True when {field}={value!r} is populated"
    )


# Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
@given(caller_name=_caller_names, signal=_signal_field_with_value)
@example(caller_name="John", signal=("intent", "scheduling"))
@example(caller_name="Jane", signal=("provider_name", "Dr. Chen"))
@example(caller_name="Pat", signal=("appointment_action", "cancel"))
@settings(max_examples=200)
def test_property_8_name_plus_signal_is_ready(
    caller_name: str, signal: tuple[str, str]
) -> None:
    """A ledger with caller_name AND a signal field is ready to hand off.

    **Validates: Requirements 6.7**

    The presence of caller_name does not interfere with hand-off readiness when
    a signal field is also present.
    """
    # Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
    field, value = signal
    ledger = CallStateLedger(caller_name=caller_name, **{field: value})

    assert ready_to_handoff(ledger) is True, (
        f"ready_to_handoff should be True with caller_name={caller_name!r} "
        f"and {field}={value!r}"
    )


# Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
@given(signals=_multiple_signal_fields)
@settings(max_examples=200)
def test_property_8_multiple_signals_is_ready(
    signals: dict[str, str],
) -> None:
    """A ledger with multiple signal fields populated is ready to hand off.

    **Validates: Requirements 6.7**

    When multiple HANDOFF_SIGNAL_FIELDS are populated simultaneously,
    ready_to_handoff returns True.
    """
    # Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
    ledger = CallStateLedger(**signals)

    assert ready_to_handoff(ledger) is True, (
        f"ready_to_handoff should be True with signals={signals!r}"
    )


# Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
@given(data=st.data())
@settings(max_examples=200)
def test_property_8_empty_ledger_never_ready(data: st.DataObject) -> None:
    """A completely empty ledger is never ready to hand off.

    **Validates: Requirements 6.7**

    With no fields populated at all (fresh ledger), the predicate must be False.
    """
    # Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off
    ledger = CallStateLedger()

    assert ready_to_handoff(ledger) is False, (
        "ready_to_handoff should be False for an empty ledger"
    )
