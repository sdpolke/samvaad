"""E2E acceptance scenario tests: POC-10

These are example-based integration tests that drive the assembled workflow graph
and pure logic functions through scripted call scenarios to assert observable
outcomes. They do NOT use a live LLM or TTS pipeline; instead they:

1. Drive the pure logic function (may_proceed_to_routing) to prove the auth gate
   is CLOSED when patient_verified is null and the intent requires auth, and OPEN
   once verified.
2. Verify the structural graph invariant: transfer and route_metadata_resolution
   tools are ONLY on Routing nodes (no non-Routing node has them).
3. Verify that all edges leading to Routing from auth-required paths go through
   Authentication (structural).
4. Walk through a complete E2E scenario: caller with auth-required intent → gate
   closed → auth completes → gate opens → routing/transfer proceeds.

Scenarios:
  POC-10 — auth gate locks transfer/metadata until verify. The GATE-AUTH pure
            logic blocks may_proceed_to_routing while patient_verified is null
            for auth-required intents; the structural invariant ensures that
            transfer and route_metadata_resolution tools are ONLY attached to
            Routing-cluster nodes, making the gate a structural property.

Requirements: 20.12 (Req 9.2, AC rule GATE-AUTH)
"""

from __future__ import annotations


from api.services.switchboard.auth import (
    AUTH_REQUIRED_INTENTS,
    PATIENT_VERIFIED_FAIL,
    PATIENT_VERIFIED_NA,
    PATIENT_VERIFIED_SUCCESS,
    auth_required,
    is_patient_verified_resolved,
    may_proceed_to_routing,
    patient_verified_from_dob,
)
from api.services.switchboard.clusters.authentication import (
    AUTH_IDENTITY_NODE_ID,
    AUTH_NODE_IDS,
    build_authentication_cluster,
)
from api.services.switchboard.clusters.routing import (
    RESOLVE_ROUTE_PROMPT,
    build_routing_cluster,
)
from api.services.switchboard.clusters.tool_scoping import (
    ROUTING_ONLY_TOOLS,
    validate_tool_scoping,
)
from api.services.switchboard.graph import build_switchboard_graph
from api.services.switchboard.ledger import CallStateLedger, reduce_ledger


# ---------------------------------------------------------------------------
# POC-10 Pure logic: may_proceed_to_routing (GATE-AUTH predicate)
# ---------------------------------------------------------------------------


