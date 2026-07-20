"""Property-based test for the narration guard (task 4.5).

Covers Property 24 — No internal narration in any emitted speech (Req 4.1, 3.2).

The property verifies that `find_internal_narration` correctly detects internal
artifacts (UUIDs, JSON, snake_case identifiers, system names, ledger field names)
in speech, and that `assert_no_internal_narration` raises `NarrationGuardError` for
any speech containing such artifacts. Conversely, clean natural-language speech
(like the mandated Appendix C/E scripts after rendering) passes without raising.
"""

# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech

from __future__ import annotations

import string
import uuid

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.ledger import LEDGER_FIELD_NAMES
from api.services.switchboard.scripts import (
    AH_BILLING_CLOSED,
    AH_MYCHART_CLOSED,
    AH_RESTRICTED_SERVICE_SCHEDULING,
    AH_RETRY_1,
    AH_RETRY_2,
    AUTH_AFTER_CONFIRM,
    AUTH_ANI_OFFER,
    AUTH_CHANGED_REQUEST,
    AUTH_DOB_PATIENT,
    AUTH_DOB_PROVIDER,
    AUTH_FAIL_ROUTE,
    AUTH_NAME_CONFIRM,
    AUTH_NO_RECORD,
    AUTH_PHONE_READBACK,
    BH_FAQ_LOOKUP,
    BH_OTHER_LOOKUP,
    BH_RETRY_1,
    BH_RETRY_2,
    BH_SCHEDULING_GATE,
    BH_SEARCH_TROUBLE,
    E_BILLING,
    E_GENERAL,
    E_HANGUP,
    E_HOTWORD_URGENT,
    E_MYCHART,
    E_PAGING,
    E_PHARMACY,
    E_RECORDS,
    E_REFERRALS,
    E_SCHEDULING_EXISTING,
    E_SCHEDULING_NEW,
    E_SWITCHBOARD_FALLBACK,
    E_TRANSFER_ERROR,
    E_TRIAGE,
    GREETING_HANGUP,
    GREETING_MEDICATION,
    GREETING_PATH_A_PERSONALIZED,
    GREETING_PATH_A_STANDARD,
    GREETING_PATH_B,
    GREETING_PATH_E,
    GREETING_ROUTING_REQUEST,
    GREETING_SCRIPT_2_PRIME_PERSONALIZED,
    GREETING_SCRIPT_3_PRIME_AFTER_HOURS,
    GREETING_SCRIPT_4_STANDARD_IN_HOURS,
    NarrationGuardError,
    SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION,
    assert_no_internal_narration,
    find_internal_narration,
    render,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Ledger field names containing underscores (the ones flagged by the guard).
LEDGER_FIELDS_WITH_UNDERSCORES: list[str] = sorted(
    name for name in LEDGER_FIELD_NAMES if "_" in name
)

#: All mandatory scripts that contain NO placeholders — safe to test as-is.
SCRIPTS_NO_PLACEHOLDERS: list[str] = [
    GREETING_ROUTING_REQUEST,
    GREETING_SCRIPT_4_STANDARD_IN_HOURS,
    GREETING_SCRIPT_3_PRIME_AFTER_HOURS,
    GREETING_PATH_A_STANDARD,
    GREETING_PATH_E,
    GREETING_MEDICATION,
    GREETING_HANGUP,
    BH_FAQ_LOOKUP,
    BH_OTHER_LOOKUP,
    BH_SCHEDULING_GATE,
    BH_SEARCH_TROUBLE,
    BH_RETRY_1,
    BH_RETRY_2,
    AH_RESTRICTED_SERVICE_SCHEDULING,
    AH_MYCHART_CLOSED,
    AH_BILLING_CLOSED,
    AH_RETRY_1,
    AH_RETRY_2,
    AUTH_ANI_OFFER,
    AUTH_NO_RECORD,
    AUTH_DOB_PATIENT,
    AUTH_DOB_PROVIDER,
    AUTH_AFTER_CONFIRM,
    AUTH_FAIL_ROUTE,
    AUTH_CHANGED_REQUEST,
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
    E_TRANSFER_ERROR,
    E_HANGUP,
]

#: Scripts requiring rendering before they can pass the guard.
SCRIPTS_WITH_PLACEHOLDERS_RENDERED: list[str] = [
    render(GREETING_SCRIPT_2_PRIME_PERSONALIZED, {"FirstName": "Alice"}),
    render(GREETING_PATH_A_PERSONALIZED, {"caller_name": "Bob Smith"}),
    render(GREETING_PATH_B, {"caller_name": "Jane Doe"}),
    render(AUTH_NAME_CONFIRM, {"FirstName": "John", "LastName": "Doe"}),
    render(
        AUTH_PHONE_READBACK,
        {
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
        },
    ),
    render(SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION, {"symptom": "headaches"}),
]

#: All clean rendered scripts (no artifacts expected).
ALL_CLEAN_SCRIPTS: list[str] = SCRIPTS_NO_PLACEHOLDERS + SCRIPTS_WITH_PLACEHOLDERS_RENDERED

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: Clean natural-language speech (letters, digits, spaces, basic punctuation).
#: Excludes straight ASCII apostrophe (') because rendered speech uses curly (').
_clean_speech = st.text(
    alphabet=st.sampled_from(
        list(string.ascii_letters + string.digits + " .,;:!?\u2019\u2014-")
    ),
    min_size=1,
    max_size=120,
).filter(lambda s: "_" not in s and "{" not in s and "}" not in s and "[" not in s and "]" not in s)

#: Generated UUIDs.
_uuid_strategy = st.builds(lambda: str(uuid.uuid4()))

#: Hex characters for UUID components.
_hex_chars = st.sampled_from("0123456789abcdefABCDEF")


def _uuid_text() -> st.SearchStrategy[str]:
    """Generate valid UUID-format strings."""
    return st.tuples(
        st.text(alphabet=_hex_chars, min_size=8, max_size=8),
        st.text(alphabet=_hex_chars, min_size=4, max_size=4),
        st.text(alphabet=_hex_chars, min_size=4, max_size=4),
        st.text(alphabet=_hex_chars, min_size=4, max_size=4),
        st.text(alphabet=_hex_chars, min_size=12, max_size=12),
    ).map(lambda parts: f"{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}-{parts[4]}")


#: JSON fragments.
_json_fragments = st.sampled_from([
    '{"intent": "scheduling"}',
    '{"caller_name": "John"}',
    "[1, 2, 3]",
    "{}",
    '{"key": "value", "nested": {"a": 1}}',
    "[scheduling, triage]",
    '{status: "active"}',
])

#: JSON-style key patterns (quoted key followed by colon).
_json_key_patterns = st.sampled_from([
    '"intent":',
    '"caller_name":',
    "'status':",
    '"patient_id":',
    '"key": "value"',
])

#: Snake_case identifiers (internal tool/variable names).
_snake_case_identifiers = st.one_of(
    st.sampled_from([
        "patient_lookup",
        "call_state",
        "route_call",
        "get_schedule",
        "internal_flag",
        "transfer_target",
        "session_id",
    ]),
    # Generate random snake_case words
    st.tuples(
        st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=8),
        st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=8),
    ).map(lambda parts: f"{parts[0]}_{parts[1]}"),
)

