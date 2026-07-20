"""Verbatim fidelity example tests for Appendix C/E script constants (task 4.4).

Each test asserts that the corresponding constant in
``api/services/switchboard/scripts.py`` equals the vendor-document text exactly
(byte-for-byte), including Script 3\u2032's deliberate comma-before-"and" punctuation.

**Validates: Requirements 18.1, 18.2, 18.4**
"""

from __future__ import annotations

from api.services.switchboard.scripts import (
    # Greeting
    GREETING_ROUTING_REQUEST,
    GREETING_SCRIPT_4_STANDARD_IN_HOURS,
    GREETING_SCRIPT_3_PRIME_AFTER_HOURS,
    GREETING_SCRIPT_2_PRIME_PERSONALIZED,
    GREETING_PATH_A_PERSONALIZED,
    GREETING_PATH_A_STANDARD,
    GREETING_PATH_B,
    GREETING_PATH_D,
    GREETING_PATH_E,
    GREETING_MEDICATION,
    GREETING_GOODBYE_RETENTION,
    GREETING_HANGUP,
    # Business Hours
    BH_FAQ_LOOKUP,
    BH_OTHER_LOOKUP,
    BH_DIRECTORY_CLOSE,
    BH_SCHEDULING_GATE,
    BH_SEARCH_TROUBLE,
    BH_RETRY_1,
    BH_RETRY_2,
    BH_LIST_CAP,
    BH_GOODBYE_RETENTION,
    BH_CLOSING,
    # After Hours
    AH_PAGING_CLARIFIER_OPTION_1,
    AH_PAGING_CLARIFIER_OPTION_2,
    AH_PAGING_CLARIFIER_OPTION_3,
    AH_RESTRICTED_SERVICE_SCHEDULING,
    AH_MYCHART_CLOSED,
    AH_BILLING_CLOSED,
    AH_DIRECTORY_GATE,
    AH_NO_MATCH,
    AH_LIVE_CONNECT_OFFER,
    AH_RETRY_1,
    AH_RETRY_2,
    AH_FOLLOW_UP_OPTION_1,
    AH_FOLLOW_UP_OPTION_2,
    # Authentication
    AUTH_ANI_OFFER,
    AUTH_PHONE_PROVIDER,
    AUTH_PHONE_PATIENT,
    AUTH_PHONE_READBACK,
    AUTH_NO_RECORD,
    AUTH_DOB_PATIENT,
    AUTH_DOB_PROVIDER,
    AUTH_NAME_CONFIRM,
    AUTH_AFTER_CONFIRM,
    AUTH_FAIL_ROUTE,
    AUTH_PUSHBACK,
    AUTH_CHANGED_REQUEST,
    AUTH_AFTER_HOURS_DOB_OPENER,
    # Scheduling Init
    SCHED_INIT_VISIT_REASON,
    SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION,
    # Appendix E
    E_SCHEDULING_NEW,
    E_SCHEDULING_EXISTING,
    E_TRIAGE,
    E_REFERRALS,
    E_PAGING,
    E_PHARMACY,
    E_BILLING,
    E_RECORDS,
    E_MYCHART,
    E_GENERAL,
    E_HOTWORD_URGENT,
    E_SWITCHBOARD_FALLBACK,
    E_SWITCHBOARD_ALT,
    E_TRANSFER_ERROR,
    E_HANGUP,
    # Renderer
    render,
)


# ===========================================================================
# Appendix C \u2014 Greeting
# ===========================================================================


