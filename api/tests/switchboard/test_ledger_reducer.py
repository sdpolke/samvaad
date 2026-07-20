"""Unit tests for the ledger reducer, never-re-ask predicate, and routing-intent
separation (task 3.1 → Requirements 2.1, 2.2, 2.3, 2.4, 15.4).

These are focused example tests that verify the pure functions compile and behave
as specified. The exhaustive property-based coverage (Properties 2, 3, 4) lives in
separate tasks (3.2, 3.3, 3.4).
"""

from __future__ import annotations

import pytest

from api.services.switchboard.ledger import (
    LEDGER_FIELD_NAMES,
    CallStateLedger,
    RoutingResolution,
    reduce_ledger,
    resolve_routing,
    should_ask,
)


class TestReduceLedger:
    def test_carries_full_ledger_forward(self) -> None:
        current = CallStateLedger(
            caller_name="Ada",
            intent="Scheduling",
            specialty="cardiology",
            after_hours=True,
        )
        reduced = reduce_ledger(current, {"patient_status": "existing"})

        # Updated field applied.
        assert reduced.patient_status == "existing"
        # Every prior field carried forward, nothing dropped/reset.
        assert reduced.caller_name == "Ada"
        assert reduced.intent == "Scheduling"
        assert reduced.specialty == "cardiology"
        assert reduced.after_hours is True

    def test_does_not_mutate_input(self) -> None:
        current = CallStateLedger(caller_name="Ada")
        reduce_ledger(current, {"caller_name": "Grace"})
        assert current.caller_name == "Ada"

    def test_only_updated_fields_change(self) -> None:
        current = CallStateLedger(caller_name="Ada", intent="Records")
        reduced = reduce_ledger(current, {"intent": "General"})
        assert reduced.intent == "General"
        assert reduced.caller_name == "Ada"

    def test_none_update_clears_field(self) -> None:
        current = CallStateLedger(provider_name="Dr. Lovelace")
        reduced = reduce_ledger(current, {"provider_name": None})
        assert reduced.provider_name is None

    def test_validators_run_on_reduced_result(self) -> None:
        current = CallStateLedger()
        reduced = reduce_ledger(current, {"selected_id": "42", "specialty": "  ENT  "})
        assert reduced.selected_id == 42
        assert reduced.specialty == "ENT"

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(KeyError):
            reduce_ledger(CallStateLedger(), {"not_a_field": "x"})


class TestShouldAsk:
    def test_true_when_string_field_unset(self) -> None:
        assert should_ask("caller_name", CallStateLedger()) is True

    def test_false_when_string_field_populated(self) -> None:
        assert should_ask("caller_name", CallStateLedger(caller_name="Ada")) is False

    def test_true_when_string_field_blank(self) -> None:
        assert should_ask("caller_name", CallStateLedger(caller_name="   ")) is True

    def test_zero_count_is_populated(self) -> None:
        # greeting_ani_match_count == 0 is a meaningful value (no ANI match).
        ledger = CallStateLedger(greeting_ani_match_count=0)
        assert should_ask("greeting_ani_match_count", ledger) is False

    def test_number_field_unset_should_ask(self) -> None:
        assert should_ask("selected_id", CallStateLedger()) is True

    def test_accepts_all_23_fields(self) -> None:
        ledger = CallStateLedger()
        assert len(LEDGER_FIELD_NAMES) == 23
        for field in LEDGER_FIELD_NAMES:
            # Must not raise for any Appendix D field name.
            assert isinstance(should_ask(field, ledger), bool)

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(KeyError):
            should_ask("not_a_field", CallStateLedger())


class TestResolveRouting:
    def test_leaves_ledger_intent_unchanged(self) -> None:
        ledger = CallStateLedger(intent="Scheduling")
        resolution = resolve_routing(ledger, "SCHEDULING_QUEUE_A")
        assert ledger.intent == "Scheduling"
        assert isinstance(resolution, RoutingResolution)
        assert resolution.ledger_intent == "Scheduling"
        assert resolution.routing_intent == "SCHEDULING_QUEUE_A"

    def test_routing_intent_not_written_back(self) -> None:
        ledger = CallStateLedger(intent="General")
        resolve_routing(ledger, "SOME_OTHER_ROUTE")
        assert ledger.intent == "General"

    def test_resolution_is_frozen(self) -> None:
        resolution = resolve_routing(CallStateLedger(intent="Records"), "RECORDS_Q")
        with pytest.raises(Exception):
            resolution.routing_intent = "TAMPERED"