#: Ledger field names with underscores.
_ledger_field_names = st.sampled_from(LEDGER_FIELDS_WITH_UNDERSCORES)

#: System names.
_system_names = st.sampled_from(["CallStateLedger"])

#: Clean speech prefix for mixed injection.
_clean_prefix = st.sampled_from([
    "Thank you for calling. ",
    "Let me help you with that. ",
    "One moment please. ",
    "I understand. ",
    "Sure, ",
    "",
])

#: Clean speech suffix for mixed injection.
_clean_suffix = st.sampled_from([
    " Is that correct?",
    " One moment.",
    " Thank you.",
    "",
])


# ===========================================================================
# Property 24: No internal narration in any emitted speech
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(script=st.sampled_from(ALL_CLEAN_SCRIPTS))
@settings(max_examples=200)
def test_property_24_rendered_mandated_scripts_pass_guard(script: str) -> None:
    """All mandated Appendix C/E scripts (rendered) pass the narration guard.

    **Validates: Requirements 4.1, 3.2**

    After rendering with proper placeholder values, every mandatory spoken line
    must pass `assert_no_internal_narration` without raising. These lines are what
    the switchboard actually speaks to callers.
    """
    # find_internal_narration must return None for clean speech
    assert find_internal_narration(script) is None, (
        f"Clean rendered script was flagged as containing narration:\n"
        f"Script: {script!r}\n"
        f"Reason: {find_internal_narration(script)!r}"
    )

    # assert_no_internal_narration must return the speech unchanged
    result = assert_no_internal_narration(script)
    assert result == script


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(uuid_str=_uuid_text(), prefix=_clean_prefix, suffix=_clean_suffix)
@example(
    uuid_str="12345678-1234-1234-1234-123456789abc",
    prefix="",
    suffix="",
)
@settings(max_examples=200)
def test_property_24_uuids_detected(
    uuid_str: str, prefix: str, suffix: str
) -> None:
    """Speech containing a UUID is detected and rejected.

    **Validates: Requirements 4.1, 3.2**

    A UUID (8-4-4-4-12 hexadecimal pattern) is an internal identifier that must
    never be spoken to the caller.
    """
    speech = f"{prefix}{uuid_str}{suffix}"
    reason = find_internal_narration(speech)
    assert reason is not None, f"UUID not detected in: {speech!r}"
    assert "UUID" in reason

    with pytest.raises(NarrationGuardError):
        assert_no_internal_narration(speech)


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(fragment=_json_fragments, prefix=_clean_prefix)
@example(fragment='{"key": "value"}', prefix="The result is ")
@settings(max_examples=200)
def test_property_24_json_structure_detected(fragment: str, prefix: str) -> None:
    """Speech containing JSON/structure characters is detected and rejected.

    **Validates: Requirements 4.1, 3.2**

    Curly braces, square brackets, and JSON key patterns are internal artifacts
    that must never appear in caller-facing speech.
    """
    speech = f"{prefix}{fragment}"
    reason = find_internal_narration(speech)
    assert reason is not None, f"JSON/structure not detected in: {speech!r}"

    with pytest.raises(NarrationGuardError):
        assert_no_internal_narration(speech)


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(key_pattern=_json_key_patterns, prefix=_clean_prefix, suffix=_clean_suffix)
@example(key_pattern='"intent":', prefix="The ", suffix=" scheduling")
@settings(max_examples=200)
def test_property_24_json_key_patterns_detected(
    key_pattern: str, prefix: str, suffix: str
) -> None:
    """Speech containing a JSON-style key pattern is detected and rejected.

    **Validates: Requirements 4.1, 3.2**

    A quoted key followed by a colon (e.g., `"intent":`) indicates internal
    serialization that should never be spoken.
    """
    speech = f"{prefix}{key_pattern}{suffix}"
    reason = find_internal_narration(speech)
    assert reason is not None, f"JSON key pattern not detected in: {speech!r}"

    with pytest.raises(NarrationGuardError):
        assert_no_internal_narration(speech)


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(identifier=_snake_case_identifiers, prefix=_clean_prefix, suffix=_clean_suffix)
@example(identifier="patient_lookup", prefix="Checking ", suffix=" now.")
@example(identifier="call_state", prefix="", suffix="")
@settings(max_examples=200)
def test_property_24_snake_case_identifiers_detected(
    identifier: str, prefix: str, suffix: str
) -> None:
    """Speech containing a snake_case identifier is detected and rejected.

    **Validates: Requirements 4.1, 3.2**

    Snake_case identifiers are internal tool/variable names that must never
    appear in caller-facing speech.
    """
    speech = f"{prefix}{identifier}{suffix}"
    reason = find_internal_narration(speech)
    assert reason is not None, f"Snake_case identifier not detected in: {speech!r}"

    with pytest.raises(NarrationGuardError):
        assert_no_internal_narration(speech)


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(system_name=_system_names, prefix=_clean_prefix, suffix=_clean_suffix)
@example(system_name="CallStateLedger", prefix="", suffix="")
@example(system_name="CallStateLedger", prefix="Updating the ", suffix=" now.")
@settings(max_examples=200)
def test_property_24_system_names_detected(
    system_name: str, prefix: str, suffix: str
) -> None:
    """Speech containing an internal system name is detected and rejected.

    **Validates: Requirements 4.1, 3.2**

    System names like 'CallStateLedger' are internal components that must never
    be mentioned to the caller.
    """
    speech = f"{prefix}{system_name}{suffix}"
    reason = find_internal_narration(speech)
    assert reason is not None, f"System name not detected in: {speech!r}"
    assert "system name" in reason.lower() or "internal" in reason.lower()

    with pytest.raises(NarrationGuardError):
        assert_no_internal_narration(speech)


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(field=_ledger_field_names, prefix=_clean_prefix, suffix=_clean_suffix)
@example(field="patient_verified", prefix="The ", suffix=" is true.")
@example(field="caller_name", prefix="", suffix="")
@example(field="greeting_ani_lookup_done", prefix="Status: ", suffix="")
@settings(max_examples=200)
def test_property_24_ledger_field_names_detected(
    field: str, prefix: str, suffix: str
) -> None:
    """Speech containing a Call State Ledger field name (with underscore) is detected.

    **Validates: Requirements 4.1, 3.2**

    Ledger field names containing underscores (e.g., `patient_verified`,
    `caller_name`, `greeting_ani_lookup_done`) are internal identifiers that
    must never be spoken to the caller.
    """
    speech = f"{prefix}{field}{suffix}"
    reason = find_internal_narration(speech)
    assert reason is not None, (
        f"Ledger field name not detected in: {speech!r}\n"
        f"Field: {field!r}"
    )

    with pytest.raises(NarrationGuardError):
        assert_no_internal_narration(speech)


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(speech=_clean_speech)
@example(speech="Thank you for calling SpinSci")
@example(speech="Let me connect you with someone who can help")
@example(speech="Could you please provide your date of birth")
@example(speech="I am speaking with Alice")
@settings(max_examples=200)
def test_property_24_clean_speech_passes_guard(speech: str) -> None:
    """Clean natural-language speech passes the narration guard without raising.

    **Validates: Requirements 4.1, 3.2**

    Speech that contains only natural language (letters, digits, spaces, and
    standard punctuation) should never trigger the guard.
    """
    result = find_internal_narration(speech)
    assert result is None, (
        f"Clean speech was incorrectly flagged:\n"
        f"Speech: {speech!r}\n"
        f"Reason: {result!r}"
    )

    # Must return unchanged
    assert assert_no_internal_narration(speech) == speech


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(
    script=st.sampled_from(ALL_CLEAN_SCRIPTS),
    artifact=st.one_of(
        _uuid_text(),
        _json_fragments,
        _snake_case_identifiers,
        _system_names,
        _ledger_field_names,
    ),
)
@settings(max_examples=200)
def test_property_24_mixed_speech_artifact_injected(
    script: str, artifact: str
) -> None:
    """A clean rendered script with an injected artifact is always detected.

    **Validates: Requirements 4.1, 3.2**

    When an internal artifact is injected into otherwise-clean speech (simulating
    a prompt leak or template error), the guard must detect and reject it.
    """
    # Inject artifact in the middle of the speech
    mid = len(script) // 2
    speech = f"{script[:mid]} {artifact} {script[mid:]}"

    reason = find_internal_narration(speech)
    assert reason is not None, (
        f"Injected artifact not detected:\n"
        f"Speech: {speech!r}\n"
        f"Artifact: {artifact!r}"
    )

    with pytest.raises(NarrationGuardError):
        assert_no_internal_narration(speech)


# Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech
@given(speech=_clean_speech)
@settings(max_examples=200)
def test_property_24_assert_returns_speech_unchanged(speech: str) -> None:
    """assert_no_internal_narration returns the input speech unchanged when clean.

    **Validates: Requirements 4.1, 3.2**

    The guard function must be transparent for clean speech: it returns the exact
    same string (not a copy with modifications).
    """
    result = assert_no_internal_narration(speech)
    assert result is speech  # identity check — same object returned