class TestGreetingVerbatim:
    """Assert each Greeting-section constant equals the vendor text exactly."""

    def test_routing_request(self) -> None:
        expected = (
            "To ensure your call is routed correctly, please provide the "
            "provider, specialty, or location you are trying to reach, along "
            "with the reason for your call today."
        )
        assert GREETING_ROUTING_REQUEST == expected

    def test_script_4_standard_in_hours(self) -> None:
        expected = (
            "Thank you for calling SpinSci. This is SpinSci AI, your virtual "
            "assistant. To ensure your call is routed correctly, please provide "
            "the provider, specialty, or location you are trying to reach, along "
            "with the reason for your call today."
        )
        assert GREETING_SCRIPT_4_STANDARD_IN_HOURS == expected

    def test_script_3_prime_after_hours(self) -> None:
        """Script 3\u2032 \u2014 no period before 'and', comma-before-'and' form."""
        expected = (
            "Our offices are currently closed, so options may be limited, but "
            "I\u2019ll do my best to help, and to ensure your call is routed "
            "correctly, please provide the provider, specialty, or location you "
            "are trying to reach, along with the reason for your call today."
        )
        assert GREETING_SCRIPT_3_PRIME_AFTER_HOURS == expected

    def test_script_2_prime_personalized(self) -> None:
        expected = "Am I speaking with {FirstName}?"
        assert GREETING_SCRIPT_2_PRIME_PERSONALIZED == expected

    def test_path_a_personalized(self) -> None:
        expected = (
            "Hi {{caller_name}}, nice to meet you. Let me help you with that."
        )
        assert GREETING_PATH_A_PERSONALIZED == expected

    def test_path_a_standard(self) -> None:
        expected = "Let me help you with that."
        assert GREETING_PATH_A_STANDARD == expected

    def test_path_b(self) -> None:
        expected = (
            "Hi {{caller_name}}, nice to meet you. To ensure your call is routed "
            "correctly, please provide the provider, specialty, or location you "
            "are trying to reach, along with the reason for your call today."
        )
        assert GREETING_PATH_B == expected

    def test_path_d(self) -> None:
        expected = (
            "No worries \u2014 I can still help you. To ensure your call is "
            "routed correctly, please provide the provider, specialty, or "
            "location you are trying to reach, along with the reason for your "
            "call today."
        )
        assert GREETING_PATH_D == expected

    def test_path_e(self) -> None:
        expected = "I didn\u2019t quite catch that. Could you repeat that for me?"
        assert GREETING_PATH_E == expected

    def test_medication(self) -> None:
        expected = "You\u2019re calling about your prescription."
        assert GREETING_MEDICATION == expected

    def test_goodbye_retention(self) -> None:
        expected = "Before you go, is there anything else I can help you with?"
        assert GREETING_GOODBYE_RETENTION == expected

    def test_hangup(self) -> None:
        expected = "Thank you for calling SpinSci. Goodbye."
        assert GREETING_HANGUP == expected


# ===========================================================================
# Appendix C \u2014 Business Hours
# ===========================================================================


class TestBusinessHoursVerbatim:
    """Assert each Business Hours constant equals the vendor text exactly."""

    def test_faq_lookup(self) -> None:
        assert BH_FAQ_LOOKUP == "Let me check that for you."

    def test_other_lookup(self) -> None:
        assert BH_OTHER_LOOKUP == "One moment."

    def test_directory_close(self) -> None:
        expected = "Can I help with anything else before we end our call?"
        assert BH_DIRECTORY_CLOSE == expected

    def test_scheduling_gate(self) -> None:
        assert BH_SCHEDULING_GATE == "Are you a new or existing patient?"

    def test_search_trouble(self) -> None:
        expected = (
            "I\u2019m having some trouble finding that. Would you like me to "
            "connect you with someone who can help?"
        )
        assert BH_SEARCH_TROUBLE == expected

    def test_retry_1(self) -> None:
        expected = (
            "I\u2019m sorry, I didn\u2019t catch that. How can I help you direct "
            "your call today?"
        )
        assert BH_RETRY_1 == expected

    def test_retry_2(self) -> None:
        expected = (
            "I\u2019m still having trouble understanding. Please tell me what "
            "you need help with \u2014 like scheduling, a nurse, or a provider."
        )
        assert BH_RETRY_2 == expected

    def test_list_cap(self) -> None:
        expected = (
            "I have a few more as well. Would you like me to continue, or does "
            "one of those sound right?"
        )
        assert BH_LIST_CAP == expected

    def test_goodbye_retention(self) -> None:
        expected = "Before you go, is there anything else I can help you with?"
        assert BH_GOODBYE_RETENTION == expected

    def test_closing(self) -> None:
        assert BH_CLOSING == "Thank you for calling SpinSci. Have a great day."


# ===========================================================================
# Appendix C \u2014 After Hours
# ===========================================================================


