"""Tests for the global node builder and add_global_prompt=False enforcement.

Verifies:
1. The global node is type "globalNode" with a non-empty prompt.
2. The prompt mentions the key rules (no system names, no medication names,
   no unconfirmed teams, short sentences, period-grouped digits).
3. Verbatim-line nodes in existing clusters have add_global_prompt=False.

Requirements: 4.1, 4.2, 4.3, 5.1, 5.2.
"""

from __future__ import annotations


from api.services.switchboard.clusters.global_node import (
    GLOBAL_NODE_ID,
    GLOBAL_PERSONA_PROMPT,
    build_global_node,
)
from api.services.switchboard.clusters.routing import build_routing_cluster
from api.services.switchboard.clusters.after_hours import (
    NODE_AH_BILLING_CLOSED,
    NODE_AH_MYCHART_CLOSED,
    build_after_hours_cluster,
)
from api.services.switchboard.clusters.business_hours import build_business_hours_cluster
from api.services.switchboard.clusters.authentication import (
    AUTH_PATIENT_LOOKUP_NODE_ID,
    AUTH_IDENTITY_NODE_ID,
    build_authentication_cluster,
)


class TestGlobalNodeBuilder:
    """Tests for `build_global_node()`."""

    def test_returns_global_node_type(self) -> None:
        """The global node must be type 'globalNode'."""
        node, node_id = build_global_node()
        assert node.type == "globalNode"

    def test_returns_correct_node_id(self) -> None:
        """The returned node ID matches the constant."""
        node, node_id = build_global_node()
        assert node_id == GLOBAL_NODE_ID
        assert node.id == GLOBAL_NODE_ID

    def test_prompt_is_non_empty(self) -> None:
        """The global node must have a non-empty prompt."""
        node, _ = build_global_node()
        assert node.data.prompt is not None
        assert len(node.data.prompt.strip()) > 0


class TestGlobalPromptRules:
    """Tests that the global prompt mentions all key persona/TTS rules."""

    def test_mentions_no_system_names(self) -> None:
        """Prompt must mention not speaking system names/JSON/UUIDs/field names."""
        prompt = GLOBAL_PERSONA_PROMPT.lower()
        assert "system names" in prompt or "system name" in prompt
        assert "json" in prompt
        assert "uuid" in prompt
        assert "field names" in prompt or "field name" in prompt

    def test_mentions_no_medication_names(self) -> None:
        """Prompt must mention not repeating medication names."""
        prompt = GLOBAL_PERSONA_PROMPT.lower()
        assert "medication" in prompt
        # Should reference the safe alternatives
        assert "your prescription" in prompt or "your medication" in prompt

    def test_mentions_no_unconfirmed_teams(self) -> None:
        """Prompt must mention not naming unconfirmed teams."""
        prompt = GLOBAL_PERSONA_PROMPT.lower()
        assert "team" in prompt or "department" in prompt
        assert "confirmed" in prompt

    def test_mentions_short_sentences(self) -> None:
        """Prompt must mention short/concise sentences for TTS clarity."""
        prompt = GLOBAL_PERSONA_PROMPT.lower()
        assert "short" in prompt
        assert "sentence" in prompt

    def test_mentions_period_grouped_digits(self) -> None:
        """Prompt must mention periods between digit groups."""
        prompt = GLOBAL_PERSONA_PROMPT.lower()
        assert "period" in prompt
        assert "digit" in prompt
        # Should include an example like 555.123.4567
        assert "555.123.4567" in GLOBAL_PERSONA_PROMPT


class TestVerbatimNodesHaveGlobalPromptFalse:
    """Verbatim-line nodes must have add_global_prompt=False."""

    def test_routing_transfer_node(self) -> None:
        """Routing cluster: Transfer node speaks verbatim Appendix E only."""
        result = build_routing_cluster()
        transfer_node = next(n for n in result.nodes if n.id == result.transfer_id)
        assert transfer_node.data.add_global_prompt is False

    def test_routing_goodbye_node(self) -> None:
        """Routing cluster: Goodbye node speaks verbatim Appendix E only."""
        result = build_routing_cluster()
        goodbye_node = next(n for n in result.nodes if n.id == result.goodbye_id)
        assert goodbye_node.data.add_global_prompt is False

    def test_routing_transfer_error_node(self) -> None:
        """Routing cluster: Transfer Error node speaks verbatim Appendix E only."""
        result = build_routing_cluster()
        error_node = next(n for n in result.nodes if n.id == result.transfer_error_id)
        assert error_node.data.add_global_prompt is False

    def test_after_hours_billing_closed_node(self) -> None:
        """After Hours cluster: Billing Closed speaks verbatim closed line."""
        result = build_after_hours_cluster()
        billing_node = next(
            n for n in result.nodes if n.id == NODE_AH_BILLING_CLOSED
        )
        assert billing_node.data.add_global_prompt is False

    def test_after_hours_mychart_closed_node(self) -> None:
        """After Hours cluster: MyChart Closed speaks verbatim closed line."""
        result = build_after_hours_cluster()
        mychart_node = next(
            n for n in result.nodes if n.id == NODE_AH_MYCHART_CLOSED
        )
        assert mychart_node.data.add_global_prompt is False

    def test_business_hours_search_trouble_node(self) -> None:
        """Business Hours cluster: Search Trouble node speaks verbatim line."""
        result = build_business_hours_cluster()
        search_trouble_node = next(
            n for n in result.nodes if n.id == result.search_trouble_id
        )
        assert search_trouble_node.data.add_global_prompt is False

    def test_authentication_patient_lookup_node(self) -> None:
        """Authentication cluster: Patient Lookup is a silent node."""
        result = build_authentication_cluster()
        patient_node = next(
            n for n in result.nodes if n.id == AUTH_PATIENT_LOOKUP_NODE_ID
        )
        assert patient_node.data.add_global_prompt is False

    def test_authentication_identity_verify_node(self) -> None:
        """Authentication cluster: Identity Verify is a silent node."""
        result = build_authentication_cluster()
        identity_node = next(
            n for n in result.nodes if n.id == AUTH_IDENTITY_NODE_ID
        )
        assert identity_node.data.add_global_prompt is False
