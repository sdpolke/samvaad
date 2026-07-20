"""Property + unit tests for After-Hours-phase pure logic (tasks 12.2, 12.3, 12.4).

Covers the three After Hours concerns implemented in
:mod:`api.services.switchboard.after_hours`:

* Property 31 — after-hours restricted-service connect decision (Req 8.2, 8.9,
  8.10, 8.11).
* Property 32 — after-hours hotword path (Req 8.3).
* Property 33 — after-hours Billing/MyChart are closed (Req 8.4, 8.5).

Each property runs >= 100 iterations (Hypothesis default) and its generators hit
the relevant edge cases (every connect response, the 10-second timeout boundary,
every closed-service intent, mixed-case keywords).
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from api.services.switchboard import scripts
from api.services.switchboard.after_hours import (
    AH_INTENT_AFTERHOURS_ANSWERING_SERVICE,
    AH_INTENT_HOSPITAL_OR_PHYSICIAN,
    RESTRICTED_CONNECT_TIMEOUT_SECONDS,
    AHClassificationRetryState,
    ClosedServiceDecision,
    ConnectResponse,
    HOTWORD_ROUTING,
    PagingClarifierAnswer,
    afterhours_closed_service,
    ah_classification_retry,
    detect_hotword,
    hotword_routing_decision,
    is_hotword,
    paging_clarifier_decision,
    paging_clarifier_line,
    restricted_service_connect_decision,
)
from api.services.switchboard.auth import PATIENT_VERIFIED_NA, Intent
from api.services.switchboard.business_hours import SILENT_TO_ROUTING

# ===========================================================================
# Property 31: After-hours restricted-service connect decision
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 31: After-hours restricted-service connect decision
@given(
    response=st.sampled_from(ConnectResponse),
    elapsed_seconds=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False),
    ),
    timed_out_flag=st.booleans(),
)
def test_property_31_restricted_service_connect_decision(
    response: ConnectResponse,
    elapsed_seconds: float | None,
    timed_out_flag: bool,
) -> None:
    """Auth+Route proceed iff the caller agreed within the 10s window; else end.

    **Validates: Requirements 8.2, 8.9, 8.10, 8.11**
    """
    decision = restricted_service_connect_decision(
        response, elapsed_seconds, timed_out=timed_out_flag
    )

    # Effective timeout: explicit flag OR elapsed strictly beyond the 10s bound.
    effective_timeout = timed_out_flag or (
        elapsed_seconds is not None
        and elapsed_seconds > RESTRICTED_CONNECT_TIMEOUT_SECONDS
    )
    expected_proceed = response is ConnectResponse.AGREED and not effective_timeout

    # Proceed to Auth+Route iff agreed within the window (Req 8.9).
    assert decision.proceed_to_auth_and_route is expected_proceed
    # The two outcomes are always logical opposites: agree proceeds, everything
    # else (decline, unintelligible, timeout) ends the flow (Req 8.10, 8.11).
    assert decision.end_restricted_flow is (not expected_proceed)
    assert decision.timed_out is bool(effective_timeout)


class TestRestrictedServiceConnectDecision:
    def test_agree_within_window_proceeds(self) -> None:
        decision = restricted_service_connect_decision(ConnectResponse.AGREED, 3.0)
        assert decision.proceed_to_auth_and_route is True
        assert decision.end_restricted_flow is False

    def test_decline_ends_flow(self) -> None:
        decision = restricted_service_connect_decision(ConnectResponse.DECLINED)
        assert decision.proceed_to_auth_and_route is False
        assert decision.end_restricted_flow is True

    def test_unintelligible_ends_flow(self) -> None:
        decision = restricted_service_connect_decision(ConnectResponse.UNINTELLIGIBLE)
        assert decision.end_restricted_flow is True

    def test_agree_at_exactly_10s_still_proceeds(self) -> None:
        # "within 10 seconds" — the bound itself is in-time.
        decision = restricted_service_connect_decision(
            ConnectResponse.AGREED, float(RESTRICTED_CONNECT_TIMEOUT_SECONDS)
        )
        assert decision.proceed_to_auth_and_route is True

    def test_agree_after_timeout_treated_as_declined(self) -> None:
        decision = restricted_service_connect_decision(
            ConnectResponse.AGREED, 10.5
        )
        assert decision.proceed_to_auth_and_route is False
        assert decision.end_restricted_flow is True
        assert decision.timed_out is True

    def test_timeout_flag_treated_as_declined(self) -> None:
        decision = restricted_service_connect_decision(
            ConnectResponse.AGREED, timed_out=True
        )
        assert decision.end_restricted_flow is True


# ===========================================================================
# Property 32: After-hours hotword path
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 32: After-hours hotword path
@given(
    keyword=st.sampled_from(["chest pain", "stroke", "bleeding", "unconscious"]),
    prefix=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=20),
    suffix=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=20),
    upper=st.booleans(),
)
def test_property_32_hotword_path(
    keyword: str, prefix: str, suffix: str, upper: bool
) -> None:
    """A detected hotword → silent Routing, patient_verified=N/A, Hotword-Urgent line.

    **Validates: Requirements 8.3**
    """
    keywords = ["chest pain", "stroke", "bleeding", "unconscious"]
    spoken = f"{prefix}{keyword}{suffix}"
    if upper:
        spoken = spoken.upper()

    # A configured keyword is detected regardless of case (config lowercases).
    assert is_hotword(spoken, keywords) is True

    decision = hotword_routing_decision(spoken, keywords)
    assert decision is not None
    # Silent turn into Routing.
    assert decision.to_routing is True
    assert decision.is_silent is True
    assert decision.spoken_filler == ""
    # patient_verified = N/A (reuses the auth vocabulary constant).
    assert decision.patient_verified == PATIENT_VERIFIED_NA
    # Hotword-Urgent transfer line.
    assert decision.transfer_line == scripts.E_HOTWORD_URGENT


class TestHotwordDetection:
    def test_no_keyword_no_detection(self) -> None:
        assert detect_hotword("I would like to schedule", ["stroke"]) is None
        assert hotword_routing_decision("hello there", ["stroke"]) is None

    def test_empty_speech(self) -> None:
        assert detect_hotword("", ["stroke"]) is None
        assert detect_hotword(None, ["stroke"]) is None

    def test_empty_keyword_list(self) -> None:
        # No configured hotwords → nothing ever fires (Req 21 config-driven).
        assert detect_hotword("chest pain right now", []) is None

    def test_case_insensitive_match(self) -> None:
        assert detect_hotword("I have CHEST PAIN", ["chest pain"]) == "chest pain"

    def test_canonical_decision_shape(self) -> None:
        assert HOTWORD_ROUTING.patient_verified == PATIENT_VERIFIED_NA
        assert HOTWORD_ROUTING.transfer_line == scripts.E_HOTWORD_URGENT
        assert HOTWORD_ROUTING.is_silent is True


# ===========================================================================
# Property 33: After-hours Billing/MyChart are closed
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 33: After-hours Billing/MyChart are closed
@given(
    intent=st.sampled_from(list(Intent)),
    cased=st.booleans(),
)
def test_property_33_billing_mychart_closed(intent: Intent, cased: bool) -> None:
    """Billing/MyChart after hours → mandated closed line, no in-hours transfer.

    **Validates: Requirements 8.4, 8.5**
    """
    raw = intent.value.lower() if cased else intent.value
    decision = afterhours_closed_service(raw)

    if intent in (Intent.BILLING, Intent.MYCHART):
        assert isinstance(decision, ClosedServiceDecision)
        assert decision.intent is intent
        assert decision.perform_in_hours_transfer is False
        expected = (
            scripts.AH_BILLING_CLOSED
            if intent is Intent.BILLING
            else scripts.AH_MYCHART_CLOSED
        )
        assert decision.closed_line == expected
    else:
        # No other intent is a closed after-hours service.
        assert decision is None


class TestAfterhoursClosedService:
    def test_billing_closed_line(self) -> None:
        decision = afterhours_closed_service("Billing")
        assert decision is not None
        assert decision.closed_line == scripts.AH_BILLING_CLOSED
        assert decision.perform_in_hours_transfer is False

    def test_mychart_closed_line(self) -> None:
        decision = afterhours_closed_service(Intent.MYCHART)
        assert decision is not None
        assert decision.closed_line == scripts.AH_MYCHART_CLOSED

    def test_unrelated_intent_returns_none(self) -> None:
        assert afterhours_closed_service("Scheduling") is None
        assert afterhours_closed_service(None) is None


# ===========================================================================
# Supporting unit tests: paging clarifier (Req 8.8) + retry machine (Req 8.6/8.7)
# ===========================================================================


class TestPagingClarifier:
    def test_provider_answer(self) -> None:
        decision = paging_clarifier_decision(PagingClarifierAnswer.PROVIDER)
        assert decision.caller_is_provider is True
        assert decision.ah_intent_selection == AH_INTENT_HOSPITAL_OR_PHYSICIAN

    def test_patient_answer(self) -> None:
        decision = paging_clarifier_decision(PagingClarifierAnswer.PATIENT)
        assert decision.caller_is_provider is False
        assert decision.ah_intent_selection == AH_INTENT_AFTERHOURS_ANSWERING_SERVICE

    def test_clarifier_lines_are_verbatim(self) -> None:
        for option in (1, 2, 3):
            assert (
                paging_clarifier_line(option)
                == scripts.AH_PAGING_CLARIFIER_OPTIONS[option - 1]
            )

    def test_invalid_option_raises(self) -> None:
        with pytest.raises(ValueError):
            paging_clarifier_line(0)
        with pytest.raises(ValueError):
            paging_clarifier_line(4)


class TestAHClassificationRetry:
    def test_first_failure_speaks_retry_1(self) -> None:
        decision = ah_classification_retry(1)
        assert decision.spoken_line == scripts.AH_RETRY_1
        assert decision.silent_transition is None
        assert decision.is_silent is False

    def test_second_failure_speaks_retry_2(self) -> None:
        decision = ah_classification_retry(2)
        assert decision.spoken_line == scripts.AH_RETRY_2
        assert decision.silent_transition is None

    def test_third_failure_silent_to_routing(self) -> None:
        decision = ah_classification_retry(3)
        assert decision.spoken_line is None
        assert decision.silent_transition is SILENT_TO_ROUTING
        assert decision.is_silent is True

    def test_beyond_third_stays_silent(self) -> None:
        decision = ah_classification_retry(7)
        assert decision.is_silent is True

    def test_zero_or_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            ah_classification_retry(0)

    def test_state_machine_progression(self) -> None:
        state = AHClassificationRetryState()
        assert state.consecutive_failures == 0
        state = state.record_failure()
        assert state.decision.spoken_line == scripts.AH_RETRY_1
        state = state.record_failure()
        assert state.decision.spoken_line == scripts.AH_RETRY_2
        state = state.record_failure()
        assert state.has_fallen_back is True
        assert state.decision.is_silent is True
        # A successful turn resets the counter.
        assert state.reset().consecutive_failures == 0
