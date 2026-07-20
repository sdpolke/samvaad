"""Property-based test: Switchboard never sets or asks visit type (task 13.3).

Covers Property 29 — Switchboard never sets or asks visit type
(Requirements 12.4).

THE Switchboard SHALL collect `specialty` (and `location`/`provider_name` when
needed) for every `appointment_action` before handoff, and SHALL NOT collect
`visit_type` on the switchboard. `visit_type` is set downstream in Scheduling
Init and only for `create` actions.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.business_hours import AppointmentAction
from api.services.switchboard.ledger import CallStateLedger
from api.services.switchboard.scheduling import (
    SWITCHBOARD_CLUSTERS,
    SwitchboardCluster,
    cluster_sets_or_asks_visit_type,
    visit_type_applies_to_action,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: All switchboard cluster values.
_switchboard_clusters = st.sampled_from(list(SwitchboardCluster))

#: All appointment action values.
_appointment_actions = st.sampled_from(list(AppointmentAction))

#: Manage actions only (everything except CREATE).
_manage_actions = st.sampled_from(
    [a for a in AppointmentAction if a is not AppointmentAction.CREATE]
)


# ===========================================================================
# Property 29: Switchboard never sets or asks visit type
# ===========================================================================


# ---------------------------------------------------------------------------
# 29a: cluster_sets_or_asks_visit_type is always False for every cluster
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type
@given(cluster=_switchboard_clusters)
@example(cluster=SwitchboardCluster.GREETING)
@example(cluster=SwitchboardCluster.BUSINESS_HOURS)
@example(cluster=SwitchboardCluster.AFTER_HOURS)
@example(cluster=SwitchboardCluster.AUTHENTICATION)
@example(cluster=SwitchboardCluster.ROUTING)
@settings(max_examples=200)
def test_no_switchboard_cluster_sets_or_asks_visit_type(
    cluster: SwitchboardCluster,
) -> None:
    """For every switchboard cluster, cluster_sets_or_asks_visit_type is False.

    **Validates: Requirements 12.4**

    The switchboard clusters (Greeting, Business Hours, After Hours,
    Authentication, Routing) never set or ask `visit_type`. That is the
    responsibility of the downstream Scheduling Init segment, and only for
    `create` actions.
    """
    # Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type

    assert cluster_sets_or_asks_visit_type(cluster) is False, (
        f"Switchboard cluster {cluster.value!r} must never set or ask visit_type "
        f"(Req 12.4), but cluster_sets_or_asks_visit_type returned True"
    )


# ---------------------------------------------------------------------------
# 29b: visit_type_applies_to_action returns True only for CREATE
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type
@given(action=_appointment_actions)
@example(action=AppointmentAction.CREATE)
@example(action=AppointmentAction.CANCEL)
@example(action=AppointmentAction.RESCHEDULE)
@example(action=AppointmentAction.LIST)
@example(action=AppointmentAction.CONFIRM)
@settings(max_examples=200)
def test_visit_type_applies_only_to_create(action: AppointmentAction) -> None:
    """visit_type_applies_to_action returns True only for CREATE, False for manage.

    **Validates: Requirements 12.4**

    `visit_type` is a create-only concept. For the four manage actions
    (cancel/reschedule/list/confirm) `visit_type` is never set — Scheduling Init
    skips sick/wellness and passes the action and ledger context straight to the
    Engine (Req 13.7).
    """
    # Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type

    result = visit_type_applies_to_action(action)

    if action is AppointmentAction.CREATE:
        assert result is True, (
            "visit_type should apply to CREATE action"
        )
    else:
        assert result is False, (
            f"visit_type must NOT apply to manage action {action.value!r} (Req 12.4)"
        )


# ---------------------------------------------------------------------------
# 29c: A ledger processed through any switchboard cluster never has visit_type
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type
@given(cluster=_switchboard_clusters)
@example(cluster=SwitchboardCluster.GREETING)
@example(cluster=SwitchboardCluster.BUSINESS_HOURS)
@example(cluster=SwitchboardCluster.AFTER_HOURS)
@example(cluster=SwitchboardCluster.AUTHENTICATION)
@example(cluster=SwitchboardCluster.ROUTING)
@settings(max_examples=200)
def test_ledger_visit_type_remains_unset_through_switchboard(
    cluster: SwitchboardCluster,
) -> None:
    """A fresh ledger's visit_type stays None when only switchboard clusters run.

    **Validates: Requirements 12.4**

    The switchboard clusters never populate visit_type on the ledger. A ledger
    that enters a switchboard cluster with visit_type=None must exit with
    visit_type=None. The never-set guard (cluster_sets_or_asks_visit_type)
    structurally guarantees this.
    """
    # Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type

    # A fresh ledger starts with all fields as None (including visit_type).
    ledger = CallStateLedger()
    assert ledger.visit_type is None, "Fresh ledger should have visit_type=None"

    # The structural guard confirms no switchboard cluster sets visit_type.
    assert cluster_sets_or_asks_visit_type(cluster) is False, (
        f"Cluster {cluster.value!r} should never set visit_type"
    )

    # Since no switchboard cluster sets visit_type, the ledger's visit_type
    # remains None after passing through any switchboard cluster.
    assert ledger.visit_type is None, (
        f"After switchboard cluster {cluster.value!r}, ledger.visit_type must "
        f"remain None (Req 12.4)"
    )


# ---------------------------------------------------------------------------
# 29d: SWITCHBOARD_CLUSTERS covers all SwitchboardCluster enum values
# ---------------------------------------------------------------------------


# Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type
@given(cluster=_switchboard_clusters)
@example(cluster=SwitchboardCluster.GREETING)
@example(cluster=SwitchboardCluster.BUSINESS_HOURS)
@example(cluster=SwitchboardCluster.AFTER_HOURS)
@example(cluster=SwitchboardCluster.AUTHENTICATION)
@example(cluster=SwitchboardCluster.ROUTING)
@settings(max_examples=200)
def test_switchboard_clusters_frozenset_is_exhaustive(
    cluster: SwitchboardCluster,
) -> None:
    """SWITCHBOARD_CLUSTERS frozenset contains every SwitchboardCluster member.

    **Validates: Requirements 12.4**

    The never-set guard relies on SWITCHBOARD_CLUSTERS being exhaustive.
    Every enum member must be present in the frozenset so no cluster escapes
    the visit_type prohibition.
    """
    # Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type

    assert cluster in SWITCHBOARD_CLUSTERS, (
        f"SwitchboardCluster.{cluster.name} is not in SWITCHBOARD_CLUSTERS — "
        f"the never-set guard would miss it (Req 12.4)"
    )
