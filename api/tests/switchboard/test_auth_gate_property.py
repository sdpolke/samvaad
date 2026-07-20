"""Property-based test for the authentication gate (task 9.2).

Covers Property 13 — Authentication gate before transfer/routing resolution
(GATE-AUTH) (Requirements 9.2, 9.3, 9.4, 9.5, 11.2).

For any traversal where ``intent`` requires authentication and ``patient_status``
is not ``new``, no ``transfer`` and no ``route_metadata_resolution`` tool
invocation occurs until ``patient_verified`` becomes Success, Fail, or N/A;
authentication is skipped only for Records and new-patient ``create``, which
still route before any transfer.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.auth import (
    AUTH_REQUIRED_INTENTS,
    DEFAULT_EXISTING_INTENTS,
    Intent,
    PATIENT_VERIFIED_FAIL,
    PATIENT_VERIFIED_NA,
    PATIENT_VERIFIED_SUCCESS,
    auth_required,
    default_patient_status,
    may_proceed_to_routing,
)
from api.services.switchboard.business_hours import (
    PATIENT_STATUS_EXISTING,
    PATIENT_STATUS_NEW,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All intents in the auth matrix — covers every Intent enum value.
_all_intents = st.sampled_from(list(Intent))

#: Auth-required intents only (all except Records).
_auth_required_intents = st.sampled_from(list(AUTH_REQUIRED_INTENTS))

#: Default-existing intents (Billing, MyChart, Paging, Directory, Pharmacy, General).
_default_existing_intents = st.sampled_from(list(DEFAULT_EXISTING_INTENTS))

#: patient_status values: None, "new", "existing", varied casing.
_patient_status_values = st.one_of(
    st.none(),
    st.just(PATIENT_STATUS_NEW),
    st.just(PATIENT_STATUS_EXISTING),
    st.just("NEW"),
    st.just("New"),
    st.just("  new  "),
    st.just("EXISTING"),
    st.just("Existing"),
    st.just("  existing  "),
    st.just("unknown"),
)

#: patient_status values that are NOT new (case-insensitively).
_patient_status_not_new = st.one_of(
    st.none(),
    st.just(PATIENT_STATUS_EXISTING),
    st.just("EXISTING"),
    st.just("Existing"),
    st.just("  existing  "),
    st.just("unknown"),
    st.just("something_else"),
    st.just(""),
)

#: patient_status values that ARE new (case-insensitively).
_patient_status_new = st.one_of(
    st.just(PATIENT_STATUS_NEW),
    st.just("NEW"),
    st.just("New"),
    st.just("  new  "),
)

#: Resolved patient_verified values (Success, Fail, N/A — including varied casing).
_patient_verified_resolved = st.one_of(
    st.just(PATIENT_VERIFIED_SUCCESS),
    st.just(PATIENT_VERIFIED_FAIL),
    st.just(PATIENT_VERIFIED_NA),
    st.just("success"),
    st.just("fail"),
    st.just("n/a"),
    st.just("SUCCESS"),
    st.just("FAIL"),
    st.just("N/A"),
    st.just("  Success  "),
    st.just("  Fail  "),
    st.just("  N/A  "),
)

#: Unresolved patient_verified values (None, empty, invalid strings).
_patient_verified_unresolved = st.one_of(
    st.none(),
    st.just(""),
    st.just("pending"),
    st.just("in_progress"),
    st.just("unknown"),
    st.just("  "),
    st.just("maybe"),
)

#: All patient_verified values for broad coverage.
_patient_verified_all = st.one_of(
    _patient_verified_resolved,
    _patient_verified_unresolved,
)


# ===========================================================================
# Property 13: Authentication gate before transfer/routing resolution
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution
@given(
    intent=_auth_required_intents,
    patient_status=_patient_status_not_new,
    patient_verified=_patient_verified_unresolved,
)
@example(
    intent=Intent.SCHEDULING,
    patient_status=PATIENT_STATUS_EXISTING,
    patient_verified=None,
)
@example(
    intent=Intent.BILLING,
    patient_status=None,
    patient_verified="",
)
@example(
    intent=Intent.TRIAGE,
    patient_status="unknown",
    patient_verified="pending",
)
@settings(max_examples=200)
def test_gate_closed_when_auth_required_and_not_verified(
    intent: Intent,
    patient_status: str | None,
    patient_verified: str | None,
) -> None:
    """Gate is closed when auth is required and patient_verified is not resolved.

    **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 11.2**

    For any auth-required intent with patient_status != "new" (for Scheduling)
    and patient_verified not in {Success, Fail, N/A}, may_proceed_to_routing
    returns False (gate is closed — no transfer/route_metadata_resolution
    allowed).
    """
    # Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution

    # Precondition: auth IS required for this combo
    assert auth_required(intent, patient_status), (
        f"Expected auth_required=True for intent={intent}, patient_status={patient_status!r}"
    )

    # The gate must be CLOSED
    result = may_proceed_to_routing(intent, patient_status, patient_verified)
    assert result is False, (
        f"Expected gate CLOSED for intent={intent}, patient_status={patient_status!r}, "
        f"patient_verified={patient_verified!r}, but got True"
    )


# Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution
@given(
    intent=_auth_required_intents,
    patient_status=_patient_status_not_new,
    patient_verified=_patient_verified_resolved,
)
@example(
    intent=Intent.SCHEDULING,
    patient_status=PATIENT_STATUS_EXISTING,
    patient_verified=PATIENT_VERIFIED_SUCCESS,
)
@example(
    intent=Intent.BILLING,
    patient_status=None,
    patient_verified=PATIENT_VERIFIED_FAIL,
)
@example(
    intent=Intent.REFERRALS,
    patient_status=PATIENT_STATUS_EXISTING,
    patient_verified=PATIENT_VERIFIED_NA,
)
@example(
    intent=Intent.MYCHART,
    patient_status=PATIENT_STATUS_EXISTING,
    patient_verified="success",
)
@settings(max_examples=200)
def test_gate_open_when_auth_required_and_verified(
    intent: Intent,
    patient_status: str | None,
    patient_verified: str | None,
) -> None:
    """Gate is open when auth is required and patient_verified is resolved.

    **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 11.2**

    For any auth-required intent where auth is required and patient_verified is
    Success/Fail/N/A, may_proceed_to_routing returns True.
    """
    # Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution

    # Precondition: auth IS required for this combo
    assert auth_required(intent, patient_status), (
        f"Expected auth_required=True for intent={intent}, patient_status={patient_status!r}"
    )

    # The gate must be OPEN
    result = may_proceed_to_routing(intent, patient_status, patient_verified)
    assert result is True, (
        f"Expected gate OPEN for intent={intent}, patient_status={patient_status!r}, "
        f"patient_verified={patient_verified!r}, but got False"
    )


# Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution
@given(
    patient_status=_patient_status_values,
    patient_verified=_patient_verified_all,
)
@example(patient_status=None, patient_verified=None)
@example(patient_status=PATIENT_STATUS_NEW, patient_verified=None)
@example(patient_status=PATIENT_STATUS_EXISTING, patient_verified="pending")
@example(patient_status="", patient_verified=PATIENT_VERIFIED_SUCCESS)
@settings(max_examples=200)
def test_gate_open_for_records_intent(
    patient_status: str | None,
    patient_verified: str | None,
) -> None:
    """Gate is always open for Records intent regardless of status/verified.

    **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 11.2**

    For intent=Records regardless of patient_status/patient_verified,
    may_proceed_to_routing returns True (Records still routes, auth is skipped).
    """
    # Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution

    result = may_proceed_to_routing(Intent.RECORDS, patient_status, patient_verified)
    assert result is True, (
        f"Expected gate OPEN for Records intent, patient_status={patient_status!r}, "
        f"patient_verified={patient_verified!r}, but got False"
    )


# Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution
@given(
    patient_status=_patient_status_new,
    patient_verified=_patient_verified_all,
)
@example(patient_status="new", patient_verified=None)
@example(patient_status="NEW", patient_verified="pending")
@example(patient_status="  new  ", patient_verified=PATIENT_VERIFIED_FAIL)
@settings(max_examples=200)
def test_gate_open_for_new_patient_scheduling(
    patient_status: str | None,
    patient_verified: str | None,
) -> None:
    """Gate is always open for new-patient Scheduling regardless of patient_verified.

    **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 11.2**

    For intent=Scheduling with patient_status="new", may_proceed_to_routing
    returns True regardless of patient_verified (new-patient create still routes).
    """
    # Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution

    result = may_proceed_to_routing(Intent.SCHEDULING, patient_status, patient_verified)
    assert result is True, (
        f"Expected gate OPEN for new-patient Scheduling, patient_status={patient_status!r}, "
        f"patient_verified={patient_verified!r}, but got False"
    )


# Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution
@given(
    intent=_auth_required_intents,
    patient_status=_patient_status_not_new,
)
@example(intent=Intent.SCHEDULING, patient_status=PATIENT_STATUS_EXISTING)
@example(intent=Intent.REFERRALS, patient_status=None)
@example(intent=Intent.TRIAGE, patient_status="unknown")
@example(intent=Intent.GENERAL, patient_status=PATIENT_STATUS_EXISTING)
@settings(max_examples=200)
def test_auth_required_for_all_except_records_and_new_scheduling(
    intent: Intent,
    patient_status: str | None,
) -> None:
    """Auth is required for all intents except Records and new-patient Scheduling.

    **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 11.2**

    For every intent in AUTH_REQUIRED_INTENTS with patient_status != "new" (or
    non-Scheduling), auth_required returns True.
    """
    # Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution

    result = auth_required(intent, patient_status)
    assert result is True, (
        f"Expected auth_required=True for intent={intent}, "
        f"patient_status={patient_status!r}, but got False"
    )


# Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution
@given(
    intent=_default_existing_intents,
    patient_status=_patient_status_values,
)
@example(intent=Intent.BILLING, patient_status=None)
@example(intent=Intent.MYCHART, patient_status=PATIENT_STATUS_NEW)
@example(intent=Intent.PAGING, patient_status="")
@example(intent=Intent.DIRECTORY, patient_status=PATIENT_STATUS_EXISTING)
@example(intent=Intent.PHARMACY, patient_status="unknown")
@example(intent=Intent.GENERAL, patient_status="  new  ")
@settings(max_examples=200)
def test_default_existing_intents_always_require_auth(
    intent: Intent,
    patient_status: str | None,
) -> None:
    """Default-existing intents always require auth after applying default_patient_status.

    **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 11.2**

    For intents in DEFAULT_EXISTING_INTENTS, after applying default_patient_status,
    auth is always required (they default to existing, so the new-patient skip
    never applies).
    """
    # Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution

    # Apply the Req 9.5 default — these intents always resolve to "existing"
    effective_status = default_patient_status(intent, patient_status)
    assert effective_status == PATIENT_STATUS_EXISTING, (
        f"Expected default_patient_status to return 'existing' for intent={intent}, "
        f"got {effective_status!r}"
    )

    # Auth is always required for these intents with effective_status="existing"
    result = auth_required(intent, effective_status)
    assert result is True, (
        f"Expected auth_required=True for default-existing intent={intent} with "
        f"effective_status={effective_status!r}, but got False"
    )


# Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution
@given(
    intent=_auth_required_intents,
    patient_status=_patient_status_not_new,
)
@example(
    intent=Intent.SCHEDULING,
    patient_status=PATIENT_STATUS_EXISTING,
)
@example(
    intent=Intent.BILLING,
    patient_status=None,
)
@example(
    intent=Intent.TRIAGE,
    patient_status=PATIENT_STATUS_EXISTING,
)
@settings(max_examples=200)
def test_auth_failure_refusal_still_opens_gate(
    intent: Intent,
    patient_status: str | None,
) -> None:
    """Auth failure/refusal (patient_verified="Fail") still opens the gate.

    **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 11.2**

    patient_verified="Fail" opens the gate just like "Success" (Req 9.7) —
    only the null/unresolved state keeps the gate closed.
    """
    # Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution

    # Precondition: auth IS required
    assert auth_required(intent, patient_status)

    # "Fail" opens the gate (Req 9.7)
    result_fail = may_proceed_to_routing(intent, patient_status, PATIENT_VERIFIED_FAIL)
    assert result_fail is True, (
        f"Expected gate OPEN with patient_verified='Fail' for intent={intent}, "
        f"patient_status={patient_status!r}, but got False"
    )

    # "Success" opens the gate
    result_success = may_proceed_to_routing(
        intent, patient_status, PATIENT_VERIFIED_SUCCESS
    )
    assert result_success is True, (
        f"Expected gate OPEN with patient_verified='Success' for intent={intent}, "
        f"patient_status={patient_status!r}, but got False"
    )

    # "N/A" also opens the gate
    result_na = may_proceed_to_routing(intent, patient_status, PATIENT_VERIFIED_NA)
    assert result_na is True, (
        f"Expected gate OPEN with patient_verified='N/A' for intent={intent}, "
        f"patient_status={patient_status!r}, but got False"
    )
