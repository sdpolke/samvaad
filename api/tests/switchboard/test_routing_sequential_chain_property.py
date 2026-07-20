"""Property-based test for the sequential exact-string routing chain (task 11.3).

Covers Property 20 — Routing chain is sequential and uses the exact string
(Requirements 10.2, 10.3).

The Routing phase completes route listing before initiating route metadata
resolution (Req 10.2), and resolves metadata using the exact routing-intent
string returned by route listing — never fabricated (Req 10.3).
"""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.routing import (
    FabricatedRoutingIntentError,
    ListingIncompleteError,
    RouteListing,
    RouteMetadataRequest,
    RoutingChainPhase,
    RoutingChainState,
    is_valid_routing_intent,
    select_route_metadata_intent,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty printable strings for routing-intent values (realistic department names)
_routing_intent_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
)

# A non-empty list of routing-intent strings (route listing result)
_routing_intent_list = st.lists(_routing_intent_text, min_size=1, max_size=10)

# A list that may include duplicates (for deduplication testing)
_routing_intent_list_with_dupes = st.lists(
    _routing_intent_text, min_size=2, max_size=10
).flatmap(
    lambda items: st.just(items + items[:1])  # guarantee at least one duplicate
)

# An empty listing
_empty_listing = st.just([])


# ===========================================================================
# Property 20: Routing chain is sequential and uses the exact string
# ===========================================================================


# ---------------------------------------------------------------------------
# Sub-property 1: Metadata resolution before listing raises ListingIncompleteError
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string
@given(routing_intent=_routing_intent_text)
@example(routing_intent="Cardiology")
@example(routing_intent="General")
@example(routing_intent="")
@settings(max_examples=200)
def test_metadata_before_listing_raises_listing_incomplete(
    routing_intent: str,
) -> None:
    """Metadata resolution before listing completes always raises ListingIncompleteError.

    **Validates: Requirements 10.2**

    When listing is None (not yet completed), requesting metadata resolution for
    ANY routing-intent string must fail with ListingIncompleteError — metadata
    resolution is never concurrent with or ahead of listing (Req 10.2).
    """
    # Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string

    with pytest.raises(ListingIncompleteError):
        select_route_metadata_intent(listing=None, routing_intent=routing_intent)


# ---------------------------------------------------------------------------
# Sub-property 2: Metadata resolution with an exact listed string always succeeds
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string
@given(
    intents=_routing_intent_list,
    index=st.integers(min_value=0, max_value=9),
)
@example(intents=["Cardiology"], index=0)
@example(intents=["General", "Neurology"], index=1)
@settings(max_examples=200)
def test_exact_listed_string_always_succeeds(
    intents: list[str],
    index: int,
) -> None:
    """Metadata resolution with the exact string from the listing always succeeds.

    **Validates: Requirements 10.3**

    After listing completes, resolving metadata with any string that IS in the
    listing must succeed and return a RouteMetadataRequest carrying that exact
    string (Req 10.3 — exact string contract).
    """
    # Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string

    listing = RouteListing(intents)
    # Pick one of the actual listed strings by index
    if not listing.routing_intents:
        return  # degenerate: all strings were empty after dedup, skip
    chosen = listing.routing_intents[index % len(listing.routing_intents)]

    result = select_route_metadata_intent(listing=listing, routing_intent=chosen)

    assert isinstance(result, RouteMetadataRequest)
    assert result.routing_intent == chosen


# ---------------------------------------------------------------------------
# Sub-property 3: Fabricated string always raises FabricatedRoutingIntentError
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string
@given(
    intents=_routing_intent_list,
    fabricated=_routing_intent_text,
)
@example(intents=["Cardiology", "Neurology"], fabricated="cardiology")  # case differs
@example(intents=["General"], fabricated="General ")  # trailing space
@example(intents=["Lab"], fabricated="lab")  # lowercase fabrication
@settings(max_examples=200)
def test_fabricated_string_always_raises(
    intents: list[str],
    fabricated: str,
) -> None:
    """Metadata resolution with a string NOT in the listing raises FabricatedRoutingIntentError.

    **Validates: Requirements 10.3**

    After listing completes, resolving metadata with a routing-intent string that
    was NOT returned by listing must always fail (Req 10.3 — never fabricated).
    """
    # Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string

    listing = RouteListing(intents)
    # Ensure fabricated is not in the listing (skip if accidentally generated an exact match)
    if fabricated in listing.routing_intents:
        return

    with pytest.raises(FabricatedRoutingIntentError):
        select_route_metadata_intent(listing=listing, routing_intent=fabricated)


