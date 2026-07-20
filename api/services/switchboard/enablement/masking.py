"""Connector-tool sensitive-field masking.

Masks every value stored under a declared ``sensitive_fields`` name (plus the
fixed set ``phone``, ``patient_id``, ``provided_dob``, ``dob_on_file``) and any
configured credential value before a connector-tool definition is surfaced in
an API response.

The masked fields never appear under a name in
``definition["switchboard"]["sensitive_fields"]``, the fixed set, or one of the
recognized credential-value key names — but the ``config.credential_uuid``
*identifier* (a reference, not a secret) is always left visible so operators
can still see which credential a tool is bound to (Req 6.2).

Requirements: 7.1, 7.2, 7.3, 7.4.
"""

from __future__ import annotations

import copy
from typing import Any

#: Sensitive fields every connector tool treats as sensitive regardless of its
#: own declared ``sensitive_fields`` (Req 7.4).
FIXED_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {"phone", "patient_id", "provided_dob", "dob_on_file"}
)

#: Key names that may hold a raw credential *value* (as opposed to
#: ``credential_uuid``, which is an identifier/reference and must stay
#: visible). No connector tool definition stores a raw secret today — this is
#: a defensive catch-all so a value that ever ended up in one of these keys
#: is never returned unmasked (Design "Connector-tool masking").
CREDENTIAL_VALUE_KEYS: frozenset[str] = frozenset(
    {
        "credential_value",
        "credential",
        "secret",
        "api_key",
        "apikey",
        "password",
        "token",
        "access_token",
        "client_secret",
        "authorization",
    }
)

#: The identifier key that must never be masked: it references a credential,
#: it does not carry a secret value (Req 6.2).
_CREDENTIAL_IDENTIFIER_KEY = "credential_uuid"

#: Structural identifier keys that must never be masked even when their
#: *value* happens to equal a sensitive field name (e.g. a ``config.parameters``
#: entry ``{"name": "phone", "value": ...}`` — the ``"name"`` key holds the
#: parameter's field identifier, not a sensitive value itself; only its
#: sibling ``value``-holding keys should be masked).
_STRUCTURAL_IDENTIFIER_KEYS: frozenset[str] = frozenset({"name", _CREDENTIAL_IDENTIFIER_KEY})

#: Keys within a ``{"name": ..., "value": ...}``-shaped parameter entry (see
#: ``config.parameters``/``config.preset_parameters``) that may carry the
#: actual value assigned to a sensitive-named parameter.
_PARAMETER_VALUE_KEYS: frozenset[str] = frozenset(
    {"value", "value_template", "default", "default_value"}
)

#: Placeholder substituted for every masked value. Never a raw secret value.
MASK_PLACEHOLDER = "***"


def _mask_walk(
    node: Any, sensitive_names: frozenset[str]
) -> Any:
    """Recursively mask sensitive values within a ``config``-shaped structure.

    Two shapes are recognized while walking dicts:

    * A direct key/value pair whose key name is in ``sensitive_names`` or in
      :data:`CREDENTIAL_VALUE_KEYS` — the value is masked in place.
    * A ``{"name": <field>, "value": ...}``-style parameter entry (the shape
      produced by ``ConnectorTool.to_tool_definition()``'s ``parameters`` list
      and by ``preset_parameters``) whose ``"name"`` matches a sensitive field
      — any of :data:`_PARAMETER_VALUE_KEYS` present on that same entry is
      masked.

    ``credential_uuid`` is never masked: it is an identifier/reference, not a
    secret value (Req 6.2).
    """
    if isinstance(node, dict):
        name_value = node.get("name")
        is_named_sensitive_entry = (
            isinstance(name_value, str) and name_value in sensitive_names
        )
        masked: dict[str, Any] = {}
        for key, value in node.items():
            if key in _STRUCTURAL_IDENTIFIER_KEYS:
                # "name" identifies *which* field a parameter entry describes
                # (e.g. {"name": "phone", "value": ...}) rather than holding a
                # value itself; "credential_uuid" is a reference, not a
                # secret. Neither is ever masked, even if its own string
                # value happens to match a sensitive field name.
                masked[key] = value
                continue
            if key in sensitive_names or key in CREDENTIAL_VALUE_KEYS:
                masked[key] = MASK_PLACEHOLDER
                continue
            if is_named_sensitive_entry and key in _PARAMETER_VALUE_KEYS:
                masked[key] = MASK_PLACEHOLDER
                continue
            masked[key] = _mask_walk(value, sensitive_names)
        return masked
    if isinstance(node, list):
        return [_mask_walk(item, sensitive_names) for item in node]
    return node


def mask_connector_tool_definition(definition: dict) -> dict:
    """Return a copy of ``definition`` with every sensitive value masked.

    Deep-copies ``definition`` and masks, within its ``config`` (including
    nested structures such as ``config.parameters``), every value stored
    under a name in ``definition["switchboard"]["sensitive_fields"]`` unioned
    with :data:`FIXED_SENSITIVE_FIELDS`, plus any value stored under a
    recognized credential-value key name (:data:`CREDENTIAL_VALUE_KEYS`).
    ``config.credential_uuid`` — the credential *identifier*, not a secret —
    is always left visible.

    This is a pure function: no I/O, no logging, and the input ``definition``
    is never mutated. It never returns a raw secret value.

    Args:
        definition: A connector-tool (or generic tool) ``definition`` payload,
            e.g. the dict produced by ``ConnectorTool.to_tool_definition()`` or
            stored on ``ToolModel.definition``.

    Returns:
        A deep copy of ``definition`` with sensitive values replaced by
        :data:`MASK_PLACEHOLDER`.
    """
    masked_definition = copy.deepcopy(definition)

    switchboard = masked_definition.get("switchboard")
    declared_sensitive_fields = (
        switchboard.get("sensitive_fields", []) if isinstance(switchboard, dict) else []
    )
    sensitive_names = frozenset(declared_sensitive_fields) | FIXED_SENSITIVE_FIELDS

    config = masked_definition.get("config")
    if isinstance(config, dict):
        masked_definition["config"] = _mask_walk(config, sensitive_names)

    return masked_definition


__all__ = [
    "FIXED_SENSITIVE_FIELDS",
    "CREDENTIAL_VALUE_KEYS",
    "MASK_PLACEHOLDER",
    "mask_connector_tool_definition",
]
