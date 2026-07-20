"""Switchboard frontend enablement layer.

This package holds the orchestration glue that makes the already-built
SpinSci switchboard (``api/services/switchboard/``) creatable, tool-bindable,
and configurable through the product: template registration, org-scoped
instantiation, connector-tool provisioning, tool-reference reconciliation,
UUID-aware gate-by-scoping validation, sensitive-field masking, and org-scoped
configuration overrides.

It is kept separate from the switchboard's pure decision logic and graph
builders so that package continues to hold only the switchboard's shape and
behavior, not product-integration concerns.

See ``.kiro/specs/switchboard-frontend-enablement/`` for the requirements and
design.
"""