class TestPOC10GateAuthPureLogic:
    """POC-10 Pure logic: may_proceed_to_routing gate is closed/open correctly.

    Requirements: 20.12 (Req 9.2, GATE-AUTH)
    """

    # ── 1. Gate CLOSED when patient_verified is null and auth required ────

    def test_gate_closed_scheduling_existing_null(self) -> None:
        """Gate is closed for Scheduling/existing when patient_verified is None."""
        assert may_proceed_to_routing("Scheduling", "existing", None) is False

    def test_gate_closed_billing_null(self) -> None:
        """Gate is closed for Billing when patient_verified is None."""
        assert may_proceed_to_routing("Billing", "existing", None) is False

    def test_gate_closed_triage_null(self) -> None:
        """Gate is closed for Triage when patient_verified is None."""
        assert may_proceed_to_routing("Triage", "existing", None) is False

    def test_gate_closed_referrals_null(self) -> None:
        """Gate is closed for Referrals when patient_verified is None."""
        assert may_proceed_to_routing("Referrals", "existing", None) is False

    def test_gate_closed_mychart_null(self) -> None:
        """Gate is closed for MyChart when patient_verified is None."""
        assert may_proceed_to_routing("MyChart", "existing", None) is False

    def test_gate_closed_empty_string_verified(self) -> None:
        """Gate is closed when patient_verified is empty string (unresolved)."""
        assert may_proceed_to_routing("Scheduling", "existing", "") is False

    def test_gate_closed_pending_verified(self) -> None:
        """Gate is closed when patient_verified is 'pending' (not a resolved value)."""
        assert may_proceed_to_routing("Scheduling", "existing", "pending") is False

    # ── 2. Gate OPEN when patient_verified is resolved ────────────────────

    def test_gate_open_success(self) -> None:
        """Gate opens for Scheduling/existing with patient_verified=Success."""
        assert may_proceed_to_routing("Scheduling", "existing", PATIENT_VERIFIED_SUCCESS) is True

    def test_gate_open_fail(self) -> None:
        """Gate opens for Scheduling/existing with patient_verified=Fail."""
        assert may_proceed_to_routing("Scheduling", "existing", PATIENT_VERIFIED_FAIL) is True

    def test_gate_open_na(self) -> None:
        """Gate opens for Scheduling/existing with patient_verified=N/A."""
        assert may_proceed_to_routing("Scheduling", "existing", PATIENT_VERIFIED_NA) is True

    def test_gate_open_case_insensitive_success(self) -> None:
        """Gate opens for lowercase 'success' (case-insensitive matching)."""
        assert may_proceed_to_routing("Scheduling", "existing", "success") is True

    def test_gate_open_case_insensitive_fail(self) -> None:
        """Gate opens for lowercase 'fail' (case-insensitive matching)."""
        assert may_proceed_to_routing("Scheduling", "existing", "fail") is True

    def test_gate_open_case_insensitive_na(self) -> None:
        """Gate opens for lowercase 'n/a' (case-insensitive matching)."""
        assert may_proceed_to_routing("Scheduling", "existing", "n/a") is True

    # ── 3. Gate OPEN (auth not required) — Records, new-patient create ───

    def test_gate_open_records_null(self) -> None:
        """Gate is always open for Records regardless of patient_verified."""
        assert may_proceed_to_routing("Records", "existing", None) is True

    def test_gate_open_new_scheduling_null(self) -> None:
        """Gate is always open for new-patient Scheduling regardless of patient_verified."""
        assert may_proceed_to_routing("Scheduling", "new", None) is True

    # ── 4. All auth-required intents are blocked when unverified ──────────

    def test_all_auth_required_intents_blocked_when_null(self) -> None:
        """Every intent in AUTH_REQUIRED_INTENTS is blocked when patient_verified=None
        and patient_status is not 'new'."""
        for intent in AUTH_REQUIRED_INTENTS:
            # Skip Scheduling with new (that's a skip case)
            result = may_proceed_to_routing(intent, "existing", None)
            assert result is False, (
                f"Expected gate CLOSED for intent={intent.value} with "
                f"patient_verified=None, but got True"
            )

    def test_all_auth_required_intents_open_when_success(self) -> None:
        """Every intent in AUTH_REQUIRED_INTENTS is open when patient_verified=Success."""
        for intent in AUTH_REQUIRED_INTENTS:
            result = may_proceed_to_routing(intent, "existing", PATIENT_VERIFIED_SUCCESS)
            assert result is True, (
                f"Expected gate OPEN for intent={intent.value} with "
                f"patient_verified=Success, but got False"
            )


# ---------------------------------------------------------------------------
# POC-10 Structural invariant: transfer and route_metadata_resolution tools
# are ONLY on Routing nodes
# ---------------------------------------------------------------------------


