"""Property-based test for after-hours routing-mode gating (task 11.6).

Covers Property 22 — After-hours routing mode gating (GATE-AH-SPEC)
(Requirements 10.7, 10.8).

When ``after_hours`` is false, the Routing phase never uses after-hours
switchboard routing mode (Req 10.7). When ``after_hours`` is true and the
traversal is resolving post-authentication routing, the after-hours routing
mode is used — except for the hotword immediate path (Req 10.8).
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.routing import uses_after_hours_routing_mode

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_booleans = st.booleans()


# ===========================================================================
# Property 22: After-hours routing mode gating
# ===========================================================================


# Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating
@given(
    is_post_authentication_routing=_booleans,
    is_hotword_immediate_path=_booleans,
)
@example(is_post_authentication_routing=True, is_hotword_immediate_path=False)
@example(is_post_authentication_routing=True, is_hotword_immediate_path=True)
@example(is_post_authentication_routing=False, is_hotword_immediate_path=False)
@example(is_post_authentication_routing=False, is_hotword_immediate_path=True)
@settings(max_examples=200)
def test_business_hours_never_uses_ah_routing(
    is_post_authentication_routing: bool,
    is_hotword_immediate_path: bool,
) -> None:
    """When after_hours=False, the result is always False regardless of other inputs.

    **Validates: Requirements 10.7**

    WHILE ``after_hours`` is false, the Routing phase SHALL NOT use after-hours
    switchboard routing mode (GATE-AH-SPEC, AC-12).
    """
    # Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating

    result = uses_after_hours_routing_mode(
        after_hours=False,
        is_post_authentication_routing=is_post_authentication_routing,
        is_hotword_immediate_path=is_hotword_immediate_path,
    )
    assert result is False, (
        f"Expected False when after_hours=False, got {result} "
        f"(post_auth={is_post_authentication_routing}, hotword={is_hotword_immediate_path})"
    )


# Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating
@given(
    is_hotword_immediate_path=st.just(False),
)
@example(is_hotword_immediate_path=False)
@settings(max_examples=200)
def test_after_hours_post_auth_non_hotword_uses_ah_routing(
    is_hotword_immediate_path: bool,
) -> None:
    """When after_hours=True, post_auth=True, hotword=False, the result is always True.

    **Validates: Requirements 10.8**

    WHILE ``after_hours`` is true and resolving post-authentication routing, the
    Routing phase SHALL use after-hours switchboard routing mode rather than the
    caller's real specialty for routing resolution, except for the hotword
    immediate path.
    """
    # Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating

    result = uses_after_hours_routing_mode(
        after_hours=True,
        is_post_authentication_routing=True,
        is_hotword_immediate_path=is_hotword_immediate_path,
    )
    assert result is True, (
        f"Expected True when after_hours=True, post_auth=True, hotword=False, got {result}"
    )


# Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating
@given(
    is_post_authentication_routing=_booleans,
)
@example(is_post_authentication_routing=True)
@example(is_post_authentication_routing=False)
@settings(max_examples=200)
def test_after_hours_hotword_path_excluded(
    is_post_authentication_routing: bool,
) -> None:
    """When after_hours=True and hotword=True, the result is always False.

    **Validates: Requirements 10.8**

    Even after hours, the hotword immediate path is excluded from after-hours
    routing mode — it bypasses the after-hours switchboard path entirely.
    """
    # Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating

    result = uses_after_hours_routing_mode(
        after_hours=True,
        is_post_authentication_routing=is_post_authentication_routing,
        is_hotword_immediate_path=True,
    )
    assert result is False, (
        f"Expected False when hotword=True (even after hours), got {result} "
        f"(post_auth={is_post_authentication_routing})"
    )


# Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating
@given(
    is_hotword_immediate_path=_booleans,
)
@example(is_hotword_immediate_path=False)
@example(is_hotword_immediate_path=True)
@settings(max_examples=200)
def test_after_hours_non_post_auth_never_uses_ah_routing(
    is_hotword_immediate_path: bool,
) -> None:
    """When after_hours=True but post_auth=False, the result is always False.

    **Validates: Requirements 10.8**

    After-hours routing mode is only used when resolving post-authentication
    routing. Pre-authentication or non-routing phases never activate it.
    """
    # Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating

    result = uses_after_hours_routing_mode(
        after_hours=True,
        is_post_authentication_routing=False,
        is_hotword_immediate_path=is_hotword_immediate_path,
    )
    assert result is False, (
        f"Expected False when post_auth=False (even after hours), got {result} "
        f"(hotword={is_hotword_immediate_path})"
    )


# Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating
@given(
    after_hours=_booleans,
    is_post_authentication_routing=_booleans,
    is_hotword_immediate_path=_booleans,
)
@example(after_hours=False, is_post_authentication_routing=False, is_hotword_immediate_path=False)
@example(after_hours=False, is_post_authentication_routing=False, is_hotword_immediate_path=True)
@example(after_hours=False, is_post_authentication_routing=True, is_hotword_immediate_path=False)
@example(after_hours=False, is_post_authentication_routing=True, is_hotword_immediate_path=True)
@example(after_hours=True, is_post_authentication_routing=False, is_hotword_immediate_path=False)
@example(after_hours=True, is_post_authentication_routing=False, is_hotword_immediate_path=True)
@example(after_hours=True, is_post_authentication_routing=True, is_hotword_immediate_path=False)
@example(after_hours=True, is_post_authentication_routing=True, is_hotword_immediate_path=True)
@settings(max_examples=200)
def test_exhaustive_truth_table(
    after_hours: bool,
    is_post_authentication_routing: bool,
    is_hotword_immediate_path: bool,
) -> None:
    """For all 8 boolean input combos, result == (after_hours AND post_auth AND NOT hotword).

    **Validates: Requirements 10.7, 10.8**

    The exhaustive truth table property: the function returns True if and only if
    all three conditions hold — after_hours is true, is_post_authentication_routing
    is true, and is_hotword_immediate_path is false.
    """
    # Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating

    result = uses_after_hours_routing_mode(
        after_hours=after_hours,
        is_post_authentication_routing=is_post_authentication_routing,
        is_hotword_immediate_path=is_hotword_immediate_path,
    )
    expected = after_hours and is_post_authentication_routing and not is_hotword_immediate_path
    assert result is expected, (
        f"Expected {expected} for (after_hours={after_hours}, "
        f"post_auth={is_post_authentication_routing}, hotword={is_hotword_immediate_path}), "
        f"got {result}"
    )
