"""Property test for connector-tool sensitive-field masking.

Generates synthetic connector-tool definitions with random sensitive-field
values (a mix of the fixed sensitive fields and arbitrary custom fields
declared by the connector), random non-sensitive field values, a
``config.credential_uuid`` identifier, and occasional stray
credential-value-shaped keys (e.g. ``config.api_key`` or an extra
credential-shaped key on a ``config.parameters`` entry). Asserts that
``mask_connector_tool_definition`` masks every declared-sensitive value and
every configured credential value, always leaves ``credential_uuid`` visible
(it is an identifier/reference, never a secret), never leaks a raw
secret/sensitive value anywhere in the masked output, and leaves non-sensitive
parameter values unchanged.

Design references:
- ``design.md`` -> "Connector-tool masking", "Property 11: Sensitive-field
  masking"
- ``requirements.md`` -> Requirements 6.2, 7.1, 7.3, 7.4

Task: 6.2.
"""

from __future__ import annotations

import string
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from api.services.switchboard.enablement.masking import (
    CREDENTIAL_VALUE_KEYS,
    FIXED_SENSITIVE_FIELDS,
    MASK_PLACEHOLDER,
    mask_connector_tool_definition,
)

_IDENTIFIER = st.text(alphabet=string.ascii_lowercase, min_size=3, max_size=10)
_UUID_STR = st.uuids().map(str)


def _collect_leaf_strings(node: Any) -> list[str]:
    """Recursively collect every string leaf value in a nested structure."""
    if isinstance(node, dict):
        leaves: list[str] = []
        for value in node.values():
            leaves.extend(_collect_leaf_strings(value))
        return leaves
    if isinstance(node, list):
        leaves = []
        for item in node:
            leaves.extend(_collect_leaf_strings(item))
        return leaves
    if isinstance(node, str):
        return [node]
    return []


@st.composite
def _connector_definitions(draw: st.DrawFn) -> dict[str, Any]:
    """Build a synthetic connector-tool definition plus the bookkeeping
    needed to assert masking behavior against it."""
    custom_sensitive_names = draw(st.sets(_IDENTIFIER, max_size=4))
    fixed_subset = draw(
        st.sets(st.sampled_from(sorted(FIXED_SENSITIVE_FIELDS)), max_size=4)
    )
    declared_sensitive_fields = sorted(custom_sensitive_names | fixed_subset)

    # This mirrors what mask_connector_tool_definition computes internally:
    # declared sensitive_fields unioned with the fixed set (Req 7.4).
    sensitive_names_expected = frozenset(declared_sensitive_fields) | FIXED_SENSITIVE_FIELDS

    non_sensitive_names = draw(
        st.sets(
            _IDENTIFIER.filter(lambda n: n not in sensitive_names_expected),
            min_size=1,
            max_size=4,
        )
    )

    parameters: list[dict[str, Any]] = []
    secret_values: set[str] = set()
    non_sensitive_value_map: dict[str, str] = {}

    for name in sorted(sensitive_names_expected):
        value = draw(_UUID_STR)
        parameters.append({"name": name, "value": value})
        secret_values.add(value)

    for name in sorted(non_sensitive_names):
        value = draw(_UUID_STR)
        parameters.append({"name": name, "value": value})
        non_sensitive_value_map[name] = value

    parameters = draw(st.permutations(parameters))
    parameters = [dict(p) for p in parameters]

    # Occasionally add a stray credential-value-shaped key onto one of the
    # parameter entries (e.g. an entry named "secret") — this key is a raw
    # credential VALUE key regardless of the entry's declared "name" field.
    param_stray_key: str | None = None
    param_stray_name: str | None = None
    if parameters and draw(st.booleans()):
        idx = draw(st.integers(min_value=0, max_value=len(parameters) - 1))
        param_stray_key = draw(st.sampled_from(sorted(CREDENTIAL_VALUE_KEYS)))
        param_stray_value = draw(_UUID_STR)
        parameters[idx][param_stray_key] = param_stray_value
        param_stray_name = parameters[idx]["name"]
        secret_values.add(param_stray_value)

    # Occasionally add a stray credential-value-shaped key directly under
    # config (e.g. config.api_key) with a raw secret value.
    config_stray_key: str | None = None
    config_stray: dict[str, str] = {}
    if draw(st.booleans()):
        config_stray_key = draw(st.sampled_from(sorted(CREDENTIAL_VALUE_KEYS)))
        config_stray_value = draw(_UUID_STR)
        config_stray[config_stray_key] = config_stray_value
        secret_values.add(config_stray_value)

    credential_uuid_value = draw(_UUID_STR)

    definition = {
        "schema_version": 1,
        "type": "http_api",
        "config": {
            "url": "",
            "credential_uuid": credential_uuid_value,
            "field_mapping": {},
            "parameters": parameters,
            "timeout_ms": 5000,
            **config_stray,
        },
        "switchboard": {
            "connector_name": "synthetic_connector",
            "clusters": ["greeting"],
            "sensitive_fields": declared_sensitive_fields,
        },
    }

    return {
        "definition": definition,
        "sensitive_names_expected": sensitive_names_expected,
        "secret_values": secret_values,
        "non_sensitive_value_map": non_sensitive_value_map,
        "credential_uuid_value": credential_uuid_value,
        "param_stray_key": param_stray_key,
        "param_stray_name": param_stray_name,
        "config_stray_key": config_stray_key,
    }


# Feature: switchboard-frontend-enablement, Property 11: Sensitive-field masking
# Validates: Requirements 6.2, 7.1, 7.3, 7.4
@given(case=_connector_definitions())
@settings(max_examples=100, deadline=None)
def test_sensitive_field_masking(case: dict[str, Any]) -> None:
    definition = case["definition"]
    sensitive_names_expected = case["sensitive_names_expected"]
    secret_values: set[str] = case["secret_values"]
    non_sensitive_value_map: dict[str, str] = case["non_sensitive_value_map"]
    credential_uuid_value: str = case["credential_uuid_value"]
    param_stray_key: str | None = case["param_stray_key"]
    param_stray_name: str | None = case["param_stray_name"]
    config_stray_key: str | None = case["config_stray_key"]

    masked = mask_connector_tool_definition(definition)
    masked_config = masked["config"]
    masked_params_by_name = {p["name"]: p for p in masked_config["parameters"]}

    # (a) Every parameter entry whose "name" is a declared-sensitive field
    # (custom sensitive_fields or the fixed set) has its value masked.
    for name in sensitive_names_expected:
        if name in masked_params_by_name:
            assert masked_params_by_name[name]["value"] == MASK_PLACEHOLDER

    # (e) Non-sensitive parameter values are left unchanged.
    for name, original_value in non_sensitive_value_map.items():
        assert masked_params_by_name[name]["value"] == original_value

    # (b) Every parameter/config entry whose key is a recognized
    # credential-value key is masked, regardless of the entry's own "name".
    if param_stray_key is not None and param_stray_name is not None:
        assert masked_params_by_name[param_stray_name][param_stray_key] == MASK_PLACEHOLDER
    if config_stray_key is not None:
        assert masked_config[config_stray_key] == MASK_PLACEHOLDER

    # (c) config.credential_uuid is never masked — it is an identifier
    # reference, not a secret, and must remain exactly as given.
    assert masked_config["credential_uuid"] == credential_uuid_value

    # (d) No raw secret/sensitive value from the input appears anywhere in
    # the masked output (deep scan).
    leaves = set(_collect_leaf_strings(masked))
    leaked = secret_values & leaves
    assert not leaked, f"raw secret value(s) leaked into masked output: {leaked}"