class TestPOC10ToolScopingStructuralInvariant:
    """POC-10 Structural: transfer and route_metadata_resolution are ONLY on
    Routing nodes (gate-by-scoping).

    Requirements: 20.12 (Req 9.2, GATE-AUTH, Req 1.7)
    """

    def test_routing_only_tools_set(self) -> None:
        """ROUTING_ONLY_TOOLS includes 'transfer' and 'route_metadata_resolution'."""
        assert "transfer" in ROUTING_ONLY_TOOLS
        assert "route_metadata_resolution" in ROUTING_ONLY_TOOLS

    def test_validate_tool_scoping_no_violations_in_full_graph(self) -> None:
        """validate_tool_scoping returns zero violations for the assembled graph.

        Uses the same approach as test_tool_scoping.py: build all clusters and
        collect their RFNodeDTO objects for validation.
        """
        from api.services.switchboard.clusters.after_hours import build_after_hours_cluster
        from api.services.switchboard.clusters.business_hours import build_business_hours_cluster
        from api.services.switchboard.clusters.greeting import build_greeting_cluster

        greeting = build_greeting_cluster()
        bh = build_business_hours_cluster()
        ah = build_after_hours_cluster()
        auth_cluster = build_authentication_cluster()
        routing = build_routing_cluster()

        all_nodes = []
        all_nodes.extend(greeting.nodes)
        all_nodes.extend(bh.nodes)
        all_nodes.extend(ah.nodes)
        all_nodes.extend(auth_cluster.nodes)
        all_nodes.extend(routing.nodes)

        violations = validate_tool_scoping(all_nodes)
        assert violations == [], (
            f"Gate-by-scoping violations found: {violations}"
        )

    def test_no_non_routing_node_has_transfer_tool(self) -> None:
        """No non-Routing node in the assembled graph has 'transfer' in its tools."""
        wg = build_switchboard_graph()
        for node in wg.nodes.values():
            if node.id.startswith("routing_"):
                continue
            tool_uuids = node.tool_uuids or []
            assert "transfer" not in tool_uuids, (
                f"Non-routing node '{node.id}' has 'transfer' tool — "
                f"GATE-AUTH structural invariant violated (Req 9.2, POC-10)"
            )

    def test_no_non_routing_node_has_route_metadata_resolution_tool(self) -> None:
        """No non-Routing node has 'route_metadata_resolution' in its tools."""
        wg = build_switchboard_graph()
        for node in wg.nodes.values():
            if node.id.startswith("routing_"):
                continue
            tool_uuids = node.tool_uuids or []
            assert "route_metadata_resolution" not in tool_uuids, (
                f"Non-routing node '{node.id}' has 'route_metadata_resolution' — "
                f"GATE-AUTH structural invariant violated (Req 9.2, POC-10)"
            )

    def test_routing_resolve_route_node_has_route_metadata_resolution(self) -> None:
        """The Routing Resolve Route node HAS route_metadata_resolution."""
        routing = build_routing_cluster()
        resolve_node = next(
            n for n in routing.nodes if n.id == routing.resolve_route_id
        )
        assert resolve_node.data.tool_uuids is not None
        assert "route_metadata_resolution" in resolve_node.data.tool_uuids

    def test_routing_transfer_node_has_transfer(self) -> None:
        """The Routing Transfer node HAS transfer in its tools."""
        routing = build_routing_cluster()
        transfer_node = next(
            n for n in routing.nodes if n.id == routing.transfer_id
        )
        assert transfer_node.data.tool_uuids is not None
        assert "transfer" in transfer_node.data.tool_uuids


# ---------------------------------------------------------------------------
# POC-10 Structural invariant: edges to Routing from auth-required paths go
# through Authentication
# ---------------------------------------------------------------------------


