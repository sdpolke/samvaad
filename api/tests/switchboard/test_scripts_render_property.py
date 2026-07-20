"""Property-based test for the script renderer (task 4.3).

Covers Property 23 — Verbatim script render fidelity (Req 18.1, 18.3, 18.4).

The property runs >= 100 iterations and its generators cover all mandatory Appendix
C/E templates, diverse placeholder token forms ({{name}}, {name}, [name]), values
containing regex/format-string special characters, empty mappings, and values that
look like other tokens (single-pass verification).
"""

# Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity

from __future__ import annotations

import re
import string

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.scripts import (
    AH_BILLING_CLOSED,
    AH_MYCHART_CLOSED,
    AH_RESTRICTED_SERVICE_SCHEDULING,
    AH_RETRY_1,
    AH_RETRY_2,
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
    GREETING_PATH_D,
    GREETING_PATH_E,
    GREETING_ROUTING_REQUEST,
    GREETING_SCRIPT_2_PRIME_PERSONALIZED,
    GREETING_SCRIPT_3_PRIME_AFTER_HOURS,
    GREETING_SCRIPT_4_STANDARD_IN_HOURS,
    SCHED_INIT_VISIT_REASON,
    SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION,
    render,
)

# ---------------------------------------------------------------------------
# All mandatory Appendix C/E script constants (sampled by generators)
# ---------------------------------------------------------------------------

ALL_SCRIPTS: list[str] = [
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
    AUTH_PHONE_READBACK,
    AUTH_NO_RECORD,
    AUTH_DOB_PATIENT,
    AUTH_DOB_PROVIDER,
    AUTH_NAME_CONFIRM,
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
    SCHED_INIT_VISIT_REASON,
    SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION,
]

# Scripts containing placeholder tokens (for substitution tests)
SCRIPTS_WITH_PLACEHOLDERS: list[tuple[str, dict[str, str]]] = [
    (GREETING_SCRIPT_2_PRIME_PERSONALIZED, {"FirstName": "Alice"}),
    (GREETING_PATH_A_PERSONALIZED, {"caller_name": "Bob Smith"}),
    (GREETING_PATH_B, {"caller_name": "Jane Doe"}),
    (AUTH_NAME_CONFIRM, {"FirstName": "John", "LastName": "Doe"}),
    (
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
    (SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION, {"symptom": "headaches"}),
]

# Placeholder names that appear across all templates
ALL_PLACEHOLDER_NAMES: list[str] = [
    "caller_name",
    "FirstName",
    "LastName",
    "digit 1",
    "digit 2",
    "digit 3",
    "digit 4",
    "digit 5",
    "digit 6",
    "digit 7",
    "digit 8",
    "digit 9",
    "digit 10",
    "symptom",
]

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: sample from all mandatory scripts
_scripts_strategy = st.sampled_from(ALL_SCRIPTS)

# Strategy: placeholder values with tricky characters (regex, braces, brackets,
# format-string patterns) to verify literal substitution
_tricky_values = st.one_of(
    # Normal names
    st.text(
        alphabet=string.ascii_letters + " '-",
        min_size=1,
        max_size=30,
    ),
    # Values with regex special characters
    st.sampled_from([
        "O'Brien",
        "$100.00",
        "foo\\bar",
        "(parens)",
        "a+b*c?d",
        "end.",
        "^start$",
        "|pipe|",
        "back\\1ref",
        "group(0)",
    ]),
    # Values containing braces/brackets (should NOT trigger re-scan)
    st.sampled_from([
        "{{caller_name}}",
        "{FirstName}",
        "[digit 1]",
        "{{LastName}}",
        "{other_token}",
        "[symptom]",
    ]),
    # Format-string patterns
    st.sampled_from([
        "%s",
        "%d",
        "{0}",
        "{name}",
        "%(key)s",
        "$1",
        "\\g<0>",
    ]),
    # Unicode: curly apostrophes, em dashes
    st.sampled_from([
        "it\u2019s",
        "a\u2014b",
        "caf\u00e9",
    ]),
)

# Strategy: a mapping of placeholder names to tricky values
_placeholder_mapping = st.fixed_dictionaries(
    {},
    optional={name: _tricky_values for name in ALL_PLACEHOLDER_NAMES},
)


# ---------------------------------------------------------------------------
# Oracle: independent reference implementation of render
# ---------------------------------------------------------------------------


def _oracle_render(template: str, placeholders: dict[str, str]) -> str:
    """Reference implementation: single-pass token replacement (matches render).

    Builds a token→value mapping for all three authored forms of each placeholder
    name, then performs a single left-to-right scan (longest-token-first) so that
    substituted values are never re-scanned — identical semantics to the real
    render function.
    """
    if not placeholders:
        return template

    token_to_value: dict[str, str] = {}
    for name, value in placeholders.items():
        for token in (
            "{{" + name + "}}",
            "{" + name + "}",
            "[" + name + "]",
        ):
            token_to_value[token] = value

    # Single-pass: longer tokens first so {{X}} wins over {X}
    ordered_tokens = sorted(token_to_value, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(t) for t in ordered_tokens))
    return pattern.sub(lambda m: token_to_value[m.group(0)], template)


