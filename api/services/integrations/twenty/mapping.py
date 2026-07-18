"""Map a completed Samvaad call to Twenty REST field values.

The render context exposed to a Twenty completion node mirrors the webhook
render context (``initial_context``, ``gathered_context``, ``annotations``)
and adds a stable ``outcome`` namespace so field mappings stay readable:

    {"stage": "{{outcome.disposition}}", "amount": "{{gathered_context.quoted_amount}}"}
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.constants import BACKEND_API_ENDPOINT
from api.services.integrations.base import IntegrationCompletionContext
from api.utils.template_renderer import get_nested_value, render_template

# Matches a template that is exactly one plain placeholder, e.g. "{{outcome.x}}".
# Templates with fallbacks ("{{x | default}}") or surrounding text fall through
# to normal string rendering.
_SINGLE_PLACEHOLDER_RE = re.compile(r"^\s*\{\{\s*([\w.]+)\s*\}\}\s*$")

_TRUE_TOKENS = {"true", "1", "yes", "y", "on"}
_FALSE_TOKENS = {"false", "0", "no", "n", "off"}


def build_render_context(context: IntegrationCompletionContext) -> dict[str, Any]:
    """Assemble the template context for a Twenty completion node."""
    workflow_run = context.workflow_run
    gathered = workflow_run.gathered_context or {}
    usage = workflow_run.usage_info or {}

    recording_url, transcript_url = _build_download_urls(context)

    outcome = {
        "workflow_run_id": workflow_run.id,
        "campaign_id": workflow_run.campaign_id,
        "disposition": gathered.get("call_disposition"),
        "duration_seconds": usage.get("call_duration_seconds"),
        "recording_url": recording_url,
        "transcript_url": transcript_url,
        "call_time": (workflow_run.created_at or datetime.now(UTC)).isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
    }

    return {
        "initial_context": workflow_run.initial_context or {},
        "gathered_context": gathered,
        "annotations": workflow_run.annotations or {},
        "cost_info": usage,
        "outcome": outcome,
        "recording_url": recording_url,
        "transcript_url": transcript_url,
    }


def _build_download_urls(
    context: IntegrationCompletionContext,
) -> tuple[str | None, str | None]:
    workflow_run = context.workflow_run
    if context.public_token:
        base = (
            f"{BACKEND_API_ENDPOINT}/api/v1/public/download/workflow/"
            f"{context.public_token}"
        )
        recording = f"{base}/recording" if workflow_run.recording_url else None
        transcript = f"{base}/transcript" if workflow_run.transcript_url else None
        return recording, transcript
    return workflow_run.recording_url, workflow_run.transcript_url


def resolve_record_id(
    render_context: dict[str, Any],
    record_id_path: str,
) -> str | None:
    """Resolve the Twenty record id from the render context via a dotted path."""
    value = get_nested_value(render_context, record_id_path)
    if value in (None, ""):
        return None
    return str(value)


def resolve_object_name(
    render_context: dict[str, Any],
    explicit_object: str | None,
    object_path: str,
) -> str | None:
    """Resolve the Twenty object name (explicit config wins over context path)."""
    if explicit_object and explicit_object.strip():
        return explicit_object.strip().strip("/")
    value = get_nested_value(render_context, object_path)
    if value in (None, ""):
        return None
    return str(value).strip().strip("/")


def render_fields(
    field_mapping: dict[str, Any],
    render_context: dict[str, Any],
    field_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Render a field mapping into Twenty-ready values.

    Type handling:
    - A mapping whose value is a single plain placeholder (``"{{outcome.x}}"``)
      resolves to the underlying value with its native type preserved, so an
      integer in the call context stays an integer.
    - ``field_types`` may declare an explicit Twenty type per field
      (``string`` | ``number`` | ``integer`` | ``boolean`` | ``json``) which is
      coerced after rendering. Explicit hints win over native preservation.
    - Fields that resolve to ``None`` or an empty string are dropped so partial
      outcomes never overwrite existing Twenty data with blanks.
    """
    types = field_types or {}
    rendered: dict[str, Any] = {}

    for field_name, template in (field_mapping or {}).items():
        value = _render_value(template, render_context)
        if value is None or value == "":
            continue

        hint = types.get(field_name)
        if hint:
            value = _coerce(field_name, value, hint)
            if value is None or value == "":
                continue

        rendered[field_name] = value

    return rendered


def _render_value(template: Any, render_context: dict[str, Any]) -> Any:
    """Render a mapping value, preserving native types for single placeholders."""
    if isinstance(template, str):
        match = _SINGLE_PLACEHOLDER_RE.match(template)
        if match:
            return get_nested_value(render_context, match.group(1))
        return render_template(template, render_context)
    return render_template(template, render_context)


def _coerce(field_name: str, value: Any, hint: str) -> Any:
    """Coerce a rendered value to the declared Twenty field type.

    On failure the original value is returned unchanged and a warning is logged,
    so a misconfigured hint never silently drops real data.
    """
    target = (hint or "").strip().lower()
    try:
        if target == "string":
            return value if isinstance(value, str) else json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        if target == "integer":
            if isinstance(value, bool):
                return int(value)
            return int(float(str(value).strip()))
        if target == "number":
            if isinstance(value, bool):
                return float(value)
            return float(str(value).strip())
        if target == "boolean":
            if isinstance(value, bool):
                return value
            token = str(value).strip().lower()
            if token in _TRUE_TOKENS:
                return True
            if token in _FALSE_TOKENS:
                return False
            raise ValueError(f"cannot interpret {value!r} as boolean")
        if target == "json":
            if isinstance(value, (dict, list)):
                return value
            return json.loads(str(value))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning(
            "[twenty] field '{}' could not be coerced to {}: {}; sending raw value",
            field_name,
            target,
            exc,
        )
        return value

    logger.warning(
        "[twenty] field '{}' has unknown type hint '{}'; sending raw value",
        field_name,
        hint,
    )
    return value