class TestAfterHoursVerbatim:
    """Assert each After Hours constant equals the vendor text exactly."""

    def test_paging_clarifier_option_1(self) -> None:
        expected = (
            "Just to route this correctly \u2014 are you calling from a hospital "
            "or medical facility, or are you the patient?"
        )
        assert AH_PAGING_CLARIFIER_OPTION_1 == expected

    def test_paging_clarifier_option_2(self) -> None:
        expected = (
            "Are you a doctor or calling from a medical facility, or are you "
            "calling for yourself as the patient?"
        )
        assert AH_PAGING_CLARIFIER_OPTION_2 == expected

    def test_paging_clarifier_option_3(self) -> None:
        expected = (
            "Are you staff calling about a patient, or are you calling for "
            "yourself?"
        )
        assert AH_PAGING_CLARIFIER_OPTION_3 == expected

    def test_restricted_service_scheduling(self) -> None:
        expected = (
            "I\u2019m sorry, our scheduling services are currently closed. "
            "You\u2019re welcome to call back during business hours, or I can "
            "connect you to someone \u2014 though they won\u2019t be from the "
            "specific office you\u2019re calling about. Would you like me to do "
            "that?"
        )
        assert AH_RESTRICTED_SERVICE_SCHEDULING == expected

    def test_mychart_closed(self) -> None:
        expected = (
            "I\u2019m sorry, MyChart support is currently closed. Please call "
            "back during business hours for live assistance."
        )
        assert AH_MYCHART_CLOSED == expected

    def test_billing_closed(self) -> None:
        expected = (
            "I\u2019m sorry, our billing department is currently closed. Please "
            "call back during business hours for billing assistance."
        )
        assert AH_BILLING_CLOSED == expected

    def test_directory_gate(self) -> None:
        assert AH_DIRECTORY_GATE == "Let me check that for you."

    def test_no_match(self) -> None:
        expected = (
            "I wasn\u2019t able to find a match. Would you like me to try a "
            "different search?"
        )
        assert AH_NO_MATCH == expected

    def test_live_connect_offer(self) -> None:
        expected = (
            "Since our offices are currently closed, I can connect you to "
            "someone \u2014 though they won\u2019t be from the specific office "
            "you\u2019re calling about. Would you like me to do that?"
        )
        assert AH_LIVE_CONNECT_OFFER == expected

    def test_retry_1(self) -> None:
        expected = "I\u2019m sorry, I didn\u2019t catch that. How can I help you?"
        assert AH_RETRY_1 == expected

    def test_retry_2(self) -> None:
        expected = (
            "I\u2019m still having trouble understanding. Could you tell me what "
            "you need help with?"
        )
        assert AH_RETRY_2 == expected

    def test_follow_up_option_1(self) -> None:
        assert AH_FOLLOW_UP_OPTION_1 == "Is there anything else I can help with?"

    def test_follow_up_option_2(self) -> None:
        expected = "Did that help, or is there anything else I can assist with?"
        assert AH_FOLLOW_UP_OPTION_2 == expected


# ===========================================================================
# Appendix C \u2014 Authentication
# ===========================================================================


class TestAuthenticationVerbatim:
    """Assert each Authentication constant equals the vendor text exactly."""

    def test_ani_offer(self) -> None:
        expected = (
            "I can use the phone number you\u2019re calling from to look up your "
            "record. Is that okay?"
        )
        assert AUTH_ANI_OFFER == expected

    def test_phone_provider(self) -> None:
        expected = (
            "Could you please provide the phone number on file for the patient "
            "you\u2019re calling about?"
        )
        assert AUTH_PHONE_PROVIDER == expected

    def test_phone_patient(self) -> None:
        expected = (
            "Could you please provide the phone number for the patient?"
        )
        assert AUTH_PHONE_PATIENT == expected

    def test_phone_readback(self) -> None:
        expected = (
            "I have [digit 1] [digit 2] [digit 3]. [digit 4] [digit 5] "
            "[digit 6]. [digit 7] [digit 8] [digit 9] [digit 10]. Is that "
            "correct?"
        )
        assert AUTH_PHONE_READBACK == expected

    def test_no_record(self) -> None:
        expected = (
            "I wasn\u2019t able to find a record with that phone number. Could "
            "you try a different number?"
        )
        assert AUTH_NO_RECORD == expected

    def test_dob_patient(self) -> None:
        assert AUTH_DOB_PATIENT == "Could you please provide your date of birth?"

    def test_dob_provider(self) -> None:
        expected = (
            "Could you please tell me the full date of birth of the patient "
            "you\u2019re calling about?"
        )
        assert AUTH_DOB_PROVIDER == expected

    def test_name_confirm(self) -> None:
        expected = (
            "Can you confirm the full name for the patient is {{FirstName}} "
            "{{LastName}}?"
        )
        assert AUTH_NAME_CONFIRM == expected

    def test_after_confirm(self) -> None:
        assert AUTH_AFTER_CONFIRM == "Thank you for confirming."

    def test_auth_fail_route(self) -> None:
        expected = "No problem. I\u2019ll connect you now."
        assert AUTH_FAIL_ROUTE == expected

    def test_pushback(self) -> None:
        expected = (
            "It helps us pull up your record. If you\u2019d prefer, I can "
            "connect you without it."
        )
        assert AUTH_PUSHBACK == expected

    def test_changed_request(self) -> None:
        expected = "Sure, let me get you to the right place for that."
        assert AUTH_CHANGED_REQUEST == expected

    def test_after_hours_dob_opener(self) -> None:
        expected = (
            "Our offices are currently closed, so options may be limited, but "
            "I\u2019ll do my best to help. Can you provide the patient\u2019s "
            "date of birth?"
        )
        assert AUTH_AFTER_HOURS_DOB_OPENER == expected


