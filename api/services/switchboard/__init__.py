"""SpinSci AI Virtual Switchboard PoC service package.

This package holds the switchboard's pure decision logic (schedule evaluation,
the Call State Ledger and its reducers, script rendering, routing/auth gates),
the workflow graph builders, and the backend connector tools. It is a
customer-specific application built on the in-repo Samvaad/Dograh workflow
engine (``api/services/workflow/``) — it does not fork the engine.

See ``.kiro/specs/spinsci-switchboard-poc/`` for the requirements and design.
"""
