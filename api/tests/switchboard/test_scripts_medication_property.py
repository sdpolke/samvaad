"""Property-based test for medication-name omission (task 4.6).

Covers Property 25 — Medication names are never spoken (Req 4.2, 11.4).

The property verifies that `prescription_speech` never returns a string containing
the medication name, regardless of what medication name is provided. The function
must always return one of two mandated verbatim lines (GREETING_MEDICATION or
E_PHARMACY), and must raise `MedicationLeakError` if a medication name happens to
be a substring of those lines (safety-net assertion).
"""

# Feature: spinsci-switchboard-poc, Property 25: Medication names are never spoken

from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.scripts import (
    E_PHARMACY,
    GREETING_MEDICATION,
    MedicationLeakError,
    prescription_speech,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: Real drug names that a caller might mention.
_real_drug_names: list[str] = [
    "Lisinopril",
    "Metformin",
    "Amoxicillin",
    "Atorvastatin",
    "Omeprazole",
    "Losartan",
    "Gabapentin",
    "Hydrochlorothiazide",
    "Sertraline",
    "Amlodipine",
    "Levothyroxine",
    "Azithromycin",
    "Ibuprofen",
    "Acetaminophen",
    "Clopidogrel",
    "Prednisone",
    "Montelukast",
    "Pantoprazole",
    "Escitalopram",
    "Rosuvastatin",
]

#: Strategy for medication names: real drugs, random text, multi-word, hyphenated.
_medication_name_strategy = st.one_of(
    st.sampled_from(_real_drug_names),
    st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        min_size=1,
        max_size=30,
    ),
    # Multi-word medication names
    st.tuples(
        st.text(alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"), min_size=2, max_size=12),
        st.text(alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"), min_size=2, max_size=12),
    ).map(lambda parts: f"{parts[0]} {parts[1]}"),
    # Hyphenated / numeric medication names
    st.tuples(
        st.text(alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"), min_size=2, max_size=10),
        st.sampled_from(["-", " ", ""]),
        st.text(alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"), min_size=1, max_size=8),
    ).map(lambda parts: f"{parts[0]}{parts[1]}{parts[2]}"),
)

#: Boolean strategy for transferring flag.
_transferring = st.booleans()

#: Medication names that are substrings of the mandated lines (trigger MedicationLeakError).
_substring_medication_names: list[str] = [
    "prescription",
    "medication",
    "calling",
    "connect",
    "moment",
    "help",
]


# ===========================================================================
# Property 25: Medication names are never spoken
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 25: Medication names are never spoken
@given(medication_name=_medication_name_strategy)
@example(medication_name="Lisinopril")
@example(medication_name="Metformin XR 500mg")
@example(medication_name="")
@settings(max_examples=200)
def test_property_25_non_transferring_never_contains_medication(medication_name: str) -> None:
    """prescription_speech(name, transferring=False) never contains the medication name.

    **Validates: Requirements 4.2, 11.4**

    For any medication name that does NOT happen to be a substring of the
    mandated GREETING_MEDICATION line, the returned speech must not contain
    the medication name.
    """
    needle = medication_name.strip()
    if needle and needle.lower() in GREETING_MEDICATION.lower():
        # This case raises MedicationLeakError — tested separately
        return

    result = prescription_speech(medication_name, transferring=False)
    if needle:
        assert needle.lower() not in result.lower(), (
            f"Medication name {medication_name!r} leaked into speech: {result!r}"
        )


# Feature: spinsci-switchboard-poc, Property 25: Medication names are never spoken
@given(medication_name=_medication_name_strategy)
@example(medication_name="Lisinopril")
@example(medication_name="Amoxicillin")
@example(medication_name="")
@settings(max_examples=200)
def test_property_25_transferring_never_contains_medication(medication_name: str) -> None:
    """prescription_speech(name, transferring=True) never contains the medication name.

    **Validates: Requirements 4.2, 11.4**

    For any medication name that does NOT happen to be a substring of the
    mandated E_PHARMACY line, the returned speech must not contain the
    medication name.
    """
    needle = medication_name.strip()
    if needle and needle.lower() in E_PHARMACY.lower():
        # This case raises MedicationLeakError — tested separately
        return

    result = prescription_speech(medication_name, transferring=True)
    if needle:
        assert needle.lower() not in result.lower(), (
            f"Medication name {medication_name!r} leaked into speech: {result!r}"
        )


# Feature: spinsci-switchboard-poc, Property 25: Medication names are never spoken
@given(medication_name=_medication_name_strategy, transferring=_transferring)
@example(medication_name="Lisinopril", transferring=False)
@example(medication_name="Gabapentin", transferring=True)
@settings(max_examples=200)
def test_property_25_always_returns_mandated_verbatim_line(
    medication_name: str, transferring: bool
) -> None:
    """prescription_speech always returns one of the two mandated verbatim lines.

    **Validates: Requirements 4.2, 11.4**

    The function never generates a novel line — it always selects either
    GREETING_MEDICATION or E_PHARMACY based on the transferring flag.
    """
    needle = medication_name.strip()
    # Skip cases where the medication name is a substring of the mandated line
    target_line = E_PHARMACY if transferring else GREETING_MEDICATION
    if needle and needle.lower() in target_line.lower():
        return

    result = prescription_speech(medication_name, transferring=transferring)
    assert result in (GREETING_MEDICATION, E_PHARMACY), (
        f"prescription_speech returned unexpected line: {result!r}"
    )
    # Verify correct line is selected based on transferring flag
    expected = E_PHARMACY if transferring else GREETING_MEDICATION
    assert result == expected


# Feature: spinsci-switchboard-poc, Property 25: Medication names are never spoken
@given(medication_name=st.sampled_from(_substring_medication_names), transferring=_transferring)
@example(medication_name="prescription", transferring=False)
@example(medication_name="medication", transferring=True)
@settings(max_examples=200)
def test_property_25_raises_for_substring_medication_names(
    medication_name: str, transferring: bool
) -> None:
    """prescription_speech raises MedicationLeakError for medication names that are substrings.

    **Validates: Requirements 4.2, 11.4**

    When a medication name happens to be a substring of the mandated line
    (e.g., "prescription" is in GREETING_MEDICATION, "medication" is in
    E_PHARMACY), the safety-net assertion fires and raises MedicationLeakError.
    """
    target_line = E_PHARMACY if transferring else GREETING_MEDICATION
    needle = medication_name.strip()

    if needle and needle.lower() in target_line.lower():
        with pytest.raises(MedicationLeakError):
            prescription_speech(medication_name, transferring=transferring)
    # If not a substring of the selected line, it should succeed normally
    else:
        result = prescription_speech(medication_name, transferring=transferring)
        assert result == target_line


# Feature: spinsci-switchboard-poc, Property 25: Medication names are never spoken
@given(drug_name=st.sampled_from(_real_drug_names))
@settings(max_examples=200)
def test_property_25_e_pharmacy_constant_never_contains_real_medications(
    drug_name: str,
) -> None:
    """The E_PHARMACY constant never contains common medication names.

    **Validates: Requirements 4.2, 11.4**

    Static verification that the Appendix E pharmacy transfer line does not
    contain any known real medication names — the line is generic and safe.
    """
    assert drug_name.lower() not in E_PHARMACY.lower(), (
        f"E_PHARMACY constant contains the medication name {drug_name!r}: {E_PHARMACY!r}"
    )


# Feature: spinsci-switchboard-poc, Property 25: Medication names are never spoken
@given(transferring=_transferring)
@example(transferring=False)
@example(transferring=True)
@settings(max_examples=200)
def test_property_25_none_medication_returns_correct_line(transferring: bool) -> None:
    """prescription_speech(None) returns the correct verbatim line without raising.

    **Validates: Requirements 4.2, 11.4**

    When no medication name is provided (None), the function returns the
    appropriate mandated line without triggering any safety checks.
    """
    result = prescription_speech(None, transferring=transferring)
    expected = E_PHARMACY if transferring else GREETING_MEDICATION
    assert result == expected