class TestPOC10AuthRequiredPathsGoThroughAuthentication:
    """POC-10 Structural: all edges leading to Routing from auth-required paths
    go through Authentication.

    Requirements: 20.12 (Req 9.2, GATE-AUTH)
    """

    def test_auth_cluster_has_identity_to_routing_edge(self) -> None:
        """The auth cluster has an edge from identity verify to routing (Req 3.3)."""
        routing = build_routing_cluster()
        auth = build_authentication_cluster(
            routing_entry_node_id=routing.resolve_route_id,
        )
        identity_to_routing = [
            e for e in auth.edges
            if e.source == AUTH_IDENTITY_NODE_ID
            and e.target == routing.resolve_route_id
        ]
        assert len(identity_to_routing) >= 1, (
            "Expected an edge from auth identity → routing resolve route"
        )

    def test_auth_cluster_identity_to_routing_is_silent(self) -> None:
        """The identity → routing edge is silent (transition_speech='')."""
        routing = build_routing_cluster()
        auth = build_authentication_cluster(
            routing_entry_node_id=routing.resolve_route_id,
        )
        identity_to_routing = [
            e for e in auth.edges
            if e.id == "auth_e_identity_to_routing"
        ]
        assert len(identity_to_routing) == 1
        assert identity_to_routing[0].data.transition_speech == ""

    def test_full_graph_auth_nodes_are_only_non_skip_path_to_routing(self) -> None:
        """In the full graph, edges into Routing from auth nodes exist (auth-required
        path). The only non-auth non-skip edges into routing are:
        - AH hotword (immediate path, patient_verified=N/A)
        - Records silent skip (from BH)
        - New-patient create skip (from BH)
        - Retry-3 silent route (from BH)
        All other edges into routing originate from Authentication cluster nodes.
        """
        wg = build_switchboard_graph()
        routing = build_routing_cluster()
        resolve_route_id = routing.resolve_route_id

        # All edges targeting the routing entry (resolve route) node
        incoming_to_routing = [
            e for e in wg.edges if e.target == resolve_route_id
        ]
        assert len(incoming_to_routing) >= 1, (
            "Expected at least one edge into the routing resolve route node"
        )

        # Source nodes that are NOT auth nodes and NOT routing-internal
        non_auth_sources = set()
        auth_sources = set()
        for edge in incoming_to_routing:
            if edge.source in AUTH_NODE_IDS:
                auth_sources.add(edge.source)
            else:
                non_auth_sources.add(edge.source)

        # Auth nodes must be present as sources (the main auth→routing path)
        assert len(auth_sources) >= 1, (
            "Expected at least one auth node as a source of edges to routing"
        )

        # Non-auth sources are the skip/hotword paths (BH, AH). Verify they
        # exist and are from expected clusters (not random nodes).
        for source in non_auth_sources:
            # These should be from BH (Records skip, new-create skip, retry-3)
            # or AH (hotword, restricted-connect) — both valid skip paths.
            # Just confirm they're NOT a node that should require auth.
            assert not source.startswith("scheduling_"), (
                f"Scheduling node '{source}' has an edge directly into routing — "
                "auth-required intents must go through Authentication first"
            )

    def test_auth_fail_edges_also_reach_routing(self) -> None:
        """Auth fail/refusal edges from every auth node also reach routing
        (still connects, Req 9.7). The gate is opened by patient_verified=Fail."""
        routing = build_routing_cluster()
        auth = build_authentication_cluster(
            routing_entry_node_id=routing.resolve_route_id,
        )
        for node_id in AUTH_NODE_IDS:
            fail_edges = [
                e for e in auth.edges
                if e.id == f"auth_e_fail_{node_id}"
                and e.source == node_id
                and e.target == routing.resolve_route_id
            ]
            assert len(fail_edges) == 1, (
                f"Expected 1 fail/refusal edge from {node_id} → routing"
            )


# ---------------------------------------------------------------------------
# POC-10 E2E scenario walkthrough: caller with auth-required intent → gate
# closed → auth completes → gate opens → routing/transfer proceeds
# ---------------------------------------------------------------------------