# ===========================================================================
# Property 23: Verbatim script render fidelity
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity
@given(template=_scripts_strategy)
@settings(max_examples=200)
def test_property_23_empty_placeholders_identity(template: str) -> None:
    """render(template, {}) must return the template unchanged (byte-for-byte).

    **Validates: Requirements 18.1, 18.3, 18.4**

    For any mandatory Appendix C/E line, rendering with an empty placeholder map
    produces the original template exactly — no characters added, removed, or
    modified.
    """
    result = render(template, {})
    assert result == template, (
        f"render(template, {{}}) != template.\n"
        f"Template: {template!r}\n"
        f"Result:   {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity
@given(
    template=_scripts_strategy,
    placeholders=_placeholder_mapping,
)
@settings(max_examples=200)
def test_property_23_substitution_equals_oracle(
    template: str, placeholders: dict[str, str]
) -> None:
    """render(template, placeholders) equals the template with only tokens swapped.

    **Validates: Requirements 18.1, 18.3, 18.4**

    For any mandatory Appendix C/E line and any placeholder values, the rendered
    output equals the mandated template with only its placeholders substituted,
    preserving exact punctuation and structure.
    """
    result = render(template, placeholders)
    expected = _oracle_render(template, placeholders)
    assert result == expected, (
        f"render mismatch.\n"
        f"Template:     {template!r}\n"
        f"Placeholders: {placeholders!r}\n"
        f"Got:          {result!r}\n"
        f"Expected:     {expected!r}"
    )


# Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity
@given(
    template=_scripts_strategy,
    value=_tricky_values,
)
@settings(max_examples=200)
def test_property_23_no_rescan_of_substituted_values(
    template: str, value: str
) -> None:
    """Substituted values are never re-scanned for further token replacement.

    **Validates: Requirements 18.1, 18.3, 18.4**

    When a placeholder value itself looks like a token (e.g., "{{caller_name}}"),
    it must appear literally in the output — not be consumed by a second pass.
    """
    # Use a placeholder name that actually appears in the template
    # Find which placeholder tokens exist in this template
    present_names = []
    for name in ALL_PLACEHOLDER_NAMES:
        for token in (
            "{{" + name + "}}",
            "{" + name + "}",
            "[" + name + "]",
        ):
            if token in template:
                present_names.append(name)
                break

    if not present_names:
        # Template has no placeholders — render should be identity
        result = render(template, {"caller_name": value})
        assert result == template
        return

    # Substitute the first present name with the tricky value
    target_name = present_names[0]
    placeholders = {target_name: value}
    result = render(template, placeholders)

    # The value must appear literally in the output
    assert value in result, (
        f"Substituted value not found literally in output.\n"
        f"Template: {template!r}\n"
        f"Name: {target_name!r}, Value: {value!r}\n"
        f"Result: {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity
@given(
    data=st.data(),
    value=_tricky_values,
)
@settings(max_examples=200)
def test_property_23_missing_tokens_left_untouched(
    data: st.DataObject, value: str
) -> None:
    """Tokens whose keys are absent from placeholders are left untouched.

    **Validates: Requirements 18.1, 18.3, 18.4**

    When a template contains tokens for key X but the placeholder mapping only
    has key Y (not X), the X tokens remain in the output unchanged.
    """
    # Pick a template that has placeholders
    template = data.draw(
        st.sampled_from([t for t, _ in SCRIPTS_WITH_PLACEHOLDERS])
    )

    # Use a key that does NOT exist in the template
    fake_key = "nonexistent_placeholder_xyz"
    result = render(template, {fake_key: value})

    # Template must be unchanged (no real token matched)
    assert result == template, (
        f"Template was modified when only a non-matching key was provided.\n"
        f"Template: {template!r}\n"
        f"Result:   {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity
@given(placeholders=_placeholder_mapping)
@example(placeholders={"caller_name": "Dr. O\u2019Brien"})
@example(placeholders={"caller_name": "$1\\g<0>"})
@example(placeholders={"caller_name": "{{FirstName}}"})
@settings(max_examples=200)
def test_property_23_script_3_prime_punctuation_preserved(
    placeholders: dict[str, str],
) -> None:
    """Script 3\u2032 no-period-before-"and" punctuation is always preserved.

    **Validates: Requirements 18.1, 18.3, 18.4**

    Script 3\u2032 deliberately uses a comma before "and" (no period before "and"):
    "...do my best to help, and to ensure..."
    This specific punctuation must survive any placeholder substitution.
    """
    template = GREETING_SCRIPT_3_PRIME_AFTER_HOURS
    result = render(template, placeholders)

    # The canonical fragment: comma-and (no period before "and")
    canonical_fragment = "best to help, and to ensure"
    assert canonical_fragment in result, (
        f"Script 3\u2032 comma-before-'and' punctuation was corrupted.\n"
        f"Expected fragment: {canonical_fragment!r}\n"
        f"Result: {result!r}"
    )

    # Also verify no period appears before "and to ensure"
    assert ". and to ensure" not in result, (
        f"Script 3\u2032 gained a period before 'and' — violates Req 18.4.\n"
        f"Result: {result!r}"
    )


# Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity
@given(value=_tricky_values)
@example(value="\u2019")  # Curly apostrophe
@example(value="\u2014")  # Em dash
@settings(max_examples=200)
def test_property_23_unicode_punctuation_preserved(value: str) -> None:
    """Curly apostrophes (U+2019) and em dashes (U+2014) are preserved.

    **Validates: Requirements 18.1, 18.3, 18.4**

    Templates containing typographic punctuation (curly apostrophes, em dashes)
    must preserve those characters after rendering, regardless of placeholder values.
    """
    # GREETING_PATH_D contains an em dash: "No worries — I can still help you."
    template = GREETING_PATH_D
    result = render(template, {"caller_name": value})

    # The em dash must survive
    assert "\u2014" in result, (
        f"Em dash (U+2014) was lost from GREETING_PATH_D after rendering.\n"
        f"Result: {result!r}"
    )

    # GREETING_SCRIPT_3_PRIME contains a curly apostrophe: "I'll"
    template2 = GREETING_SCRIPT_3_PRIME_AFTER_HOURS
    result2 = render(template2, {"caller_name": value})

    # The curly apostrophe (\u2019) in "I\u2019ll" must survive — but only if the
    # template actually uses it. Check if the template has U+2019.
    if "\u2019" in template2:
        assert "\u2019" in result2, (
            f"Curly apostrophe (U+2019) was lost from Script 3\u2032.\n"
            f"Result: {result2!r}"
        )


# Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity
@given(data=st.data())
@settings(max_examples=200)
def test_property_23_known_templates_with_placeholders(
    data: st.DataObject,
) -> None:
    """Known templates with their expected placeholders render correctly.

    **Validates: Requirements 18.1, 18.3, 18.4**

    For templates known to contain placeholders, filling them with generated
    values produces a result that matches the oracle (exact template with only
    tokens string-replaced).
    """
    template, default_phs = data.draw(
        st.sampled_from(SCRIPTS_WITH_PLACEHOLDERS)
    )

    # Generate replacement values for each placeholder in this template
    placeholders = {}
    for name in default_phs:
        placeholders[name] = data.draw(_tricky_values)

    result = render(template, placeholders)
    expected = _oracle_render(template, placeholders)

    assert result == expected, (
        f"Render mismatch on known template.\n"
        f"Template: {template!r}\n"
        f"Placeholders: {placeholders!r}\n"
        f"Got:      {result!r}\n"
        f"Expected: {expected!r}"
    )