# ===========================================================================
# Appendix C \u2014 Scheduling Init
# ===========================================================================


class TestSchedulingInitVerbatim:
    """Assert each Scheduling Init constant equals the vendor text exactly."""

    def test_visit_reason(self) -> None:
        assert SCHED_INIT_VISIT_REASON == (
            "What is the reason for your visit today?"
        )

    def test_wellness_symptom_disambiguation(self) -> None:
        expected = (
            "Just to make sure I schedule the right type of visit \u2014 are you "
            "looking for an annual wellness exam, or would you like to be seen "
            "for your [symptom]?"
        )
        assert SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION == expected


# ===========================================================================
# Appendix E \u2014 Transfer lines
# ===========================================================================


class TestAppendixEVerbatim:
    """Assert each Appendix E transfer/goodbye/error constant equals vendor text."""

    def test_scheduling_new(self) -> None:
        expected = (
            "Let me get you over to our scheduling department. One moment."
        )
        assert E_SCHEDULING_NEW == expected

    def test_scheduling_existing(self) -> None:
        expected = (
            "Let me connect you with our scheduling team for existing patients. "
            "One moment."
        )
        assert E_SCHEDULING_EXISTING == expected

    def test_triage(self) -> None:
        expected = (
            "Let me connect you with our nurse triage team. One moment."
        )
        assert E_TRIAGE == expected

    def test_referrals(self) -> None:
        expected = (
            "Let me connect you with the referrals department. One moment."
        )
        assert E_REFERRALS == expected

    def test_paging(self) -> None:
        assert E_PAGING == "Let me connect you now. One moment."

    def test_pharmacy(self) -> None:
        expected = (
            "Let me connect you with someone who can help with your medication. "
            "One moment."
        )
        assert E_PHARMACY == expected

    def test_billing(self) -> None:
        expected = (
            "Let me get you over to the Billing department. One moment."
        )
        assert E_BILLING == expected

    def test_records(self) -> None:
        expected = (
            "Let me get you over to the Records department. One moment."
        )
        assert E_RECORDS == expected

    def test_mychart(self) -> None:
        expected = (
            "Let me get you over to the My Chart department. One moment."
        )
        assert E_MYCHART == expected

    def test_general(self) -> None:
        expected = (
            "Let me connect you with someone who can help. One moment."
        )
        assert E_GENERAL == expected

    def test_hotword_urgent(self) -> None:
        expected = (
            "Let me connect you with someone who can help right away. One moment."
        )
        assert E_HOTWORD_URGENT == expected

    def test_switchboard_fallback(self) -> None:
        assert E_SWITCHBOARD_FALLBACK == "One moment while I connect you."

    def test_switchboard_alt(self) -> None:
        expected = (
            "Let me connect you with someone who can help. One moment."
        )
        assert E_SWITCHBOARD_ALT == expected

    def test_transfer_error(self) -> None:
        expected = (
            "I apologize for the inconvenience. Please try calling back shortly. "
            "Thank you for calling SpinSci."
        )
        assert E_TRANSFER_ERROR == expected

    def test_hangup(self) -> None:
        assert E_HANGUP == "Thank you for calling SpinSci. Goodbye."