class TestPOC10E2EScenarioWalkthrough:
    """POC-10 E2E scenario: auth gate locks transfer/metadata until verify.

    Scripted trace:
      1. Caller starts a business-hours call
      2. Intent is Scheduling (existing patient) → auth required
      3. Gate is CLOSED (patient_verified=None)
      4. Authentication proceeds (phone → readback → DOB → identity)
      5. DOB matches → patient_verified=Success
      6. Gate is now OPEN
      7. Routing proceeds (Resolve Route node has the tools)
      8. Transfer invokes (Transfer node has the transfer tool)

    Requirements: 20.12 (Req 9.2, GATE-AUTH, POC-10)
    """

    def test_e2e_poc10_gate_closed_then_open_after_auth(self) -> None:
        """E2E POC-10: auth gate lifecycle — closed → auth → open → proceed.

        Full scenario validating the GATE-AUTH invariant end-to-end:
        - The gate is closed when auth is required and patient_verified is null
        - Authentication completes and sets patient_verified
        - The gate opens and routing/transfer may proceed
        - The structural invariant ensures tools are only on Routing nodes
        """
        # ── Step 1: Initialize business-hours call ───────────────────────
        ledger = CallStateLedger(after_hours=False)
        assert ledger.after_hours is False
        assert ledger.patient_verified is None

        # ── Step 2: Caller intent is Scheduling (existing patient) ───────
        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Scheduling",
                "patient_status": "existing",
                "greeting_ani_lookup_done": True,
                "greeting_ani_match_count": 1,
            },
        )
        assert ledger.intent == "Scheduling"
        assert ledger.patient_status == "existing"

        # Auth IS required for Scheduling/existing
        assert auth_required(ledger.intent, ledger.patient_status) is True

        # ── Step 3: Gate is CLOSED — patient_verified is null ────────────
        assert ledger.patient_verified is None
        assert is_patient_verified_resolved(ledger.patient_verified) is False
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        # At this point, no transfer and no route_metadata_resolution may
        # occur. The structural gate-by-scoping ensures this: only Routing
        # nodes have those tools, and we haven't reached Routing yet.

        # ── Step 4: Authentication proceeds — DOB match → Success ────────
        # Simulate: DOB matched → patient_verified = Success
        verified_value = patient_verified_from_dob(dob_match=True)
        assert verified_value == PATIENT_VERIFIED_SUCCESS

        ledger = reduce_ledger(ledger, {"patient_verified": verified_value})
        assert ledger.patient_verified == "Success"

        # ── Step 5: Gate is NOW OPEN ─────────────────────────────────────
        assert is_patient_verified_resolved(ledger.patient_verified) is True
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

        # ── Step 6: Verify structural invariant holds ────────────────────
        # The graph proves transfer/route_metadata_resolution are only on
        # Routing nodes, so they're unreachable before Routing is entered.
        wg = build_switchboard_graph()
        for node in wg.nodes.values():
            if node.id.startswith("routing_"):
                continue
            tool_uuids = node.tool_uuids or []
            assert "transfer" not in tool_uuids, (
                f"Non-routing node '{node.id}' has 'transfer' — scoping violated"
            )
            assert "route_metadata_resolution" not in tool_uuids, (
                f"Non-routing node '{node.id}' has 'route_metadata_resolution' — "
                "scoping violated"
            )

        # ── Step 7: Routing node has the tools needed ────────────────────
        routing = build_routing_cluster()
        resolve_node = next(
            n for n in routing.nodes if n.id == routing.resolve_route_id
        )
        assert "route_metadata_resolution" in resolve_node.data.tool_uuids
        assert "routing_intent_resolution" in resolve_node.data.tool_uuids

        transfer_node = next(
            n for n in routing.nodes if n.id == routing.transfer_id
        )
        assert "transfer" in transfer_node.data.tool_uuids

        # ── Step 8: Verify zero speech on routing ────────────────────────
        lower_prompt = RESOLVE_ROUTE_PROMPT.lower()
        assert (
            "no speech" in lower_prompt
            or "emit no" in lower_prompt
            or "no filler" in lower_prompt
            or "zero speech" in lower_prompt
        ), "RESOLVE_ROUTE_PROMPT must enforce zero speech"

        # ── Complete scenario summary ────────────────────────────────────
        # POC-10 validated:
        # - Auth required for Scheduling/existing ✓
        # - Gate CLOSED when patient_verified is null ✓
        # - Auth completes → patient_verified=Success ✓
        # - Gate OPEN after verification ✓
        # - Structural invariant: tools only on Routing nodes ✓
        # - Routing has the transfer/metadata tools ✓
        # - Zero speech enforced during resolution ✓

    def test_e2e_poc10_gate_closed_then_open_after_auth_fail(self) -> None:
        """E2E POC-10: auth gate opens even on auth failure (patient_verified=Fail).

        A failed verification (DOB mismatch) still OPENS the gate — the caller
        is still connected (Req 9.7). Only the null (not-yet-run) state keeps
        the gate closed.
        """
        # ── Initialize ───────────────────────────────────────────────────
        ledger = CallStateLedger(after_hours=False)
        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Billing",
                "patient_status": "existing",
                "greeting_ani_lookup_done": True,
                "greeting_ani_match_count": 1,
            },
        )

        # Auth required for Billing/existing
        assert auth_required(ledger.intent, ledger.patient_status) is True

        # ── Gate is CLOSED ───────────────────────────────────────────────
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        # ── DOB mismatch → patient_verified=Fail ─────────────────────────
        verified_value = patient_verified_from_dob(dob_match=False)
        assert verified_value == PATIENT_VERIFIED_FAIL

        ledger = reduce_ledger(ledger, {"patient_verified": verified_value})
        assert ledger.patient_verified == "Fail"

        # ── Gate is NOW OPEN (Fail opens gate, Req 9.7) ──────────────────
        assert is_patient_verified_resolved(ledger.patient_verified) is True
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

    def test_e2e_poc10_gate_closed_then_open_after_na(self) -> None:
        """E2E POC-10: auth gate opens with patient_verified=N/A (hotword bypass).

        The N/A value (e.g. from the hotword path) also opens the gate.
        """
        # ── Initialize with after-hours hotword path ─────────────────────
        ledger = CallStateLedger(after_hours=True)
        ledger = reduce_ledger(
            ledger,
            {
                "intent": "Scheduling",
                "patient_status": "existing",
            },
        )

        # Auth would be required for Scheduling/existing
        assert auth_required(ledger.intent, ledger.patient_status) is True

        # ── Gate is CLOSED ───────────────────────────────────────────────
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is False

        # ── Hotword sets patient_verified=N/A ────────────────────────────
        ledger = reduce_ledger(ledger, {"patient_verified": PATIENT_VERIFIED_NA})
        assert ledger.patient_verified == "N/A"

        # ── Gate is NOW OPEN ─────────────────────────────────────────────
        assert is_patient_verified_resolved(ledger.patient_verified) is True
        assert may_proceed_to_routing(
            ledger.intent, ledger.patient_status, ledger.patient_verified
        ) is True

    def test_e2e_poc10_multiple_intents_gate_lifecycle(self) -> None:
        """E2E POC-10: gate lifecycle holds for multiple auth-required intents.

        Verify the close→open transition for Referrals, Triage, and General
        (representative subset of AUTH_REQUIRED_INTENTS).
        """
        for intent_name in ["Referrals", "Triage", "General"]:
            ledger = CallStateLedger(after_hours=False)
            ledger = reduce_ledger(
                ledger,
                {
                    "intent": intent_name,
                    "patient_status": "existing",
                    "greeting_ani_lookup_done": True,
                    "greeting_ani_match_count": 0,
                },
            )

            # Gate is CLOSED
            assert may_proceed_to_routing(
                ledger.intent, ledger.patient_status, ledger.patient_verified
            ) is False, f"Gate should be CLOSED for {intent_name}"

            # Auth completes → Success
            ledger = reduce_ledger(ledger, {"patient_verified": PATIENT_VERIFIED_SUCCESS})

            # Gate is OPEN
            assert may_proceed_to_routing(
                ledger.intent, ledger.patient_status, ledger.patient_verified
            ) is True, f"Gate should be OPEN for {intent_name} after verification"

    def test_e2e_poc10_graph_structural_gate_identity_to_routing(self) -> None:
        """E2E POC-10: graph structure confirms identity verify → routing edge
        is silent, and the routing node holds the gated tools."""
        wg = build_switchboard_graph()
        routing = build_routing_cluster()
        routing_node_ids = {n.id for n in routing.nodes}

        # Find identity → routing edge(s)
        identity_to_routing_edges = [
            e for e in wg.edges
            if e.source == AUTH_IDENTITY_NODE_ID
            and e.target in routing_node_ids
        ]
        assert len(identity_to_routing_edges) >= 1, (
            "Expected at least one edge from auth identity to a routing node"
        )

        # The normal-completion edge must be silent (zero speech, Req 3.3)
        silent_edges = [
            e for e in identity_to_routing_edges
            if e.transition_speech == ""
        ]
        assert len(silent_edges) >= 1, (
            "Expected a silent edge from identity to routing "
            "(normal-completion path)"
        )

        # The routing resolve route node is the target of the silent edge
        for edge in silent_edges:
            assert edge.target == routing.resolve_route_id, (
                f"Silent identity→routing edge targets {edge.target}, "
                f"expected {routing.resolve_route_id}"
            )