# ---------------------------------------------------------------------------
# Sub-property 4: RoutingChainState enforces sequential phases
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string
@given(
    intents=_routing_intent_list,
    index=st.integers(min_value=0, max_value=9),
)
@example(intents=["Cardiology", "Neurology"], index=0)
@example(intents=["General"], index=0)
@settings(max_examples=200)
def test_state_machine_enforces_sequential_phases(
    intents: list[str],
    index: int,
) -> None:
    """RoutingChainState enforces LISTING -> LISTING_COMPLETE -> METADATA_RESOLVED.

    **Validates: Requirements 10.2**

    The state machine starts in LISTING phase, advances to LISTING_COMPLETE after
    complete_listing, and only then can resolve_metadata succeed (advancing to
    METADATA_RESOLVED). Attempting resolve_metadata before complete_listing raises.
    """
    # Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string

    state = RoutingChainState()

    # Phase 1: starts in LISTING
    assert state.phase == RoutingChainPhase.LISTING
    assert not state.listing_complete

    # Attempting resolve_metadata in LISTING phase must raise
    with pytest.raises(ListingIncompleteError):
        state.resolve_metadata("anything")

    # Phase 2: complete listing -> LISTING_COMPLETE
    listing = RouteListing(intents)
    state_after_listing = state.complete_listing(listing)
    assert state_after_listing.phase == RoutingChainPhase.LISTING_COMPLETE
    assert state_after_listing.listing_complete

    # Phase 3: resolve metadata with an exact string -> METADATA_RESOLVED
    if not listing.routing_intents:
        return  # degenerate after dedup
    chosen = listing.routing_intents[index % len(listing.routing_intents)]
    state_resolved = state_after_listing.resolve_metadata(chosen)
    assert state_resolved.phase == RoutingChainPhase.METADATA_RESOLVED
    assert state_resolved.resolved_intent == chosen


# ---------------------------------------------------------------------------
# Sub-property 5: is_valid_routing_intent is exact (case-sensitive, no normalization)
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string
@given(
    intents=_routing_intent_list,
    index=st.integers(min_value=0, max_value=9),
)
@example(intents=["Cardiology"], index=0)
@example(intents=["Neurology", "Billing"], index=1)
@settings(max_examples=200)
def test_is_valid_routing_intent_exact_match_only(
    intents: list[str],
    index: int,
) -> None:
    """is_valid_routing_intent returns True only for exact members (case-sensitive).

    **Validates: Requirements 10.3**

    No normalization, no case-folding, no substring matching — only an exact
    string from the listing is valid.
    """
    # Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string

    listing = RouteListing(intents)
    if not listing.routing_intents:
        return

    # Exact member -> True
    exact = listing.routing_intents[index % len(listing.routing_intents)]
    assert is_valid_routing_intent(listing, exact) is True

    # Case-swapped version (if different from original AND not in listing) -> False
    swapped = exact.swapcase()
    if swapped != exact and swapped not in listing.routing_intents:
        assert is_valid_routing_intent(listing, swapped) is False

    # With trailing space -> False
    with_space = exact + " "
    if with_space not in listing.routing_intents:
        assert is_valid_routing_intent(listing, with_space) is False


# ---------------------------------------------------------------------------
# Sub-property 6: RouteListing deduplicates while preserving order
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string
@given(intents=st.lists(_routing_intent_text, min_size=0, max_size=15))
@example(intents=["A", "B", "A", "C", "B"])
@example(intents=["X", "X", "X"])
@example(intents=[])
@settings(max_examples=200)
def test_route_listing_deduplicates_preserving_order(
    intents: list[str],
) -> None:
    """RouteListing deduplicates while preserving first-seen order.

    **Validates: Requirements 10.2, 10.3**

    The listing holds exactly the unique routing-intent strings in the order they
    first appeared, so membership checks are unambiguous and ordering is stable.
    """
    # Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string

    listing = RouteListing(intents)
    result = listing.routing_intents

    # No duplicates
    assert len(result) == len(set(result))

    # Preserves first-seen order
    seen: list[str] = []
    for item in intents:
        if item not in seen:
            seen.append(item)
    assert result == tuple(seen)

    # Every original item is still present (just deduped)
    for item in intents:
        assert item in result