# ===========================================================================
# Script 3\u2032 punctuation-specific tests (Req 18.4)
# ===========================================================================


class TestScript3PrimePunctuation:
    """Specifically verify Script 3\u2032's no-period-before-'and' punctuation."""

    def test_comma_before_and_present(self) -> None:
        """The canonical form is '...best to help, and to ensure...'"""
        assert "best to help, and to ensure" in GREETING_SCRIPT_3_PRIME_AFTER_HOURS

    def test_no_period_before_and(self) -> None:
        """There must NOT be a period before 'and to ensure'."""
        assert ". and to ensure" not in GREETING_SCRIPT_3_PRIME_AFTER_HOURS
        assert ".and to ensure" not in GREETING_SCRIPT_3_PRIME_AFTER_HOURS

    def test_curly_apostrophe_in_ill(self) -> None:
        """Script 3\u2032 uses U+2019 (curly apostrophe) in 'I\u2019ll'."""
        assert "I\u2019ll" in GREETING_SCRIPT_3_PRIME_AFTER_HOURS

    def test_no_ascii_apostrophe_in_ill(self) -> None:
        """Script 3\u2032 does NOT use ASCII apostrophe in 'I'll'."""
        assert "I'll" not in GREETING_SCRIPT_3_PRIME_AFTER_HOURS


# ===========================================================================
# Render fidelity \u2014 placeholder substitution preserves verbatim text
# ===========================================================================


class TestRenderFidelity:
    """Verify render() preserves non-placeholder text exactly after substitution."""

    def test_script_2_prime_render(self) -> None:
        """render() on Script 2\u2032 substitutes {FirstName} correctly."""
        result = render(GREETING_SCRIPT_2_PRIME_PERSONALIZED, {"FirstName": "Alice"})
        assert result == "Am I speaking with Alice?"

    def test_path_a_personalized_render(self) -> None:
        """render() on Path A personalized substitutes {{caller_name}}."""
        result = render(GREETING_PATH_A_PERSONALIZED, {"caller_name": "Bob Smith"})
        assert result == "Hi Bob Smith, nice to meet you. Let me help you with that."

    def test_path_b_render(self) -> None:
        """render() on Path B preserves the routing request after substitution."""
        result = render(GREETING_PATH_B, {"caller_name": "Jane"})
        expected = (
            "Hi Jane, nice to meet you. To ensure your call is routed correctly, "
            "please provide the provider, specialty, or location you are trying "
            "to reach, along with the reason for your call today."
        )
        assert result == expected

    def test_auth_name_confirm_render(self) -> None:
        """render() substitutes both {{FirstName}} and {{LastName}}."""
        result = render(
            AUTH_NAME_CONFIRM, {"FirstName": "John", "LastName": "Doe"}
        )
        assert result == "Can you confirm the full name for the patient is John Doe?"

    def test_phone_readback_render(self) -> None:
        """render() substitutes [digit N] tokens in the phone read-back."""
        digits = {
            "digit 1": "5",
            "digit 2": "5",
            "digit 3": "5",
            "digit 4": "1",
            "digit 5": "2",
            "digit 6": "3",
            "digit 7": "4",
            "digit 8": "5",
            "digit 9": "6",
            "digit 10": "7",
        }
        result = render(AUTH_PHONE_READBACK, digits)
        expected = "I have 5 5 5. 1 2 3. 4 5 6 7. Is that correct?"
        assert result == expected

    def test_wellness_symptom_render(self) -> None:
        """render() substitutes [symptom] in the disambiguation line."""
        result = render(
            SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION, {"symptom": "headaches"}
        )
        expected = (
            "Just to make sure I schedule the right type of visit \u2014 are you "
            "looking for an annual wellness exam, or would you like to be seen "
            "for your headaches?"
        )
        assert result == expected

    def test_render_preserves_em_dash_in_path_d(self) -> None:
        """render() preserves the U+2014 em dash in Path D even with no tokens."""
        result = render(GREETING_PATH_D, {})
        assert "\u2014" in result
        assert result == GREETING_PATH_D

    def test_render_preserves_script_3_prime_punctuation(self) -> None:
        """render() never introduces a period before 'and' in Script 3\u2032."""
        result = render(GREETING_SCRIPT_3_PRIME_AFTER_HOURS, {})
        assert "best to help, and to ensure" in result
        assert ". and to ensure" not in result
